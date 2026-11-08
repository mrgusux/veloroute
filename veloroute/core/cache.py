"""
Pluggable Prompt Caching Engine
===============================
Supports:
  - InMemoryCache (LRU local cache)
  - RedisCache (shared cache)
  - SQLCache (SQLite/PostgreSQL database cache)
"""
from __future__ import annotations
from abc import ABC, abstractmethod
import time
from collections import OrderedDict
from typing import Optional, Dict, Any

from veloroute.schema import CompletionResponse

class BaseCache(ABC):
    """Abstract base class for all cache backends."""

    @abstractmethod
    async def get(self, key: str) -> Optional[CompletionResponse]:
        """Retrieve a cached response by key."""
        pass

    @abstractmethod
    async def set(self, key: str, value: CompletionResponse, ttl: float) -> None:
        """Store a response in the cache with a TTL (seconds)."""
        pass

    @abstractmethod
    async def clear(self) -> int:
        """Clear all cached responses and return count of items cleared."""
        pass

    @abstractmethod
    async def stats(self) -> Dict[str, Any]:
        """Return statistics on the cache state."""
        pass


class InMemoryCache(BaseCache):
    """Thread-safe-compatible local memory cache with LRU eviction and expiration."""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._cache: OrderedDict[str, tuple[CompletionResponse, float]] = OrderedDict()

    async def get(self, key: str) -> Optional[CompletionResponse]:
        if key not in self._cache:
            return None
        value, expires_at = self._cache[key]
        if time.time() > expires_at:
            del self._cache[key]
            return None
        # Move to end to track LRU
        self._cache.move_to_end(key)
        return value

    async def set(self, key: str, value: CompletionResponse, ttl: float) -> None:
        now = time.time()
        # Evict expired keys
        expired_keys = [k for k, (_, exp) in self._cache.items() if now > exp]
        for k in expired_keys:
            del self._cache[k]

        # Evict LRU key if full
        if len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)

        self._cache[key] = (value, now + ttl)

    async def clear(self) -> int:
        count = len(self._cache)
        self._cache.clear()
        return count

    async def stats(self) -> Dict[str, Any]:
        now = time.time()
        active = sum(1 for _, exp in self._cache.values() if now < exp)
        return {
            "total": len(self._cache),
            "active": active,
            "expired": len(self._cache) - active,
        }


class RedisCache(BaseCache):
    """Redis-backed prompt cache for distributed environments."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0", prefix: str = "velo:cache:"):
        self.redis_url = redis_url
        self.prefix = prefix
        self._client = None

    def _get_client(self):
        if self._client is None:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._client

    async def get(self, key: str) -> Optional[CompletionResponse]:
        client = self._get_client()
        raw = await client.get(f"{self.prefix}{key}")
        if not raw:
            return None
        try:
            return CompletionResponse.model_validate_json(raw)
        except Exception:
            return None

    async def set(self, key: str, value: CompletionResponse, ttl: float) -> None:
        client = self._get_client()
        raw = value.model_dump_json()
        await client.set(f"{self.prefix}{key}", raw, ex=int(ttl))

    async def clear(self) -> int:
        client = self._get_client()
        keys = await client.keys(f"{self.prefix}*")
        if keys:
            await client.delete(*keys)
        return len(keys)

    async def stats(self) -> Dict[str, Any]:
        client = self._get_client()
        keys = await client.keys(f"{self.prefix}*")
        return {
            "total": len(keys),
            "active": len(keys),
            "expired": 0,
        }


# Dynamic ORM Table creation for SQLCache to ensure no metadata collision
try:
    from sqlalchemy.orm import declarative_base, Mapped, mapped_column
    from sqlalchemy import Text, Float, select, delete
    Base = declarative_base()

    class SQLCacheRow(Base):
        __tablename__ = "velo_prompt_cache"
        key: Mapped[str] = mapped_column(Text, primary_key=True)
        value: Mapped[str] = mapped_column(Text)
        expires_at: Mapped[float] = mapped_column(Float)
    _HAS_SQLALCHEMY = True
except ImportError:
    _HAS_SQLALCHEMY = False
    Base = object
    SQLCacheRow = None
    select = None
    delete = None


class SQLCache(BaseCache):
    """SQL database cache using SQLAlchemy async ORM."""

    def __init__(self, url: str = "sqlite+aiosqlite:///veloroute_cache.db"):
        clean_url = url or ""
        if clean_url.startswith("sqlite://") and not clean_url.startswith("sqlite+aiosqlite://"):
            clean_url = clean_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        elif (clean_url.startswith("postgres://") or clean_url.startswith("postgresql://")) and "+asyncpg" not in clean_url:
            clean_url = "postgresql+asyncpg://" + clean_url.split("://", 1)[1]
        elif clean_url.startswith("mysql://") and "+aiomysql" not in clean_url:
            clean_url = "mysql+aiomysql://" + clean_url.split("://", 1)[1]
        self.url = clean_url
        self._engine = None
        self._session_factory = None
        self._initialized = False

    async def _init_db(self):
        if not _HAS_SQLALCHEMY:
            raise ImportError("SQLCache requires 'sqlalchemy'. Install with: pip install sqlalchemy aiosqlite")
        if not self._initialized:
            from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
            self._engine = create_async_engine(self.url, echo=False)
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
            self._initialized = True

    async def get(self, key: str) -> Optional[CompletionResponse]:
        await self._init_db()
        async with self._session_factory() as session:
            row = await session.get(SQLCacheRow, key)
            if not row:
                return None
            if time.time() > row.expires_at:
                await session.delete(row)
                await session.commit()
                return None
            try:
                return CompletionResponse.model_validate_json(row.value)
            except Exception:
                return None

    async def set(self, key: str, value: CompletionResponse, ttl: float) -> None:
        await self._init_db()
        now = time.time()
        async with self._session_factory() as session:
            row = await session.get(SQLCacheRow, key)
            if row:
                row.value = value.model_dump_json()
                row.expires_at = now + ttl
            else:
                session.add(SQLCacheRow(
                    key=key,
                    value=value.model_dump_json(),
                    expires_at=now + ttl
                ))
            await session.commit()

    async def clear(self) -> int:
        await self._init_db()
        async with self._session_factory() as session:
            rows = (await session.execute(select(SQLCacheRow))).scalars().all()
            await session.execute(delete(SQLCacheRow))
            await session.commit()
            return len(rows)

    async def stats(self) -> Dict[str, Any]:
        await self._init_db()
        now = time.time()
        async with self._session_factory() as session:
            rows = (await session.execute(select(SQLCacheRow))).scalars().all()
            active = sum(1 for r in rows if r.expires_at > now)
            return {
                "total": len(rows),
                "active": active,
                "expired": len(rows) - active,
            }
