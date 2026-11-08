"""
VeloRoute: Blazing-Fast LLM Routing, Failover & Telemetry Gateway
================================================================
Auto multi-key rotation, intelligent error handling, streaming resilience,
agentic tool loops, structured output, prompt caching, budget enforcement,
and persistent storage — all in one unified gateway.
"""
__version__ = "1.0.0"

from veloroute.core.errors import (
    VeloRouteError,
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
from veloroute.schema import (
    CompletionRequest,
    Message,
    CompletionResponse,
    StreamChunk,
    Tool,
    ToolParameter,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingData,
    EmbeddingUsage,
)
from veloroute.core.keys import KeyManager, KeyStatus
from veloroute.core.router import ModelRouter, RoutingStrategy, ComplexityEvaluator, ComplexityPair
from veloroute.core.stream import RetryPolicy, SSEParser, StreamChunkAggregator
from veloroute.core.mcp import MCPRegistry, MCPTool, MCPCallResult
from veloroute.utils import (
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
from veloroute.core.injection import InjectionGuard, InjectionBlockedError
from veloroute.core.prompts import PromptRegistry, PromptVersion
from veloroute.core.semantic_cache import SemanticCache
from veloroute.core.semantic import SemanticRouter
from veloroute.core.secrets import (
    SecretLoader,
    EnvSecretLoader,
    AWSSecretLoader,
    GCPSecretLoader,
    VaultSecretLoader,
    SecretNotFoundError,
    SecretLoadError,
)
from veloroute.client import VeloRoute, LLMClient

__all__ = [
    "__version__",
    # Client
    "VeloRoute",
    "LLMClient",
    # Schema
    "CompletionRequest",
    "Message",
    "CompletionResponse",
    "StreamChunk",
    "Tool",
    "ToolParameter",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "EmbeddingData",
    "EmbeddingUsage",
    # Key management
    "KeyManager",
    "KeyStatus",
    # Routing & Resilience
    "ModelRouter",
    "RoutingStrategy",
    "RetryPolicy",
    "SSEParser",
    "StreamChunkAggregator",
    "ComplexityEvaluator",
    "ComplexityPair",
    # MCP (Model Context Protocol)
    "MCPRegistry",
    "MCPTool",
    "MCPCallResult",
    # Errors
    "VeloRouteError",
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
    "InjectionGuard",
    "InjectionBlockedError",
    # Prompt registry
    "PromptRegistry",
    "PromptVersion",
    # Semantic cache
    "SemanticCache",
    # Semantic router
    "SemanticRouter",
    # Secret loaders
    "SecretLoader",
    "EnvSecretLoader",
    "AWSSecretLoader",
    "GCPSecretLoader",
    "VaultSecretLoader",
    "SecretNotFoundError",
    "SecretLoadError",
]
