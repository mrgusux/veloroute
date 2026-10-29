"""
Redis Driver
============
Manages synchronous and asynchronous connections to Redis.
"""
from typing import Optional
from llmcycle.drivers.base import BaseDriver

class RedisDriver(BaseDriver):
    """
    Manages both synchronous and asynchronous connections to a Redis server.
    
    Usage:
        driver = RedisDriver("redis://localhost:6379/0")
        
        # Sync (for ConfigLoader)
        client = driver.get_sync_client()
        
        # Async (for StorageManager)
        await driver.connect_async()
        aclient = driver.get_async_client()
    """
    def __init__(self, url: str):
        super().__init__(url)
        self._sync_client = None
        self._async_client = None
        
    @property
    def backend_type(self) -> str:
        from llmcycle.storage.base import StorageBackend
        return StorageBackend.REDIS

    def connect(self) -> None:
        """Initialize the synchronous Redis client if not already created."""
        if self._sync_client is None:
            try:
                import redis
            except ImportError as e:
                raise ImportError(
                    "RedisDriver requires 'redis'. Install with: pip install redis"
                ) from e
            self._sync_client = redis.Redis.from_url(self.url, decode_responses=True)

    async def connect_async(self) -> None:
        """Initialize the asynchronous Redis client if not already created."""
        if self._async_client is None:
            try:
                from redis.asyncio import from_url
            except ImportError as e:
                raise ImportError(
                    "RedisDriver requires 'redis'. Install with: pip install redis[asyncio]"
                ) from e
            self._async_client = await from_url(self.url, decode_responses=True)

    def disconnect(self) -> None:
        """Close the synchronous client."""
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None

    async def disconnect_async(self) -> None:
        """Close the asynchronous client."""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None

    def get_sync_client(self):
        """Returns the active synchronous redis client, connecting if needed."""
        if self._sync_client is None:
            self.connect()
        return self._sync_client

    def get_async_client(self):
        """
        Returns the active asynchronous redis client.
        Note: You must call `await driver.connect_async()` before getting the async client.
        """
        if self._async_client is None:
            raise RuntimeError(
                "Async client is not connected. Call `await driver.connect_async()` first."
            )
        return self._async_client
