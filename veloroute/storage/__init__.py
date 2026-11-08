"""
VeloRoute Storage Layer
======================
Pick ONE backend via enum. Configure via env or direct args.

Quick start:
    from veloroute.storage import StorageBackend, StorageManager

    # Via env:
    #   VELOROUTE_STORAGE_BACKEND=sqlite
    #   VELOROUTE_STORAGE_URL=sqlite+aiosqlite:///./veloroute.db
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
    uv add veloroute[sqlite]    # SQLite
    uv add veloroute[postgres]  # PostgreSQL
    uv add veloroute[mysql]     # MySQL / MariaDB
    uv add veloroute[mssql]     # SQL Server
    uv add veloroute[mongo]     # MongoDB
    uv add veloroute[redis]     # Redis
    uv add veloroute[storage]   # All backends
"""
from veloroute.storage.base import StorageBackend, BaseStorage
from veloroute.storage.manager import StorageManager
from veloroute.storage.models import (
    Workplace, Team, User, Session, LLMRequest, HistoryMessage
)
from veloroute.storage.analytics import Analytics

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
