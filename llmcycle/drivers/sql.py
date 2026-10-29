"""
SQL Driver
==========
Manages asynchronous connections to SQL databases via SQLAlchemy.
"""
from typing import Optional
from llmcycle.drivers.base import BaseDriver

class SQLDriver(BaseDriver):
    """
    Manages asynchronous connections to an SQL database.
    
    Usage:
        driver = SQLDriver("sqlite+aiosqlite:///:memory:")
        await driver.connect_async()
        engine = driver.get_engine()
    """
    def __init__(self, url: str):
        clean_url = url or ""
        if clean_url.startswith("sqlite://") and not clean_url.startswith("sqlite+aiosqlite://"):
            clean_url = clean_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        elif (clean_url.startswith("postgres://") or clean_url.startswith("postgresql://")) and "+asyncpg" not in clean_url:
            clean_url = "postgresql+asyncpg://" + clean_url.split("://", 1)[1]
        elif clean_url.startswith("mysql://") and "+aiomysql" not in clean_url:
            clean_url = "mysql+aiomysql://" + clean_url.split("://", 1)[1]
        super().__init__(clean_url)
        self._engine = None
        self._sessionmaker = None
        
    @property
    def backend_type(self) -> str:
        from llmcycle.storage.base import StorageBackend
        if self.url.startswith("postgres"):
            return StorageBackend.POSTGRES
        elif self.url.startswith("mysql"):
            return StorageBackend.MYSQL
        elif self.url.startswith("mssql"):
            return StorageBackend.MSSQL
        else:
            return StorageBackend.SQLITE

    def connect(self) -> None:
        """SQLAlchemy uses async initialization in LLMCycle."""
        pass

    async def connect_async(self) -> None:
        """Initialize the asynchronous SQLAlchemy engine if not already created."""
        if self._engine is None:
            try:
                from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
            except ImportError as e:
                raise ImportError(
                    "SQLDriver requires 'sqlalchemy'. Install with: pip install sqlalchemy"
                ) from e
                
            # Connect args logic identical to sql.py
            connect_args = {"check_same_thread": False} if "sqlite" in self.url else {}
            self._engine = create_async_engine(
                self.url,
                echo=False,
                future=True,
                connect_args=connect_args
            )
            self._sessionmaker = async_sessionmaker(
                self._engine, 
                expire_on_commit=False
            )

    def disconnect(self) -> None:
        """Close synchronous connection (no-op)."""
        pass

    async def disconnect_async(self) -> None:
        """Close the asynchronous engine."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None

    def get_engine(self):
        """Returns the active SQLAlchemy engine."""
        if self._engine is None:
            raise RuntimeError(
                "SQL engine is not connected. Call `await driver.connect_async()` first."
            )
        return self._engine
        
    def get_sessionmaker(self):
        """Returns the active SQLAlchemy sessionmaker."""
        if self._sessionmaker is None:
            raise RuntimeError(
                "SQL sessionmaker is not available. Call `await driver.connect_async()` first."
            )
        return self._sessionmaker
