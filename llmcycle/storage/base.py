"""
LLMCycle Storage — Abstract Base + Backend Enum
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, List

from llmcycle.storage.models import (
    Workplace, Team, User, Session, LLMRequest, HistoryMessage,
    ToolCall, RequestFeedback, StoreConfig
)


class StorageBackend(Enum):
    """
    Choose exactly ONE backend.

    Usage:
        from llmcycle.storage import StorageBackend, StorageManager

        store = StorageManager(
            backend=StorageBackend.SQLITE,
            url="sqlite+aiosqlite:///./llmcycle.db"
        )

        # or
        store = StorageManager(StorageBackend.POSTGRES,  "postgresql+asyncpg://user:pass@host/db")
        store = StorageManager(StorageBackend.MYSQL,     "mysql+aiomysql://user:pass@host/db")
        store = StorageManager(StorageBackend.MSSQL,     "mssql+aioodbc://user:pass@host/db?driver=ODBC+Driver+18+for+SQL+Server")
        store = StorageManager(StorageBackend.MONGO,     "mongodb://localhost:27017/llmcycle")
        store = StorageManager(StorageBackend.REDIS,     "redis://localhost:6379/0")
    """
    SQLITE   = "sqlite"
    POSTGRES = "postgres"
    MYSQL    = "mysql"
    MSSQL    = "mssql"
    MONGO    = "mongo"
    REDIS    = "redis"


class BaseStorage(ABC):
    """Abstract interface every backend must implement."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def ping(self) -> dict:
        """
        Test the connection. Returns:
            {"ok": True, "backend": "sqlite", "latency_ms": 1.2}
        or:
            {"ok": False, "backend": "redis", "error": "Connection refused"}
        """
        ...

    # ── Workplaces ──────────────────────────────────────────────────
    @abstractmethod
    async def create_workplace(self, wp: Workplace) -> Workplace: ...

    @abstractmethod
    async def get_workplace(self, id: str) -> Optional[Workplace]: ...

    @abstractmethod
    async def list_workplaces(self) -> List[Workplace]: ...

    # ── Teams ────────────────────────────────────────────────────────
    @abstractmethod
    async def create_team(self, team: Team) -> Team: ...

    @abstractmethod
    async def get_team(self, id: str) -> Optional[Team]: ...

    @abstractmethod
    async def list_teams(self, workplace_id: Optional[str] = None) -> List[Team]: ...

    # ── Users ────────────────────────────────────────────────────────
    @abstractmethod
    async def create_user(self, user: User) -> User: ...

    @abstractmethod
    async def get_user(self, id: str) -> Optional[User]: ...

    @abstractmethod
    async def get_user_by_username(self, username: str) -> Optional[User]: ...

    @abstractmethod
    async def list_users(self, team_id: Optional[str] = None) -> List[User]: ...

    @abstractmethod
    async def update_user(self, user: User) -> User: ...

    @abstractmethod
    async def delete_user(self, id: str) -> None: ...

    # ── Sessions ─────────────────────────────────────────────────────
    @abstractmethod
    async def create_session(self, session: Session) -> Session: ...

    @abstractmethod
    async def get_session(self, id: str) -> Optional[Session]: ...

    @abstractmethod
    async def update_session(self, session: Session) -> Session: ...

    @abstractmethod
    async def list_sessions(self, user_id: Optional[str] = None,
                            team_id: Optional[str] = None,
                            limit: int = 50) -> List[Session]: ...

    # ── Requests ─────────────────────────────────────────────────────
    @abstractmethod
    async def save_request(self, req: LLMRequest) -> LLMRequest: ...

    @abstractmethod
    async def get_request(self, id: str) -> Optional[LLMRequest]: ...

    @abstractmethod
    async def list_requests(self, session_id: Optional[str] = None,
                            user_id: Optional[str] = None,
                            limit: int = 100) -> List[LLMRequest]: ...

    # ── History ──────────────────────────────────────────────────────
    @abstractmethod
    async def add_message(self, msg: HistoryMessage) -> HistoryMessage: ...

    async def add_messages(
        self, msgs: "List[HistoryMessage]"
    ) -> "List[HistoryMessage]":
        """
        Persist multiple messages in order (batch helper).

        Default implementation calls add_message() sequentially.
        Override for atomic batch inserts.

        Usage::

            await store.add_messages([
                HistoryMessage(session_id=sid, role="user",      content="Hi"),
                HistoryMessage(session_id=sid, role="assistant", content="Hello!"),
            ])
        """
        results = []
        for m in msgs:
            results.append(await self.add_message(m))
        return results

    async def add_turn(
        self,
        session_id: str,
        user_content: str,
        assistant_content: str,
        request_id: str = "",
        metadata: dict = None,
    ) -> "List[HistoryMessage]":
        """
        Add a complete user + assistant turn in one call.

        Usage::

            msgs = await store.add_turn(
                session_id="sess-1",
                user_content="What is RAG?",
                assistant_content="RAG stands for Retrieval-Augmented Generation.",
                request_id=req.id,
            )
        """
        from llmcycle.storage.models import HistoryMessage as _HM
        user_msg = _HM(
            session_id=session_id, role="user",
            content=user_content, metadata=metadata or {},
        )
        asst_msg = _HM(
            session_id=session_id, role="assistant",
            content=assistant_content,
            request_id=request_id or None,
            metadata=metadata or {},
        )
        return await self.add_messages([user_msg, asst_msg])

    # Backward-compat alias (deprecated — use add_message instead)
    async def append_history(self, msg: "HistoryMessage") -> "HistoryMessage":
        """Deprecated. Use add_message() instead."""
        return await self.add_message(msg)

    @abstractmethod
    async def get_history(self, session_id: str,
                          limit: int = 100) -> List[HistoryMessage]: ...

    @abstractmethod
    async def clear_history(self, session_id: str) -> None: ...

    @abstractmethod
    async def purge_by_range(
        self,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        entities: Optional[List[str]] = None,
    ) -> dict:
        """
        Delete stored data by date range.

        Args:
            from_ts:  Unix timestamp lower bound (inclusive). None = no lower bound.
            to_ts:    Unix timestamp upper bound (inclusive). None = no upper bound.
            entities: Which entity types to purge. Options:
                        "requests"  - LLM request logs
                        "history"   - Conversation history messages
                        "sessions"  - Session records
                        "all"       - Everything above
                      Default: ["requests"] (safest)

        Returns:
            {"deleted": {"requests": 120, "history": 340, "sessions": 15}}

        Examples::

            # Delete all requests older than 30 days
            import time
            await store.purge_by_range(to_ts=time.time() - 30 * 86400)

            # Delete everything in a specific range
            await store.purge_by_range(
                from_ts=1700000000,
                to_ts=1700086400,
                entities=["requests", "history", "sessions"]
            )

            # Delete all cached data (full wipe)
            await store.purge_by_range(entities=["all"])
        """
        ...

    # ── Request lifecycle ────────────────────────────────────────────
    @abstractmethod
    async def update_request_status(
        self,
        request_id: str,
        status: str,
        error: Optional[str] = None,
        cancelled_at: Optional[float] = None,
    ) -> None:
        """
        Update only the status (and optional error/cancelled_at) of an existing request.
        Used for mid-stream cancellation and timeout tracking without re-saving the full record.

        Args:
            request_id:   LLMRequest.id to update.
            status:       New status — "success" | "error" | "cancelled" | "timeout".
            error:        Optional error message to store.
            cancelled_at: Unix timestamp of when the cancellation occurred.

        Examples::

            # Mark a request as cancelled mid-stream
            await store.update_request_status(
                req_id,
                status="cancelled",
                cancelled_at=time.time(),
            )

            # Mark as timed out
            await store.update_request_status(req_id, status="timeout", error="Exceeded 30s")
        """
        ...

    @abstractmethod
    async def cancel_request(self, request_id: str) -> None:
        """
        Convenience shortcut: mark a request as cancelled right now.
        Equivalent to: update_request_status(id, "cancelled", cancelled_at=time.time())
        """
        ...

    # ── Tool calls ───────────────────────────────────────────────────
    @abstractmethod
    async def save_tool_call(self, tool_call: ToolCall) -> ToolCall:
        """
        Persist a tool/function call returned by the LLM.

        Usage::

            tool = ToolCall(
                request_id=req.id,
                name="get_weather",
                arguments={"city": "London"},
                arguments_raw='{\"city\": \"London\"}',
            )
            saved = await store.save_tool_call(tool)
        """
        ...

    @abstractmethod
    async def update_tool_call(self, tool_call: ToolCall) -> ToolCall:
        """
        Update a tool call with its execution result.

        Usage::

            tool.result = json.dumps({"temp": 18})
            tool.executed_at = time.time()
            tool.status = "success"
            await store.update_tool_call(tool)
        """
        ...

    @abstractmethod
    async def list_tool_calls(
        self,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[ToolCall]:
        """
        List tool calls filtered by request, session, or status.

        Examples::

            # All tool calls for a request
            tools = await store.list_tool_calls(request_id=req.id)

            # All pending tool calls in a session
            pending = await store.list_tool_calls(session_id=sid, status="pending")
        """
        ...

    # ── Feedback ─────────────────────────────────────────────────────
    @abstractmethod
    async def save_feedback(self, feedback: RequestFeedback) -> RequestFeedback:
        """
        Save human feedback (thumbs up/down, rating, comment) on a completed request.

        Usage::

            await store.save_feedback(RequestFeedback(
                request_id=req.id,
                user_id="user-123",
                thumbs_up=True,
                rating=5,
                comment="Perfect!",
            ))
        """
        ...

    @abstractmethod
    async def list_feedback(
        self,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[RequestFeedback]:
        """List feedback records filtered by request, user, or session."""
        ...

    # ── Configuration ────────────────────────────────────────────────
    @abstractmethod
    async def save_config(self, key: str, value: dict) -> StoreConfig:
        """Save a generic JSON configuration object."""
        ...

    @abstractmethod
    async def get_config(self, key: str) -> Optional[StoreConfig]:
        """Retrieve a saved configuration object."""
        ...
