from __future__ import annotations
from typing import Dict, Any
import uuid

from agentic_ai_system.agents.text_to_sql.agent import TextToSQLAgent
from agentic_ai_system.agents.sql_executor.agent import SQLExecAgent
from agentic_ai_system.validators.sql_hygiene import validate_sql
from agentic_ai_system.agents.composer.agent import ComposerAgent
from agentic_ai_system.validators.domain_guard import check_in_domain

def run_pipeline(user_prompt: str) -> Dict[str, Any]:
    trace_id = str(uuid.uuid4())
    try:
        # ✅ Domain Guard: กันคำถามนอกเรื่องตั้งแต่หน้าประตู
        dg = check_in_domain(user_prompt)
        if not dg.allowed:
            return {
                "trace_id": trace_id,
                "status": "fail",
                "error": {
                    "error_code": "OUT_OF_DOMAIN",
                    "message": dg.message,
                    "retryable": False
                }
            }


        t2s = TextToSQLAgent()
        exec_agent = SQLExecAgent()
        composer = ComposerAgent()

        sql_res = t2s.invoke({"raw_user_prompt": user_prompt})
        if sql_res.get("status") != "success":
            return {"trace_id": trace_id, "status": "fail", "error": sql_res.get("error"), "stage": "text_to_sql"}

        cmd = sql_res["result"]["command"]
        ok, reason = validate_sql(cmd.get("statement",""), dialect="postgres")
        if not ok:
            return {"trace_id": trace_id, "status": "fail",
                    "error": {"error_code": "SQL_VALIDATION_FAILED", "message": reason, "retryable": False}}

        exec_res = exec_agent.invoke({"sql_command": cmd})
        if exec_res.get("status") != "success":
            return {"trace_id": trace_id, "status": "fail", "error": exec_res.get("error"), "stage": "sql_executor"}

        compose_res = composer.invoke({
            "trace_id": trace_id,
            "user_prompt": user_prompt,
            "sql": cmd.get("statement"),
            "result": exec_res.get("result", {})
        })

        markdown = None
        if compose_res.get("status") == "success":
            markdown = (compose_res.get("result") or {}).get("markdown") or ""
        else:
            # fallback ให้แชทมีคำตอบเสมอ
            markdown = (
                "### คำตอบ\n"
                "- (composer ล้มเหลว) แสดงหลักฐานด้านขวาจาก trace_id ได้เลย\n\n"
                "### หลักฐาน\n"
                f"**trace_id:** `{trace_id}`\n"
            )
            
        return {
            "trace_id": trace_id,
            "status": "success",
            "sql": cmd.get("statement"),
            "params": cmd.get("params", {}),
            "result": exec_res.get("result", {}),
            "answer_markdown": markdown
        }
    except Exception as e:
        return {
            "trace_id": trace_id,
            "status": "fail",
            "error": {"error_code": "INTERNAL_ERROR", "message": str(e), "retryable": False}
        }
