"""
MongoDB async backend — uses motor.
pip install motor
"""
from __future__ import annotations
from typing import Optional, List
from llmcycle.storage.base import BaseStorage
from llmcycle.storage.models import (
    Workplace, Team, User, Session, LLMRequest, HistoryMessage, StoreConfig
)


class MongoStorage(BaseStorage):
    """
    MongoDB backend via motor (async).
    URL: mongodb://user:pass@host:27017/dbname
    """
    def __init__(self, url: str, db_name: str = "llmcycle"):
        self.url = url
        self.db_name = db_name
        self._client = None
        self._db = None

    async def connect(self):
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError:
            raise ImportError("MongoDB backend requires 'motor'. Install: pip install motor")
        self._client = AsyncIOMotorClient(self.url)
        self._db = self._client[self.db_name]
        # Indexes
        await self._db.users.create_index("username", unique=True)
        await self._db.sessions.create_index([("user_id", 1), ("started_at", -1)])
        await self._db.llm_requests.create_index([("session_id", 1), ("created_at", -1)])
        await self._db.llm_requests.create_index([("user_id", 1), ("created_at", -1)])
        await self._db.llm_requests.create_index("created_at")
        await self._db.history.create_index([("session_id", 1), ("created_at", 1)])

    async def disconnect(self):
        if self._client:
            self._client.close()

    async def ping(self) -> dict:
        """Verify MongoDB connection via server ping command."""
        import time
        try:
            t0 = time.monotonic()
            await self._client.admin.command("ping")
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            return {"ok": True, "backend": "mongo", "url": self.url, "latency_ms": latency_ms}
        except Exception as e:
            return {"ok": False, "backend": "mongo", "url": self.url, "error": str(e)}

    def _col(self, name): return self._db[name]

    # ── Workplaces ──────────────────────────────────────────────────
    async def create_workplace(self, wp: Workplace) -> Workplace:
        await self._col("workplaces").insert_one(wp.model_dump())
        return wp

    async def get_workplace(self, id: str) -> Optional[Workplace]:
        doc = await self._col("workplaces").find_one({"id": id})
        return Workplace(**doc) if doc else None

    async def list_workplaces(self) -> List[Workplace]:
        docs = await self._col("workplaces").find().to_list(None)
        return [Workplace(**d) for d in docs]

    # ── Teams ────────────────────────────────────────────────────────
    async def create_team(self, team: Team) -> Team:
        await self._col("teams").insert_one(team.model_dump())
        return team

    async def get_team(self, id: str) -> Optional[Team]:
        doc = await self._col("teams").find_one({"id": id})
        return Team(**doc) if doc else None

    async def list_teams(self, workplace_id: Optional[str] = None) -> List[Team]:
        q = {"workplace_id": workplace_id} if workplace_id else {}
        docs = await self._col("teams").find(q).to_list(None)
        return [Team(**d) for d in docs]

    # ── Users ────────────────────────────────────────────────────────
    async def create_user(self, user: User) -> User:
        await self._col("users").insert_one(user.model_dump())
        return user

    async def get_user(self, id: str) -> Optional[User]:
        doc = await self._col("users").find_one({"id": id})
        return User(**doc) if doc else None

    async def get_user_by_username(self, username: str) -> Optional[User]:
        doc = await self._col("users").find_one({"username": username})
        return User(**doc) if doc else None

    async def list_users(self, team_id: Optional[str] = None) -> List[User]:
        q = {"team_id": team_id} if team_id else {}
        docs = await self._col("users").find(q).to_list(None)
        return [User(**d) for d in docs]

    async def update_user(self, user: User) -> User:
        await self._col("users").replace_one({"id": user.id}, user.model_dump())
        return user

    async def delete_user(self, id: str) -> None:
        await self._col("users").delete_one({"id": id})

    # ── Sessions ─────────────────────────────────────────────────────
    async def create_session(self, session: Session) -> Session:
        await self._col("sessions").insert_one(session.model_dump())
        return session

    async def get_session(self, id: str) -> Optional[Session]:
        doc = await self._col("sessions").find_one({"id": id})
        return Session(**doc) if doc else None

    async def update_session(self, session: Session) -> Session:
        await self._col("sessions").replace_one({"id": session.id}, session.model_dump())
        return session

    async def list_sessions(self, user_id=None, team_id=None, limit=50) -> List[Session]:
        q = {}
        if user_id: q["user_id"] = user_id
        if team_id: q["team_id"] = team_id
        docs = await self._col("sessions").find(q).sort("started_at", -1).limit(limit).to_list(None)
        return [Session(**d) for d in docs]

    # ── Requests ─────────────────────────────────────────────────────
    async def save_request(self, req: LLMRequest) -> LLMRequest:
        await self._col("llm_requests").insert_one(req.model_dump())
        return req

    async def get_request(self, id: str) -> Optional[LLMRequest]:
        doc = await self._col("llm_requests").find_one({"id": id})
        return LLMRequest(**doc) if doc else None

    async def list_requests(self, session_id=None, user_id=None, limit=100) -> List[LLMRequest]:
        q = {}
        if session_id: q["session_id"] = session_id
        if user_id: q["user_id"] = user_id
        docs = await self._col("llm_requests").find(q).sort("created_at", -1).limit(limit).to_list(None)
        return [LLMRequest(**d) for d in docs]

    # ── History ──────────────────────────────────────────────────────
    async def append_history(self, msg: HistoryMessage) -> HistoryMessage:
        await self._col("history").insert_one(msg.model_dump())
        return msg

    async def get_history(self, session_id: str, limit=100) -> List[HistoryMessage]:
        docs = await self._col("history").find({"session_id": session_id}).sort("created_at", 1).limit(limit).to_list(None)
        return [HistoryMessage(**d) for d in docs]

    async def clear_history(self, session_id: str) -> None:
        await self._col("history").delete_many({"session_id": session_id})

    # ── Analytics (MongoDB native aggregation) ───────────────────────
    async def aggregate_requests(self, match: dict) -> dict:
        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": None,
                "total": {"$sum": 1},
                "total_prompt_tokens": {"$sum": "$prompt_tokens"},
                "total_completion_tokens": {"$sum": "$completion_tokens"},
                "avg_latency_ms": {"$avg": "$latency_ms"},
                "errors": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
                "fallbacks": {"$sum": {"$cond": ["$fallback_used", 1, 0]}},
            }}
        ]
        docs = await self._col("llm_requests").aggregate(pipeline).to_list(None)
        return docs[0] if docs else {}

    async def requests_by_provider(self, match: dict) -> list:
        pipeline = [
            {"$match": match},
            {"$group": {"_id": "$provider", "count": {"$sum": 1}, "tokens": {"$sum": {"$add": ["$prompt_tokens", "$completion_tokens"]}}, "avg_latency": {"$avg": "$latency_ms"}}},
            {"$sort": {"count": -1}}
        ]
        return await self._col("llm_requests").aggregate(pipeline).to_list(None)

    async def requests_by_model(self, match: dict) -> list:
        pipeline = [
            {"$match": match},
            {"$group": {"_id": "$model", "count": {"$sum": 1}, "tokens": {"$sum": {"$add": ["$prompt_tokens", "$completion_tokens"]}}}},
            {"$sort": {"count": -1}}
        ]
        return await self._col("llm_requests").aggregate(pipeline).to_list(None)

    # ── Purge by date range ───────────────────────────────────────────
    async def purge_by_range(
        self,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        entities: Optional[List[str]] = None,
    ) -> dict:
        """Delete MongoDB documents within a timestamp range."""
        targets = set(entities or ["requests"])
        if "all" in targets:
            targets = {"requests", "history", "sessions"}

        def _q(field: str) -> dict:
            q = {}
            if from_ts is not None or to_ts is not None:
                q[field] = {}
                if from_ts is not None: q[field]["$gte"] = from_ts
                if to_ts   is not None: q[field]["$lte"] = to_ts
            return q

        deleted = {}
        if "requests" in targets:
            r = await self._col("llm_requests").delete_many(_q("created_at"))
            deleted["requests"] = r.deleted_count
        if "history" in targets:
            r = await self._col("history").delete_many(_q("created_at"))
            deleted["history"] = r.deleted_count
        if "sessions" in targets:
            r = await self._col("sessions").delete_many(_q("started_at"))
            deleted["sessions"] = r.deleted_count

        return {"deleted": deleted}

    # ── Configuration ────────────────────────────────────────────────
    async def save_config(self, key: str, value: dict) -> StoreConfig:
        config = StoreConfig(key=key, value=value)
        await self._col("configs").replace_one(
            {"key": key},
            config.model_dump(),
            upsert=True
        )
        return config

    async def get_config(self, key: str) -> Optional[StoreConfig]:
        doc = await self._col("configs").find_one({"key": key})
        return StoreConfig(**doc) if doc else None
