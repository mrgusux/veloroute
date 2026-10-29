"""
LLMCycle Drivers
================

Drivers manage database connections, allowing you to declare connections once
and share them across multiple LLMCycle components (Storage, Config, Cache).
"""
from abc import ABC, abstractmethod

from llmcycle.storage.base import StorageBackend

class BaseDriver(ABC):
    """Abstract base class for all drivers."""
    
    def __init__(self, url: str):
        self.url = url
        
    @property
    @abstractmethod
    def backend_type(self) -> StorageBackend:
        """The storage backend this driver supports."""
        pass
    
    @abstractmethod
    def connect(self) -> None:
        """Initialize synchronous connections if any."""
        pass
        
    @abstractmethod
    async def connect_async(self) -> None:
        """Initialize asynchronous connections if any."""
        pass
        
    @abstractmethod
    def disconnect(self) -> None:
        """Close synchronous connections."""
        pass
        
    @abstractmethod
    async def disconnect_async(self) -> None:
        """Close asynchronous connections."""
        pass
