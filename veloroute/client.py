"""
VeloRoute Client - All-in-One LLM Interface
============================================
Features:
  - Auto-discovers providers from .env (*_API_KEYS pattern)
  - Multi-key rotation with per-key health tracking
  - Smart routing: Priority / Round-Robin / Lowest-Latency / Cost-Optimized
  - Resilient streaming with mid-stream failover
  - Timeout + cancellation tracking (status: success/error/cancelled/timeout)
  - Auto-save to storage with session/user/team/tags
  - Model aliases (map "fast" → "groq/llama-3-70b")
  - Prompt caching (in-memory / semantic similarity with TTL)
  - Structured output (tool-calling API by default, JSON-prompt fallback)
  - Agentic tool-calling loop with max_tool_calls guard
  - Budget enforcement (raises BudgetExceededError if cost_usd exceeded)
  - Context window auto-trim (truncate messages to fit model limits)
  - Request/response middleware hooks (on_before / on_after / on_trace)
  - Parallel batch completions with concurrency control
  - Prompt injection & jailbreak guard (InjectionGuard)
  - Shadow routing / dark launching (shadow_models on complete)
  - Response validation with auto-retry (validators on complete)
  - Prompt registry with versioned templates (PromptRegistry)
  - Semantic caching (TF-IDF cosine similarity)
  - Secret manager adapters (Env / AWS / GCP / Vault)
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os
import secrets
import time as _time
from typing import (
    Any, AsyncGenerator, Callable, Dict, List, Optional, Type, TypeVar, Union
)

from dotenv import load_dotenv

from veloroute.schema import (
    CompletionRequest, CompletionResponse, Message, Tool,
    EmbeddingRequest, EmbeddingResponse, StreamEvent,
)
from veloroute.core.keys import KeyManager
from veloroute.core.cache import BaseCache, InMemoryCache
from veloroute.core.router import ModelRouter, RoutingStrategy
from veloroute.core.stream import StreamResilienceManager, RetryPolicy, SmartRetryState
from veloroute.core.errors import (
    MaxToolCallsExceededError, BudgetExceededError,
    StructuredOutputError, AllProvidersFailedError,
    AuthenticationError, RateLimitError, QuotaExceededError,
    VeloRouteError,
    PermissionDeniedError, BadRequestError, ContentPolicyError, ContextWindowError,
)
from veloroute.core.injection import InjectionGuard, InjectionBlockedError
from veloroute.core.prompts import PromptRegistry
from veloroute.core.semantic_cache import SemanticCache
from veloroute.core.groups import GroupManager
from veloroute.core.mcp import MCPRegistry
from veloroute.providers.openai_compatible import OpenAICompatibleProvider
from veloroute.providers.registry import PROVIDER_REGISTRY
from veloroute.utils import (
    parse_model, DEFAULT_PRICING, DEFAULT_CONTEXT_WINDOWS,
    get_model_pricing, get_model_context_window,
    count_tokens, count_message_tokens,
)
from veloroute.core.config_loader import ConfigLoader, EnvConfigLoader, RedisConfigLoader
from veloroute.gateway.keys import VirtualKeyManager
from veloroute.observability import get_metrics
from enum import Enum

class ConfigSource(Enum):
    ENV = "env"
    REDIS = "redis"

logger = logging.getLogger(__name__)

T = TypeVar("T")


class _CacheEntry:
    """In-memory prompt cache entry."""
    __slots__ = ("response", "expires_at")
    def __init__(self, response: CompletionResponse, ttl: float):
        self.response   = response
        self.expires_at = _time.monotonic() + ttl


class VeloRoute:
    """
    All-in-one LLM router and client.

    Quick start::

        client = VeloRoute()
        response = await client.complete("openai/gpt-4o-mini", "What is RAG?")
        async for chunk in client.stream("groq/llama-3.1-70b", "Write a poem"):
            print(chunk, end="")

    With Storage Auto-Save & Unified Drivers::

        from veloroute.client import VeloRoute, ConfigSource
        from veloroute.storage import StorageManager
        
        # 1. Setup Storage (Auto-builds Drivers)
        store = StorageManager(url="redis://localhost:6379/0")
        
        # 2. Client auto-inherits the driver for Config Loading!
        client = VeloRoute(
            storage=store, 
            config_source=ConfigSource.REDIS,
            session_id="sess-1", 
            user_id="user-1"
        )

    Dynamic Model Groups (Aliases & Fallbacks)::

        client.router.groups.set("fast", ["groq/llama3", "openai/gpt-4o-mini"])
        
        # ACTIVE_FIRST routing automatically skips exhausted providers!
        # Pass a group as a fallback or primary target:
        response = await client.complete(group="fast", prompt="Hello!", strategy=RoutingStrategy.ACTIVE_FIRST)
        
        # You can also pass both model AND group:
        response = await client.complete(model="openai/gpt-4o", group="fast", prompt="Hello!")

        # Persist groups to your database (SQL/Mongo/Redis)
        await client.router.groups.save()

    Tool calling loop::

        async def execute_tool(name, args):
            if name == "get_weather":
                return {"temp": 18, "city": args["city"]}

        result = await client.complete_with_tools(
            "openai/gpt-4o",
            prompt="What is the weather in London?",
            tools=[{"type": "function", "function": {"name": "get_weather", ...}}],
            tool_executor=execute_tool,
            max_tool_calls=5,
        )

    Structured output::

        class Answer(BaseModel):
            city: str
            temperature: int

        answer = await client.complete_structured(
            "openai/gpt-4o-mini",
            "What is the weather in London? Reply as JSON.",
            schema=Answer,
        )

    Budget enforcement::

        client = VeloRoute(max_cost_usd=1.00)   # raises BudgetExceededError at $1

    Prompt Caching & Semantic Caching::

        # Exact match cache
        res1 = await client.complete("openai/gpt-4o", "What is 2+2?", cache_ttl=300)
        res2 = await client.complete("openai/gpt-4o", "What is 2+2?", cache_ttl=300) # Instant
        
        # Semantic cache (TF-IDF Cosine Similarity)
        client = VeloRoute(semantic_cache=SemanticCache(similarity_threshold=0.85))
        res3 = await client.complete("openai/gpt-4o", "How do I build a RAG app?")
        res4 = await client.complete("openai/gpt-4o", "What's the best way to make a RAG application?") # Instant
    Args:
        env_path: Path to the .env file for auto-loading provider configs.
        fallbacks: Optional dictionary of fallback chains mapping models/providers to a list of fallback models.
        groups: Optional dictionary mapping group names to a list of models. Groups can be dynamically managed via `client.router.groups`.
        strategy: Routing strategy enum. E.g., PRIORITY, ROUND_ROBIN, LOWEST_LATENCY, COST_OPTIMIZED, ACTIVE_FIRST.
        config_source: Source for config auto-loading (ENV or REDIS).
        config_prefix: Prefix for searching config keys.
        config_suffix: Suffix for searching config keys (e.g., _API_KEYS).
        redis_url: Redis URL if config_source=REDIS.
        log_level: Logging level (e.g., "WARNING").
        storage: Optional StorageManager instance. If provided, enables DB persistence for configs, history, groups, etc.
        session_id: Default session stamped on all requests.
        user_id: Default user stamped on all requests.
        team_id: Default team stamped on all requests.
        workplace_id: Default workplace stamped on all requests.
        max_cost_usd: Hard budget enforcement.
        pricing: Custom pricing override dictionary.
        context_windows: Custom context window dictionary.
        auto_trim_context: Automatically truncate messages if over context limit.
        cache: Cache settings for prompts (True for InMemory or instance of BaseCache).
        semantic_cache: Semantic similarity cache for prompt matching.
        rate_limits: Client-side rate limiting dictionary.
        guardrail: True to enable default guardrail, or instance of GuardrailManager.
        injection_guard: True to enable prompt injection guards.
        attachment_storage: Storage path/type for attachments.
        proxy: Proxy string for network requests.
    """

    def __init__(
        self,
        env_path: str = ".env",
        fallbacks: Optional[Dict[str, List[str]]] = None,
        groups: Optional[Dict[str, List[str]]] = None,
        strategy: RoutingStrategy = RoutingStrategy.PRIORITY,
        config_source: ConfigSource = ConfigSource.ENV,
        config_prefix: str = "",
        config_suffix: str = "_API_KEYS",
        redis_url: Optional[str] = None,
        log_level: str = "WARNING",
        # Storage integration
        storage=None,                      # Optional[StorageManager]
        session_id: Optional[str] = None,  # default session stamped on all requests
        user_id: Optional[str] = None,     # default user stamped on all requests
        team_id: Optional[str] = None,
        workplace_id: Optional[str] = None,
        # Budget enforcement
        max_cost_usd: Optional[float] = None,
        # Pricing override
        pricing: Optional[Dict[str, Dict[str, float]]] = None,
        # Context window limits
        context_windows: Optional[Dict[str, int]] = None,
        auto_trim_context: bool = True,    # auto-truncate messages if over context limit
        # Caching layer
        cache: Optional[Union[bool, BaseCache]] = False,  # Pluggable prompt cache
        semantic_cache: Optional[Union[bool, SemanticCache]] = False,  # Semantic similarity cache
        # Rate limits
        rate_limits: Optional[Union[bool, Dict[str, Dict[str, int]]]] = False,
        # Guardrails
        guardrail: Optional[Union[bool, Any]] = False,
        # Prompt injection / jailbreak protection
        injection_guard: Optional[Union[bool, InjectionGuard]] = False,
        # Attachment Storage integration
        attachment_storage: Optional[str] = None,
        attachment_config: Optional[dict] = None,
        # Proxy settings
        proxy: Optional[str] = None,
    ):
        logging.basicConfig(level=getattr(logging, log_level.upper(), logging.WARNING))

        # BOM-aware .env loader
        from pathlib import Path as _Path
        env_file = _Path(env_path)
        if env_file.exists():
            for _enc in ("utf-8-sig", "utf-16", "utf-8", "latin-1"):
                try:
                    for _line in env_file.read_text(encoding=_enc).splitlines():
                        _line = _line.strip()
                        if not _line or _line.startswith("#") or "=" not in _line:
                            continue
                        _k, _, _v = _line.partition("=")
                        _k = _k.strip(); _v = _v.strip().strip('"').strip("'")
                        if _k and _k not in os.environ:
                            os.environ[_k] = _v
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue

        self.key_manager  = KeyManager()
        self._providers: Dict[str, OpenAICompatibleProvider] = {}
        self._custom_models: Dict[str, List[str]] = {}

        self.storage      = storage
        self.session_id   = session_id
        self.user_id      = user_id
        self.team_id      = team_id
        self.workplace_id = workplace_id

        # Virtual-key gateway.  Enforcement activates as soon as a key exists
        # (or VELOROUTE_REQUIRE_API_KEY is set); see gateway/keys.py.
        self.virtual_keys = VirtualKeyManager(storage=storage)
        self.metrics = get_metrics()

        from veloroute.core.attachments import AttachmentManager
        att_cfg = attachment_config or {}
        self.attachment_manager = AttachmentManager(
            storage_type=attachment_storage,
            **att_cfg
        )

        self.max_cost_usd    = max_cost_usd
        self._total_cost_usd = 0.0         # accumulated cost this session
        self.proxy           = proxy or os.environ.get("VELOROUTE_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or None

        self.pricing         = {**DEFAULT_PRICING, **(pricing or {})}
        self.context_windows = {**DEFAULT_CONTEXT_WINDOWS, **(context_windows or {})}
        self.auto_trim_context = auto_trim_context
        self.privacy_mode: bool = os.environ.get("VELOROUTE_PRIVACY_MODE", "").lower() in ("1", "true", "yes")

        from veloroute.core.context_optimizer import ContextOptimizer
        self.context_optimizer = ContextOptimizer()

        from veloroute.core.prompt_sizer import PromptSizer
        self.prompt_sizer = PromptSizer()

        self._aliases: Dict[str, str] = {}
        from veloroute.core.transform import TransformManager
        self.transforms = TransformManager()

        self._cache = None
        if cache is True:
            self._cache = InMemoryCache()
        elif cache:
            self._cache = cache

        self.rate_limit_manager = None
        if rate_limits is True:
            from veloroute.core.rate_limit import RateLimitManager
            self.rate_limit_manager = RateLimitManager({"default": {"rpm": 60, "tpm": 40000}})
        elif rate_limits:
            from veloroute.core.rate_limit import RateLimitManager
            self.rate_limit_manager = RateLimitManager(rate_limits)

        self.guardrail = None
        if guardrail is True:
            from veloroute.core.guardrail import GuardrailManager
            self.guardrail = GuardrailManager()
        elif guardrail:
            self.guardrail = guardrail

        self.injection_guard: Optional[InjectionGuard] = None
        if injection_guard is True:
            self.injection_guard = InjectionGuard()
        elif injection_guard:
            self.injection_guard = injection_guard

        self._semantic_cache: Optional[SemanticCache] = None
        if semantic_cache is True:
            self._semantic_cache = SemanticCache()
        elif semantic_cache:
            self._semantic_cache = semantic_cache

        self.prompts = PromptRegistry()

        # Set client.on_before / on_after / on_error / on_trace to async callables:
        #   async def hook(model, messages, kwargs): ...  # on_before
        #   async def hook(model, response): ...          # on_after
        #   async def hook(model, exception): ...         # on_error
        #   async def hook(trace: dict): ...              # on_trace  (OTel-compatible)
        self.on_before: Optional[Callable] = None
        self.on_after:  Optional[Callable] = None
        self.on_error:  Optional[Callable] = None
        self.on_trace:  Optional[Callable] = None

        self.groups = GroupManager(groups)
        self.groups.storage = self.storage
        
        # Initialize the appropriate config loader based on user preferences
        if config_source == ConfigSource.ENV:
            self._config_loader = EnvConfigLoader(prefix=config_prefix, suffix=config_suffix)
        elif config_source == ConfigSource.REDIS:
            active_driver = getattr(self.storage, 'driver', None) if self.storage else None
            if not redis_url and not active_driver:
                raise ValueError("redis_url or a StorageManager with a driver must be provided when using ConfigSource.REDIS")
            self._config_loader = RedisConfigLoader(
                redis_url=redis_url or getattr(active_driver, 'url', ""), 
                prefix=config_prefix, 
                suffix=config_suffix, 
                driver=active_driver
            )
        else:
            raise ValueError(f"Unknown config_source: {config_source}")

        self._auto_load_configs()
        self.router      = ModelRouter(
            fallbacks=fallbacks or {}, 
            groups=self.groups, 
            strategy=strategy, 
            pricing=self.pricing,
            key_manager=self.key_manager,
            aliases=self._aliases,
        )
        self.router.storage = self.storage
        self._stream_mgr = StreamResilienceManager(self.router, self.key_manager, self._providers)
        self.mcp = MCPRegistry(llm_client=self)

    def register_mcp_tool(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        input_schema: Optional[Dict[str, Any]] = None,
        server_name: str = "local",
    ):
        """Register a function as an MCP tool on this client."""
        return self.mcp.register_tool(
            name=name,
            handler=handler,
            description=description,
            input_schema=input_schema,
            server_name=server_name,
        )

    # ─── Auto-discovery ──────────────────────────────────────────────────────

    def _auto_load_configs(self):
        """Scan configured loaders and register providers."""
        configs = self._config_loader.load_configs()
        for provider_name, config in configs.items():
                p_key = provider_name.lower()
                
                # Prevent environment variable typos by verifying against registry or checking for custom base URL
                if provider_name.upper() not in PROVIDER_REGISTRY and not config.get("base_url"):
                    logger.warning(f"Skipping auto-load of invalid/unknown provider '{provider_name}' in env config (no registry match or explicit BASE_URL).")
                    continue

                keys = [k.strip() for k in config.get("api_keys", "").split(",") if k.strip()]
                base_url = (
                    config.get("base_url")
                    or PROVIDER_REGISTRY.get(provider_name.upper())
                    or f"https://api.{p_key}.com/v1"
                )
                if not keys:
                    if any(x in p_key for x in ("ollama", "lm_studio", "vllm", "llamafile", "localai")) or "localhost" in base_url or "127.0.0.1" in base_url:
                        keys = [p_key]
                    else:
                        continue
                if p_key not in self._providers:
                    self._providers[p_key] = OpenAICompatibleProvider(base_url, provider_name=p_key, proxy=self.proxy)
                self.key_manager.add_keys(p_key, keys)
                models_val = config.get("models")
                if models_val:
                    models_list = [m.strip() for m in models_val.split(",") if m.strip()]
                    self.set_custom_models(p_key, models_list)
                logger.info(f"Registered provider [{p_key}] with {len(keys)} key(s) → {base_url}")

        if "mock" not in self._providers:
            self._providers["mock"] = OpenAICompatibleProvider("mock://internal", provider_name="mock", proxy=self.proxy)
            self.key_manager.add_keys("mock", ["mock-key"])
            self.set_custom_models("mock", ["gpt-4o", "claude-3-7-sonnet", "deepseek-r1", "general-purpose"])

    # ─── Provider management ─────────────────────────────────────────────────

    def set_custom_models(self, provider: str, models: Optional[List[str]]) -> None:
        """Store explicit custom models for a provider, bypassing dynamic discovery."""
        p = provider.lower()
        if models is not None and len(models) > 0:
            seen = set()
            cleaned = []
            for m in models:
                s = m.strip().strip("\"'")
                if s.lower().startswith(f"{p}/"):
                    s = s[len(p) + 1:].strip()
                if s and s not in seen:
                    seen.add(s)
                    cleaned.append(s)
            self._custom_models[p] = cleaned
            logger.info(f"Set {len(cleaned)} custom model(s) for provider [{p}]")
        else:
            self._custom_models.pop(p, None)

    def get_custom_models(self, provider: str) -> Optional[List[str]]:
        """Return explicit custom models if configured for a provider, else None."""
        p = provider.lower()
        return list(self._custom_models[p]) if p in self._custom_models else None

    def remove_custom_models(self, provider: str) -> bool:
        """Remove explicit custom models for a provider, restoring dynamic discovery."""
        p = provider.lower()
        return self._custom_models.pop(p, None) is not None

    def add_provider(
        self,
        name: str,
        api_keys: List[str],
        base_url: Optional[str] = None,
        models: Optional[List[str]] = None,
    ):
        """Manually register a provider at runtime."""
        p = name.lower()
        url = (base_url.rstrip("/") if base_url else None) or PROVIDER_REGISTRY.get(name.upper()) or f"https://api.{p}.com/v1"
        self._providers[p] = OpenAICompatibleProvider(url, provider_name=p, proxy=self.proxy)
        self.key_manager.add_keys(p, api_keys)
        if models is not None:
            self.set_custom_models(p, models)

    def remove_provider(self, name: str) -> bool:
        """Remove a provider, its keys, custom models, and associated routing fallback rules."""
        p = name.lower()
        removed = p in self._providers
        self._providers.pop(p, None)
        self.remove_custom_models(p)
        self.key_manager.remove_provider(p)
        if hasattr(self, "router") and self.router:
            self.router.remove_provider(p)
        logger.info(f"Removed provider [{p}]")
        return removed

    def update_provider(
        self,
        name: str,
        api_keys: Optional[List[str]] = None,
        base_url: Optional[str] = None,
        models: Optional[List[str]] = None,
    ) -> bool:
        """Update provider base_url, API keys, and/or custom models at runtime."""
        p = name.lower()
        if base_url:
            clean_url = base_url.strip().rstrip("/")
            if p in self._providers:
                self._providers[p].base_url = clean_url
            else:
                self._providers[p] = OpenAICompatibleProvider(clean_url, provider_name=p, proxy=self.proxy)
        elif p not in self._providers:
            default_url = PROVIDER_REGISTRY.get(name.upper()) or f"https://api.{p}.com/v1"
            self._providers[p] = OpenAICompatibleProvider(default_url, provider_name=p, proxy=self.proxy)

        if api_keys is not None:
            self.key_manager.set_keys(p, api_keys)
        if models is not None:
            self.set_custom_models(p, models)
        logger.info(f"Updated provider [{p}]")
        return True

    def remove_key(self, provider: str, key_or_hint: str) -> bool:
        """Remove a single key from a provider."""
        return self.key_manager.remove_key(provider, key_or_hint)

    def get_providers(self) -> List[str]:
        return list(self._providers.keys())

    async def get_models(self, provider: str) -> List[str]:
        p = provider.lower()
        if p not in self._providers:
            return []
        if p in self._custom_models and self._custom_models[p] is not None:
            return list(self._custom_models[p])
        # Read-only discovery must not consume a key rotation slot or inflate
        # request counters (the old get_next_key() did both).
        key = self.key_manager.peek_key(p, include_unusable=True)
        if not key:
            return []
        return await self._providers[p].get_models(key)

    async def discover_models(
        self,
        provider: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query upstream /models directly, bypassing any cached or custom model lists.
        Returns list of model dicts: [{'id': str, 'is_free': bool, 'raw': dict}, ...].
        """
        from veloroute.utils import is_free_model
        p = provider.lower()
        url = base_url
        if not url:
            if p in self._providers:
                url = self._providers[p].base_url
            else:
                url = PROVIDER_REGISTRY.get(provider.upper()) or f"https://api.{p}.com/v1"

        key = api_key
        if not key and p in self._providers:
            key = self.key_manager.peek_key(p, include_unusable=True)
        if not key:
            if any(x in p for x in ("ollama", "lm_studio", "vllm", "llamafile", "localai")) or "localhost" in url or "127.0.0.1" in url:
                key = p
            else:
                raise VeloRouteError(f"No API key provided for '{provider or url}' to discover models")

        provider_instance = OpenAICompatibleProvider(url, provider_name=p, proxy=self.proxy)
        try:
            detailed = await provider_instance.get_models_detailed(key, raise_on_error=True)
            result = []
            seen = set()
            for item in detailed:
                m_id = item.get("id") if isinstance(item, dict) else str(item)
                if not m_id or m_id in seen:
                    continue
                seen.add(m_id)
                free = is_free_model(
                    m_id,
                    raw_info=item if isinstance(item, dict) else None,
                    provider_name=p,
                    base_url=url,
                )
                result.append({
                    "id": m_id,
                    "is_free": free,
                    "raw": item if isinstance(item, dict) else {"id": m_id},
                })
            result.sort(key=lambda x: x["id"])
            return result
        finally:
            await provider_instance.aclose_all()

    async def get_all_live_models(self) -> Dict[str, List[str]]:
        """Fetch all dynamic live models across all configured providers in parallel."""
        providers = self.get_providers()
        tasks = {p: self.get_models(p) for p in providers}
        results = {}
        for p, fut in zip(tasks.keys(), await asyncio.gather(*tasks.values(), return_exceptions=True)):
            if isinstance(fut, Exception):
                logger.warning(f"Failed to fetch live models for {p}: {fut}")
                results[p] = []
            else:
                results[p] = fut
        return results

    def get_key_stats(self, provider: str) -> List[dict]:
        return self.key_manager.get_stats(provider)

    async def ping_provider(
        self,
        provider: str,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 10.0,
    ) -> dict:
        """
        Probe provider with a live test request to verify reachability, key validity,
        and measure roundtrip latency (One-API & LiteLLM health check style).
        Automatically updates KeyManager health and ModelRouter latency tracking.
        """
        p = provider.lower()
        if p not in self._providers:
            return {"healthy": False, "provider": p, "error": f"Provider '{p}' not registered"}

        key = api_key or self.key_manager.get_next_key(p)
        if not key:
            # Fall back to any registered key for this provider (even if currently rate-limited or circuit-broken)
            # so the health check probe can test if it has recovered!
            with self.key_manager._lock:
                records = self.key_manager._keys.get(p, [])
                if records:
                    key = records[0].key

        if not key:
            return {"healthy": False, "provider": p, "error": f"No active keys for provider '{p}'"}

        result = await self._providers[p].ping(key, model=model, timeout=timeout)
        if result.get("healthy"):
            self.key_manager.report_success(p, key)
            self.router.record_latency(p, result.get("latency_ms", 0.0))
        else:
            err_type = result.get("error_type", "")
            mapped_type = "auth" if "Auth" in err_type or "Permission" in err_type else "server"
            self.key_manager.report_error(p, key, mapped_type)
        return result

    async def ping_all_providers(self, timeout: float = 10.0) -> Dict[str, dict]:
        """Concurrently probe all configured providers with live payload probes."""
        providers = self.get_providers()
        tasks = {p: self.ping_provider(p, timeout=timeout) for p in providers}
        results = {}
        for p, fut in zip(tasks.keys(), await asyncio.gather(*tasks.values(), return_exceptions=True)):
            if isinstance(fut, Exception):
                results[p] = {"healthy": False, "provider": p, "error": str(fut)}
            else:
                results[p] = fut
        return results

    # ─── Aliases ─────────────────────────────────────────────────────────────

    def alias(self, name: str, model: str) -> None:
        """
        Create a model alias.

        Usage::

            client.alias("fast",    "groq/llama-3.1-70b")
            client.alias("smart",   "openai/gpt-4o")
            client.alias("cheap",   "deepseek/deepseek-chat")

            response = await client.complete("fast", "Explain RAG")
            # resolves to groq/llama-3.1-70b automatically
        """
        self._aliases[name] = model
        if hasattr(self, "router") and self.router:
            self.router.alias(name, model)

    def remove_alias(self, name: str) -> bool:
        """Remove a model alias."""
        removed = self._aliases.pop(name, None) is not None
        if hasattr(self, "router") and self.router:
            self.router.remove_alias(name)
        return removed

    def list_aliases(self) -> Dict[str, str]:
        """List all configured model aliases."""
        if hasattr(self, "router") and self.router and self.router.aliases:
            self._aliases.update(self.router.aliases)
        return dict(self._aliases)

    def _resolve_model(self, model: str) -> str:
        """Resolve alias → real model string."""
        if hasattr(self, "router") and self.router:
            return self.router.resolve_model(model)
        return self._aliases.get(model, model)


    # ─── Pricing helpers ─────────────────────────────────────────────────────

    def _get_pricing(self, model: str) -> Optional[Dict[str, float]]:
        """Return {input, output} pricing for a model (exact or normalized match)."""
        return get_model_pricing(model, self.pricing)

    def _estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> Optional[float]:
        price = self._get_pricing(model)
        if not price:
            return None
        return (prompt_tokens / 1000) * price["input"] + (completion_tokens / 1000) * price["output"]

    def get_cost_summary(self) -> Dict[str, float]:
        """Return total accumulated cost for this client session."""
        return {"total_cost_usd": self._total_cost_usd, "budget_usd": self.max_cost_usd}

    def _check_budget(self, new_cost: Optional[float]) -> None:
        """Raise BudgetExceededError if adding new_cost would exceed max_cost_usd."""
        if self.max_cost_usd is not None and new_cost is not None:
            if self._total_cost_usd + new_cost > self.max_cost_usd:
                raise BudgetExceededError(
                    spent=self._total_cost_usd,
                    budget=self.max_cost_usd,
                )

    # ─── Context window helpers ───────────────────────────────────────────────

    def _get_content_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        parts.append(part.get("text", ""))
                    elif part.get("type") == "image_url":
                        parts.append("[Image Attachment]")
                    elif part.get("type") == "input_audio":
                        parts.append("[Audio Attachment]")
                    elif part.get("type") == "document":
                        parts.append("[Document Attachment]")
            return "".join(parts)
        return ""

    def _estimate_tokens(self, text: str, model: str = "gpt-4o") -> int:
        """Estimate tokens using tiktoken or robust multilingual heuristic."""
        return count_tokens(text, model=model)

    def _estimate_message_tokens(self, message: Any, model: str) -> int:
        """Estimate a message including tool-call payloads (not just content)."""
        if isinstance(message, dict):
            role = message.get("role", "")
            content = message.get("content", "")
            tool_calls = message.get("tool_calls")
            tool_call_id = message.get("tool_call_id")
        else:
            role = getattr(message, "role", "")
            content = getattr(message, "content", "")
            tool_calls = getattr(message, "tool_calls", None)
            tool_call_id = getattr(message, "tool_call_id", None)

        tokens = self._estimate_tokens(self._get_content_text(content), model=model)
        if tool_calls:
            try:
                tokens += self._estimate_tokens(
                    json.dumps(tool_calls, default=str), model=model
                )
            except Exception:
                tokens += 16
        if tool_call_id:
            tokens += 4
        # Small per-message overhead (role separators).
        return tokens + 4

    def _trim_messages(self, messages: List[Any], model: str, reserve: int = 512) -> List[Any]:
        """
        Auto-trim messages to fit within the model's context window.

        Messages are removed in *atomic groups*: an assistant message with
        ``tool_calls`` and all immediately following ``tool`` results stay
        together.  Trimming a tool result without its assistant call (or vice
        versa) produces an invalid conversation that every OpenAI-compatible
        provider rejects with HTTP 400.
        """
        limit = get_model_context_window(model, self.context_windows)
        if not limit or not messages:
            return messages

        def _role(m: Any) -> str:
            return m.get("role", "") if isinstance(m, dict) else getattr(m, "role", "")

        def _tool_calls(m: Any) -> Any:
            return m.get("tool_calls") if isinstance(m, dict) else getattr(m, "tool_calls", None)

        total = sum(self._estimate_message_tokens(m, model) for m in messages)
        if total + reserve <= limit:
            return messages

        system = [m for m in messages if _role(m) == "system"]
        non_system = [m for m in messages if _role(m) != "system"]

        # Group consecutive tool results with the preceding assistant turn.
        groups: List[List[Any]] = []
        for m in non_system:
            if _role(m) == "tool" and groups:
                groups[-1].append(m)
            else:
                groups.append([m])

        def _valid_group(group: List[Any]) -> bool:
            has_tool_result = any(_role(m) == "tool" for m in group)
            if not has_tool_result:
                return True
            return any(
                _role(m) == "assistant" and bool(_tool_calls(m))
                for m in group
            )

        system_tokens = sum(self._estimate_message_tokens(m, model) for m in system)
        budget = limit - reserve - system_tokens
        kept_groups: List[List[Any]] = []
        for group in reversed(groups):
            group_tokens = sum(self._estimate_message_tokens(m, model) for m in group)
            if budget - group_tokens >= 0:
                kept_groups.insert(0, group)
                budget -= group_tokens
            else:
                break

        # Never start with an orphaned tool result.
        while kept_groups and not _valid_group(kept_groups[0]):
            kept_groups.pop(0)

        # If the newest turn alone exceeds the budget, keep it anyway; dropping
        # the user's actual question is worse than slightly exceeding context.
        if not kept_groups and groups:
            candidate = groups[-1]
            if _valid_group(candidate):
                kept_groups = [candidate]

        kept = [m for group in kept_groups for m in group]
        result = system + kept
        logger.warning(
            f"Auto-trimmed messages from {len(messages)} to {len(result)} "
            f"to fit context window."
        )
        return result

    # ─── Prompt cache ─────────────────────────────────────────────────────────

    def _cache_key(self, model: str, messages: List[dict], kwargs: dict) -> str:
        """
        Cache identity includes *every* generation parameter.

        The old key only covered temperature/max_tokens/top_p, so a request
        with different ``tools``, ``tool_choice`` or ``response_format`` could
        receive an unrelated cached response.  ``default=str`` keeps exotic
        provider parameters hashable.
        """
        payload = json.dumps(
            {"model": model, "messages": messages, "params": kwargs},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    async def _cache_get(self, key: str) -> Optional[CompletionResponse]:
        if not self._cache:
            return None
        return await self._cache.get(key)

    async def _cache_set(self, key: str, response: CompletionResponse, ttl: float) -> None:
        if not self._cache:
            return
        await self._cache.set(key, response, ttl)

    async def cache_clear(self) -> int:
        """Clear all cached responses. Returns number of entries cleared."""
        if not self._cache:
            return 0
        return await self._cache.clear()

    async def cache_stats(self) -> Dict[str, Any]:
        """Return info about current prompt cache state."""
        if not self._cache:
            return {}
        return await self._cache.stats()

    # ─── Storage helpers ──────────────────────────────────────────────────────

    async def _save(self, **kwargs) -> Optional[str]:
        """
        Fire-and-forget storage save (non-fatal).

        Returns the generated ``LLMRequest.id`` so callers can link follow-up
        records (tool calls, child turns) to this request.
        """
        if not self.storage:
            return None
        if getattr(self, "privacy_mode", False) or os.environ.get("VELOROUTE_PRIVACY_MODE", "").lower() in ("1", "true", "yes"):
            # Zero-Retention Privacy Mode active: discard request body and prompt storage
            return None
        try:
            from veloroute.storage.models import LLMRequest as _R
            record = _R(**kwargs)
            await self.storage.save_request(record)
            return record.id
        except Exception as e:
            logger.warning(f"Storage save failed (non-fatal): {e}")
            return None

    def _apply_slash_directives(
        self,
        prompt: Optional[str],
        messages: Optional[List[dict]],
        strategy: Optional[RoutingStrategy],
    ) -> Tuple[Optional[str], Optional[List[dict]], Optional[RoutingStrategy]]:
        """
        Inspect prompt or last user message for leading slash-command directives
        (/fast, /cheap, /smart, /reason, /hedge, /kv, /quality, /terse) and return
        (cleaned_prompt, cleaned_messages, effective_strategy).
        """
        from veloroute.core.router import parse_slash_command

        meta: Dict[str, Any] = {}
        if isinstance(prompt, str) and prompt.lstrip().startswith("/"):
            cleaned_p, p_meta = parse_slash_command(prompt)
            if p_meta:
                prompt = cleaned_p
                meta.update(p_meta)

        if messages and isinstance(messages, list):
            for idx in range(len(messages) - 1, -1, -1):
                m = messages[idx]
                if isinstance(m, dict) and m.get("role") == "user":
                    content = m.get("content")
                    if isinstance(content, str) and content.lstrip().startswith("/"):
                        cleaned_c, c_meta = parse_slash_command(content)
                        if c_meta:
                            messages[idx] = {**m, "content": cleaned_c}
                            if not meta:
                                meta.update(c_meta)
                    break

        if meta:
            if strategy is None and "strategy" in meta:
                strategy = meta["strategy"]
            if meta.get("terse"):
                if isinstance(prompt, str) and prompt:
                    prompt = self.optimizer.compress_text(prompt)
                if messages and isinstance(messages, list):
                    for idx in range(len(messages) - 1, -1, -1):
                        m = messages[idx]
                        if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str):
                            compressed = self.optimizer.compress_text(m["content"])
                            messages[idx] = {**m, "content": f"{compressed}\n\n[Respond concisely with zero fluff.]"}
                            break
        return prompt, messages, strategy

    # ─── Inference: complete ──────────────────────────────────────────────────

    async def complete(
        self,
        model: Optional[str] = None,
        prompt: Optional[str] = None,
        messages: Optional[List[dict]] = None,
        group: Optional[str] = None,
        strategy: Optional[RoutingStrategy] = None,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 30.0,
        jitter: bool = True,
        key_strategy: str = "round_robin",
        timeout: Optional[float] = None,
        cache_ttl: Optional[float] = None,    # seconds; None = no cache
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        workplace_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        parent_request_id: Optional[str] = None,
        turn_number: int = 0,
        attachments: Optional[List[Union[str, bytes, dict]]] = None,
        shadow_models: Optional[List[str]] = None,
        validators: Optional[List[Callable]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> CompletionResponse:
        """
        One-shot completion with smart retry.

        Args:
            model:              Model string, e.g. "openai/gpt-4o-mini" or an alias.
            prompt:             User prompt (convenience — builds a single user message).
            messages:           Full messages list (overrides prompt).
            group:              Optional group ID to use for routing/fallback. 
                                If both model and group are provided, model is tried first, 
                                and group is used as the fallback list.
            strategy:           Optional RoutingStrategy override for this request.
            cache_ttl:          Cache identical prompts for this many seconds (0 = no cache).
            parent_request_id:  Link to a parent request (used in tool-call chains).
            turn_number:        Which turn in an agentic loop (0 = first user turn).
            timeout:            Raise asyncio.TimeoutError after N seconds.
            tags:               Labels saved with the storage record.
            attachments:        Optional list of documents, audio, video, or image attachments.
            shadow_models:      Fire-and-forget completions on these models in parallel
                                (dark launching / A/B). Results are logged only.
            validators:         List of callables (sync or async) — each receives
                                (model, response) and raises on failure. On validator
                                failure the call behaves as an error (no retry via
                                shadow_models but surfaces the ValidationError).
        """
        self._check_budget(0.0)
        
        if not model and not group:
            raise ValueError("Must provide 'model' or 'group'.")
            
        if model:
            if hasattr(self, "transforms"):
                model = self.transforms.transform_model(model)
            model = self._resolve_model(model)

        if messages is None:
            if prompt is None:
                raise ValueError("Provide either 'prompt' or 'messages'.")
            prompt, _, strategy = self._apply_slash_directives(prompt, None, strategy)
            if attachments:
                messages = [{"role": "user", "content": self.attachment_manager.format_message_content(prompt, attachments)}]
            else:
                messages = [{"role": "user", "content": prompt}]
        else:
            messages = [
                (m.model_dump(exclude_none=True) if hasattr(m, "model_dump") else (dict(m) if isinstance(m, dict) else dict(m.__dict__)))
                for m in messages
            ]
            prompt, messages, strategy = self._apply_slash_directives(prompt, messages, strategy)
            if attachments:
                user_msg_idx = None
                for idx in range(len(messages) - 1, -1, -1):
                    if messages[idx].get("role") == "user":
                        user_msg_idx = idx
                        break
                if user_msg_idx is not None:
                    current_content = messages[user_msg_idx].get("content", "")
                    messages[user_msg_idx]["content"] = self.attachment_manager.format_message_content(
                        self._get_content_text(current_content),
                        attachments
                    )
                else:
                    messages.append({"role": "user", "content": self.attachment_manager.format_message_content("", attachments)})

        if self.injection_guard:
            prompt_text_for_guard = prompt or "".join(
                self._get_content_text(m.get("content", ""))
                for m in (messages or [])
                if m.get("role") == "user"
            )
            result = self.injection_guard.scan(prompt_text_for_guard)
            if result.blocked:
                raise InjectionBlockedError(result)

        # Rate Limit check
        if self.rate_limit_manager:
            prompt_text = prompt or "".join(self._get_content_text(m.get("content", "")) for m in messages)
            est_tokens = self._estimate_tokens(prompt_text)
            await self.rate_limit_manager.get_limiter(model or group).acquire(est_tokens)

        # Guardrails: Mask prompt/messages in-flight
        if self.guardrail:
            if messages:
                new_messages = []
                for m in messages:
                    c = m.get("content")
                    if isinstance(c, str):
                        new_messages.append({**m, "content": self.guardrail.mask_prompt(c)})
                    elif isinstance(c, list):
                        new_parts = []
                        for part in c:
                            if isinstance(part, dict) and part.get("type") == "text":
                                new_parts.append({**part, "text": self.guardrail.mask_prompt(part.get("text", ""))})
                            else:
                                new_parts.append(part)
                        new_messages.append({**m, "content": new_parts})
                    else:
                        new_messages.append(m)
                messages = new_messages
            if prompt:
                prompt = self.guardrail.mask_prompt(prompt)

        # Context trim
        if self.auto_trim_context:
            messages = self._trim_messages(messages, model or group or "")

        # Semantic cache check — scoped to the resolved model.  Checking this
        # before model selection (the old behaviour) could replay a response
        # produced by a completely different model.
        if self._semantic_cache and (prompt or messages):
            _sc_query = prompt or " ".join(
                self._get_content_text(m.get("content", "")) for m in messages
            )
            _sc_hit = await self._semantic_cache.get(
                _sc_query, model=model or group or ""
            )
            if _sc_hit:
                logger.debug(f"Semantic cache hit for model={model}")
                self.metrics.inc_cache_hit("semantic")
                cached = _sc_hit.model_copy(deep=True)
                cached.cached = True
                saved_id = await self._save(
                    model=model or group or "", provider=cached.provider or "",
                    prompt=prompt or "", response=cached.content or "",
                    prompt_tokens=cached.prompt_tokens or 0,
                    completion_tokens=cached.completion_tokens or 0,
                    status="success", is_cached=True,
                    session_id=session_id or self.session_id,
                    user_id=user_id or self.user_id,
                    team_id=team_id or self.team_id,
                    workplace_id=workplace_id or self.workplace_id,
                    tags=tags or [], parent_request_id=parent_request_id,
                    turn_number=turn_number,
                )
                cached.request_id = saved_id or cached.request_id or cached.id
                return cached

        # Prompt cache check
        cache_key = None
        if cache_ttl:
            cache_key = self._cache_key(model or group or "", messages, kwargs)
            cached = await self._cache_get(cache_key)
            if cached:
                logger.debug(f"Prompt cache hit for model={model}")
                self.metrics.inc_cache_hit("prompt")
                cached = cached.model_copy(deep=True)
                cached.cached = True
                saved_id = await self._save(
                    model=model or group or "", provider=cached.provider or "",
                    prompt=prompt or "", response=cached.content or "",
                    prompt_tokens=cached.prompt_tokens or 0,
                    completion_tokens=cached.completion_tokens or 0,
                    status="success", is_cached=True,
                    session_id=session_id or self.session_id,
                    user_id=user_id or self.user_id,
                    team_id=team_id or self.team_id,
                    workplace_id=workplace_id or self.workplace_id,
                    tags=tags or [], parent_request_id=parent_request_id,
                    turn_number=turn_number,
                )
                cached.request_id = saved_id or cached.request_id or cached.id
                return cached

        # Before hook
        if self.on_before:
            try:
                await self.on_before(model or group or "", messages, kwargs)
            except Exception as e:
                logger.warning(f"on_before hook raised: {e}")

        req = CompletionRequest(
            model=model or group,
            messages=[Message(**m) for m in messages],
            **kwargs,
        )
        policy = RetryPolicy(
            max_retries=max_retries,
            retry_delay=retry_delay,
            backoff_factor=backoff_factor,
            max_delay=max_delay,
            jitter=jitter,
        )
        t0 = _time.monotonic()
        error_msg: Optional[str] = None
        error_type: Optional[str] = None
        status = "success"
        cancelled_at: Optional[float] = None
        response = None

        try:
            coro = self._stream_mgr.complete(
                req,
                retry_policy=policy,
                strategy=strategy,
                group=group,
                key_strategy=key_strategy,
                headers=headers,
            )
            response = await (asyncio.wait_for(coro, timeout=timeout) if timeout else coro)

            # Unmask response if guardrails are active
            if response and response.content and self.guardrail:
                response.content = self.guardrail.unmask_response(response.content)

            # Apply response redaction transforms
            if response and response.content and hasattr(self, "transforms"):
                response.content = self.transforms.transform_response_text(response.content)

            if validators and response:
                for validator in validators:
                    try:
                        result = validator(model or group or "", response)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as ve:
                        logger.warning(f"Response validator {validator.__name__!r} failed: {ve}")
                        raise

            if shadow_models and response:
                async def _shadow_call(shadow_model: str, _msgs: list, _kw: dict):
                    try:
                        shadow_resp = await self.complete(
                            shadow_model, messages=_msgs, **_kw
                        )
                        logger.info(
                            f"[Shadow] model={shadow_model} "
                            f"tokens={shadow_resp.prompt_tokens}+{shadow_resp.completion_tokens} "
                            f"latency={shadow_resp.latency_ms:.0f}ms"
                        )
                    except Exception as se:
                        logger.warning(f"[Shadow] model={shadow_model} failed: {se}")

                _shadow_kw = {k: v for k, v in kwargs.items()}
                for _sm in shadow_models:
                    asyncio.ensure_future(
                        _shadow_call(self._resolve_model(_sm), list(messages), _shadow_kw)
                    )

            # After hook
            if self.on_after:
                try:
                    await self.on_after(model or group or "", response)
                except Exception as e:
                    logger.warning(f"on_after hook raised: {e}")

        except asyncio.CancelledError:
            status = "cancelled"; cancelled_at = _time.time(); error_msg = "Request cancelled"
            error_type = "CancelledError"
            raise
        except asyncio.TimeoutError:
            status = "timeout"; error_msg = f"Exceeded {timeout}s timeout"
            error_type = "TimeoutError"
            raise
        except Exception as e:
            error_msg = str(e); status = "error"; error_type = type(e).__name__
            if self.on_error:
                try:
                    await self.on_error(model or group or "", e)
                except Exception:
                    pass
            raise
        finally:
            latency_ms = round((_time.monotonic() - t0) * 1000, 2)
            fallback_used = bool(getattr(response, "fallback_used", False))
            retries = int(getattr(response, "retries", 0) or 0)
            save_status = "fallback" if status == "success" and fallback_used else status
            cost = self._estimate_cost(
                model or group or "",
                getattr(response, "prompt_tokens", 0) or 0,
                getattr(response, "completion_tokens", 0) or 0,
            )
            if status == "success":
                self._check_budget(cost)
            if cost:
                self._total_cost_usd += cost
            price = self._get_pricing(model or group or "")
            saved_id = await self._save(
                model=model or group or "",
                provider=getattr(response, "provider", ""),
                prompt=prompt or "",
                response=getattr(response, "content", ""),
                prompt_tokens=getattr(response, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(response, "completion_tokens", 0) or 0,
                latency_ms=latency_ms,
                timeout_ms=timeout * 1000 if timeout else None,
                status=save_status, error=error_msg, cancelled_at=cancelled_at,
                fallback_used=fallback_used,
                retries=retries,
                has_tool_calls=bool(getattr(response, "tool_calls", None)),
                cost_usd=cost,
                input_cost_per_1k=price["input"] if price else None,
                output_cost_per_1k=price["output"] if price else None,
                session_id=session_id or self.session_id,
                user_id=user_id or self.user_id,
                team_id=team_id or self.team_id,
                workplace_id=workplace_id or self.workplace_id,
                tags=tags or [],
                parent_request_id=parent_request_id,
                turn_number=turn_number,
            )
            if response is not None:
                response.request_id = (
                    saved_id
                    or getattr(response, "request_id", None)
                    or getattr(response, "id", None)
                    or f"req-{secrets.token_hex(8)}"
                )
            try:
                self.metrics.record_request(
                    provider=getattr(response, "provider", "") or "",
                    model=model or group or "",
                    status=save_status,
                    latency_ms=latency_ms,
                    prompt_tokens=getattr(response, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(response, "completion_tokens", 0) or 0,
                    error_type=error_type,
                    fallback_used=fallback_used,
                )
            except Exception:
                pass

        # Cache the response
        if cache_key and response:
            await self._cache_set(cache_key, response, cache_ttl)

        # Semantic cache: store on success, scoped to the resolved model.
        if self._semantic_cache and response and status == "success":
            _sc_store_query = prompt or " ".join(
                self._get_content_text(m.get("content", "")) for m in messages
            )
            await self._semantic_cache.set(
                _sc_store_query, response, model=model or group or ""
            )

        if self.on_trace and response:
            try:
                trace_span = {
                    "name":               "veloroute.complete",
                    "model":              model or group or "",
                    "provider":           getattr(response, "provider", ""),
                    "status":             save_status,
                    "request_id":         getattr(response, "request_id", None),
                    "fallback_used":      getattr(response, "fallback_used", False),
                    "retries":            getattr(response, "retries", 0),
                    "latency_ms":         round((_time.monotonic() - t0) * 1000, 2),
                    "prompt_tokens":      getattr(response, "prompt_tokens", 0),
                    "completion_tokens":  getattr(response, "completion_tokens", 0),
                    "cost_usd":           self._estimate_cost(
                        model or group or "",
                        getattr(response, "prompt_tokens", 0),
                        getattr(response, "completion_tokens", 0),
                    ),
                    "session_id":         session_id or self.session_id,
                    "user_id":            user_id or self.user_id,
                    "tags":               tags or [],
                    "timestamp":          _time.time(),
                }
                _t = self.on_trace(trace_span)
                if asyncio.iscoroutine(_t):
                    await _t
            except Exception as te:
                logger.warning(f"on_trace hook raised: {te}")

        return response

    # ─── Inference: stream ────────────────────────────────────────────────────

    async def stream_events(
        self,
        model: Optional[str] = None,
        prompt: Optional[str] = None,
        messages: Optional[List[dict]] = None,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 30.0,
        jitter: bool = True,
        key_strategy: str = "round_robin",
        group: Optional[str] = None,
        strategy: Optional[RoutingStrategy] = None,
        stop_event: Optional[asyncio.Event] = None,
        timeout: Optional[float] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        workplace_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        parent_request_id: Optional[str] = None,
        turn_number: int = 0,
        attachments: Optional[List[Union[str, bytes, dict]]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> AsyncGenerator["StreamEvent", None]:
        """
        Stream structured events: content, reasoning, tool-call deltas, usage,
        finish reason and a terminal done event.

        Use this when proxying an OpenAI-compatible API or when reasoning /
        tool-call fidelity matters.  ``stream()`` remains the string-only
        convenience wrapper.
        """
        if not model and not group:
            raise ValueError("Must provide 'model' or 'group'.")

        if model:
            model = self._resolve_model(model)

        if messages is None:
            if prompt is None:
                raise ValueError("Provide either 'prompt' or 'messages'.")
            prompt, _, strategy = self._apply_slash_directives(prompt, None, strategy)
            if attachments:
                messages = [{"role": "user", "content": self.attachment_manager.format_message_content(prompt, attachments)}]
            else:
                messages = [{"role": "user", "content": prompt}]
        else:
            messages = [
                (m.model_dump(exclude_none=True) if hasattr(m, "model_dump") else (dict(m) if isinstance(m, dict) else dict(m.__dict__)))
                for m in messages
            ]
            prompt, messages, strategy = self._apply_slash_directives(prompt, messages, strategy)
            if attachments:
                user_msg_idx = None
                for idx in range(len(messages) - 1, -1, -1):
                    if messages[idx].get("role") == "user":
                        user_msg_idx = idx
                        break
                if user_msg_idx is not None:
                    current_content = messages[user_msg_idx].get("content", "")
                    messages[user_msg_idx]["content"] = self.attachment_manager.format_message_content(
                        self._get_content_text(current_content),
                        attachments
                    )
                else:
                    messages.append({"role": "user", "content": self.attachment_manager.format_message_content("", attachments)})

        # Rate Limit check
        if self.rate_limit_manager:
            prompt_text = prompt or "".join(self._get_content_text(m.get("content", "")) for m in messages)
            est_tokens = self._estimate_tokens(prompt_text)
            await self.rate_limit_manager.get_limiter(model or group).acquire(est_tokens)

        # Guardrails: Mask prompt/messages in-flight
        if self.guardrail:
            if messages:
                new_messages = []
                for m in messages:
                    c = m.get("content")
                    if isinstance(c, str):
                        new_messages.append({**m, "content": self.guardrail.mask_prompt(c)})
                    elif isinstance(c, list):
                        new_parts = []
                        for part in c:
                            if isinstance(part, dict) and part.get("type") == "text":
                                new_parts.append({**part, "text": self.guardrail.mask_prompt(part.get("text", ""))})
                            else:
                                new_parts.append(part)
                        new_messages.append({**m, "content": new_parts})
                    else:
                        new_messages.append(m)
                messages = new_messages
            if prompt:
                prompt = self.guardrail.mask_prompt(prompt)

        if self.auto_trim_context:
            messages = self._trim_messages(messages, model or group or "")

        req = CompletionRequest(
            model=model or group,
            messages=[Message(**m) for m in messages],
            stream=True,
            **kwargs,
        )
        policy = RetryPolicy(
            max_retries=max_retries,
            retry_delay=retry_delay,
            backoff_factor=backoff_factor,
            max_delay=max_delay,
            jitter=jitter,
        )
        t0 = _time.monotonic()
        deadline = (t0 + timeout) if timeout else None
        chunks: List[str] = []
        reasoning_chunks: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        usage: Dict[str, int] = {}
        error_msg: Optional[str] = None
        error_type: Optional[str] = None
        status = "success"
        cancelled_at: Optional[float] = None
        first_chunk_at: Optional[float] = None
        provider = ""
        response_id = ""
        finish_reason: Optional[str] = None
        fallback_used = False
        retries = 0
        completed = False

        def _event(etype: str, **fields) -> "StreamEvent":
            return StreamEvent(
                type=etype,
                model=model or group or "",
                provider=provider,
                id=response_id or None,
                fallback_used=fallback_used,
                retries=retries,
                **fields,
            )

        try:
            async for raw in self._stream_mgr.safe_stream_events(
                req,
                stop_event=stop_event,
                retry_policy=policy,
                strategy=strategy,
                group=group,
                key_strategy=key_strategy,
                headers=headers,
            ):
                if deadline and _time.monotonic() > deadline:
                    status = "timeout"; error_msg = f"Stream exceeded {timeout}s"; cancelled_at = _time.time()
                    error_type = "TimeoutError"
                    break
                if stop_event and stop_event.is_set():
                    status = "cancelled"; cancelled_at = _time.time(); error_msg = "Stream cancelled by caller"
                    error_type = "CancelledError"
                    break

                etype = raw.get("type")
                provider = raw.get("provider") or provider
                response_id = raw.get("id") or response_id
                if "fallback_used" in raw:
                    fallback_used = bool(raw["fallback_used"])
                if "retries" in raw:
                    retries = int(raw["retries"] or 0)

                if etype == "content":
                    text = raw.get("text") or ""
                    if not text:
                        continue
                    if self.guardrail:
                        text = self.guardrail.unmask_response(text)
                    if first_chunk_at is None:
                        first_chunk_at = _time.monotonic()
                    chunks.append(text)
                    yield _event("content", content=text)

                elif etype == "reasoning":
                    text = raw.get("text") or ""
                    if not text:
                        continue
                    if self.guardrail:
                        text = self.guardrail.unmask_response(text)
                    if first_chunk_at is None:
                        first_chunk_at = _time.monotonic()
                    reasoning_chunks.append(text)
                    yield _event("reasoning", reasoning_content=text)

                elif etype == "tool_call":
                    tc = raw.get("tool_call") or {}
                    if tc:
                        tool_calls.append(tc)
                        yield _event("tool_call", tool_call=tc)

                elif etype == "usage":
                    raw_usage = raw.get("usage") or {}
                    if isinstance(raw_usage, dict):
                        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                            if raw_usage.get(k) is not None:
                                usage[k] = int(raw_usage[k])
                    yield _event("usage", usage=dict(usage))

                elif etype == "finish":
                    finish_reason = raw.get("finish_reason") or finish_reason
                    yield _event("finish", finish_reason=finish_reason)

                elif etype == "error":
                    status = "error"
                    error_msg = raw.get("error") or "Stream failed"
                    error_type = raw.get("error_type") or "StreamError"
                    yield _event("error", error=error_msg)
                    break

                elif etype == "done":
                    completed = True
                    if finish_reason is None:
                        finish_reason = raw.get("finish_reason")
                    yield _event("done", finish_reason=finish_reason or "stop")
                    break

            if not completed and status == "success" and not error_msg:
                # Provider ended without an explicit sentinel.
                completed = True
                if finish_reason is None:
                    finish_reason = "tool_calls" if tool_calls else "stop"
                yield _event("done", finish_reason=finish_reason)

        except asyncio.CancelledError:
            status = "cancelled"; cancelled_at = _time.time(); error_msg = "Stream task cancelled"
            error_type = "CancelledError"
            raise
        except GeneratorExit:
            status = "cancelled"; cancelled_at = _time.time(); error_msg = "Stream consumer closed"
            error_type = "GeneratorExit"
            raise
        except Exception as e:
            error_msg = str(e); status = "error"; error_type = type(e).__name__
            raise
        finally:
            latency_ms = round((_time.monotonic() - t0) * 1000, 2)
            ttft = round((first_chunk_at - t0) * 1000, 2) if first_chunk_at else None

            response_text = "".join(chunks)
            if self.guardrail:
                response_text = self.guardrail.unmask_response(response_text)

            prompt_text = prompt or "".join(self._get_content_text(m.get("content", "")) for m in (messages or []))
            prompt_tokens = int(usage.get("prompt_tokens") or self._estimate_tokens(prompt_text))
            if usage.get("completion_tokens"):
                completion_tokens = int(usage["completion_tokens"])
            else:
                completion_tokens = self._estimate_tokens(
                    response_text
                    + "".join(reasoning_chunks)
                    + json.dumps(tool_calls, default=str)
                )

            cost = self._estimate_cost(
                model or group or "",
                prompt_tokens,
                completion_tokens,
            )
            if status == "success":
                self._check_budget(cost)
            if cost:
                self._total_cost_usd += cost

            price = self._get_pricing(model or group or "")
            save_status = "fallback" if status == "success" and fallback_used else status
            await self._save(
                model=model or group or "", provider=provider,
                prompt=prompt or "", response=response_text,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms, time_to_first_token_ms=ttft,
                timeout_ms=timeout * 1000 if timeout else None,
                status=save_status, error=error_msg, cancelled_at=cancelled_at,
                fallback_used=fallback_used,
                retries=retries,
                has_tool_calls=bool(tool_calls),
                session_id=session_id or self.session_id,
                user_id=user_id or self.user_id,
                team_id=team_id or self.team_id,
                workplace_id=workplace_id or self.workplace_id,
                tags=tags or [],
                parent_request_id=parent_request_id,
                turn_number=turn_number,
            )
            try:
                self.metrics.record_request(
                    provider=provider,
                    model=model or group or "",
                    status=save_status,
                    latency_ms=latency_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    error_type=error_type,
                    fallback_used=fallback_used,
                )
            except Exception:
                pass

    async def stream(self, *args, **kwargs) -> AsyncGenerator[str, None]:
        """
        Stream plain text content (backwards-compatible).

        Delegates to :meth:`stream_events` and yields only content deltas.
        Reasoning content, tool calls and usage are still recorded in storage
        and metrics; use ``stream_events()`` to consume them.
        """
        async for event in self.stream_events(*args, **kwargs):
            if event.type == "content" and event.content:
                yield event.content

    # ─── Structured output ────────────────────────────────────────────────────

    async def complete_structured(
        self,
        model: str,
        prompt: Optional[str] = None,
        messages: Optional[List[dict]] = None,
        schema: Type[T] = None,
        group: Optional[str] = None,
        strategy: Optional[RoutingStrategy] = None,
        max_retries_parse: int = 2,
        use_tool_format: bool = True,   # ← True by default: tool-calling is more reliable
        **kwargs,
    ) -> T:
        """
        Complete and return a strictly validated Pydantic object.

        Args:
            model:    Model to use.
            prompt:   The prompt text.
            messages: Alternatively, full message list.
            schema:   Pydantic model class to validate output against.
            group:    Optional group ID for routing.
            strategy: Optional RoutingStrategy override.
        """
        if schema is None:
            raise ValueError("schema= is required for complete_structured()")

        # ── Build base messages ──────────────────────────────────────────────
        if messages is None:
            if prompt is None:
                raise ValueError("Provide either 'prompt' or 'messages'.")
            base_messages = [{"role": "user", "content": prompt}]
        else:
            base_messages = list(messages)

        # ════════════════════════════════════════════════════════════════════
        # MODE A — Tool-calling (default, most reliable)
        # The schema is converted into an OpenAI function definition.
        # The model MUST call it, so fields arrive pre-parsed — zero JSON
        # parsing headaches, zero markdown stripping.
        # ════════════════════════════════════════════════════════════════════
        if use_tool_format:
            tool_name = f"extract_{schema.__name__.lower()}"
            tool_def = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": (
                        f"Extract and return structured data as a {schema.__name__} object. "
                        "Fill every field accurately based on the conversation."
                    ),
                    "parameters": schema.model_json_schema(),
                },
            }

            response = await self.complete(
                model,
                group=group,
                strategy=strategy,
                messages=base_messages,
                tools=[tool_def],
                tool_choice={"type": "function", "function": {"name": tool_name}},
                **kwargs,
            )

            # Parse the tool-call arguments if the model returned one
            raw_tool_calls = getattr(response, "tool_calls", None) or []
            for tc in raw_tool_calls:
                fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
                if fn.get("name") == tool_name:
                    args_raw = fn.get("arguments", "{}")
                    try:
                        data = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                        return schema.model_validate(data)
                    except Exception as e:
                        logger.warning(
                            f"complete_structured tool-call parse failed ({e}); "
                            "falling back to JSON-prompt mode."
                        )
                        break  # fall through to MODE B below

            # No tool_calls in response — provider doesn't support it; fall back
            logger.info(
                "complete_structured: no tool_calls in response — "
                "retrying with JSON-prompt fallback."
            )

        # ════════════════════════════════════════════════════════════════════
        # MODE B — JSON-prompt (legacy / explicit fallback)
        # The model is asked to output plain JSON. We parse it ourselves,
        # with self-correction loops on failure.
        # ════════════════════════════════════════════════════════════════════
        schema_hint = (
            f"Reply ONLY with valid JSON matching this schema: "
            f"{json.dumps(schema.model_json_schema(), indent=2)}\n"
            "Do not include any text outside the JSON object."
        )
        fb_messages = [{"role": "system", "content": schema_hint}] + base_messages

        last_error = None
        raw = ""
        for attempt in range(max_retries_parse + 1):
            response = await self.complete(model, group=group, strategy=strategy, messages=fb_messages, **kwargs)
            raw = (response.content or "").strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            try:
                data = json.loads(raw)
                return schema.model_validate(data)
            except Exception as e:
                last_error = e
                logger.warning(
                    f"complete_structured JSON-prompt attempt {attempt+1} failed: {e}"
                )
                if attempt < max_retries_parse:
                    # Self-correction: feed the bad output + error back to the model
                    fb_messages = list(fb_messages) + [
                        {"role": "assistant", "content": raw},
                        {
                            "role": "user",
                            "content": (
                                f"The response was not valid JSON or did not match the schema.\n"
                                f"Validation error: {e}\n"
                                "Please output ONLY a valid JSON object that matches the schema."
                            ),
                        },
                    ]

        raise StructuredOutputError(
            f"Failed to parse LLM response into {schema.__name__} after "
            f"{max_retries_parse+1} attempts: {last_error}",
            raw_response=raw,
        )

    # ─── Agentic tool loop ────────────────────────────────────────────────────

    async def complete_with_tools(
        self,
        model: str,
        prompt: Optional[str] = None,
        messages: Optional[List[dict]] = None,
        tools: Optional[List[dict]] = None,
        tool_executor: Optional[Callable] = None,
        max_tool_calls: int = 10,
        group: Optional[str] = None,
        strategy: Optional[RoutingStrategy] = None,
        timeout: Optional[float] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        **kwargs,
    ) -> CompletionResponse:
        """
        Run a full agentic tool-calling loop.

        Automatically:
          1. Calls the LLM with your tools list
          2. Detects tool_calls in the response
          3. Executes each tool via tool_executor(name, arguments) -> result
          4. Appends tool results to messages and loops
          5. Stops when the model returns a final text response (no tool calls)
          6. Raises MaxToolCallsExceededError if max_tool_calls is exceeded
          7. Saves every intermediate request + tool call to storage

        Args:
            model:          "provider/model-name"
            prompt:         User prompt (or pass messages=)
            messages:       Full messages list (overrides prompt)
            tools:          OpenAI-format tool definitions list
            tool_executor:  async or sync callable: (name: str, arguments: dict) -> Any
                            Return value is JSON-serialized and sent back to the LLM
            max_tool_calls: Hard cap on total tool calls (default: 10)
            timeout:        Per-turn timeout in seconds

        Usage::

            async def my_tools(name, args):
                if name == "get_weather":
                    return {"temp": 18, "city": args["city"]}
                if name == "search":
                    return {"results": ["doc1", "doc2"]}

            final = await client.complete_with_tools(
                "openai/gpt-4o",
                prompt="What is the weather in London and Paris?",
                tools=[get_weather_schema, search_schema],
                tool_executor=my_tools,
                max_tool_calls=6,
            )
            print(final.content)
        """
        model = self._resolve_model(model)

        # Normalize tools: accept Tool objects or raw dicts
        if tools:
            tools = [
                t.to_dict() if isinstance(t, Tool) else t
                for t in tools
            ]

        if messages is None:
            if prompt is None:
                raise ValueError("Provide either 'prompt' or 'messages'.")
            messages = [{"role": "user", "content": prompt}]

        messages = list(messages)  # local copy
        tool_call_count = 0
        parent_req_id: Optional[str] = None

        while True:
            response = await self.complete(
                model,
                messages=messages,
                tools=tools or [],
                timeout=timeout,
                session_id=session_id or self.session_id,
                user_id=user_id or self.user_id,
                tags=tags,
                parent_request_id=parent_req_id,
                turn_number=tool_call_count,
                **kwargs,
            )

            # Track parent chain
            if hasattr(response, "request_id"):
                parent_req_id = response.request_id

            # Check if the model wants to call tools
            raw_tool_calls = getattr(response, "tool_calls", None) or []

            if not raw_tool_calls:
                # No tool calls — this is the final response
                return response

            # Append the assistant turn with tool calls to messages
            messages.append({
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": raw_tool_calls,
            })

            # Execute each tool call
            for tc in raw_tool_calls:
                if tool_call_count >= max_tool_calls:
                    raise MaxToolCallsExceededError(
                        tool_call_count=tool_call_count,
                        max_tool_calls=max_tool_calls,
                        partial_messages=messages,
                    )

                tc_id   = tc.get("id", "")
                tc_name = tc.get("function", {}).get("name", "")
                tc_args_raw = tc.get("function", {}).get("arguments", "{}")

                try:
                    tc_args = json.loads(tc_args_raw) if isinstance(tc_args_raw, str) else tc_args_raw
                except json.JSONDecodeError:
                    tc_args = {}

                # Execute
                if tool_executor:
                    if asyncio.iscoroutinefunction(tool_executor):
                        result = await tool_executor(tc_name, tc_args)
                    else:
                        result = tool_executor(tc_name, tc_args)
                else:
                    result = {"error": f"No tool_executor registered for '{tc_name}'"}

                result_str = json.dumps(result) if not isinstance(result, str) else result

                # Save tool call to storage
                if self.storage:
                    try:
                        from veloroute.storage.models import ToolCall as _TC
                        _tc_obj = _TC(
                            request_id=parent_req_id or "",
                            session_id=session_id or self.session_id,
                            user_id=user_id or self.user_id,
                            name=tc_name,
                            arguments=tc_args,
                            arguments_raw=tc_args_raw if isinstance(tc_args_raw, str) else json.dumps(tc_args_raw),
                            result=result_str,
                            executed_at=_time.time(),
                            status="success",
                        )
                        await self.storage.save_tool_call(_tc_obj)
                    except Exception as e:
                        logger.warning(f"Tool call storage save failed: {e}")

                # Append tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result_str,
                })
                tool_call_count += 1

    # ─── Batch completions ────────────────────────────────────────────────────

    async def complete_batch(
        self,
        model: str,
        prompts: List[str],
        max_retries: int = 2,
        retry_delay: float = 1.0,
        timeout: Optional[float] = None,
        cache_ttl: Optional[float] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        concurrency: int = 5,
        **kwargs,
    ) -> List[Optional[CompletionResponse]]:
        """
        Run multiple prompts in parallel against the same model.

        Returns a list in the same order as prompts. Failed items return None.

        Usage::

            responses = await client.complete_batch(
                "openai/gpt-4o-mini",
                ["Explain RAG", "Explain LoRA", "Explain RLHF"],
                concurrency=3,
            )
        """
        sem = asyncio.Semaphore(concurrency)

        async def _one(p: str) -> Optional[CompletionResponse]:
            async with sem:
                try:
                    return await self.complete(
                        model, prompt=p,
                        max_retries=max_retries, retry_delay=retry_delay,
                        timeout=timeout, cache_ttl=cache_ttl,
                        session_id=session_id, user_id=user_id, tags=tags,
                        **kwargs,
                    )
                except Exception as e:
                    logger.warning(f"Batch item failed: {e}")
                    return None

        return list(await asyncio.gather(*[_one(p) for p in prompts]))

    # ─── Embeddings ──────────────────────────────────────────────────────────

    async def embed(
        self,
        model: str,
        input: Union[str, List[str]],
        dimensions: Optional[int] = None,
        encoding_format: Optional[str] = None,
        user: Optional[str] = None,
        strategy: Optional[RoutingStrategy] = None,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 30.0,
        jitter: bool = True,
        key_strategy: str = "round_robin",
        timeout: Optional[float] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        **kwargs,
    ) -> EmbeddingResponse:
        """
        Generate embeddings with intelligent routing, key rotation, and circuit breaking.
        """
        resolved_model = self._resolve_model(model)
        route = self.router.get_route(resolved_model, strategy=strategy)
        req = EmbeddingRequest(
            model=resolved_model,
            input=input,
            dimensions=dimensions,
            encoding_format=encoding_format,
            user=user,
        )
        policy = RetryPolicy(
            max_retries=max_retries,
            retry_delay=retry_delay,
            backoff_factor=backoff_factor,
            max_delay=max_delay,
            jitter=jitter,
        )
        state = SmartRetryState(policy)
        errors: List[Exception] = []
        t0 = _time.monotonic()
        status = "success"
        error_msg = None
        response = None

        try:
            for provider_name, model_name in route:
                if provider_name not in self._providers:
                    continue
                provider = self._providers[provider_name]
                keys_tried = 0
                max_keys = max(policy.max_retries + 1, self.key_manager.key_count(provider_name)["total"])

                while keys_tried < max_keys:
                    key = self.key_manager.get_next_key(provider_name, strategy=key_strategy)
                    if not key:
                        break
                    keys_tried += 1

                    prov_req = req.model_copy()
                    prov_req.model = model_name or resolved_model

                    try:
                        call_coro = provider.embeddings(prov_req, api_key=key, timeout=timeout)
                        response = await (asyncio.wait_for(call_coro, timeout=timeout) if timeout else call_coro)
                        self.key_manager.report_success(provider_name, key)
                        self.router.record_latency(provider_name, response.latency_ms or 50.0)
                        return response

                    except AuthenticationError as e:
                        self.key_manager.report_error(provider_name, key, "auth")
                        errors.append(e)
                        continue

                    except (RateLimitError, QuotaExceededError) as e:
                        err_type = "rate_limit" if isinstance(e, RateLimitError) else "quota"
                        self.key_manager.report_error(provider_name, key, err_type)
                        self.router.record_latency(provider_name, 30000.0)
                        errors.append(e)
                        has_alt = self.key_manager.key_count(provider_name)["active"] > 0
                        await state.wait_if_needed(provider_name, has_alt)
                        if has_alt:
                            continue
                        break

                    except PermissionDeniedError as e:
                        errors.append(e)
                        break

                    except (BadRequestError, ContentPolicyError, ContextWindowError) as e:
                        errors.append(e)
                        break

                    except VeloRouteError as e:
                        self.key_manager.report_error(provider_name, key, "server")
                        self.router.record_latency(provider_name, 30000.0)
                        errors.append(e)
                        has_alt = self.key_manager.key_count(provider_name)["active"] > 0
                        await state.wait_if_needed(provider_name, has_alt)
                        if has_alt:
                            continue
                        break

                    except Exception as e:
                        errors.append(e)
                        break

                if not state.has_budget and errors:
                    break

            raise AllProvidersFailedError(errors)

        except Exception as e:
            status = "error"
            error_msg = str(e)
            raise
        finally:
            latency_ms = round((_time.monotonic() - t0) * 1000, 2)
            total_tokens = getattr(getattr(response, "usage", None), "total_tokens", 0)
            await self._save(
                model=model,
                provider=getattr(response, "provider", ""),
                prompt=str(input)[:500],
                response=f"[Embedding {len(response.data) if response else 0} vectors]",
                prompt_tokens=total_tokens,
                completion_tokens=0,
                latency_ms=latency_ms,
                timeout_ms=timeout * 1000 if timeout else None,
                status=status,
                error=error_msg,
                session_id=session_id or self.session_id,
                user_id=user_id or self.user_id,
                team_id=team_id or self.team_id,
                tags=tags or [],
            )

    # ─── Audio ───────────────────────────────────────────────────────────────

    async def image_generate(
        self,
        model: str,
        prompt: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        key_strategy: str = "round_robin",
        max_retries: int = 2,
        retry_delay: float = 1.0,
        strategy: Optional[RoutingStrategy] = None,
    ) -> dict:
        """Generate images with the configured route, key pools and fallbacks.

        Image costs are provider-specific and are not inferred from token prices.
        Callers that enforce a spend budget must supply a separate image price.
        """
        resolved_model = self._resolve_model(model)
        route = self.router.get_route(resolved_model, strategy=strategy)
        policy = RetryPolicy(max_retries=max_retries, retry_delay=retry_delay)
        state = SmartRetryState(policy)
        errors: List[Exception] = []

        for provider_name, model_name in route:
            if provider_name not in self._providers:
                continue
            provider = self._providers[provider_name]
            keys_tried = 0
            max_keys = max(
                policy.max_retries + 1,
                self.key_manager.key_count(provider_name)["total"],
            )
            while keys_tried < max_keys:
                key = self.key_manager.get_next_key(
                    provider_name, strategy=key_strategy
                )
                if not key:
                    break
                keys_tried += 1
                request_payload = dict(params or {})
                request_payload["model"] = model_name or resolved_model
                request_payload["prompt"] = prompt
                try:
                    result = await provider.image_generations(
                        request_payload, api_key=key, headers=headers
                    )
                    self.key_manager.report_success(provider_name, key)
                    return result
                except AuthenticationError as exc:
                    self.key_manager.report_error(provider_name, key, "auth")
                    errors.append(exc)
                    continue
                except (RateLimitError, QuotaExceededError) as exc:
                    error_type = "rate_limit" if isinstance(exc, RateLimitError) else "quota"
                    self.key_manager.report_error(provider_name, key, error_type)
                    errors.append(exc)
                    has_alt = self.key_manager.key_count(provider_name)["active"] > 0
                    await state.wait_if_needed(provider_name, has_alt)
                    if has_alt:
                        continue
                    break
                except VeloRouteError as exc:
                    self.key_manager.report_error(provider_name, key, "server")
                    errors.append(exc)
                    # Invalid input and policy failures should not be repeated
                    # with another credential for the same provider.
                    if 400 <= exc.status_code < 500:
                        break
                    has_alt = self.key_manager.key_count(provider_name)["active"] > 0
                    await state.wait_if_needed(provider_name, has_alt)
                    if has_alt:
                        continue
                    break
                except Exception as exc:
                    self.key_manager.report_error(provider_name, key, "server")
                    errors.append(exc)
                    break

            if not state.has_budget and errors:
                break
        raise AllProvidersFailedError(errors)

    # ─── Audio ───────────────────────────────────────────────────────────────

    async def audio_transcribe(
        self,
        file_bytes: bytes,
        filename: str,
        model: str = "whisper-1",
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        response_format: str = "json",
        temperature: Optional[float] = None,
        key_strategy: str = "round_robin",
        max_retries: int = 2,
        retry_delay: float = 1.0,
        strategy: Optional[RoutingStrategy] = None,
    ) -> dict:
        """Transcribe audio with route fallback, key rotation, and error resilience."""
        resolved_model = self._resolve_model(model)
        route = self.router.get_route(resolved_model, strategy=strategy)
        policy = RetryPolicy(max_retries=max_retries, retry_delay=retry_delay)
        state = SmartRetryState(policy)
        errors: List[Exception] = []

        for provider_name, model_name in route:
            if provider_name not in self._providers:
                continue
            provider = self._providers[provider_name]
            keys_tried = 0
            max_keys = max(policy.max_retries + 1, self.key_manager.key_count(provider_name)["total"])

            while keys_tried < max_keys:
                key = self.key_manager.get_next_key(provider_name, strategy=key_strategy)
                if not key:
                    break
                keys_tried += 1

                try:
                    res = await provider.audio_transcriptions(
                        file_bytes=file_bytes,
                        filename=filename,
                        model=model_name or "whisper-1",
                        api_key=key,
                        language=language,
                        prompt=prompt,
                        response_format=response_format,
                        temperature=temperature,
                    )
                    self.key_manager.report_success(provider_name, key)
                    return res
                except AuthenticationError as e:
                    self.key_manager.report_error(provider_name, key, "auth")
                    errors.append(e)
                    continue
                except (RateLimitError, QuotaExceededError) as e:
                    err_type = "rate_limit" if isinstance(e, RateLimitError) else "quota"
                    self.key_manager.report_error(provider_name, key, err_type)
                    errors.append(e)
                    has_alt = self.key_manager.key_count(provider_name)["active"] > 0
                    await state.wait_if_needed(provider_name, has_alt)
                    if has_alt:
                        continue
                    break
                except (PermissionDeniedError, BadRequestError, ContentPolicyError) as e:
                    errors.append(e)
                    break
                except Exception as e:
                    self.key_manager.report_error(provider_name, key, "server")
                    errors.append(e)
                    has_alt = self.key_manager.key_count(provider_name)["active"] > 0
                    await state.wait_if_needed(provider_name, has_alt)
                    if has_alt:
                        continue
                    break

            if not state.has_budget and errors:
                break

        raise AllProvidersFailedError(errors)

    async def audio_speech(
        self,
        input_text: str,
        model: str = "tts-1",
        voice: str = "alloy",
        response_format: str = "mp3",
        speed: float = 1.0,
        key_strategy: str = "round_robin",
        max_retries: int = 2,
        retry_delay: float = 1.0,
        strategy: Optional[RoutingStrategy] = None,
    ) -> bytes:
        """Generate text-to-speech audio bytes with route fallback and key rotation."""
        resolved_model = self._resolve_model(model)
        route = self.router.get_route(resolved_model, strategy=strategy)
        policy = RetryPolicy(max_retries=max_retries, retry_delay=retry_delay)
        state = SmartRetryState(policy)
        errors: List[Exception] = []

        for provider_name, model_name in route:
            if provider_name not in self._providers:
                continue
            provider = self._providers[provider_name]
            keys_tried = 0
            max_keys = max(policy.max_retries + 1, self.key_manager.key_count(provider_name)["total"])

            while keys_tried < max_keys:
                key = self.key_manager.get_next_key(provider_name, strategy=key_strategy)
                if not key:
                    break
                keys_tried += 1

                try:
                    res = await provider.audio_speech(
                        input_text=input_text,
                        model=model_name or "tts-1",
                        voice=voice,
                        api_key=key,
                        response_format=response_format,
                        speed=speed,
                    )
                    self.key_manager.report_success(provider_name, key)
                    return res
                except AuthenticationError as e:
                    self.key_manager.report_error(provider_name, key, "auth")
                    errors.append(e)
                    continue
                except (RateLimitError, QuotaExceededError) as e:
                    err_type = "rate_limit" if isinstance(e, RateLimitError) else "quota"
                    self.key_manager.report_error(provider_name, key, err_type)
                    errors.append(e)
                    has_alt = self.key_manager.key_count(provider_name)["active"] > 0
                    await state.wait_if_needed(provider_name, has_alt)
                    if has_alt:
                        continue
                    break
                except (PermissionDeniedError, BadRequestError, ContentPolicyError) as e:
                    errors.append(e)
                    break
                except Exception as e:
                    self.key_manager.report_error(provider_name, key, "server")
                    errors.append(e)
                    has_alt = self.key_manager.key_count(provider_name)["active"] > 0
                    await state.wait_if_needed(provider_name, has_alt)
                    if has_alt:
                        continue
                    break

            if not state.has_budget and errors:
                break

        raise AllProvidersFailedError(errors)

    # ─── Context manager support ─────────────────────────────────────────────

    async def __aenter__(self):
        if self.storage:
            await self.storage.connect()
        return self

    async def __aexit__(self, *_):
        if self.storage:
            await self.storage.disconnect()

    def __repr__(self) -> str:
        return (
            f"VeloRoute(providers={self.get_providers()}, "
            f"strategy={self.router.strategy.value}, "
            f"storage={'yes' if self.storage else 'no'}, "
            f"cost=${self._total_cost_usd:.4f})"
        )


# Compatibility alias
LLMClient = VeloRoute
