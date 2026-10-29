from abc import ABC, abstractmethod
from typing import AsyncGenerator
from llmcycle.schema import CompletionRequest

class LLMProvider(ABC):
    """Base class for all specific LLM implementations."""
    
    @abstractmethod
    async def generate(self, request: CompletionRequest, api_key: str) -> str:
        """Generate a complete string response."""
        pass

    @abstractmethod
    async def generate_stream(self, request: CompletionRequest, api_key: str) -> AsyncGenerator[str, None]:
        """Generate a streaming response."""
        pass
        
    @abstractmethod
    async def get_models(self, api_key: str) -> list[str]:
        """Return a list of models supported by this provider."""
        pass
