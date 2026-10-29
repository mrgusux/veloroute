"""
Redis async backend — sessions, requests, history stored as JSON hashes/lists.
Best for: high-speed session caching, short-lived request logs.
pip install redis[asyncio]
"""
from __future__ import annotations
import json, time
from typing import Optional, List
from llmcycle.storage.base import BaseStorage
from llmcycle.storage.models import (
    Workplace, Team, User, Session, LLMRequest, HistoryMessage, StoreConfig
)

_PREFIX = "llmc:"

class RedisStorage(BaseStorage):
    """
    Redis backend via redis-py asyncio.
    URL: redis://localhost:6379/0  or  rediss://... (TLS)

    Key scheme:
      llmc:workplace:{id}      → JSON hash
      llmc:workplaces          → list of IDs
      llmc:team:{id}           → JSON hash
      llmc:teams               → list of IDs
      llmc:user:{id}           → JSON hash
      llmc:user:name:{username}→ id lookup
      llmc:users               → list of IDs
      llmc:session:{id}        → JSON hash
      llmc:sessions:user:{uid} → sorted set by timestamp
      llmc:req:{id}            → JSON hash
      llmc:reqs:session:{sid}  → sorted set by timestamp
      llmc:reqs:user:{uid}     → sorted set by timestamp
      llmc:history:{sid}       → list (RPUSH)
    """

    def __init__(self, url: str, ttl_sessions: int = 86400, ttl_requests: int = 604800, key_prefix: str = "llmc_", driver=None):
        self.url = url
        self.ttl_sessions = ttl_sessions   # 1 day default
        self.ttl_requests = ttl_requests   # 7 days default
        self._prefix = key_prefix
        self.driver = driver
        self._r = None

    async def connect(self):
        if self.driver:
            await self.driver.connect_async()
            self._r = self.driver.get_async_client()
        else:
            try:
                from redis.asyncio import from_url
            except ImportError:
                raise ImportError("Redis backend requires 'redis'. Install: pip install redis[asyncio]")
            self._r = await from_url(self.url, decode_responses=True)

    async def disconnect(self):
        if self._r:
            await self._r.aclose()

    async def ping(self) -> dict:
        """Verify Redis connection using native PING command."""
        import time
        try:
            t0 = time.monotonic()
            result = await self._r.ping()  # returns True
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            return {"ok": bool(result), "backend": "redis", "url": self.url, "latency_ms": latency_ms}
        except Exception as e:
            return {"ok": False, "backend": "redis", "url": self.url, "error": str(e)}

    def _k(self, *parts): return self._prefix + ":".join(parts)

    async def _set(self, key: str, obj: dict, ttl: int = 0):
        await self._r.set(key, json.dumps(obj))
        if ttl: await self._r.expire(key, ttl)

    async def _get(self, key: str) -> Optional[dict]:
        v = await self._r.get(key)
        return json.loads(v) if v else None

    # ── Workplaces ──────────────────────────────────────────────────
    async def create_workplace(self, wp: Workplace) -> Workplace:
        await self._set(self._k("workplace", wp.id), wp.model_dump())
        await self._r.sadd(self._k("workplaces"), wp.id)
        return wp

    async def get_workplace(self, id: str) -> Optional[Workplace]:
        d = await self._get(self._k("workplace", id))
        return Workplace(**d) if d else None

    async def list_workplaces(self) -> List[Workplace]:
        ids = await self._r.smembers(self._k("workplaces"))
        out = []
        for id in ids:
            d = await self._get(self._k("workplace", id))
            if d: out.append(Workplace(**d))
        return out

    # ── Teams ────────────────────────────────────────────────────────
    async def create_team(self, team: Team) -> Team:
        await self._set(self._k("team", team.id), team.model_dump())
        await self._r.sadd(self._k("teams"), team.id)
        await self._r.sadd(self._k("teams:wp", team.workplace_id), team.id)
        return team

    async def get_team(self, id: str) -> Optional[Team]:
        d = await self._get(self._k("team", id))
        return Team(**d) if d else None

    async def list_teams(self, workplace_id: Optional[str] = None) -> List[Team]:
        key = self._k("teams:wp", workplace_id) if workplace_id else self._k("teams")
        ids = await self._r.smembers(key)
        out = []
        for id in ids:
            d = await self._get(self._k("team", id))
            if d: out.append(Team(**d))
        return out

    # ── Users ────────────────────────────────────────────────────────
    async def create_user(self, user: User) -> User:
        await self._set(self._k("user", user.id), user.model_dump())
        await self._r.set(self._k("user:name", user.username), user.id)
        await self._r.sadd(self._k("users"), user.id)
        if user.team_id:
            await self._r.sadd(self._k("users:team", user.team_id), user.id)
        return user

    async def get_user(self, id: str) -> Optional[User]:
        d = await self._get(self._k("user", id))
        return User(**d) if d else None

    async def get_user_by_username(self, username: str) -> Optional[User]:
        uid = await self._r.get(self._k("user:name", username))
        return await self.get_user(uid) if uid else None

    async def list_users(self, team_id: Optional[str] = None) -> List[User]:
        key = self._k("users:team", team_id) if team_id else self._k("users")
        ids = await self._r.smembers(key)
        out = []
        for id in ids:
            d = await self._get(self._k("user", id))
            if d: out.append(User(**d))
        return out

    async def update_user(self, user: User) -> User:
        await self._set(self._k("user", user.id), user.model_dump())
        return user

    async def delete_user(self, id: str) -> None:
        d = await self._get(self._k("user", id))
        if d:
            await self._r.delete(self._k("user:name", d["username"]))
            await self._r.delete(self._k("user", id))
            await self._r.srem(self._k("users"), id)

    # ── Sessions ─────────────────────────────────────────────────────
    async def create_session(self, session: Session) -> Session:
        await self._set(self._k("session", session.id), session.model_dump(), self.ttl_sessions)
        if session.user_id:
            await self._r.zadd(self._k("sessions:user", session.user_id), {session.id: session.started_at})
        if session.team_id:
            await self._r.zadd(self._k("sessions:team", session.team_id), {session.id: session.started_at})
        return session

    async def get_session(self, id: str) -> Optional[Session]:
        d = await self._get(self._k("session", id))
        return Session(**d) if d else None

    async def update_session(self, session: Session) -> Session:
        await self._set(self._k("session", session.id), session.model_dump(), self.ttl_sessions)
        return session

    async def list_sessions(self, user_id=None, team_id=None, limit=50) -> List[Session]:
        if user_id:
            ids = await self._r.zrevrange(self._k("sessions:user", user_id), 0, limit - 1)
        elif team_id:
            ids = await self._r.zrevrange(self._k("sessions:team", team_id), 0, limit - 1)
        else:
            return []
        out = []
        for id in ids:
            d = await self._get(self._k("session", id))
            if d: out.append(Session(**d))
        return out

    # ── Requests ─────────────────────────────────────────────────────
    async def save_request(self, req: LLMRequest) -> LLMRequest:
        await self._set(self._k("req", req.id), req.model_dump(), self.ttl_requests)
        if req.session_id:
            await self._r.zadd(self._k("reqs:session", req.session_id), {req.id: req.created_at})
        if req.user_id:
            await self._r.zadd(self._k("reqs:user", req.user_id), {req.id: req.created_at})
        await self._r.zadd(self._k("reqs:all"), {req.id: req.created_at})
        return req

    async def get_request(self, id: str) -> Optional[LLMRequest]:
        d = await self._get(self._k("req", id))
        return LLMRequest(**d) if d else None

    async def list_requests(self, session_id=None, user_id=None, limit=100) -> List[LLMRequest]:
        if session_id:
            ids = await self._r.zrevrange(self._k("reqs:session", session_id), 0, limit - 1)
        elif user_id:
            ids = await self._r.zrevrange(self._k("reqs:user", user_id), 0, limit - 1)
        else:
            ids = await self._r.zrevrange(self._k("reqs:all"), 0, limit - 1)
        out = []
        for id in ids:
            d = await self._get(self._k("req", id))
            if d: out.append(LLMRequest(**d))
        return out

    # ── History ──────────────────────────────────────────────────────
    async def add_message(self, msg: HistoryMessage) -> HistoryMessage:
        key = self._k("history", msg.session_id)
        await self._r.rpush(key, json.dumps(msg.model_dump()))
        await self._r.expire(key, self.ttl_sessions)
        return msg

    async def get_history(self, session_id: str, limit=100) -> List[HistoryMessage]:
        raw = await self._r.lrange(self._k("history", session_id), -limit, -1)
        return [HistoryMessage(**json.loads(r)) for r in raw]

    async def clear_history(self, session_id: str) -> None:
        await self._r.delete(self._k("history", session_id))

    # ── Purge by date range ───────────────────────────────────────────
    async def purge_by_range(
        self,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        entities: Optional[List[str]] = None,
    ) -> dict:
        """
        Delete Redis keys within a timestamp range.

        Uses ZRANGEBYSCORE on sorted-set indexes to find IDs in range,
        then deletes each data key and removes from indexes.
        """
        targets = set(entities or ["requests"])
        if "all" in targets:
            targets = {"requests", "history", "sessions"}

        lo = from_ts if from_ts is not None else "-inf"
        hi = to_ts   if to_ts   is not None else "+inf"
        deleted = {}

        if "requests" in targets:
            # Global sorted set has ALL request IDs scored by created_at
            ids = await self._r.zrangebyscore(self._k("reqs:all"), lo, hi)
            count = 0
            for rid in ids:
                await self._r.delete(self._k("req", rid))
                await self._r.zrem(self._k("reqs:all"), rid)
                count += 1
            deleted["requests"] = count

        if "sessions" in targets:
            # Scan all user session sorted sets
            count = 0
            pattern = self._k("sessions:user:*")
            async for key in self._r.scan_iter(match=pattern):
                ids = await self._r.zrangebyscore(key, lo, hi)
                for sid in ids:
                    await self._r.delete(self._k("session", sid))
                    await self._r.zrem(key, sid)
                    count += 1
            deleted["sessions"] = count

        if "history" in targets:
            # History lists don't have timestamps — purge all if no range,
            # or scan and filter each message if range specified.
            count = 0
            pattern = self._k("history:*")
            async for key in self._r.scan_iter(match=pattern):
                if from_ts is None and to_ts is None:
                    count += await self._r.llen(key)
                    await self._r.delete(key)
                else:
                    # Filter in-process: keep messages outside range
                    raw = await self._r.lrange(key, 0, -1)
                    keep, remove = [], 0
                    for item in raw:
                        try:
                            msg = json.loads(item)
                            ts = msg.get("created_at", 0)
                            in_range = (from_ts is None or ts >= from_ts) and \
                                       (to_ts   is None or ts <= to_ts)
                            if in_range:
                                remove += 1
                            else:
                                keep.append(item)
                        except Exception:
                            keep.append(item)
                    if remove:
                        await self._r.delete(key)
                        if keep:
                            await self._r.rpush(key, *keep)
                        count += remove
            deleted["history"] = count

        return {"deleted": deleted}

    # ── Configuration ────────────────────────────────────────────────

    async def save_config(self, key: str, value: dict) -> StoreConfig:
        config = StoreConfig(key=key, value=value)
        await self._set(self._k("config", key), config.model_dump())
        return config

    async def get_config(self, key: str) -> Optional[StoreConfig]:
        d = await self._get(self._k("config", key))
        return StoreConfig(**d) if d else None
