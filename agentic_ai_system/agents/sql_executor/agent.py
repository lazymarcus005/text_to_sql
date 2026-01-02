from __future__ import annotations
from typing import Dict, Any, List
import os, time
from decimal import Decimal

from langchain_core.runnables import Runnable
from sqlalchemy import create_engine, text


def _db_url() -> str:
    return (
        f"postgresql+psycopg2://{os.getenv('POSTGRES_USER','app')}:"
        f"{os.getenv('POSTGRES_PASSWORD','app_pw')}@"
        f"{os.getenv('POSTGRES_HOST','db')}:"
        f"{os.getenv('POSTGRES_PORT','5432')}/"
        f"{os.getenv('POSTGRES_DB','appdb')}"
    )


def _to_json_safe(x: Any) -> Any:
    """Convert values to JSON-serializable types (handles Decimal recursively)."""
    if isinstance(x, Decimal):
        # preserve integers as int, otherwise float
        return int(x) if x == x.to_integral_value() else float(x)
    if isinstance(x, dict):
        return {k: _to_json_safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_to_json_safe(v) for v in x]
    return x


class SQLExecAgent(Runnable):
    agent_name = "sql_executor"
    agent_version = "2.0.1"

    def __init__(self):
        self.engine = create_engine(_db_url(), pool_pre_ping=True)

    def invoke(self, input: Dict[str, Any], config=None) -> Dict[str, Any]:
        cmd = input.get("sql_command") or {}
        sql = cmd.get("statement")
        params = cmd.get("params") or {}

        if not sql:
            return {
                "agent_name": self.agent_name,
                "agent_version": self.agent_version,
                "status": "fail",
                "error": {"error_code": "NO_SQL", "message": "Missing sql_command.statement", "retryable": False},
            }

        max_rows = int(os.getenv("SQL_MAX_ROWS", "200"))
        timeout_ms = int(os.getenv("SQL_STATEMENT_TIMEOUT_MS", "5000"))

        t0 = time.time()
        with self.engine.connect() as conn:
            conn.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
            res = conn.execute(text(sql), params)
            rows = res.fetchmany(max_rows)
            cols = list(res.keys())

        dt_ms = int((time.time() - t0) * 1000)

        # ✅ convert Decimal (and nested) to JSON-safe
        rows_dicts: List[Dict[str, Any]] = []
        for r in rows:
            row_map = dict(r._mapping)
            rows_dicts.append(_to_json_safe(row_map))

        return {
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "status": "success",
            "result": {
                "columns": cols,
                "rows_sample": rows_dicts,
                "row_count": len(rows_dicts),
                "execution_time_ms": dt_ms,
            },
        }
