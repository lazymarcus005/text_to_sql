# agentic_ai_system/agents/text_to_sql/agent.py
from __future__ import annotations
from pathlib import Path

from typing import Dict, Any, Optional, List
import os, json

from langchain_core.runnables import Runnable
from langchain_core.prompts import ChatPromptTemplate

from agentic_ai_system.orchestration.llm_models import get_llm
from agentic_ai_system.agents.text_to_sql.prompt import SYSTEM_RULES
from agentic_ai_system.validators.sql_hygiene import extract_json_like, normalize_sql, validate_sql
from agentic_ai_system.utils.prompt_safety import escape_curly_braces, assert_prompt_vars
# from agentic_ai_system.agents.text_to_sql.schema_retriever import PostgresSchemaRetriever
from agentic_ai_system.agents.text_to_sql.schema_retriever import MariaDBSchemaRetriever


class TextToSQLAgent(Runnable):
    agent_name = "text_to_sql"
    agent_version = "2.0.2"

    def __init__(self):
        self.llm = get_llm()

        # self.schema_retriever = PostgresSchemaRetriever()
        self.schema_retriever = MariaDBSchemaRetriever()

        # Escape braces in SYSTEM_RULES so JSON examples won't be treated as template vars
        safe_system = escape_curly_braces(SYSTEM_RULES, allowed_vars=set())
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", safe_system),
            ("human", "{q}")
        ])
        
        self.knowledge_dir = Path(__file__).resolve().parent / "knowlages"
        self.knowledge_text = self._load_knowledge_files([
            "vw_c12_summary_assis.md",
            "vw_c102_request_tambon.md",
            "vw_disaster_animal_count.md",
            "data_dictionary_th.md",
            "er_diagram.md",
        ])

        assert_prompt_vars(set(self.prompt.input_variables), {"q"})

    def _parse_and_validate(self, raw: str) -> Dict[str, Any]:
        raw = (raw or "").strip()
        jtxt = extract_json_like(raw) or raw
        data = json.loads(jtxt)

        if not isinstance(data, dict):
            raise ValueError("JSON root must be an object")

        sql = normalize_sql(data.get("sql", ""))
        ok, reason = validate_sql(sql, dialect="mysql")
        if not ok:
            raise ValueError(reason)

        data["sql"] = sql
        data.setdefault("params", {})
        data.setdefault("assumptions", [])
        data.setdefault("expected_columns", [])
        return data

    def _format_history(self, history: Any, max_items: int = 10) -> str:
        """
        history expected as: list[{"role": "...", "content": "..."}]
        Keep it short to avoid prompt bloat.
        """
        if not history:
            return ""

        if not isinstance(history, list):
            return ""

        # take last max_items
        items = history[-max_items:]
        lines: List[str] = []
        for m in items:
            if not isinstance(m, dict):
                continue
            role = (m.get("role") or "").strip()
            content = (m.get("content") or "").strip()
            if not content:
                continue

            # hard trim per line to reduce bloat
            if len(content) > 500:
                content = content[:500] + "…"

            if role not in ("user", "assistant", "system"):
                role = "user"

            label = "User" if role == "user" else ("Assistant" if role == "assistant" else "System")
            lines.append(f"- {label}: {content}")

        return "\n".join(lines).strip()

    def _load_knowledge_files(self, filenames: List[str], max_chars_each: int = 8000) -> str:
        blocks: List[str] = []
        for fn in filenames:
            p = self.knowledge_dir / fn
            if not p.exists():
                continue
            txt = p.read_text(encoding="utf-8", errors="ignore").strip()
            if not txt:
                continue

            # กัน prompt บวมเกินไป
            if len(txt) > max_chars_each:
                txt = txt[:max_chars_each] + "\n…(truncated)…"

            blocks.append(f"### {fn}\n{txt}")

        if not blocks:
            return ""

        return "Domain knowledge (read carefully; use as context, do not invent schema):\n" + "\n\n".join(blocks)

    def invoke(self, input: Dict[str, Any], config=None) -> Dict[str, Any]:
        user_prompt = input.get("raw_user_prompt", "")
        history = input.get("history", None)  # list of dicts from memory store
        max_retries = int(os.getenv("TEXT2SQL_MAX_RETRIES", "3"))

        # --- NEW: external repair inputs (from SQL execution failure) ---
        previous_sql = (input.get("previous_sql") or "").strip()
        execution_error = input.get("execution_error") or {}
        attempt_no = input.get("attempt", None)

        def _trim(s: str, n: int) -> str:
            s = (s or "").strip()
            return s if len(s) <= n else (s[:n] + "…")

        # Build repair_note BEFORE the loop if execution_error exists
        repair_note = ""
        if isinstance(execution_error, dict) and (execution_error.get("message") or execution_error.get("code")):
            err_code = str(execution_error.get("code") or "").strip()
            err_msg = str(execution_error.get("message") or "").strip()

            # Keep these small to avoid prompt bloat
            previous_sql_short = _trim(previous_sql, 2000)
            err_msg_short = _trim(err_msg, 600)

            # External execution feedback section (strong instruction: no schema guessing)
            repair_note = (
                "EXECUTION FEEDBACK (the previous SQL failed when executed):\n"
                f"- Attempt: {attempt_no}\n" if attempt_no is not None else
                "EXECUTION FEEDBACK (the previous SQL failed when executed):\n"
            )
            repair_note += (
                f"- Previous SQL: {previous_sql_short}\n"
                f"- DB Error: {err_code + ': ' if err_code else ''}{err_msg_short}\n\n"
                "Fix requirements:\n"
                "- Rewrite the SQL so it EXECUTES successfully and still answers the current question.\n"
                "- Use ONLY the schema provided above. DO NOT guess table/column names.\n"
                "- If an unknown column/table error happened, DO NOT invent names: instead re-check schema context.\n"
                "- Output ONLY valid JSON with keys: sql, params, assumptions, expected_columns.\n"
                "- SQL must be ONE SELECT statement, start with SELECT, end with ';'.\n"
            )

        last_err = None

        for _ in range(max_retries):
            chain = self.prompt | self.llm
            base_prompt = self._build_prompt(user_prompt, history=history)

            # Include repair_note (execution feedback or last validation repair) if present
            msg = base_prompt if not repair_note else (base_prompt + "\n\n" + repair_note)

            resp = chain.invoke({"q": msg})
            raw = getattr(resp, "content", "") or ""

            try:
                data = self._parse_and_validate(raw)
                return {
                    "agent_name": self.agent_name,
                    "agent_version": self.agent_version,
                    "status": "success",
                    "result": {
                        "command": {
                            "type": "sql",
                            "dialect": "mysql",
                            "statement": data["sql"],
                            "params": data.get("params", {}) or {},
                        },
                        "assumptions": data.get("assumptions", []),
                        "expected_columns": data.get("expected_columns", []),
                    },
                }
            except Exception as e:
                # Internal retry: JSON parse / SQL hygiene failed
                last_err = str(e)

                # If we already had EXECUTION FEEDBACK, keep it and append the formatting rules.
                # (Prevents the model from "fixing execution" but breaking JSON shape.)
                if "EXECUTION FEEDBACK" in (repair_note or ""):
                    repair_note = (
                        repair_note
                        + "\n"
                        + "ADDITIONAL FORMAT FIX (your last output failed validation):\n"
                        + "- Output ONLY valid JSON, nothing else.\n"
                        + "- JSON must have keys: sql, params, assumptions, expected_columns.\n"
                        + f"- Fix this error: {_trim(last_err, 400)}\n"
                    )
                else:
                    repair_note = (
                        "REPAIR INSTRUCTIONS:\n"
                        "- Output ONLY valid JSON, nothing else.\n"
                        "- JSON must have keys: sql, params, assumptions, expected_columns.\n"
                        f"- Fix this error: {_trim(last_err, 400)}\n"
                        "- SQL must be ONE SELECT statement, start with SELECT, end with ';'.\n"
                    )

        return {
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "status": "fail",
            "error": {"error_code": "TEXT2SQL_FAILED", "message": last_err or "Unknown", "retryable": False},
        }

    # def invoke(self, input: Dict[str, Any], config=None) -> Dict[str, Any]:
    #     user_prompt = input.get("raw_user_prompt", "")
    #     history = input.get("history", None)  # list of dicts from memory store
    #     max_retries = int(os.getenv("TEXT2SQL_MAX_RETRIES", "3"))

    #     repair_note = ""
    #     last_err = None

    #     for _ in range(max_retries):
    #         chain = self.prompt | self.llm
    #         base_prompt = self._build_prompt(user_prompt, history=history)
    #         msg = base_prompt if not repair_note else (base_prompt + "\n\n" + repair_note)

    #         resp = chain.invoke({"q": msg})
    #         raw = getattr(resp, "content", "") or ""

    #         try:
    #             data = self._parse_and_validate(raw)
    #             return {
    #                 "agent_name": self.agent_name,
    #                 "agent_version": self.agent_version,
    #                 "status": "success",
    #                 "result": {
    #                     "command": {
    #                         "type": "sql",
    #                         "dialect": "mysql",
    #                         "statement": data["sql"],
    #                         "params": data.get("params", {}) or {}
    #                     },
    #                     "assumptions": data.get("assumptions", []),
    #                     "expected_columns": data.get("expected_columns", [])
    #                 }
    #             }
    #         except Exception as e:
    #             last_err = str(e)
    #             repair_note = (
    #                 "REPAIR INSTRUCTIONS:\n"
    #                 "- Output ONLY valid JSON, nothing else.\n"
    #                 "- JSON must have keys: sql, params, assumptions, expected_columns.\n"
    #                 f"- Fix this error: {last_err}\n"
    #                 "- SQL must be ONE SELECT statement, start with SELECT, end with ';'.\n"
    #             )

    #     return {
    #         "agent_name": self.agent_name,
    #         "agent_version": self.agent_version,
    #         "status": "fail",
    #         "error": {"error_code": "TEXT2SQL_FAILED", "message": last_err or "Unknown", "retryable": False}
    #     }

    def _build_prompt(self, user_prompt: str, history: Optional[Any] = None) -> str:
        # IMPORTANT: schema retrieval uses ONLY current question to avoid drift
        retrieved = self.schema_retriever.retrieve_relevant(
            user_prompt,
            top_k_tables=6,
            expand_fk_hops=1,
        )
        schema_ctx = self.schema_retriever.format_context(retrieved)

        history_text = self._format_history(history, max_items=10)

        parts: List[str] = []

        if history_text:
            parts.append(
                "Conversation context (most recent last; use as background, do not invent schema):\n"
                + history_text
            )

        parts.append("Current question:\n" + (user_prompt or ""))

        parts.append(schema_ctx)

        if self.knowledge_text:
            parts.append(
                "Additional domain knowledge (about important views):\n"
                + self.knowledge_text
            )

        parts.append(
            "Rules:\n"
            "- Use ONLY the schema provided above.\n"
            "- Do NOT guess table or column names.\n"
            "- If the question is ambiguous, state assumptions explicitly.\n"
            "- If prior context implies filters/time range/entities, apply them and state assumptions.\n"
        )

        return "\n\n".join([p for p in parts if p and p.strip()])
