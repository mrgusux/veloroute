"""
MongoDB Driver
==============
Manages asynchronous connections to MongoDB.
"""
from typing import Optional
from llmcycle.drivers.base import BaseDriver

class MongoDriver(BaseDriver):
    """
    Manages asynchronous connections to a MongoDB database.
    
    Usage:
        driver = MongoDriver("mongodb://localhost:27017")
        await driver.connect_async()
        db = driver.get_database("llmcycle")
    """
    def __init__(self, url: str):
        super().__init__(url)
        self._client = None
        
    @property
    def backend_type(self) -> str:
        from llmcycle.storage.base import StorageBackend
        return StorageBackend.MONGO

    def connect(self) -> None:
        """MongoDB motor driver uses async initialization."""
        pass

    async def connect_async(self) -> None:
        """Initialize the asynchronous MongoDB client if not already created."""
        if self._client is None:
            try:
                from motor.motor_asyncio import AsyncIOMotorClient
            except ImportError as e:
                raise ImportError(
                    "MongoDriver requires 'motor'. Install with: pip install motor"
                ) from e
            self._client = AsyncIOMotorClient(self.url)

    def disconnect(self) -> None:
        """Close synchronous connection (no-op)."""
        pass

    async def disconnect_async(self) -> None:
        """Close the asynchronous client."""
        if self._client:
            self._client.close()
            self._client = None

    def get_database(self, db_name: str):
        """Returns the requested motor database object."""
        if self._client is None:
            raise RuntimeError(
                "Mongo client is not connected. Call `await driver.connect_async()` first."
            )
        return self._client[db_name]
