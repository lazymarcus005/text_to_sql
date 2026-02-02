# from __future__ import annotations
# from typing import Dict, Any
# import os, json

# from langchain_core.runnables import Runnable
# from langchain_core.prompts import ChatPromptTemplate

# from agentic_ai_system.orchestration.llm_models import get_llm
# from agentic_ai_system.agents.text_to_sql.prompt import SYSTEM_RULES
# from agentic_ai_system.validators.sql_hygiene import extract_json_like, normalize_sql, validate_sql
# from agentic_ai_system.utils.prompt_safety import escape_curly_braces, assert_prompt_vars
# # from agentic_ai_system.agents.text_to_sql.schema_retriever import PostgresSchemaRetriever
# from agentic_ai_system.agents.text_to_sql.schema_retriever import MariaDBSchemaRetriever

# class TextToSQLAgent(Runnable):
#     agent_name = "text_to_sql"
#     agent_version = "2.0.2"

#     def __init__(self):
#         self.llm = get_llm()

#         # ✅ เพิ่มบรรทัดนี้
#         # self.schema_retriever = PostgresSchemaRetriever()
#         self.schema_retriever = MariaDBSchemaRetriever()

#         # Escape braces in SYSTEM_RULES so JSON examples won't be treated as template vars
#         safe_system = escape_curly_braces(SYSTEM_RULES, allowed_vars=set())
#         self.prompt = ChatPromptTemplate.from_messages([
#             ("system", safe_system),
#             ("human", "{q}")
#         ])
#         assert_prompt_vars(set(self.prompt.input_variables), {"q"})

#     def _parse_and_validate(self, raw: str) -> Dict[str, Any]:
#         raw = (raw or "").strip()
#         jtxt = extract_json_like(raw) or raw
#         data = json.loads(jtxt)

#         if not isinstance(data, dict):
#             raise ValueError("JSON root must be an object")

#         sql = normalize_sql(data.get("sql", ""))
#         ok, reason = validate_sql(sql, dialect="mysql")
#         if not ok:
#             raise ValueError(reason)

#         data["sql"] = sql
#         data.setdefault("params", {})
#         data.setdefault("assumptions", [])
#         data.setdefault("expected_columns", [])
#         return data

#     def invoke(self, input: Dict[str, Any], config=None) -> Dict[str, Any]:
#         user_prompt = input.get("raw_user_prompt", "")
#         max_retries = int(os.getenv("TEXT2SQL_MAX_RETRIES", "3"))

#         repair_note = ""
#         last_err = None

#         for _ in range(max_retries):
#             chain = self.prompt | self.llm
#             base_prompt = self._build_prompt(user_prompt)
#             msg = base_prompt if not repair_note else (base_prompt + "\n\n" + repair_note)

#             resp = chain.invoke({"q": msg})
#             raw = getattr(resp, "content", "") or ""

#             try:
#                 data = self._parse_and_validate(raw)
#                 return {
#                     "agent_name": self.agent_name,
#                     "agent_version": self.agent_version,
#                     "status": "success",
#                     "result": {
#                         "command": {
#                             "type": "sql",
#                             "dialect": "mysql",
#                             "statement": data["sql"],
#                             "params": data.get("params", {}) or {}
#                         },
#                         "assumptions": data.get("assumptions", []),
#                         "expected_columns": data.get("expected_columns", [])
#                     }
#                 }
#             except Exception as e:
#                 last_err = str(e)
#                 repair_note = (
#                     "REPAIR INSTRUCTIONS:\n"
#                     "- Output ONLY valid JSON, nothing else.\n"
#                     "- JSON must have keys: sql, params, assumptions, expected_columns.\n"
#                     f"- Fix this error: {last_err}\n"
#                     "- SQL must be ONE SELECT statement, start with SELECT, end with ';'.\n"
#                 )

#         return {
#             "agent_name": self.agent_name,
#             "agent_version": self.agent_version,
#             "status": "fail",
#             "error": {"error_code": "TEXT2SQL_FAILED", "message": last_err or "Unknown", "retryable": False}
#         }

#     def _build_prompt(self, user_prompt: str) -> str:
#         retrieved = self.schema_retriever.retrieve_relevant(
#             user_prompt,
#             top_k_tables=6,
#             expand_fk_hops=1,
#         )
#         schema_ctx = self.schema_retriever.format_context(retrieved)

#         return (
#             user_prompt
#             + "\n\n"
#             + schema_ctx
#             + "\n\nRules:\n"
#             "- Use ONLY the schema provided above.\n"
#             "- Do NOT guess table or column names.\n"
#             "- If the question is ambiguous, state assumptions explicitly.\n"
#         )
