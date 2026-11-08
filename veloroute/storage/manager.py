"""
StorageManager — single entry point for all storage operations.

Priority:  direct args > env vars > defaults

Env vars:
    VELOROUTE_STORAGE_BACKEND=sqlite | postgres | mysql | mssql | mongo | redis
    VELOROUTE_STORAGE_URL=<connection url>

Usage:
    # 1. Via env (zero-code config)
    #    Set VELOROUTE_STORAGE_BACKEND=postgres
    #        VELOROUTE_STORAGE_URL=postgresql+asyncpg://user:pass@host/db
    store = StorageManager()

    # 2. Via enum (explicit, overrides env)
    store = StorageManager(
        backend=StorageBackend.SQLITE,
        url="sqlite+aiosqlite:///./veloroute.db"
    )

    # 3. Attach to client
    client = VeloRoute(storage=store)

    # 4. Use analytics
    stats = await client.storage.analytics.summary(
        from_ts=..., to_ts=..., user_id="u1"
    )
"""
from __future__ import annotations
import os
from typing import Optional, Union

from veloroute.storage.base import BaseStorage, StorageBackend
from veloroute.storage.models import (
    Workplace, Team, User, Session, LLMRequest, HistoryMessage,
)
from veloroute.storage.analytics import Analytics


# ── Default URLs per backend ──────────────────────────────────────────────────
_DEFAULT_URLS = {
    StorageBackend.SQLITE:   "sqlite+aiosqlite:///./veloroute.db",
    StorageBackend.POSTGRES: "postgresql+asyncpg://localhost/veloroute",
    StorageBackend.MYSQL:    "mysql+aiomysql://localhost/veloroute",
    StorageBackend.MSSQL:    "mssql+aioodbc://localhost/veloroute?driver=ODBC+Driver+18+for+SQL+Server",
    StorageBackend.MONGO:    "mongodb://localhost:27017/veloroute",
    StorageBackend.REDIS:    "redis://localhost:6379/0",
}


class StorageManager:
    """
    The one class you interact with — wraps any backend, exposes analytics.

    Args:
        backend:      StorageBackend enum. If None, read from VELOROUTE_STORAGE_BACKEND env.
        url:          Connection URL. If None, read from VELOROUTE_STORAGE_URL env.
        schema:       DB schema (PostgreSQL/MSSQL). If None, read VELOROUTE_STORAGE_SCHEMA.
                      MongoDB: maps to database name. Redis: ignored.
                      Default: None (uses DB default schema).
        table_prefix: Prefix for all table/collection/key names.
                      If None, read VELOROUTE_STORAGE_TABLE_PREFIX. Default: "velo_".
        driver:       Optional Database Driver (SQLDriver, MongoDriver, RedisDriver).
                      If passed, automatically overrides backend and url.
                      If omitted, automatically built based on the selected backend and url.

    Env vars (all overridden by direct args):
        VELOROUTE_STORAGE_BACKEND      = sqlite | postgres | mysql | mssql | mongo | redis
        VELOROUTE_STORAGE_URL          = <connection url>
        VELOROUTE_STORAGE_SCHEMA       = myschema           (optional)
        VELOROUTE_STORAGE_TABLE_PREFIX = velo_              (optional, default: velo_)

    Examples::

        # Zero-config SQLite (default)
        store = StorageManager(StorageBackend.SQLITE)

        # PostgreSQL with custom schema + prefix
        store = StorageManager(
            backend=StorageBackend.POSTGRES,
            url="postgresql+asyncpg://user:pass@host/db",
            schema="analytics",
            table_prefix="llm_",
        )

        # Auto-detect driver from an explicitly declared RedisDriver
        from veloroute.drivers import RedisDriver
        driver = RedisDriver("redis://localhost:6379/0")
        store = StorageManager(driver=driver)

    Installation per backend::

        uv add veloroute[sqlite]    # SQLite — zero config
        uv add veloroute[postgres]  # PostgreSQL
        uv add veloroute[mysql]     # MySQL / MariaDB
        uv add veloroute[mssql]     # SQL Server
        uv add veloroute[mongo]     # MongoDB
        uv add veloroute[redis]     # Redis
        uv add veloroute[storage]   # All backends
    """

    def __init__(
        self,
        backend: Optional[Union[StorageBackend, str]] = None,
        url: Optional[str] = None,
        schema: Optional[str] = None,
        table_prefix: Optional[str] = None,
        driver=None,  # Optional[BaseDriver]
    ):
        # Normalize string backend if provided
        if isinstance(backend, str):
            b_str = backend.lower()
            if b_str == "postgresql":
                b_str = "postgres"
            try:
                backend = StorageBackend(b_str)
            except ValueError:
                raise ValueError(
                    f"Unknown backend='{backend}'. Valid: {[b.value for b in StorageBackend]}"
                )

        # Resolve backend: arg > env > None
        if backend is None:
            env_b = os.environ.get("VELOROUTE_STORAGE_BACKEND", "").lower()
            if env_b:
                if env_b == "postgresql":
                    env_b = "postgres"
                try:
                    backend = StorageBackend(env_b)
                except ValueError:
                    raise ValueError(
                        f"Unknown storage backend '{env_b}'. "
                        f"Valid: {[b.value for b in StorageBackend]}"
                    )

        # Resolve URL: arg > env > default
        if url is None:
            url = os.environ.get("VELOROUTE_STORAGE_URL", "")
        if backend and not url:
            url = _DEFAULT_URLS[backend]

        # Resolve schema: arg > env > None
        if schema is None:
            schema = os.environ.get("VELOROUTE_STORAGE_SCHEMA") or None

        # Resolve table_prefix: arg > env > default "velo_"
        if table_prefix is None:
            table_prefix = os.environ.get("VELOROUTE_STORAGE_TABLE_PREFIX", "velo_")

        # Auto-infer backend from URL if URL is provided but backend is not
        if not backend and url:
            if url.startswith("redis"):
                backend = StorageBackend.REDIS
            elif url.startswith("mongodb"):
                backend = StorageBackend.MONGO
            elif url.startswith("postgres"):
                backend = StorageBackend.POSTGRES
            elif url.startswith("mysql"):
                backend = StorageBackend.MYSQL
            elif url.startswith("mssql"):
                backend = StorageBackend.MSSQL
            elif url.startswith("sqlite"):
                backend = StorageBackend.SQLITE

        # Auto-extract backend and url from driver if provided
        if driver is not None:
            backend = driver.backend_type
            url = driver.url

        self.backend_type = backend
        self.url = url
        self.schema = schema
        self.table_prefix = table_prefix
        
        # Auto-detect driver if not provided but backend and url exist
        if driver is None and self.backend_type and self.url:
            if self.backend_type == StorageBackend.REDIS:
                from veloroute.drivers.redis import RedisDriver
                driver = RedisDriver(self.url)
            elif self.backend_type == StorageBackend.MONGO:
                from veloroute.drivers.mongo import MongoDriver
                driver = MongoDriver(self.url)
            elif self.backend_type in (StorageBackend.SQLITE, StorageBackend.POSTGRES, StorageBackend.MYSQL, StorageBackend.MSSQL):
                from veloroute.drivers.sql import SQLDriver
                driver = SQLDriver(self.url)
                
        self.driver = driver
            
        self._backend: Optional[BaseStorage] = None
        self.analytics: Optional[Analytics] = None

    def _build_backend(self) -> BaseStorage:
        b = self.backend_type
        if b in (StorageBackend.SQLITE, StorageBackend.POSTGRES,
                 StorageBackend.MYSQL, StorageBackend.MSSQL):
            from veloroute.storage.backends.sql import SQLStorage
            return SQLStorage(self.url, schema=self.schema, table_prefix=self.table_prefix, driver=self.driver)
        elif b == StorageBackend.MONGO:
            from veloroute.storage.backends.mongo import MongoStorage
            db_name = self.schema or "veloroute"
            return MongoStorage(self.url, db_name=db_name, collection_prefix=self.table_prefix, driver=self.driver)
        elif b == StorageBackend.REDIS:
            from veloroute.storage.backends.redis_ import RedisStorage
            return RedisStorage(self.url, key_prefix=self.table_prefix, driver=self.driver)
        else:
            raise ValueError(
                f"No backend configured. Set VELOROUTE_STORAGE_BACKEND or pass backend=StorageBackend.SQLITE"
            )

    async def connect(self):
        """Connect to the chosen storage. Call once at startup."""
        self._backend = self._build_backend()
        await self._backend.connect()
        self.analytics = Analytics(self._backend)

    async def disconnect(self):
        """Disconnect gracefully. Call at shutdown."""
        if self._backend:
            await self._backend.disconnect()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *_):
        await self.disconnect()

    async def ping(self) -> dict:
        """
        Test the storage connection. Safe to call before or after connect().

        Returns:
            {"ok": True,  "backend": "sqlite", "latency_ms": 0.8}
            {"ok": False, "backend": "redis",  "error": "Connection refused"}

        Usage:
            store = StorageManager(StorageBackend.SQLITE)
            await store.connect()
            result = await store.ping()
            # {"ok": True, "backend": "sqlite", "latency_ms": 0.9}
        """
        if self._backend is None:
            # Try a quick connect + ping + disconnect
            try:
                backend = self._build_backend()
                await backend.connect()
                result = await backend.ping()
                await backend.disconnect()
                return result
            except Exception as e:
                return {
                    "ok": False,
                    "backend": self.backend_type.value if self.backend_type else "unknown",
                    "url": self.url,
                    "error": str(e),
                }
        return await self._backend.ping()

    # ── Delegate all CRUD to the active backend ───────────────────────────────

    def __getattr__(self, name):
        if self._backend and hasattr(self._backend, name):
            return getattr(self._backend, name)
        raise AttributeError(
            f"StorageManager: attribute '{name}' not found. "
            f"Did you call 'await storage.connect()' first?"
        )
