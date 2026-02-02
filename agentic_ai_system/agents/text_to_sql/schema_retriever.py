from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import os
import re

from sqlalchemy import create_engine, text as sql_text, bindparam


def _db_url() -> str:
    # Keep env interface เดิม (POSTGRES_*) แต่ชี้ไป MariaDB
    return (
        
        f"mysql+pymysql://{os.getenv('DB_USER','app')}:"
        f"{os.getenv('DB_PASSWORD','app_pw')}@"
        f"{os.getenv('DB_HOST','db')}:"
        f"{os.getenv('DB_PORT','3306')}/"
        f"{os.getenv('DB_NAME','nocobase')}?charset=utf8mb4"
    )

def _tokenize(s: str) -> List[str]:
    s = (s or "").lower()
    return re.findall(r"[a-z0-9_]+", s)


@dataclass
class TableInfo:
    schema: str  # MariaDB: schema == database name (table_schema)
    name: str
    columns: List[Dict[str, Any]]  # {name, data_type, nullable}


@dataclass
class ForeignKeyInfo:
    src_schema: str
    src_table: str
    src_col: str
    dst_schema: str
    dst_table: str
    dst_col: str


class MariaDBSchemaRetriever:
    """
    MariaDB schema retriever (MySQL-compatible)
    - tables/columns: information_schema
    - fk relations: information_schema.KEY_COLUMN_USAGE
    """

    def __init__(
        self,
        *,
        include_schemas: Optional[List[str]] = None,
        exclude_schemas: Optional[List[str]] = None,
        max_columns_per_table: int = 40,
    ) -> None:
        self.engine = create_engine(_db_url())
        # MariaDB “schema” ใน information_schema = ชื่อ database
        self.include_schemas = include_schemas or [os.getenv("DB_NAME", "nocobase")]
        self.exclude_schemas = set(
            exclude_schemas
            or ["information_schema", "mysql", "performance_schema", "sys"]
        )
        self.max_columns_per_table = max_columns_per_table

    def list_tables(self) -> List[Tuple[str, str]]:
        q = (
            sql_text(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema IN :schemas
                ORDER BY table_schema, table_name;
                """
            )
            .bindparams(bindparam("schemas", expanding=True))
        )

        with self.engine.connect() as conn:
            rows = conn.execute(q, {"schemas": self.include_schemas}).fetchall()

        out: List[Tuple[str, str]] = []
        for sch, name in rows:
            if sch in self.exclude_schemas:
                continue
            out.append((sch, name))
        return out

    def list_columns(self, schema: str, table: str) -> List[Dict[str, Any]]:
        q = sql_text(
            """
            SELECT column_name, column_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
            ORDER BY ordinal_position;
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(q, {"schema": schema, "table": table}).fetchall()

        cols: List[Dict[str, Any]] = []
        for col_name, col_type, is_nullable in rows[: self.max_columns_per_table]:
            cols.append(
                {
                    "name": col_name,
                    "data_type": col_type,          # MariaDB: column_type จะละเอียดกว่า data_type
                    "nullable": (is_nullable == "YES"),
                }
            )
        return cols

    def list_foreign_keys(self) -> List[ForeignKeyInfo]:
        q = (
            sql_text(
                """
                SELECT
                  kcu.table_schema AS src_schema,
                  kcu.table_name   AS src_table,
                  kcu.column_name  AS src_col,
                  kcu.referenced_table_schema AS dst_schema,
                  kcu.referenced_table_name   AS dst_table,
                  kcu.referenced_column_name  AS dst_col
                FROM information_schema.key_column_usage kcu
                WHERE kcu.referenced_table_name IS NOT NULL
                  AND kcu.table_schema IN :schemas
                  AND kcu.referenced_table_schema IN :schemas
                ORDER BY 1,2,3;
                """
            )
            .bindparams(bindparam("schemas", expanding=True))
        )

        with self.engine.connect() as conn:
            rows = conn.execute(q, {"schemas": self.include_schemas}).fetchall()

        fks: List[ForeignKeyInfo] = []
        for r in rows:
            fk = ForeignKeyInfo(
                src_schema=r[0],
                src_table=r[1],
                src_col=r[2],
                dst_schema=r[3],
                dst_table=r[4],
                dst_col=r[5],
            )
            if fk.src_schema in self.exclude_schemas or fk.dst_schema in self.exclude_schemas:
                continue
            fks.append(fk)
        return fks

    def snapshot(self) -> Dict[str, Any]:
        tables = self.list_tables()
        table_infos: List[TableInfo] = []
        for sch, t in tables:
            table_infos.append(TableInfo(schema=sch, name=t, columns=self.list_columns(sch, t)))

        fks = self.list_foreign_keys()
        return {"tables": table_infos, "foreign_keys": fks}

    def retrieve_relevant(
        self,
        question: str,
        *,
        top_k_tables: int = 6,
        expand_fk_hops: int = 1,
    ) -> Dict[str, Any]:
        snap = self.snapshot()
        tables: List[TableInfo] = snap["tables"]
        fks: List[ForeignKeyInfo] = snap["foreign_keys"]

        q_tokens = set(_tokenize(question)) if question else set()

        scored: List[Tuple[int, TableInfo]] = []
        for t in tables:
            score = 0
            name_tokens = set(_tokenize(t.name))
            score += 8 * len(q_tokens & name_tokens)
            for c in t.columns:
                col_tokens = set(_tokenize(c["name"]))
                score += 2 * len(q_tokens & col_tokens)
            scored.append((score, t))

        scored.sort(key=lambda x: x[0], reverse=True)
        picked = [t for s, t in scored if s > 0][:top_k_tables]

        if not picked:
            picked = [t for _, t in scored[: min(top_k_tables, len(scored))]]

        picked_set = {(t.schema, t.name) for t in picked}

        for _ in range(max(0, expand_fk_hops)):
            added = set()
            for fk in fks:
                a = (fk.src_schema, fk.src_table)
                b = (fk.dst_schema, fk.dst_table)
                if a in picked_set and b not in picked_set:
                    added.add(b)
                if b in picked_set and a not in picked_set:
                    added.add(a)
            if not added:
                break
            picked_set |= added

        picked_tables = [t for t in tables if (t.schema, t.name) in picked_set]
        picked_fk = [
            fk for fk in fks
            if (fk.src_schema, fk.src_table) in picked_set and (fk.dst_schema, fk.dst_table) in picked_set
        ]

        return {"tables": picked_tables, "foreign_keys": picked_fk}

    @staticmethod
    def format_context(retrieved: Dict[str, Any]) -> str:
        tables: List[TableInfo] = retrieved["tables"]
        fks: List[ForeignKeyInfo] = retrieved["foreign_keys"]

        lines: List[str] = []
        lines.append("DATABASE SCHEMA (use ONLY these tables/columns):")

        for t in tables:
            cols = ", ".join([f"{c['name']} ({c['data_type']})" for c in t.columns])
            lines.append(f"- {t.schema}.{t.name}: {cols}")

        if fks:
            lines.append("RELATIONSHIPS (FK):")
            for fk in fks:
                lines.append(
                    f"- {fk.src_schema}.{fk.src_table}.{fk.src_col} -> {fk.dst_schema}.{fk.dst_table}.{fk.dst_col}"
                )

        return "\n".join(lines)
