from __future__ import annotations
from typing import Set

def escape_curly_braces(template: str, allowed_vars: Set[str]) -> str:
    """Escape all { } in template except placeholders like {q} that you intentionally use."""
    s = template or ""
    for v in allowed_vars:
        s = s.replace("{" + v + "}", f"@@VAR_{v}@@")
    s = s.replace("{", "{{").replace("}", "}}")
    for v in allowed_vars:
        s = s.replace(f"@@VAR_{v}@@", "{" + v + "}")
    return s

def assert_prompt_vars(input_variables: Set[str], expected: Set[str]) -> None:
    got = set(input_variables or set())
    missing = expected - got
    extra = got - expected
    if missing or extra:
        raise ValueError(
            f"Prompt vars mismatch. expected={sorted(expected)}, got={sorted(got)}, "
            f"missing={sorted(missing)}, extra={sorted(extra)}"
        )
