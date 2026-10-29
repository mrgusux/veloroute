"""
LLMCycle Storage Layer
======================
Pick ONE backend via enum. Configure via env or direct args.

Quick start:
    from llmcycle.storage import StorageBackend, StorageManager

    # Via env:
    #   LLMCYCLE_STORAGE_BACKEND=sqlite
    #   LLMCYCLE_STORAGE_URL=sqlite+aiosqlite:///./llmcycle.db
    store = StorageManager()
    await store.connect()

    # Or direct:
    store = StorageManager(StorageBackend.POSTGRES, "postgresql+asyncpg://user:pass@host/db")
    await store.connect()

    # Test connection:
    print(await store.ping())
    # {"ok": True, "backend": "postgres", "latency_ms": 1.4}

    # Analytics:
    stats = await store.analytics.summary(from_ts=yesterday, user_id="u-1")
    by_prov = await store.analytics.by_provider()
    ts = await store.analytics.timeseries(bucket="hour")

Install per backend:
    uv add llmcycle[sqlite]    # SQLite
    uv add llmcycle[postgres]  # PostgreSQL
    uv add llmcycle[mysql]     # MySQL / MariaDB
    uv add llmcycle[mssql]     # SQL Server
    uv add llmcycle[mongo]     # MongoDB
    uv add llmcycle[redis]     # Redis
    uv add llmcycle[storage]   # All backends
"""
from llmcycle.storage.base import StorageBackend, BaseStorage
from llmcycle.storage.manager import StorageManager
from llmcycle.storage.models import (
    Workplace, Team, User, Session, LLMRequest, HistoryMessage
)
from llmcycle.storage.analytics import Analytics

__all__ = [
    # Enums & base
    "StorageBackend",
    "BaseStorage",
    # Main interface
    "StorageManager",
    # Analytics
    "Analytics",
    # Models
    "Workplace",
    "Team",
    "User",
    "Session",
    "LLMRequest",
    "HistoryMessage",
]
