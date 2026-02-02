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
from typing import Optional

from agentic_ai_system.agents.text_to_sql.agent import TextToSQLAgent
from agentic_ai_system.agents.composer.agent import ComposerAgent
from agentic_ai_system.validators.sql_hygiene import validate_sql
from agentic_ai_system.validators.domain_guard import check_in_domain
from agentic_ai_system.memory.store import store

def _db_url() -> str:
    return (
        f"mysql+pymysql://{os.getenv('DB_USER','app')}:"
        f"{os.getenv('DB_PASSWORD','app_pw')}@"
        f"{os.getenv('DB_HOST','db')}:"
        f"{os.getenv('DB_PORT','3306')}/"
        f"{os.getenv('DB_NAME','nocobase')}?charset=utf8mb4"
    )


# def _sse(event: str, data: Any) -> bytes:
#     # Keep payload compact; UI can JSON.parse(data).
#     return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")
def _sse(event: str, data: Any) -> bytes:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False, default=_json_default)}\n\n"
    ).encode("utf-8")


def _safe_err(code: str, message: str, retryable: bool = False) -> Dict[str, Any]:
    return {"error_code": code, "message": message, "retryable": retryable}


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
                # SQLAlchemy Row -> dict
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
    history = store.get_history_dicts(conversation_id)

    # config knobs
    max_rows = int(os.getenv("SQL_MAX_ROWS", "200"))
    chunk_size = int(os.getenv("SQL_STREAM_CHUNK_SIZE", "50"))
    timeout_ms = int(os.getenv("SQL_STATEMENT_TIMEOUT_MS", "5000"))

    # 1) Domain guard
    # yield _sse("step", {"trace_id": trace_id, "stage": "domain_guard", "message": "Checking your question…"})
    # dg = check_in_domain(user_prompt)
    # if not dg.allowed:
    #     yield _sse("error", _safe_err("OUT_OF_DOMAIN", dg.message, retryable=False))
    #     yield _sse("done", {"trace_id": trace_id, "status": "fail"})
    #     return
    # yield _sse("step", {"trace_id": trace_id, "stage": "domain_guard", "message": "Looks good. Generating SQL…", "status": "ok"})

    # 2) Text-to-SQL (LLM)
    t2s = TextToSQLAgent()
    yield _sse("step", {"trace_id": trace_id, "stage": "text_to_sql", "message": "Drafting SQL…"})
    # sql_res = t2s.invoke({"raw_user_prompt": user_prompt})
    sql_res = t2s.invoke({"raw_user_prompt": user_prompt, "history": history})
    if sql_res.get("status") != "success":
        err = sql_res.get("error") or _safe_err("TEXT_TO_SQL_FAILED", "LLM failed to generate SQL", retryable=True)
        yield _sse("error", err)
        yield _sse("done", {"trace_id": trace_id, "status": "fail"})
        return

    cmd = (sql_res.get("result") or {}).get("command") or {}
    statement = (cmd.get("statement") or "").strip()
    params = cmd.get("params") or {}
    yield _sse("sql", {"trace_id": trace_id, "sql": statement, "params": params})

    # 3) Validate SQL
    yield _sse("step", {"trace_id": trace_id, "stage": "sql_validate", "message": "Validating SQL…"})
    ok, reason = validate_sql(statement, dialect="mysql")
    if not ok:
        yield _sse("error", _safe_err("SQL_VALIDATION_FAILED", reason, retryable=False))
        yield _sse("done", {"trace_id": trace_id, "status": "fail"})
        return
    yield _sse("step", {"trace_id": trace_id, "stage": "sql_validate", "message": "SQL looks safe. Running query…", "status": "ok"})

    # 4) Execute SQL (stream rows)
    yield _sse("step", {"trace_id": trace_id, "stage": "sql_execute", "message": "Query running…"})
    all_rows: List[Dict[str, Any]] = []
    cols: List[str] = []
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
            yield _sse("rows", {"trace_id": trace_id, **chunk})
        yield _sse("step", {"trace_id": trace_id, "stage": "sql_execute", "message": f"Got {len(all_rows)} rows (sample). Composing answer…", "status": "ok"})
    except Exception as e:
        yield _sse("error", _safe_err("SQL_EXECUTION_FAILED", str(e), retryable=False))
        yield _sse("done", {"trace_id": trace_id, "status": "fail"})
        return

    # 5) Composer (LLM -> markdown answer)
    composer = ComposerAgent()
    yield _sse("step", {"trace_id": trace_id, "stage": "compose", "message": "Writing the answer…"})

    try:
        rows_sample_safe = _to_jsonable(all_rows)
        params_safe = _to_jsonable(params)

        compose_res = composer.invoke(
            {
                "trace_id": trace_id,
                "user_prompt": user_prompt,
                "history": history,
                "sql": statement,
                "params": params_safe,
                "result": {
                    "columns": cols,
                    "rows_sample": rows_sample_safe,
                    "row_count": len(all_rows),
                },
            }
        )
    except Exception as e:
        # สำคัญ: กันไม่ให้ SSE หลุด แล้ว UI เห็น network error
        yield _sse("error", _safe_err("COMPOSER_FAILED", str(e), retryable=True))
        yield _sse("done", {"trace_id": trace_id, "status": "fail"})
        return

    if compose_res.get("status") == "success":
        markdown = ((compose_res.get("result") or {}).get("markdown")) or ""
    else:
        markdown = (
            "### คำตอบ\n"
            "- (composer ล้มเหลว) แสดงผลลัพธ์ตัวอย่างด้านบนแทน\n\n"
            f"**trace_id:** `{trace_id}`\n"
        )

    yield _sse("answer", {"trace_id": trace_id, "markdown": markdown})

    store.append(conversation_id, "user", user_prompt)
    store.append(conversation_id, "assistant", markdown)
    
    yield _sse("done", {"trace_id": trace_id, "status": "success"})

def _json_default(o: Any):
    if isinstance(o, Decimal):
        # แนะนำ str() เพื่อไม่เสีย precision
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
