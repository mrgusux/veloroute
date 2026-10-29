"""
LLMCycle - Production-Grade All-in-One Universal LLM Router
============================================================
Auto multi-key rotation, intelligent error handling, streaming resilience,
agentic tool loops, structured output, prompt caching, budget enforcement,
and persistent storage — all in one library.
"""
from .client import LLMCycle
from .schema import (
    CompletionRequest, Message, CompletionResponse, StreamChunk, Tool, ToolParameter,
    EmbeddingRequest, EmbeddingResponse, EmbeddingData, EmbeddingUsage,
)
from .core.keys import KeyManager, KeyStatus
from .core.router import ModelRouter, RoutingStrategy
from .core.stream import RetryPolicy, SSEParser, StreamChunkAggregator
from .core.errors import (
    LLMCycleError,
    RateLimitError,
    AuthenticationError,
    PermissionDeniedError,
    NotFoundError,
    BadRequestError,
    ProviderError,
    InternalServerError,
    BadGatewayError,
    ServiceUnavailableError,
    GatewayTimeoutError,
    APIConnectionError,
    APIResponseError,
    AllProvidersFailedError,
    StreamInterruptedError,
    MaxToolCallsExceededError,
    BudgetExceededError,
    ContextWindowError,
    StructuredOutputError,
    QuotaExceededError,
    ContentPolicyError,
)
from .utils import (
    count_tokens,
    count_message_tokens,
    get_model_pricing,
    get_model_context_window,
    extract_forward_headers,
    merge_request_headers,
    parse_model,
    MODEL_PRICING,
    CONTEXT_WINDOWS,
)
# New market features
from .core.injection import InjectionGuard, InjectionBlockedError
from .core.prompts import PromptRegistry, PromptVersion
from .core.semantic_cache import SemanticCache
from .core.semantic import SemanticRouter
from .core.secrets import (
    SecretLoader, EnvSecretLoader,
    AWSSecretLoader, GCPSecretLoader, VaultSecretLoader,
    SecretNotFoundError, SecretLoadError,
)

__all__ = [
    # Client
    "LLMCycle",
    # Schema
    "CompletionRequest", "Message", "CompletionResponse", "StreamChunk",
    "Tool", "ToolParameter",
    "EmbeddingRequest", "EmbeddingResponse", "EmbeddingData", "EmbeddingUsage",
    # Key management
    "KeyManager", "KeyStatus",
    # Routing & Resilience
    "ModelRouter", "RoutingStrategy", "RetryPolicy", "SSEParser", "StreamChunkAggregator",
    # Errors
    "LLMCycleError",
    "RateLimitError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "BadRequestError",
    "ProviderError",
    "InternalServerError",
    "BadGatewayError",
    "ServiceUnavailableError",
    "GatewayTimeoutError",
    "APIConnectionError",
    "APIResponseError",
    "AllProvidersFailedError",
    "StreamInterruptedError",
    "MaxToolCallsExceededError",
    "BudgetExceededError",
    "ContextWindowError",
    "StructuredOutputError",
    "QuotaExceededError",
    "ContentPolicyError",
    # Token & Pricing & Headers
    "count_tokens",
    "count_message_tokens",
    "get_model_pricing",
    "get_model_context_window",
    "extract_forward_headers",
    "merge_request_headers",
    "parse_model",
    "MODEL_PRICING",
    "CONTEXT_WINDOWS",
    # Injection guard
    "InjectionGuard", "InjectionBlockedError",
    # Prompt registry
    "PromptRegistry", "PromptVersion",
    # Semantic cache
    "SemanticCache",
    # Semantic router
    "SemanticRouter",
    # Secret loaders
    "SecretLoader", "EnvSecretLoader",
    "AWSSecretLoader", "GCPSecretLoader", "VaultSecretLoader",
    "SecretNotFoundError", "SecretLoadError",
]

__version__ = "0.2.5"

