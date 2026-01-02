# agentic_ai_system/validators/domain_guard.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple
import re


@dataclass(frozen=True)
class DomainGuardResult:
    allowed: bool
    message: str
    matched_keywords: List[str]


# โดเมนที่อนุญาต: orders, branches, sales/revenue
_KEYWORD_GROUPS: List[List[str]] = [
    # orders / order-related
    [
        "order", "orders", "purchase", "purchases",
        "คำสั่งซื้อ", "ออเดอร์", "รายการสั่งซื้อ", "สถานะคำสั่งซื้อ", "สถานะออเดอร์",
        "ยอดสั่งซื้อ", "จำนวนออเดอร์", "cancel", "cancelled", "คืนเงิน", "refund",
        "delivery", "shipping", "จัดส่ง",
    ],
    # branches / branch-related
    [
        "branch", "branches", "store", "stores", "location",
        "สาขา", "หน้าร้าน", "ร้าน", "สาขาไหน", "สาขาใด",
    ],
    # sales / revenue / metrics
    [
        "sale", "sales", "revenue", "income", "turnover", "gmv", "aov",
        "ยอดขาย", "รายได้", "รายรับ", "ยอดเงิน", "ยอดรวม", "มูลค่า", "กำไร", "gross",
        "top", "อันดับ", "best seller", "bestseller",
    ],
    # time/filter (ช่วยให้คำถาม metric ผ่านง่ายขึ้น)
    [
        "today", "yesterday", "this week", "last week", "this month", "last month",
        "this year", "last year", "date", "time", "range", "between",
        "วันนี้", "เมื่อวาน", "สัปดาห์นี้", "เดือนนี้", "ปีนี้", "ช่วง", "ระหว่าง", "วันที่",
    ],
]

# บางคำมันสั้น/กว้างเกินไป เลยใส่เป็น “ต้อง match แบบคำเต็ม” ลด false positive
_STRICT_WORDS = {"top", "date", "time", "range", "gross"}


def _normalize(text: str) -> str:
    text = (text or "").strip().lower()
    # ลด noise
    text = re.sub(r"\s+", " ", text)
    return text


def _match_keyword(q: str, kw: str) -> bool:
    if kw in _STRICT_WORDS:
        # match แบบเป็นคำ (word boundary) สำหรับอังกฤษ
        return re.search(rf"\b{re.escape(kw)}\b", q) is not None
    # ไทยไม่มี word boundary ชัด เลยใช้ contains ได้
    return kw in q


def check_in_domain(user_prompt: str) -> DomainGuardResult:
    """
    อนุญาตเฉพาะคำถามเกี่ยวกับ: คำสั่งซื้อ / สาขา / การขาย-รายได้
    ถ้านอกโดเมน -> allowed=False พร้อมข้อความบอกให้ถามใหม่ในกรอบ
    """
    q = _normalize(user_prompt)

    matched: List[str] = []
    for group in _KEYWORD_GROUPS:
        for kw in group:
            if _match_keyword(q, kw):
                matched.append(kw)

    # เกณฑ์ง่ายๆ: มีคีย์เวิร์ดโดเมนอย่างน้อย 1 คำ -> ผ่าน
    if matched:
        return DomainGuardResult(
            allowed=True,
            message="",
            matched_keywords=sorted(set(matched)),
        )

    # ไม่ผ่าน -> ปฏิเสธ + ชี้ทางกลับเข้าโดเมน
    msg = (
        "ตอนนี้รองรับเฉพาะคำถามเกี่ยวกับ **คำสั่งซื้อ / สาขา / ยอดขาย-รายได้** เท่านั้น\n"
        "ลองถามใหม่แบบนี้ได้ เช่น:\n"
        "- ยอดขายรวมเดือนนี้ แยกตามสาขา\n"
        "- จำนวนคำสั่งซื้อวันนี้ของแต่ละสาขา\n"
        "- Top 5 สาขาตามยอดขายช่วง 30 วันที่ผ่านมา\n"
    )
    return DomainGuardResult(allowed=False, message=msg, matched_keywords=[])
