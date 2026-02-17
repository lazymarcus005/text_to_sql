# validators/llm_domain_guard.py
"""
LLM-based domain guard for Thai Text-to-SQL (disaster relief / reports / logs).

Drop-in-ish replacement for regex/lexical domain guard:
- returns DomainGuardResult with:
  - decision: "ALLOW" | "ASK" | "DENY"
  - allowed: bool (True only when decision == "ALLOW")
  - message: Thai message to show user (deny/ask reasons + questions)
  - questions: list[str] (only for ASK)
  - confidence: float 0..1

Integration tip:
dg = check_in_domain(user_prompt, llm=your_llm_callable)
if dg.decision == "DENY": ...
elif dg.decision == "ASK": ... (ask user for more info)
else: ... generate SQL

LLM callable contract (recommended):
async def llm(messages: list[dict], model: str) -> str
or sync def llm(...)->str
where messages = [{"role":"system","content":...},{"role":"user","content":...}]
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union
import inspect
from langchain_core.messages import SystemMessage, HumanMessage


Decision = str  # "ALLOW" | "ASK" | "DENY"


@dataclass
class DomainGuardResult:
    decision: Decision
    allowed: bool
    message: str
    questions: List[str] = field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""


# ---- Scope summary (keep short & stable; don't paste full schema every time) ----
SCOPE_SUMMARY_TH = """ระบบนี้ตอบคำถามโดยดึงข้อมูลจากฐานข้อมูลงาน "รายงาน/บันทึก/ช่วยเหลือภัยพิบัติด้านปศุสัตว์" เท่านั้น เช่น
- รายงาน/สรุป ศปส.1/2/3/4, รอบรายงาน, ตารางเวลารายงาน
- พื้นที่ภัยพิบัติ/เขตช่วยเหลือ, ประวัติการช่วยเหลือ, ความเสียหาย, คำขอรับการช่วยเหลือ (กษ.01/กษ.02)
- การแจกอาหารสัตว์, อพยพสัตว์, การรักษาสัตว์, โควต้า/อัตราช่วยเหลือ
- ข้อมูลสถานที่ (จังหวัด/อำเภอ/ตำบล/หมู่บ้าน), ประเภทสัตว์/อาหาร/การรักษา/ภัยพิบัติ
- ทรัพยากรเตรียมพร้อม (จุดอพยพ, ยานพาหนะ, คอกสัตว์, เสบียง, ถุงยังชีพ, หน่วยสัตวแพทย์, ตั้งศูนย์ฯ)
- เอกสาร/ไฟล์ในระบบ และข้อมูลผู้ใช้/หน่วยงาน/บันทึกการใช้งานที่เกี่ยวข้อง

นอกเหนือจากงานข้างต้น (คุยทั่วไป/ความรู้รอบตัว/เขียนโค้ด/การเมือง/แปลภาษา ฯลฯ) ถือว่านอกขอบเขต
"""


SYSTEM_PROMPT = f"""You are a strict domain guard for a Thai Text-to-SQL system.

SCOPE (Thai):
{SCOPE_SUMMARY_TH}

TASK:
Given the user question, output ONLY valid JSON with:
- decision: "ALLOW" | "ASK" | "DENY"
- confidence: number 0.0..1.0
- reason: short Thai sentence (why)
- questions: array of 0-2 Thai clarifying questions (ONLY if decision="ASK", else []).

RULES:
- ALLOW if the intent can reasonably be answered by querying the database within scope.
- ASK if in-scope but missing essential constraints (ช่วงเวลา/พื้นที่/ประเภทภัย/ประเภทสัตว์/รอบรายงาน ฯลฯ).
- DENY if outside scope or general chat unrelated to the database.
- Do NOT generate SQL.
- Do NOT mention table names.
- Be brief.
"""


USER_PROMPT_TEMPLATE = """User question (Thai or mixed):
{question}
"""


def _default_deny_message(reason: str) -> str:
    return (
        f"{reason}\n\n"
        "ขอบเขตที่รองรับคือคำถามเกี่ยวกับรายงาน/บันทึก/การช่วยเหลือภัยพิบัติด้านปศุสัตว์ "
        "(เช่น รายงาน ศปส., พื้นที่ภัยพิบัติ/เขตช่วยเหลือ, ยอดช่วยเหลือ/ความเสียหาย, คำขอช่วยเหลือ, "
        "ข้อมูลจังหวัด-อำเภอ-ตำบล, ประเภทสัตว์/ภัย/การรักษา, เอกสารในระบบ ฯลฯ)"
    )


def _extract_first_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Robust-ish JSON extractor:
    - finds the first {...} block
    - attempts json.loads
    """
    if not text:
        return None

    # If model returns markdown fenced json, strip fences
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # Try direct load first
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Find first JSON object block
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None

    blob = m.group(0)
    try:
        obj = json.loads(blob)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


def _normalize_decision(d: Any) -> Decision:
    if not isinstance(d, str):
        return "DENY"
    d2 = d.strip().upper()
    if d2 in ("ALLOW", "ASK", "DENY"):
        return d2
    return "DENY"


def _clamp01(x: Any) -> float:
    try:
        v = float(x)
    except Exception:
        return 0.0
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _safe_questions(q: Any) -> List[str]:
    if not isinstance(q, list):
        return []
    out: List[str] = []
    for item in q[:2]:
        if isinstance(item, str):
            s = item.strip()
            if s:
                out.append(s)
    return out


def _fallback_heuristic(question: str) -> DomainGuardResult:
    """
    If LLM is not available, do a minimal heuristic:
    - allow if contains obvious in-scope keywords
    - otherwise deny (or ask if looks like in-scope but vague)
    """
    q = (question or "").lower()

    in_scope_hits = [
        "ภัย", "อพยพ", "ช่วยเหลือ", "ศปส", "ความเสียหาย", "กษ.", "กษ", "โควต", "อัตรา",
        "จังหวัด", "อำเภอ", "ตำบล", "หมู่บ้าน", "สัตว์", "อาหารสัตว์", "รักษา", "สัตวแพทย์",
        "รายงาน", "สรุป", "ยอด", "เอกสาร", "ไฟล์", "ผู้ใช้", "หน่วยงาน", "บันทึกการใช้งาน",
    ]
    out_scope_hits = [
        "เขียนโค้ด", "python", "javascript", "node", "react", "การเมือง", "ข่าว", "หุ้น", "btc",
        "แปลภาษา", "แต่งกลอน", "แต่งนิยาย", "สูตรอาหาร", "ท่องเที่ยว",
    ]

    if any(k in q for k in out_scope_hits) and not any(k in q for k in in_scope_hits):
        reason = "คำถามนี้ดูไม่เกี่ยวกับรายงาน/บันทึก/การช่วยเหลือภัยพิบัติในระบบ"
        return DomainGuardResult(
            decision="DENY",
            allowed=False,
            message=_default_deny_message(reason),
            confidence=0.55,
            reason=reason,
        )

    if any(k in q for k in in_scope_hits):
        # If vague words without constraints, ask
        vague = any(v in q for v in ["ล่าสุด", "ช่วงนี้", "ทั้งหมด", "สรุปยอด", "รายงาน"])
        if vague and not any(t in q for t in ["วันนี้", "เมื่อวาน", "เดือน", "ปี", "ตั้งแต่", "ถึง", "ช่วง", "ระหว่าง"]):
            reason = "ยังอยู่ในขอบเขต แต่ต้องการรายละเอียดเพิ่มเพื่อดึงข้อมูลให้ตรง"
            qs = ["ต้องการช่วงเวลาไหน (เช่น วันนี้/สัปดาห์นี้/เดือนนี้/ระบุวันที่เริ่ม-สิ้นสุด)?", "ต้องการพื้นที่ไหน (จังหวัด/อำเภอ) หรือประเภทภัยพิบัติอะไร?"]
            return DomainGuardResult(
                decision="ASK",
                allowed=False,
                message=reason,
                questions=qs,
                confidence=0.55,
                reason=reason,
            )

        return DomainGuardResult(
            decision="ALLOW",
            allowed=True,
            message="",
            confidence=0.6,
            reason="ดูเป็นคำถามในขอบเขตงานของระบบ",
        )

    reason = "คำถามนี้อยู่นอกขอบเขตฐานข้อมูลที่ระบบรองรับ"
    return DomainGuardResult(
        decision="DENY",
        allowed=False,
        message=_default_deny_message(reason),
        confidence=0.55,
        reason=reason,
    )

async def _call_llm_async(llm, messages, model: str) -> str:
    """
    Supports:
    - LangChain chat model: .invoke(list[BaseMessage]) or .ainvoke(...)
    - async llm(messages=..., model=...) -> str
    - sync llm(messages=..., model=...) -> str
    - llm(messages, model) positional
    """

    # 1) LangChain chat model path
    if hasattr(llm, "invoke") or hasattr(llm, "ainvoke"):
        lc_msgs = []
        for m in messages:
            role = (m.get("role") or "").strip()
            content = m.get("content", "") or ""
            if role == "system":
                lc_msgs.append(SystemMessage(content=content))
            else:
                lc_msgs.append(HumanMessage(content=content))

        # prefer async if available
        if hasattr(llm, "ainvoke") and callable(getattr(llm, "ainvoke")):
            resp = await llm.ainvoke(lc_msgs)
        else:
            resp = llm.invoke(lc_msgs)

        return getattr(resp, "content", "") or str(resp)

    # 2) Generic callable client path (your original)
    try:
        sig = inspect.signature(llm)
        params = sig.parameters
        if "messages" in params and "model" in params:
            res = llm(messages=messages, model=model)
        else:
            res = llm(messages, model)
    except Exception:
        res = llm(messages, model)

    if inspect.isawaitable(res):
        res = await res

    if not isinstance(res, str):
        if isinstance(res, dict) and "content" in res and isinstance(res["content"], str):
            return res["content"]
        return str(res)
    return res

async def llm_domain_guard(
    user_question: str,
    *,
    llm: Optional[Callable[..., Any]] = None,
    model: str = "gpt-4.1-mini",
    confidence_ask_threshold: float = 0.60,
) -> DomainGuardResult:
    """
    Main LLM guard. Returns DomainGuardResult.

    - If llm is None -> fallback heuristic
    - If LLM returns bad JSON -> fallback heuristic
    - If confidence < threshold -> force ASK (to reduce false reject)
    """
    if not llm:
        return _fallback_heuristic(user_question)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(question=user_question)},
    ]

    raw = await _call_llm_async(llm, messages, model=model)
    obj = _extract_first_json(raw)
    if not obj:
        return _fallback_heuristic(user_question)

    decision = _normalize_decision(obj.get("decision"))
    confidence = _clamp01(obj.get("confidence"))
    reason = (obj.get("reason") or "").strip()
    questions = _safe_questions(obj.get("questions"))

    # Force ASK if low confidence and not clearly ALLOW
    if confidence < confidence_ask_threshold and decision in ("DENY", "ASK"):
        decision = "ASK"

    if decision == "ALLOW":
        return DomainGuardResult(
            decision="ALLOW",
            allowed=True,
            message="",
            questions=[],
            confidence=confidence,
            reason=reason or "อยู่ในขอบเขตงานของระบบ",
        )

    if decision == "ASK":
        if not questions:
            questions = [
                "ต้องการช่วงเวลาไหน (เช่น วันนี้/สัปดาห์นี้/เดือนนี้/ระบุวันที่เริ่ม-สิ้นสุด)?",
                "ต้องการพื้นที่ไหน (จังหวัด/อำเภอ) หรือประเภทภัยพิบัติ/ประเภทสัตว์อะไร?",
            ]
        msg = reason or "ยังอยู่ในขอบเขต แต่ต้องการรายละเอียดเพิ่มเพื่อดึงข้อมูลให้ตรง"
        return DomainGuardResult(
            decision="ASK",
            allowed=False,
            message=msg,
            questions=questions,
            confidence=confidence,
            reason=msg,
        )

    # DENY
    deny_reason = reason or "คำถามนี้อยู่นอกขอบเขตฐานข้อมูลที่ระบบรองรับ"
    return DomainGuardResult(
        decision="DENY",
        allowed=False,
        message=_default_deny_message(deny_reason),
        questions=[],
        confidence=confidence,
        reason=deny_reason,
    )


def check_in_domain(
    user_question: str,
    *,
    llm: Optional[Callable[..., Any]] = None,
    model: str = "gpt-4.1-mini",
    confidence_ask_threshold: float = 0.60,
) -> DomainGuardResult:
    """
    Sync wrapper (so you can keep your current code style).
    If you already run in async context, call `await llm_domain_guard(...)`.
    """
    if not llm:
        return _fallback_heuristic(user_question)

    # If llm is async, run it in a simple event loop
    if inspect.iscoroutinefunction(llm):
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # running loop: user should use async version
                # fallback to heuristic to avoid deadlock
                return _fallback_heuristic(user_question)
        except Exception:
            loop = None

        return asyncio.run(
            llm_domain_guard(
                user_question,
                llm=llm,
                model=model,
                confidence_ask_threshold=confidence_ask_threshold,
            )
        )

    # llm is sync: still call async function via asyncio.run
    import asyncio

    return asyncio.run(
        llm_domain_guard(
            user_question,
            llm=llm,
            model=model,
            confidence_ask_threshold=confidence_ask_threshold,
        )
    )