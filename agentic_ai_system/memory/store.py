# agentic_ai_system/memory/store.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from collections import deque
from threading import RLock
from time import time
from typing import Deque, Dict, List, Literal, Optional


Role = Literal["user", "assistant", "system"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str
    ts: float  # unix timestamp (seconds)

    def to_dict(self) -> dict:
        return asdict(self)


class InMemoryConversationStore:
    """
    MVP memory store:
    - In-memory only (restart server = memory gone)
    - Per conversation_id keeps last N messages (role/content/timestamp)
    - Thread-safe enough for typical FastAPI usage
    """

    def __init__(
        self,
        max_messages: int = 10,
        max_chars_per_message: int = 1500,
        default_conversation_id: str = "default",
    ) -> None:
        if max_messages <= 0:
            raise ValueError("max_messages must be > 0")
        if max_chars_per_message <= 0:
            raise ValueError("max_chars_per_message must be > 0")

        self.max_messages = max_messages
        self.max_chars_per_message = max_chars_per_message
        self.default_conversation_id = default_conversation_id

        self._lock = RLock()
        self._data: Dict[str, Deque[Message]] = {}

    def _normalize_cid(self, conversation_id: Optional[str]) -> str:
        cid = (conversation_id or "").strip()
        return cid if cid else self.default_conversation_id

    def _trim(self, content: str) -> str:
        content = content or ""
        if len(content) <= self.max_chars_per_message:
            return content
        # keep it simple: hard cut
        return content[: self.max_chars_per_message]

    def get_history(self, conversation_id: Optional[str]) -> List[Message]:
        """
        Returns messages oldest->newest.
        """
        cid = self._normalize_cid(conversation_id)
        with self._lock:
            q = self._data.get(cid)
            if not q:
                return []
            return list(q)

    def get_history_dicts(self, conversation_id: Optional[str]) -> List[dict]:
        """
        Convenience helper if you want JSON-serializable history.
        """
        return [m.to_dict() for m in self.get_history(conversation_id)]

    def append(self, conversation_id: Optional[str], role: Role, content: str) -> None:
        cid = self._normalize_cid(conversation_id)
        msg = Message(role=role, content=self._trim(content), ts=time())

        with self._lock:
            if cid not in self._data:
                self._data[cid] = deque(maxlen=self.max_messages)
            self._data[cid].append(msg)

    def clear(self, conversation_id: Optional[str]) -> None:
        cid = self._normalize_cid(conversation_id)
        with self._lock:
            self._data.pop(cid, None)

    def size(self, conversation_id: Optional[str]) -> int:
        cid = self._normalize_cid(conversation_id)
        with self._lock:
            q = self._data.get(cid)
            return len(q) if q else 0


# Simple singleton for easy import everywhere
store = InMemoryConversationStore(
    max_messages=10,           # change to 20 if you want 10 turns (user+assistant)
    max_chars_per_message=1500,
    default_conversation_id="default",
)
