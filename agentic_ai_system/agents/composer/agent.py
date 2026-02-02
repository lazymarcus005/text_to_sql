from __future__ import annotations
from typing import Dict, Any, List, Optional
import json

from langchain_core.runnables import Runnable
from langchain_core.prompts import ChatPromptTemplate

from agentic_ai_system.orchestration.llm_models import get_llm
from agentic_ai_system.utils.prompt_safety import escape_curly_braces, assert_prompt_vars
from agentic_ai_system.agents.composer.prompt import SYSTEM_RULES


def _md_escape(s: Any) -> str:
    if s is None:
        return ""
    text = str(s)
    # basic pipe escape for markdown tables
    return text.replace("|", "\\|").replace("\n", " ")


def _rows_to_md_table(columns: List[str], rows: List[dict], max_rows: int = 10) -> str:
    cols = columns or (list(rows[0].keys()) if rows else [])
    cols = cols[:20]  # hard cap columns to keep UI readable
    use_rows = (rows or [])[:max_rows]

    header = "| " + " | ".join(_md_escape(c) for c in cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body_lines = []
    for r in use_rows:
        body_lines.append("| " + " | ".join(_md_escape(r.get(c)) for c in cols) + " |")

    if not cols:
        return "_(no columns)_"
    if not use_rows:
        return "_(no rows)_"

    return "\n".join([header, sep] + body_lines)


def _format_history_for_payload(history: Any, max_items: int = 10) -> List[dict]:
    """
    history expected as list[{"role": "...", "content": "...", ...}]
    Returns a compact list for payload to avoid prompt bloat.
    """
    if not history or not isinstance(history, list):
        return []

    items = history[-max_items:]
    out: List[dict] = []
    for m in items:
        if not isinstance(m, dict):
            continue
        role = (m.get("role") or "user").strip()
        content = (m.get("content") or "").strip()
        if not content:
            continue

        # trim each message to keep payload small
        if len(content) > 500:
            content = content[:500] + "…"

        if role not in ("user", "assistant", "system"):
            role = "user"

        out.append({"role": role, "content": content})
    return out


class ComposerAgent(Runnable):
    agent_name = "composer"
    agent_version = "1.0.1"  # bump version since behavior changed

    def __init__(self):
        self.llm = get_llm()

        safe_system = escape_curly_braces(SYSTEM_RULES, allowed_vars=set())
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", safe_system),
            ("human", "{payload_json}")
        ])
        assert_prompt_vars(set(self.prompt.input_variables), {"payload_json"})

    def invoke(self, input: Dict[str, Any], config=None) -> Dict[str, Any]:
        """
        input:
          {
            "user_prompt": str,
            "sql": str,
            "result": { "columns": [...], "rows_sample":[...], "row_count": int, ... },
            "history": list[{"role": "...", "content": "..."}]   # optional
          }
        """
        user_prompt = input.get("user_prompt", "")
        sql = input.get("sql", "")
        history = input.get("history")  # optional list of dicts

        result = input.get("result") or {}
        columns = result.get("columns") or []
        rows_sample = result.get("rows_sample") or []
        row_count = result.get("row_count")

        evidence_table = _rows_to_md_table(columns, rows_sample, max_rows=10)

        conversation_context = _format_history_for_payload(history, max_items=10)

        # ส่งให้ LLM “สรุป” + บริบทก่อนหน้า + หลักฐาน
        payload = {
            "conversation_context": conversation_context,  # <-- NEW
            "question": user_prompt,
            "sql": sql,
            "row_count": row_count,
            "columns": columns,
            "rows_sample": rows_sample[:10],
            "evidence_table_markdown": evidence_table,
        }

        chain = self.prompt | self.llm
        resp = chain.invoke({"payload_json": json.dumps(payload, ensure_ascii=False)})

        md = getattr(resp, "content", "") or ""
        if not md.strip():
            # fallback deterministic markdown (กัน LLM เงียบ)
            md = (
                f"### คำตอบ\n- _ไม่สามารถสรุปจาก LLM ได้_ \n\n"
                f"### หลักฐาน\n"
                f"**SQL**\n```sql\n{sql}\n```\n\n"
                f"**Result sample**\n{evidence_table}\n"
            )

        return {
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "status": "success",
            "result": {
                "markdown": md,
                "evidence_table": evidence_table
            }
        }
