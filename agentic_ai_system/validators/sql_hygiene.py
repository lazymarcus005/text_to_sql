import re
from typing import Tuple, Optional
import sqlglot

CODE_FENCE_RE = re.compile(r"```(?:sql|json)?\s*([\s\S]*?)```", re.IGNORECASE)
JSON_OBJ_RE = re.compile(r"\{[\s\S]*\}")

DANGEROUS = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE")
DANGEROUS_RE = re.compile(r"\b(" + "|".join(DANGEROUS) + r")\b", re.IGNORECASE)

def extract_json_like(text: str) -> Optional[str]:
    text = (text or "").strip()
    m = CODE_FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    m2 = JSON_OBJ_RE.search(text)
    return m2.group(0).strip() if m2 else None

def normalize_sql(sql: str) -> str:
    s = (sql or "").strip()
    m = CODE_FENCE_RE.search(s)
    if m:
        s = m.group(1).strip()

    up = s.upper()
    idx = up.find("SELECT")
    if idx != -1:
        s = s[idx:].strip()

    # keep only first statement
    if ";" in s:
        s = s.split(";", 1)[0].strip() + ";"
    else:
        s = s.rstrip() + ";"
    return s

def validate_sql(sql: str, dialect: str = "mysql"):
    if not sql or not sql.strip():
        return False, "SQL is empty"

    s = normalize_sql(sql)  # แนะนำให้ normalize ก่อน
    if not s.lstrip().upper().startswith("SELECT"):
        return False, "SQL must start with SELECT."

    if DANGEROUS_RE.search(s):
        return False, "Only SELECT is allowed (DDL/DML keyword detected)."

    try:
        parsed = sqlglot.parse_one(s, dialect=dialect)
        if parsed is None:
            return False, "SQL parse returned None."
    except Exception as e:
        return False, f"SQL parse error: {e}"

    return True, "ok"