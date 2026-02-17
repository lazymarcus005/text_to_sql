from __future__ import annotations

"""
Streaming pipeline runner.

This module is designed to be used with FastAPI's StreamingResponse.

Typical usage (in main.py):

    from fastapi.responses import StreamingResponse
    from agentic_ai_system.orchestration.executor_stream import stream_sse_pipeline

    @app.post("/query/stream")
    def query_stream(q: Query):
        return StreamingResponse(
            stream_sse_pipeline(q.user_prompt),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                # If you sit behind nginx, you usually want:
                # "X-Accel-Buffering": "no",
            },
        )

Events emitted:
- step:    {"stage": "...", "message": "...", ...}
- sql:     {"sql": "...", "params": {...}}
- rows:    {"columns": [...], "rows": [...], "chunk_index": n, "row_count": k}
- answer:  {"markdown": "..."}
- error:   {"error_code": "...", "message": "...", "retryable": bool}
- done:    {"trace_id": "...", "status": "success"|"fail"}
"""

from typing import Dict, Any, Iterator, List, Optional
import os
import json
import time
import uuid

from decimal import Decimal
from datetime import date, datetime
from uuid import UUID
from sqlalchemy import create_engine, text as sql_text

from agentic_ai_system.agents.text_to_sql.agent import TextToSQLAgent
from agentic_ai_system.agents.composer.agent import ComposerAgent
from agentic_ai_system.validators.sql_hygiene import validate_sql
from agentic_ai_system.validators.domain_guard import check_in_domain
# from agentic_ai_system.validators.llm_domain_guard import check_in_domain
from agentic_ai_system.memory.store import store


def _db_url() -> str:
    return (
        f"mysql+pymysql://{os.getenv('DB_USER','app')}:"
        f"{os.getenv('DB_PASSWORD','app_pw')}@"
        f"{os.getenv('DB_HOST','db')}:"
        f"{os.getenv('DB_PORT','3306')}/"
        f"{os.getenv('DB_NAME','nocobase')}?charset=utf8mb4"
    )


def _sse(event: str, data: Any) -> bytes:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False, default=_json_default)}\n\n"
    ).encode("utf-8")


def _safe_err(code: str, message: str, retryable: bool = False) -> Dict[str, Any]:
    return {"error_code": code, "message": message, "retryable": retryable}


def _classify_sql_error(e: Exception) -> tuple[str, str, bool]:
    """
    Best-effort classification for retry logic.
    Retryable means: LLM can likely fix by rewriting SQL (unknown column/table, syntax, ambiguous, etc.)
    Non-retryable means: infra/auth/permissions/timeouts (usually).
    """
    msg = str(e) if e is not None else "Unknown SQL error"
    m = msg.lower()

    # Non-retryable: auth/permission/connectivity (usually not solvable by rewriting SQL)
    non_retryable_markers = [
        "access denied",
        "permission",
        "not authorized",
        "authentication",
        "auth failed",
        "can't connect",
        "cannot connect",
        "connection refused",
        "connection reset",
        "lost connection",
        "server has gone away",
        "too many connections",
        "ssl",
    ]
    for mk in non_retryable_markers:
        if mk in m:
            return ("SQL_EXECUTION_FAILED", msg, False)

    # Timeouts: you can choose to make this retryable with "reduce scope" logic,
    # but by default treat as non-retryable to avoid loops.
    timeout_markers = [
        "timeout",
        "timed out",
        "max_statement_time",
        "statement timeout",
        "lock wait timeout",
        "deadlock",
    ]
    for mk in timeout_markers:
        if mk in m:
            return ("SQL_TIMEOUT", msg, False)

    # Retryable: common SQL mistakes that a rewrite can fix
    retryable_markers = [
        "unknown column",
        "unknown table",
        "doesn't exist",
        "does not exist",
        "no such table",
        "ambiguous",
        "syntax",
        "you have an error in your sql syntax",
        "invalid",
        "cannot resolve",
        "column not found",
        "table not found",
        "bad field",
    ]
    for mk in retryable_markers:
        if mk in m:
            return ("SQL_EXECUTION_FAILED_RETRYABLE", msg, True)

    # Default: be conservative; if it's not obviously infra/auth, allow one repair attempt.
    return ("SQL_EXECUTION_FAILED", msg, True)


def _run_sql_stream(
    sql: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    chunk_size: int = 50,
    max_rows: int = 200,
    timeout_ms: int = 5000,
) -> Iterator[Dict[str, Any]]:
    """
    Stream rows in chunks using a single DB round-trip.
    This is sync (SQLAlchemy sync engine). Good enough for demo/proto.
    """
    params = params or {}
    engine = create_engine(_db_url())

    sent = 0
    chunk_index = 0
    t0 = time.time()

    with engine.connect() as conn:
        conn.execute(sql_text("SET SESSION max_statement_time = :t"), {"t": int(timeout_ms) / 1000})
        res = conn.execute(sql_text(sql), params)
        cols = list(res.keys())

        while sent < max_rows:
            remaining = max_rows - sent
            n = min(chunk_size, remaining)
            rows = res.fetchmany(n)
            if not rows:
                break

            out_rows: List[Dict[str, Any]] = []
            for r in rows:
                out_rows.append(dict(r._mapping))

            sent += len(out_rows)
            dt_ms = int((time.time() - t0) * 1000)

            yield {
                "columns": cols,
                "rows": out_rows,
                "chunk_index": chunk_index,
                "row_count": len(out_rows),
                "rows_sent_total": sent,
                "elapsed_ms": dt_ms,
            }
            chunk_index += 1


def stream_sse_pipeline(user_prompt: str, conversation_id: Optional[str] = None) -> Iterator[bytes]:
    """
    Streaming version of orchestration/executor.run_pipeline.
    It yields SSE bytes so the client can update UI in realtime.
    """
    trace_id = str(uuid.uuid4())

    # Ensure conversation_id always exists for memory store
    if not conversation_id:
        conversation_id = trace_id
    history = store.get_history_dicts(conversation_id)

    # config knobs
    max_rows = int(os.getenv("SQL_MAX_ROWS", "200"))
    chunk_size = int(os.getenv("SQL_STREAM_CHUNK_SIZE", "50"))
    timeout_ms = int(os.getenv("SQL_STATEMENT_TIMEOUT_MS", "5000"))
    max_exec_retries = int(os.getenv("SQL_EXEC_MAX_RETRIES", "2"))

    # 1) Domain guard (optional / currently disabled)
    yield _sse("step", {"trace_id": trace_id, "stage": "domain_guard", "message": "Checking your question…"})
    dg = check_in_domain(user_prompt)
    if not dg.allowed:
        # yield _sse("error", _safe_err("OUT_OF_DOMAIN", dg.message, retryable=False))
        # yield _sse("done", {"trace_id": trace_id, "status": "fail"})
        yield _sse("error", _safe_err("OUT_OF_DOMAIN", "Question is outside supported domain", retryable=False))
        yield _sse("answer", {"trace_id": trace_id, "markdown": dg.message})
        yield _sse("done", {"trace_id": trace_id, "status": "fail"})

        return
    yield _sse("step", {"trace_id": trace_id, "stage": "domain_guard", "message": "Looks good. Generating SQL…", "status": "ok"})

    # 2-4) Text-to-SQL + Validate + Execute (with retry loop)
    t2s = TextToSQLAgent()

    # 1) Domain guard (LLM)
     # 1) Domain guard (LLM)


    # yield _sse("step", {"trace_id": trace_id, "stage": "domain_guard", "message": "Checking your question…"})

    # dg = check_in_domain(
    #     user_prompt,
    #     llm=t2s.llm,  # <-- reuse langchain model
    #     model=os.getenv("DOMAIN_GUARD_MODEL", "gpt-4.1-mini"),
    #     confidence_ask_threshold=float(os.getenv("DOMAIN_GUARD_ASK_THRESHOLD", "0.60")),
    # )

    # if dg.decision == "DENY":
    #     yield _sse("error", _safe_err("OUT_OF_DOMAIN", "Question is outside supported domain", retryable=False))
    #     yield _sse("answer", {"trace_id": trace_id, "markdown": dg.message})
    #     yield _sse("done", {"trace_id": trace_id, "status": "fail"})
    #     return

    # if dg.decision == "ASK":
    #     qs = "\n".join([f"- {q}" for q in (dg.questions or [])])
    #     markdown = dg.message
    #     if qs:
    #         markdown = f"{markdown}\n\nขอถามเพิ่ม:\n{qs}"
    #     yield _sse("answer", {"trace_id": trace_id, "markdown": markdown})
    #     yield _sse("done", {"trace_id": trace_id, "status": "needs_input"})
    #     return

    # yield _sse("step", {"trace_id": trace_id, "stage": "domain_guard", "message": "Looks good. Generating SQL…", "status": "ok"})

    # continue pipeline as usual...
    attempt = 0
    attempt_traces: List[Dict[str, Any]] = []

    final_statement = ""
    final_params: Dict[str, Any] = {}
    all_rows: List[Dict[str, Any]] = []
    cols: List[str] = []

    while attempt <= max_exec_retries:
        # 2) Text-to-SQL (LLM)
        msg = "Drafting SQL…" if attempt == 0 else f"Revising SQL… (attempt {attempt+1}/{max_exec_retries+1})"
        yield _sse("step", {"trace_id": trace_id, "attempt": attempt, "stage": "text_to_sql", "message": msg})

        t2s_payload: Dict[str, Any] = {"raw_user_prompt": user_prompt, "history": history}
        if attempt > 0 and attempt_traces:
            prev = attempt_traces[-1]
            t2s_payload.update(
                {
                    "previous_sql": prev.get("sql", ""),
                    "previous_params": prev.get("params", {}),
                    "execution_error": prev.get("error", {}),
                    "attempt": attempt,
                }
            )

        sql_res = t2s.invoke(t2s_payload)
        if sql_res.get("status") != "success":
            err = sql_res.get("error") or _safe_err("TEXT_TO_SQL_FAILED", "LLM failed to generate SQL", retryable=True)
            err = {"trace_id": trace_id, "attempt": attempt, **err}
            yield _sse("error", err)
            
            # OPTIONAL: send a human-friendly markdown answer too
            fallback_md = (
                "### คำตอบ\n"
                "- ขออภัยค่ะ ไม่สามารถสร้างคำสั่ง SQL ได้ เนื่องจากคำถามอาจไม่ชัดเจนหรือคำถามอาจไม่อยู่ในขอบเขตที่ระบบรองรับ\n\n"
                "### ข้อเสนอแนะ\n"
                "- ลองระบุชื่อข้อมูล/ตารางที่ต้องการ (เช่น  `b21_feed_count`: ข้อมูลจำนวนอาหารสัตว์ที่แจกจ่าย, `b100_disaster_area`: ข้อมูลประกาศเขตการช่วยเหลือ)..\n"
                "- ระบุช่วงเวลา/เงื่อนไขให้ชัดขึ้น\n\n"
                f"**trace_id:** `{trace_id}`\n"
            )
            yield _sse("answer", {"trace_id": trace_id, "attempt": attempt, "markdown": fallback_md})
            return

        cmd = (sql_res.get("result") or {}).get("command") or {}
        statement = (cmd.get("statement") or "").strip()
        params = cmd.get("params") or {}

        yield _sse("sql", {"trace_id": trace_id, "attempt": attempt, "sql": statement, "params": params})

        # 3) Validate SQL
        yield _sse("step", {"trace_id": trace_id, "attempt": attempt, "stage": "sql_validate", "message": "Validating SQL…"})
        ok, reason = validate_sql(statement, dialect="mysql")
        if not ok:
            attempt_traces.append({
                "sql": statement,
                "params": params,
                "error": {"code": "SQL_VALIDATION_FAILED", "message": reason, "retryable": True},
            })
            yield _sse("error", {"trace_id": trace_id, "attempt": attempt, **_safe_err("SQL_VALIDATION_FAILED", reason, retryable=True)})

            if attempt < max_exec_retries:
                yield _sse("step", {"trace_id": trace_id, "attempt": attempt, "stage": "sql_validate",
                                    "message": f"SQL failed validation — revising… (next attempt {attempt+2}/{max_exec_retries+1})"})
                attempt += 1
                continue

            yield _sse("done", {"trace_id": trace_id, "attempt": attempt, "status": "fail"})
            return
        # if not ok:
        #     yield _sse(
        #         "error",
        #         {"trace_id": trace_id, "attempt": attempt, **_safe_err("SQL_VALIDATION_FAILED", reason, retryable=False)},
        #     )
        #     yield _sse("done", {"trace_id": trace_id, "attempt": attempt, "status": "fail"})
        #     return

        yield _sse(
            "step",
            {
                "trace_id": trace_id,
                "attempt": attempt,
                "stage": "sql_validate",
                "message": "SQL looks safe. Running query…",
                "status": "ok",
            },
        )

        # 4) Execute SQL (stream rows)
        yield _sse("step", {"trace_id": trace_id, "attempt": attempt, "stage": "sql_execute", "message": "Query running…"})

        # reset buffers per attempt (important: do not mix partial rows from failed attempts)
        all_rows = []
        cols = []

        try:
            for chunk in _run_sql_stream(
                statement,
                params,
                chunk_size=chunk_size,
                max_rows=max_rows,
                timeout_ms=timeout_ms,
            ):
                cols = chunk["columns"]
                all_rows.extend(chunk["rows"])
                yield _sse("rows", {"trace_id": trace_id, "attempt": attempt, **chunk})

            # success: capture final sql/params
            final_statement = statement
            final_params = params

            yield _sse(
                "step",
                {
                    "trace_id": trace_id,
                    "attempt": attempt,
                    "stage": "sql_execute",
                    "message": f"Got {len(all_rows)} rows (sample). Composing answer…",
                    "status": "ok",
                },
            )
            break

        except Exception as e:
            code, msg_err, retryable = _classify_sql_error(e)

            err_payload = _safe_err(code, msg_err, retryable=retryable)
            # keep trace for LLM repair
            attempt_traces.append(
                {
                    "sql": statement,
                    "params": params,
                    "error": {"code": code, "message": msg_err, "retryable": retryable},
                }
            )

            yield _sse("error", {"trace_id": trace_id, "attempt": attempt, **err_payload})

            if retryable and attempt < max_exec_retries:
                yield _sse(
                    "step",
                    {
                        "trace_id": trace_id,
                        "attempt": attempt,
                        "stage": "sql_execute",
                        "message": f"Query failed — revising SQL… (next attempt {attempt+2}/{max_exec_retries+1})",
                    },
                )
                attempt += 1
                continue

            
            fallback_md = (
                "### คำตอบ\n"
                "- ขออภัยค่ะ ไม่สามารถสร้างคำสั่ง SQL ได้ เนื่องจากคำถามอาจไม่ชัดเจนหรือคำถามอาจไม่อยู่ในขอบเขตที่ระบบรองรับ\n\n"
                "### ข้อเสนอแนะ\n"
                "- ลองระบุชื่อข้อมูล/ตารางที่ต้องการ (เช่น  `b21_feed_count`: ข้อมูลจำนวนอาหารสัตว์ที่แจกจ่าย, `b100_disaster_area`: ข้อมูลประกาศเขตการช่วยเหลือ)..\n"
                "- ระบุช่วงเวลา/เงื่อนไขให้ชัดขึ้น\n\n"
                f"**trace_id:** `{trace_id}`\n"
            )
            yield _sse("answer", {"trace_id": trace_id, "attempt": attempt, "markdown": fallback_md})
            # yield _sse("done", {"trace_id": trace_id, "attempt": attempt, "status": "fail"})
            return

    # Safety: if loop ended without break (shouldn't happen), fail fast
    if not final_statement:
        # OPTIONAL: send a human-friendly markdown answer too
        fallback_md = (
            "### คำตอบ\n"
            "- ขออภัยค่ะ ไม่สามารถสร้างคำสั่ง SQL ได้ เนื่องจากคำถามอาจไม่ชัดเจนหรือคำถามอาจไม่อยู่ในขอบเขตที่ระบบรองรับ\n\n"
            "### ข้อเสนอแนะ\n"
            "- ลองระบุชื่อข้อมูล/ตารางที่ต้องการ (เช่น  `b21_feed_count`: ข้อมูลจำนวนอาหารสัตว์ที่แจกจ่าย, `b100_disaster_area`: ข้อมูลประกาศเขตการช่วยเหลือ)..\n"
            "- ระบุช่วงเวลา/เงื่อนไขให้ชัดขึ้น\n\n"
            f"**trace_id:** `{trace_id}`\n"
        )
        yield _sse("answer", {"trace_id": trace_id, "attempt": attempt, "markdown": fallback_md})
        return

    # 5) Composer (LLM -> markdown answer)
    composer = ComposerAgent()
    yield _sse("step", {"trace_id": trace_id, "attempt": attempt, "stage": "compose", "message": "Writing the answer…"})

    try:
        rows_sample_safe = _to_jsonable(all_rows)
        params_safe = _to_jsonable(final_params)

        attempt_count = attempt + 1
        meta = {
            "attempt_count": attempt_count,
            "max_rows_limit": max_rows,
            "is_sampled": (len(all_rows) >= max_rows),
            "timeout_ms": timeout_ms,
        }

        compose_res = composer.invoke(
            {
                "trace_id": trace_id,
                "user_prompt": user_prompt,
                "history": history,
                "sql": final_statement,
                "params": params_safe,
                "result": {
                    "columns": cols,
                    "rows_sample": rows_sample_safe,
                    "row_count": len(all_rows),
                },
                "meta": meta,
            }
        )
    except Exception as e:
        yield _sse("error", {"trace_id": trace_id, "attempt": attempt, **_safe_err("COMPOSER_FAILED", str(e), retryable=True)})
        yield _sse("done", {"trace_id": trace_id, "attempt": attempt, "status": "fail"})
        return

    if compose_res.get("status") == "success":
        markdown = ((compose_res.get("result") or {}).get("markdown")) or ""
    else:
        markdown = (
            "### คำตอบ\n"
            "- (composer ล้มเหลว) แสดงผลลัพธ์ตัวอย่างด้านบนแทน\n\n"
            f"**trace_id:** `{trace_id}`\n"
        )

    yield _sse("answer", {"trace_id": trace_id, "attempt": attempt, "markdown": markdown})

    store.append(conversation_id, "user", user_prompt)
    store.append(conversation_id, "assistant", markdown)

    yield _sse("done", {"trace_id": trace_id, "attempt": attempt, "status": "success"})


def _json_default(o: Any):
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, UUID):
        return str(o)
    if isinstance(o, (bytes, bytearray)):
        return o.decode("utf-8", errors="replace")
    return str(o)


def _to_jsonable(obj: Any) -> Any:
    # แปลง nested dict/list ที่มี Decimal/datetime/UUID ให้กลายเป็นของที่ JSON ได้
    return json.loads(json.dumps(obj, ensure_ascii=False, default=_json_default))
