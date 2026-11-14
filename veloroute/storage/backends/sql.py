"""
SQLAlchemy async backend — covers SQLite, PostgreSQL, MySQL, MSSQL.
One implementation, four databases.

Required packages per DB:
  SQLite:   pip install aiosqlite
  Postgres: pip install asyncpg
  MySQL:    pip install aiomysql
  MSSQL:    pip install aioodbc
"""
from __future__ import annotations
import json, time as _time
from typing import Optional, List, Any

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Text, Float, Integer, Boolean, select, delete, update

from veloroute.storage.base import BaseStorage
from veloroute.storage.models import (
    Workplace, Team, User, Session, LLMRequest, HistoryMessage,
    ToolCall, RequestFeedback, StoreConfig
)


# ─── ORM Tables ──────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass

def _j(v) -> str:  return json.dumps(v)
def _u(s) -> Any:  return json.loads(s) if s else {}
def _ul(s) -> Any: return json.loads(s) if s else []


class WorkplaceRow(Base):
    __tablename__ = "workplaces"
    id: Mapped[str]      = mapped_column(Text, primary_key=True)
    name: Mapped[str]    = mapped_column(Text)
    settings: Mapped[str]    = mapped_column(Text, default="{}")
    created_at: Mapped[float] = mapped_column(Float)
    metadata_: Mapped[str]   = mapped_column("metadata", Text, default="{}")

class TeamRow(Base):
    __tablename__ = "teams"
    id: Mapped[str]           = mapped_column(Text, primary_key=True)
    name: Mapped[str]         = mapped_column(Text)
    workplace_id: Mapped[str] = mapped_column(Text)
    member_ids: Mapped[str]   = mapped_column(Text, default="[]")
    created_at: Mapped[float] = mapped_column(Float)
    metadata_: Mapped[str]    = mapped_column("metadata", Text, default="{}")

class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[str]             = mapped_column(Text, primary_key=True)
    username: Mapped[str]       = mapped_column(Text, unique=True, index=True)
    email: Mapped[Optional[str]]= mapped_column(Text, nullable=True)
    role: Mapped[str]           = mapped_column(Text, default="member")
    team_id: Mapped[Optional[str]]      = mapped_column(Text, nullable=True)
    workplace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[float]   = mapped_column(Float)
    metadata_: Mapped[str]      = mapped_column("metadata", Text, default="{}")

class SessionRow(Base):
    __tablename__ = "sessions"
    id: Mapped[str]              = mapped_column(Text, primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)
    team_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model: Mapped[str]           = mapped_column(Text, default="")
    started_at: Mapped[float]    = mapped_column(Float)
    ended_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_requests: Mapped[int]  = mapped_column(Integer, default=0)
    total_tokens: Mapped[int]    = mapped_column(Integer, default=0)
    metadata_: Mapped[str]       = mapped_column("metadata", Text, default="{}")

class RequestRow(Base):
    __tablename__ = "llm_requests"
    id: Mapped[str]              = mapped_column(Text, primary_key=True)
    session_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)
    user_id: Mapped[Optional[str]]    = mapped_column(Text, nullable=True, index=True)
    team_id: Mapped[Optional[str]]    = mapped_column(Text, nullable=True, index=True)
    workplace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_request_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    turn_number: Mapped[int]         = mapped_column(Integer, default=0)
    model: Mapped[str]               = mapped_column(Text)
    provider: Mapped[str]            = mapped_column(Text, default="")
    prompt: Mapped[str]              = mapped_column(Text, default="")
    response: Mapped[str]            = mapped_column(Text, default="")
    prompt_tokens: Mapped[int]       = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int]   = mapped_column(Integer, default=0)
    total_tokens: Mapped[int]        = mapped_column(Integer, default=0)
    latency_ms: Mapped[float]        = mapped_column(Float, default=0.0)
    time_to_first_token_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str]              = mapped_column(Text, default="success", index=True)
    error: Mapped[Optional[str]]     = mapped_column(Text, nullable=True)
    fallback_used: Mapped[bool]      = mapped_column(Boolean, default=False)
    retries: Mapped[int]             = mapped_column(Integer, default=0)
    cancelled_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    timeout_ms: Mapped[Optional[float]]   = mapped_column(Float, nullable=True)
    cost_usd: Mapped[Optional[float]]     = mapped_column(Float, nullable=True)
    tags: Mapped[str]                = mapped_column(Text, default="[]")
    has_tool_calls: Mapped[bool]     = mapped_column(Boolean, default=False)
    is_cached: Mapped[bool]          = mapped_column(Boolean, default=False)
    input_cost_per_1k: Mapped[Optional[float]]  = mapped_column(Float, nullable=True)
    output_cost_per_1k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[float]        = mapped_column(Float, index=True)
    metadata_: Mapped[str]           = mapped_column("metadata", Text, default="{}")

class ToolCallRow(Base):
    __tablename__ = "tool_calls"
    id: Mapped[str]                   = mapped_column(Text, primary_key=True)
    request_id: Mapped[str]           = mapped_column(Text, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)
    user_id: Mapped[Optional[str]]    = mapped_column(Text, nullable=True)
    name: Mapped[str]                 = mapped_column(Text)
    arguments: Mapped[str]            = mapped_column(Text, default="{}")
    arguments_raw: Mapped[str]        = mapped_column(Text, default="")
    result: Mapped[Optional[str]]     = mapped_column(Text, nullable=True)
    result_tokens: Mapped[int]        = mapped_column(Integer, default=0)
    executed_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str]               = mapped_column(Text, default="pending", index=True)
    error: Mapped[Optional[str]]      = mapped_column(Text, nullable=True)
    created_at: Mapped[float]         = mapped_column(Float)
    metadata_: Mapped[str]            = mapped_column("metadata", Text, default="{}")

class FeedbackRow(Base):
    __tablename__ = "feedback"
    id: Mapped[str]                   = mapped_column(Text, primary_key=True)
    request_id: Mapped[str]           = mapped_column(Text, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_id: Mapped[Optional[str]]    = mapped_column(Text, nullable=True, index=True)
    thumbs_up: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    rating: Mapped[Optional[int]]     = mapped_column(Integer, nullable=True)
    comment: Mapped[Optional[str]]    = mapped_column(Text, nullable=True)
    tags: Mapped[str]                 = mapped_column(Text, default="[]")
    created_at: Mapped[float]         = mapped_column(Float)
    metadata_: Mapped[str]            = mapped_column("metadata", Text, default="{}")

class HistoryRow(Base):
    __tablename__ = "history"
    id: Mapped[str]                   = mapped_column(Text, primary_key=True)
    session_id: Mapped[str]           = mapped_column(Text, index=True)
    request_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    role: Mapped[str]                 = mapped_column(Text)
    content: Mapped[str]              = mapped_column(Text)
    tool_call_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[float]         = mapped_column(Float)
    metadata_: Mapped[str]            = mapped_column("metadata", Text, default="{}")

class ConfigRow(Base):
    __tablename__ = "configs"
    key: Mapped[str]        = mapped_column(Text, primary_key=True)
    value: Mapped[str]      = mapped_column(Text, default="{}")
    updated_at: Mapped[float] = mapped_column(Float)


# ─── Backend ──────────────────────────────────────────────────────────────────

class SQLStorage(BaseStorage):
    """
    Single SQLAlchemy async backend for SQLite / PostgreSQL / MySQL / MSSQL.

    Args:
        url:          SQLAlchemy async connection URL.
        schema:       DB schema name (PostgreSQL/MSSQL). None = use DB default.
        table_prefix: Prefix for all table names. Default: "velo_".

    URL format:
        sqlite:   sqlite+aiosqlite:///./veloroute.db
        postgres: postgresql+asyncpg://user:pass@host/db
        mysql:    mysql+aiomysql://user:pass@host/db
        mssql:    mssql+aioodbc://user:pass@host/db?driver=ODBC+Driver+18+for+SQL+Server
    """

    def __init__(self, url: str, schema: Optional[str] = None, table_prefix: str = "velo_", driver=None):
        clean_url = url or ""
        if clean_url.startswith("sqlite://") and not clean_url.startswith("sqlite+aiosqlite://"):
            clean_url = clean_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        elif (clean_url.startswith("postgres://") or clean_url.startswith("postgresql://")) and "+asyncpg" not in clean_url:
            clean_url = "postgresql+asyncpg://" + clean_url.split("://", 1)[1]
        elif clean_url.startswith("mysql://") and "+aiomysql" not in clean_url:
            clean_url = "mysql+aiomysql://" + clean_url.split("://", 1)[1]
        self.url = clean_url
        self.schema = schema
        self.table_prefix = table_prefix
        self.driver = driver
        self._engine = None
        self._session_factory = None
        self._meta: Optional[Base] = None

    def _make_meta(self) -> Base:
        """Dynamically create ORM metadata with custom table names and schema."""
        p = self.table_prefix
        s = self.schema

        class _Base(DeclarativeBase):
            pass

        class _WorkplaceRow(_Base):
            __tablename__ = f"{p}workplaces"
            __table_args__ = ({"schema": s} if s else {})
            id: Mapped[str]       = mapped_column(Text, primary_key=True)
            name: Mapped[str]     = mapped_column(Text)
            settings: Mapped[str] = mapped_column(Text, default="{}")
            created_at: Mapped[float] = mapped_column(Float)
            metadata_: Mapped[str]    = mapped_column("metadata", Text, default="{}")

        class _TeamRow(_Base):
            __tablename__ = f"{p}teams"
            __table_args__ = ({"schema": s} if s else {})
            id: Mapped[str]           = mapped_column(Text, primary_key=True)
            name: Mapped[str]         = mapped_column(Text)
            workplace_id: Mapped[str] = mapped_column(Text)
            member_ids: Mapped[str]   = mapped_column(Text, default="[]")
            created_at: Mapped[float] = mapped_column(Float)
            metadata_: Mapped[str]    = mapped_column("metadata", Text, default="{}")

        class _UserRow(_Base):
            __tablename__ = f"{p}users"
            __table_args__ = ({"schema": s} if s else {})
            id: Mapped[str]                = mapped_column(Text, primary_key=True)
            username: Mapped[str]          = mapped_column(Text, unique=True, index=True)
            email: Mapped[Optional[str]]   = mapped_column(Text, nullable=True)
            role: Mapped[str]              = mapped_column(Text, default="member")
            team_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
            workplace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
            hashed_password: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
            created_at: Mapped[float]      = mapped_column(Float)
            metadata_: Mapped[str]         = mapped_column("metadata", Text, default="{}")

        class _SessionRow(_Base):
            __tablename__ = f"{p}sessions"
            __table_args__ = ({"schema": s} if s else {})
            id: Mapped[str]                   = mapped_column(Text, primary_key=True)
            user_id: Mapped[Optional[str]]    = mapped_column(Text, nullable=True, index=True)
            team_id: Mapped[Optional[str]]    = mapped_column(Text, nullable=True)
            model: Mapped[str]                = mapped_column(Text, default="")
            started_at: Mapped[float]         = mapped_column(Float)
            ended_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
            total_requests: Mapped[int]       = mapped_column(Integer, default=0)
            total_tokens: Mapped[int]         = mapped_column(Integer, default=0)
            metadata_: Mapped[str]            = mapped_column("metadata", Text, default="{}")

        class _RequestRow(_Base):
            __tablename__ = f"{p}requests"
            __table_args__ = ({"schema": s} if s else {})
            id: Mapped[str]                   = mapped_column(Text, primary_key=True)
            session_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)
            user_id: Mapped[Optional[str]]    = mapped_column(Text, nullable=True, index=True)
            model: Mapped[str]                = mapped_column(Text)
            provider: Mapped[str]             = mapped_column(Text)
            prompt: Mapped[str]               = mapped_column(Text, default="")
            response: Mapped[str]             = mapped_column(Text, default="")
            prompt_tokens: Mapped[int]        = mapped_column(Integer, default=0)
            completion_tokens: Mapped[int]    = mapped_column(Integer, default=0)
            latency_ms: Mapped[float]         = mapped_column(Float, default=0.0)
            status: Mapped[str]               = mapped_column(Text, default="success")
            error: Mapped[Optional[str]]      = mapped_column(Text, nullable=True)
            fallback_used: Mapped[bool]       = mapped_column(Boolean, default=False)
            retries: Mapped[int]              = mapped_column(Integer, default=0)
            created_at: Mapped[float]         = mapped_column(Float)
            metadata_: Mapped[str]            = mapped_column("metadata", Text, default="{}")

        class _HistoryRow(_Base):
            __tablename__ = f"{p}history"
            __table_args__ = ({"schema": s} if s else {})
            id: Mapped[str]                   = mapped_column(Text, primary_key=True)
            session_id: Mapped[str]           = mapped_column(Text, index=True)
            request_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
            role: Mapped[str]                 = mapped_column(Text)
            content: Mapped[str]              = mapped_column(Text)
            created_at: Mapped[float]         = mapped_column(Float)
            metadata_: Mapped[str]            = mapped_column("metadata", Text, default="{}")

        class _ConfigRow(_Base):
            __tablename__ = f"{p}configs"
            __table_args__ = ({"schema": s} if s else {})
            key: Mapped[str]        = mapped_column(Text, primary_key=True)
            value: Mapped[str]      = mapped_column(Text, default="{}")
            updated_at: Mapped[float] = mapped_column(Float)

        # Expose row classes as instance attributes for CRUD methods
        self.WorkplaceRow = _WorkplaceRow
        self.TeamRow      = _TeamRow
        self.UserRow      = _UserRow
        self.SessionRow   = _SessionRow
        self.RequestRow   = _RequestRow
        self.HistoryRow   = _HistoryRow
        self.ConfigRow    = _ConfigRow
        return _Base

    async def connect(self):
        if self.driver:
            await self.driver.connect_async()
            self._engine = self.driver.get_engine()
            self._session_factory = self.driver.get_sessionmaker()
        else:
            connect_args = {"check_same_thread": False, "timeout": 30.0} if "sqlite" in self.url else {}
            kw = {"pool_pre_ping": True}
            if "sqlite" in self.url:
                kw["pool_recycle"] = 3600
            self._engine = create_async_engine(self.url, echo=False, connect_args=connect_args, **kw)
            self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def disconnect(self):
        if self._engine:
            await self._engine.dispose()

    async def ping(self) -> dict:
        """Verify the DB connection with a lightweight SELECT 1."""
        import time
        backend_name = self.url.split(":")[0].split("+")[0]  # e.g. 'sqlite', 'postgresql'
        try:
            t0 = time.monotonic()
            from sqlalchemy import text
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            return {"ok": True, "backend": backend_name, "url": self.url, "latency_ms": latency_ms}
        except Exception as e:
            return {"ok": False, "backend": backend_name, "url": self.url, "error": str(e)}

    def _s(self) -> AsyncSession:
        return self._session_factory()

    # ── Workplaces ──────────────────────────────────────────────────
    async def create_workplace(self, wp: Workplace) -> Workplace:
        async with self._s() as s:
            s.add(WorkplaceRow(id=wp.id, name=wp.name, settings=_j(wp.settings), created_at=wp.created_at, metadata_=_j(wp.metadata)))
            await s.commit()
        return wp

    async def get_workplace(self, id: str) -> Optional[Workplace]:
        async with self._s() as s:
            row = await s.get(WorkplaceRow, id)
            return Workplace(id=row.id, name=row.name, settings=_u(row.settings), created_at=row.created_at, metadata=_u(row.metadata_)) if row else None

    async def list_workplaces(self) -> List[Workplace]:
        async with self._s() as s:
            rows = (await s.execute(select(WorkplaceRow))).scalars().all()
            return [Workplace(id=r.id, name=r.name, settings=_u(r.settings), created_at=r.created_at, metadata=_u(r.metadata_)) for r in rows]

    # ── Teams ────────────────────────────────────────────────────────
    async def create_team(self, team: Team) -> Team:
        async with self._s() as s:
            s.add(TeamRow(id=team.id, name=team.name, workplace_id=team.workplace_id, member_ids=_j(team.member_ids), created_at=team.created_at, metadata_=_j(team.metadata)))
            await s.commit()
        return team

    async def get_team(self, id: str) -> Optional[Team]:
        async with self._s() as s:
            row = await s.get(TeamRow, id)
            return Team(id=row.id, name=row.name, workplace_id=row.workplace_id, member_ids=_ul(row.member_ids), created_at=row.created_at, metadata=_u(row.metadata_)) if row else None

    async def list_teams(self, workplace_id: Optional[str] = None) -> List[Team]:
        async with self._s() as s:
            q = select(TeamRow)
            if workplace_id:
                q = q.where(TeamRow.workplace_id == workplace_id)
            rows = (await s.execute(q)).scalars().all()
            return [Team(id=r.id, name=r.name, workplace_id=r.workplace_id, member_ids=_ul(r.member_ids), created_at=r.created_at, metadata=_u(r.metadata_)) for r in rows]

    # ── Users ────────────────────────────────────────────────────────
    async def create_user(self, user: User) -> User:
        async with self._s() as s:
            s.add(UserRow(id=user.id, username=user.username, email=user.email, role=user.role, team_id=user.team_id, workplace_id=user.workplace_id, hashed_password=user.hashed_password, created_at=user.created_at, metadata_=_j(user.metadata)))
            await s.commit()
        return user

    async def get_user(self, id: str) -> Optional[User]:
        async with self._s() as s:
            row = await s.get(UserRow, id)
            return self._user(row) if row else None

    async def get_user_by_username(self, username: str) -> Optional[User]:
        async with self._s() as s:
            row = (await s.execute(select(UserRow).where(UserRow.username == username))).scalar_one_or_none()
            return self._user(row) if row else None

    async def list_users(self, team_id: Optional[str] = None) -> List[User]:
        async with self._s() as s:
            q = select(UserRow)
            if team_id:
                q = q.where(UserRow.team_id == team_id)
            return [self._user(r) for r in (await s.execute(q)).scalars().all()]

    async def update_user(self, user: User) -> User:
        async with self._s() as s:
            row = await s.get(UserRow, user.id)
            if row:
                row.username = user.username; row.email = user.email; row.role = user.role
                row.team_id = user.team_id; row.workplace_id = user.workplace_id
                row.hashed_password = user.hashed_password; row.metadata_ = _j(user.metadata)
                await s.commit()
        return user

    async def delete_user(self, id: str) -> None:
        async with self._s() as s:
            await s.execute(delete(UserRow).where(UserRow.id == id))
            await s.commit()

    def _user(self, r: UserRow) -> User:
        return User(id=r.id, username=r.username, email=r.email, role=r.role, team_id=r.team_id, workplace_id=r.workplace_id, hashed_password=r.hashed_password, created_at=r.created_at, metadata=_u(r.metadata_))

    # ── Sessions ─────────────────────────────────────────────────────
    async def create_session(self, session: Session) -> Session:
        async with self._s() as s:
            s.add(SessionRow(id=session.id, user_id=session.user_id, team_id=session.team_id, model=session.model, started_at=session.started_at, ended_at=session.ended_at, total_requests=session.total_requests, total_tokens=session.total_tokens, metadata_=_j(session.metadata)))
            await s.commit()
        return session

    async def get_session(self, id: str) -> Optional[Session]:
        async with self._s() as s:
            row = await s.get(SessionRow, id)
            return self._session(row) if row else None

    async def update_session(self, session: Session) -> Session:
        async with self._s() as s:
            row = await s.get(SessionRow, session.id)
            if row:
                row.ended_at = session.ended_at; row.total_requests = session.total_requests
                row.total_tokens = session.total_tokens; row.metadata_ = _j(session.metadata)
                await s.commit()
        return session

    async def list_sessions(self, user_id=None, team_id=None, limit=50) -> List[Session]:
        async with self._s() as s:
            q = select(SessionRow)
            if user_id: q = q.where(SessionRow.user_id == user_id)
            if team_id: q = q.where(SessionRow.team_id == team_id)
            q = q.limit(limit).order_by(SessionRow.started_at.desc())
            return [self._session(r) for r in (await s.execute(q)).scalars().all()]

    def _session(self, r: SessionRow) -> Session:
        return Session(id=r.id, user_id=r.user_id, team_id=r.team_id, model=r.model, started_at=r.started_at, ended_at=r.ended_at, total_requests=r.total_requests, total_tokens=r.total_tokens, metadata=_u(r.metadata_))

    # ── Requests ─────────────────────────────────────────────────────
    async def save_request(self, req: LLMRequest) -> Optional[LLMRequest]:
        try:
            async with self._s() as s:
                s.add(RequestRow(
                    id=req.id, session_id=req.session_id,
                    user_id=req.user_id,
                    team_id=getattr(req, 'team_id', None),
                    workplace_id=getattr(req, 'workplace_id', None),
                    parent_request_id=getattr(req, 'parent_request_id', None),
                    turn_number=getattr(req, 'turn_number', 0),
                    model=req.model, provider=req.provider,
                    prompt=req.prompt, response=req.response,
                    prompt_tokens=req.prompt_tokens,
                    completion_tokens=req.completion_tokens,
                    total_tokens=getattr(req, 'total_tokens', req.prompt_tokens + req.completion_tokens),
                    latency_ms=req.latency_ms,
                    time_to_first_token_ms=getattr(req, 'time_to_first_token_ms', None),
                    status=req.status, error=req.error,
                    fallback_used=req.fallback_used, retries=req.retries,
                    cancelled_at=getattr(req, 'cancelled_at', None),
                    timeout_ms=getattr(req, 'timeout_ms', None),
                    cost_usd=getattr(req, 'cost_usd', None),
                    input_cost_per_1k=getattr(req, 'input_cost_per_1k', None),
                    output_cost_per_1k=getattr(req, 'output_cost_per_1k', None),
                    tags=_j(getattr(req, 'tags', [])),
                    has_tool_calls=getattr(req, 'has_tool_calls', False),
                    is_cached=getattr(req, 'is_cached', False),
                    created_at=req.created_at, metadata_=_j(req.metadata),
                ))
                await s.commit()
            return req
        except asyncio.CancelledError:
            return None
        except Exception as e:
            logger.debug("save_request non-fatal failure: %s", e)
            return None

    async def get_request(self, id: str) -> Optional[LLMRequest]:
        async with self._s() as s:
            row = await s.get(RequestRow, id)
            return self._req(row) if row else None

    async def list_requests(self, session_id=None, user_id=None, limit=100) -> List[LLMRequest]:
        async with self._s() as s:
            q = select(RequestRow)
            if session_id: q = q.where(RequestRow.session_id == session_id)
            if user_id: q = q.where(RequestRow.user_id == user_id)
            q = q.limit(limit).order_by(RequestRow.created_at.desc())
            return [self._req(r) for r in (await s.execute(q)).scalars().all()]

    def _req(self, r) -> LLMRequest:
        return LLMRequest(
            id=r.id, session_id=r.session_id,
            user_id=r.user_id,
            team_id=getattr(r, 'team_id', None),
            workplace_id=getattr(r, 'workplace_id', None),
            parent_request_id=getattr(r, 'parent_request_id', None),
            turn_number=getattr(r, 'turn_number', 0),
            model=r.model, provider=r.provider,
            prompt=r.prompt, response=r.response,
            prompt_tokens=r.prompt_tokens,
            completion_tokens=r.completion_tokens,
            total_tokens=getattr(r, 'total_tokens', 0),
            latency_ms=r.latency_ms,
            time_to_first_token_ms=getattr(r, 'time_to_first_token_ms', None),
            status=r.status, error=r.error,
            fallback_used=r.fallback_used, retries=r.retries,
            cancelled_at=getattr(r, 'cancelled_at', None),
            timeout_ms=getattr(r, 'timeout_ms', None),
            cost_usd=getattr(r, 'cost_usd', None),
            input_cost_per_1k=getattr(r, 'input_cost_per_1k', None),
            output_cost_per_1k=getattr(r, 'output_cost_per_1k', None),
            tags=_ul(getattr(r, 'tags', '[]')),
            has_tool_calls=getattr(r, 'has_tool_calls', False),
            is_cached=getattr(r, 'is_cached', False),
            created_at=r.created_at, metadata=_u(r.metadata_),
        )

    # ── History ──────────────────────────────────────────────────────
    async def add_message(self, msg: HistoryMessage) -> HistoryMessage:
        async with self._s() as s:
            s.add(HistoryRow(
                id=msg.id, session_id=msg.session_id,
                request_id=msg.request_id, role=msg.role,
                content=msg.content,
                tool_call_id=getattr(msg, 'tool_call_id', None),
                created_at=msg.created_at, metadata_=_j(msg.metadata),
            ))
            await s.commit()
        return msg

    async def get_history(self, session_id: str, limit=100) -> List[HistoryMessage]:
        async with self._s() as s:
            q = (select(HistoryRow).where(HistoryRow.session_id == session_id)
                 .order_by(HistoryRow.created_at).limit(limit))
            rows = (await s.execute(q)).scalars().all()
            return [
                HistoryMessage(
                    id=r.id, session_id=r.session_id,
                    request_id=r.request_id, role=r.role,
                    content=r.content,
                    tool_call_id=getattr(r, 'tool_call_id', None),
                    created_at=r.created_at, metadata=_u(r.metadata_),
                )
                for r in rows
            ]

    async def clear_history(self, session_id: str) -> None:
        async with self._s() as s:
            await s.execute(delete(HistoryRow).where(HistoryRow.session_id == session_id))
            await s.commit()

    # ── Purge by date range ───────────────────────────────────────────
    async def purge_by_range(
        self,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        entities: Optional[List[str]] = None,
    ) -> dict:
        """Delete rows within a timestamp range. Returns deleted count per entity."""
        targets = set(entities or ["requests"])
        if "all" in targets:
            targets = {"requests", "history", "sessions"}

        deleted = {}
        # Use dynamic row classes if _make_meta was called, else fall back to module-level
        RR = getattr(self, "RequestRow", RequestRow)
        HR = getattr(self, "HistoryRow", HistoryRow)
        SR = getattr(self, "SessionRow", SessionRow)

        def _range_clause(col):
            clauses = []
            if from_ts is not None: clauses.append(col >= from_ts)
            if to_ts   is not None: clauses.append(col <= to_ts)
            return clauses

        async with self._s() as s:
            if "requests" in targets:
                q = delete(RR)
                for c in _range_clause(RR.created_at): q = q.where(c)
                result = await s.execute(q)
                deleted["requests"] = result.rowcount

            if "history" in targets:
                q = delete(HR)
                for c in _range_clause(HR.created_at): q = q.where(c)
                result = await s.execute(q)
                deleted["history"] = result.rowcount

            if "sessions" in targets:
                q = delete(SR)
                for c in _range_clause(SR.started_at): q = q.where(c)
                result = await s.execute(q)
                deleted["sessions"] = result.rowcount

            await s.commit()

        return {"deleted": deleted}

    # ── Request lifecycle ────────────────────────────────────────────────
    async def update_request_status(
        self,
        request_id: str,
        status: str,
        error: Optional[str] = None,
        cancelled_at: Optional[float] = None,
    ) -> None:
        """Update status, error, cancelled_at on an existing request row."""
        RR = getattr(self, "RequestRow", RequestRow)
        vals = {"status": status}
        if error        is not None: vals["error"]        = error
        if cancelled_at is not None: vals["cancelled_at"] = cancelled_at
        async with self._s() as s:
            await s.execute(update(RR).where(RR.id == request_id).values(**vals))
            await s.commit()

    async def cancel_request(self, request_id: str) -> None:
        """Shortcut: mark request as cancelled with current timestamp."""
        await self.update_request_status(
            request_id, status="cancelled", cancelled_at=_time.time()
        )

    # ── Tool calls ───────────────────────────────────────────────────────
    async def save_tool_call(self, tc: ToolCall) -> ToolCall:
        TCR = getattr(self, "ToolCallRow", ToolCallRow)
        async with self._s() as s:
            s.add(TCR(
                id=tc.id, request_id=tc.request_id,
                session_id=tc.session_id, user_id=tc.user_id,
                name=tc.name, arguments=_j(tc.arguments),
                arguments_raw=tc.arguments_raw,
                result=tc.result, result_tokens=tc.result_tokens,
                executed_at=tc.executed_at, status=tc.status,
                error=tc.error, created_at=tc.created_at,
                metadata_=_j(tc.metadata),
            ))
            await s.commit()
        return tc

    async def update_tool_call(self, tc: ToolCall) -> ToolCall:
        TCR = getattr(self, "ToolCallRow", ToolCallRow)
        async with self._s() as s:
            row = await s.get(TCR, tc.id)
            if row:
                row.result        = tc.result
                row.result_tokens = tc.result_tokens
                row.executed_at   = tc.executed_at
                row.status        = tc.status
                row.error         = tc.error
                row.metadata_     = _j(tc.metadata)
                await s.commit()
        return tc

    async def list_tool_calls(
        self,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[ToolCall]:
        TCR = getattr(self, "ToolCallRow", ToolCallRow)
        async with self._s() as s:
            q = select(TCR)
            if request_id: q = q.where(TCR.request_id == request_id)
            if session_id: q = q.where(TCR.session_id == session_id)
            if status:     q = q.where(TCR.status == status)
            q = q.limit(limit).order_by(TCR.created_at.desc())
            rows = (await s.execute(q)).scalars().all()
            return [ToolCall(
                id=r.id, request_id=r.request_id,
                session_id=r.session_id, user_id=r.user_id,
                name=r.name, arguments=_u(r.arguments),
                arguments_raw=r.arguments_raw,
                result=r.result, result_tokens=r.result_tokens,
                executed_at=r.executed_at, status=r.status,
                error=r.error, created_at=r.created_at,
                metadata=_u(r.metadata_),
            ) for r in rows]

    # ── Feedback ─────────────────────────────────────────────────────────
    async def save_feedback(self, fb: RequestFeedback) -> RequestFeedback:
        FR = getattr(self, "FeedbackRow", FeedbackRow)
        async with self._s() as s:
            s.add(FR(
                id=fb.id, request_id=fb.request_id,
                session_id=fb.session_id, user_id=fb.user_id,
                thumbs_up=fb.thumbs_up, rating=fb.rating,
                comment=fb.comment, tags=_j(fb.tags),
                created_at=fb.created_at, metadata_=_j(fb.metadata),
            ))
            await s.commit()
        return fb

    async def list_feedback(
        self,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[RequestFeedback]:
        FR = getattr(self, "FeedbackRow", FeedbackRow)
        async with self._s() as s:
            q = select(FR)
            if request_id: q = q.where(FR.request_id == request_id)
            if user_id:    q = q.where(FR.user_id == user_id)
            if session_id: q = q.where(FR.session_id == session_id)
            q = q.limit(limit).order_by(FR.created_at.desc())
            rows = (await s.execute(q)).scalars().all()
            return [RequestFeedback(
                id=r.id, request_id=r.request_id,
                session_id=r.session_id, user_id=r.user_id,
                thumbs_up=r.thumbs_up, rating=r.rating,
                comment=r.comment, tags=_ul(r.tags),
                created_at=r.created_at, metadata=_u(r.metadata_),
            ) for r in rows]

    async def save_config(self, key: str, value: dict) -> StoreConfig:
        async with self._session_factory() as s:
            import time
            CR = getattr(self, "ConfigRow", ConfigRow)
            existing = await s.get(CR, key)
            now = time.time()
            if existing:
                existing.value = _j(value)
                existing.updated_at = now
            else:
                s.add(CR(
                    key=key,
                    value=_j(value),
                    updated_at=now
                ))
            await s.commit()
            return StoreConfig(key=key, value=value, updated_at=now)

    async def get_config(self, key: str) -> Optional[StoreConfig]:
        async with self._session_factory() as s:
            CR = getattr(self, "ConfigRow", ConfigRow)
            row = await s.get(CR, key)
            if row:
                return StoreConfig(
                    key=row.key,
                    value=_u(row.value),
                    updated_at=row.updated_at
                )
            return None
