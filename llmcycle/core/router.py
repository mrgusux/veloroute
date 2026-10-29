"""
ModelRouter - Sort-Order Routing & Fallback
============================================
Supports:
  - Priority-ordered fallback chains per model/provider
  - RoutingStrategy enum: PRIORITY | ROUND_ROBIN | LOWEST_LATENCY
  - Latency tracking with EWMA (exponentially weighted moving average)
"""
from __future__ import annotations
import time
import threading
import logging
from enum import Enum
from typing import Any, List, Dict, Optional, Tuple

from llmcycle.utils import parse_model

logger = logging.getLogger(__name__)


class RoutingStrategy(Enum):
    PRIORITY       = "priority"        # follow explicit sort order
    ROUND_ROBIN    = "round_robin"     # cycle across all providers
    LOWEST_LATENCY = "lowest_latency"  # pick the statistically fastest
    CANARY         = "canary"          # canary percentage traffic splits
    WEIGHTED       = "weighted"        # weight-based routing
    COST_OPTIMIZED = "cost_optimized"  # route to cheapest provider first
    ACTIVE_FIRST   = "active_first"    # prioritize active providers (healthy keys)
    LEAST_BUSY     = "least_busy"      # route to provider with lowest active/total usage
    USAGE_BASED    = "usage_based"     # alias for least_busy


class LatencyTracker:
    """Per-provider EWMA latency tracking."""
    ALPHA = 0.3  # smoothing factor

    def __init__(self):
        self._latencies: Dict[str, float] = {}
        self._lock = threading.Lock()

    def record(self, provider: str, latency_ms: float):
        with self._lock:
            prev = self._latencies.get(provider, latency_ms)
            self._latencies[provider] = self.ALPHA * latency_ms + (1 - self.ALPHA) * prev

    def get(self, provider: str) -> float:
        return self._latencies.get(provider, 999999.0)

    def all(self) -> Dict[str, float]:
        return dict(self._latencies)


def infer_provider(model_name: str, configured_providers: Optional[List[str]] = None) -> Optional[str]:
    """Infer the target provider for a bare model name based on known model family patterns."""
    m = model_name.lower().strip()
    configured = [p.lower() for p in (configured_providers or [])]

    # Model family mappings (prefixes -> prioritized candidates)
    families = [
        (("gpt-", "o1-", "o3-", "chatgpt-", "text-embedding-", "whisper-", "tts-", "dall-e-", "davinci"), ["openai", "azure"]),
        (("claude-",), ["anthropic"]),
        (("gemini-",), ["gemini", "google", "vertexai"]),
        (("deepseek-",), ["deepseek"]),
        (("command-", "embed-english-", "embed-multilingual-"), ["cohere"]),
        (("mistral-", "codestral-", "pixtral-"), ["mistral"]),
        (("grok-",), ["xai"]),
        (("llama-", "mixtral-"), ["groq", "together", "fireworks", "deepinfra", "openrouter"]),
        (("qwen-",), ["dashscope", "together", "groq", "openrouter"]),
    ]

    for prefixes, candidates in families:
        if any(m.startswith(prefix) for prefix in prefixes):
            # Prefer configured provider if available
            for cand in candidates:
                if cand in configured:
                    return cand
            return candidates[0]

    # If only 1 provider is configured and model is bare, default to that provider
    if configured and len(configured) == 1:
        return configured[0]

    return None


class ModelRouter:
    """
    Determines the ordered list of (provider, model) pairs to try for a request.

    Fallback config format:
        {
          "openai/gpt-4o": ["anthropic/claude-3-5-sonnet", "groq/llama-3.1-70b"],
          "groq": ["together", "fireworks"],   # provider-level fallback
          "logical-model": {"openai/gpt-4o-mini": 0.85, "groq/llama-3.1-70b": 0.15}  # Canary/Weighted routing
        }
    """

    def __init__(
        self,
        fallbacks: Optional[Dict[str, Any]] = None,
        strategy: RoutingStrategy = RoutingStrategy.PRIORITY,
        pricing: Optional[Dict[str, Dict[str, float]]] = None,
        groups=None, # Optional[Union[Dict[str, List[str]], GroupManager]]
        key_manager=None, # Optional[KeyManager]
        aliases: Optional[Dict[str, str]] = None,
    ):
        self.fallbacks = fallbacks or {}
        self.strategy  = strategy
        self.pricing   = pricing or {}   # shared with client — same DEFAULT_PRICING dict
        self.aliases   = aliases or {}   # virtual model aliasing: "smart" -> "openai/gpt-4o"
        
        # If passed a dict, wrap it in GroupManager. Otherwise keep it.
        from llmcycle.core.groups import GroupManager
        if isinstance(groups, dict) or groups is None:
            self.groups = GroupManager(groups)
        else:
            self.groups = groups
            
        self.key_manager = key_manager
        self.latency   = LatencyTracker()
        self._rr_index: Dict[str, int] = {}
        self._lock     = threading.Lock()
        self.storage   = None

    def alias(self, name: str, target: str) -> None:
        """Register a model alias."""
        with self._lock:
            self.aliases[name] = target

    def remove_alias(self, name: str) -> bool:
        """Remove a model alias."""
        with self._lock:
            return self.aliases.pop(name, None) is not None

    def resolve_model(self, model: str) -> str:
        """Resolve model alias chains (up to 5 hops to prevent cycles)."""
        curr = model
        visited = set()
        while curr in self.aliases and curr not in visited and len(visited) < 5:
            visited.add(curr)
            curr = self.aliases[curr]
        return curr

    def get_route(self, model: str, strategy: Optional[RoutingStrategy] = None) -> List[Tuple[str, str]]:
        """
        Returns ordered list of (provider, model) tuples to try.
        Input model format: "provider/model" or just "model", or an alias.
        """
        current_strategy = strategy or self.strategy
        model = self.resolve_model(model)

        # Under CANARY or WEIGHTED strategies, look up if a dictionary weight split is configured
        if current_strategy in (RoutingStrategy.CANARY, RoutingStrategy.WEIGHTED):
            primary_p, _ = parse_model(model)
            fb_val = self.fallbacks.get(model) or self.fallbacks.get(primary_p)
            if isinstance(fb_val, dict) and fb_val:
                import random
                choices = list(fb_val.keys())
                weights = list(fb_val.values())
                selected = random.choices(choices, weights=weights, k=1)[0]

                # Make selected primary, followed by the rest as fallback order sorted by weight descending
                remaining = [c for c in choices if c != selected]
                remaining.sort(key=lambda c: fb_val[c], reverse=True)

                candidates = [parse_model(selected)] + [parse_model(r) for r in remaining]
                return self._apply_strategy(candidates, model, strategy=current_strategy)

        # Handle groups
        if model in self.groups:
            candidates = [parse_model(m) for m in self.groups.get(model)]
            return self._apply_strategy(candidates, model, strategy=current_strategy)

        from llmcycle.providers.registry import PROVIDER_REGISTRY

        primary_provider, primary_model = parse_model(model)

        # If bare model name (no slash), check if we can infer the provider
        if "/" not in model:
            configured = self.key_manager.list_providers() if self.key_manager else []
            if primary_provider not in [c.lower() for c in configured]:
                inferred = infer_provider(primary_model, configured)
                if inferred:
                    primary_provider = inferred

        # Look up fallbacks by full key ("openai/gpt-4o") or provider key ("openai")
        fb_key = f"{primary_provider}/{primary_model}" if primary_provider != primary_model else primary_provider
        fb_list = self.fallbacks.get(model) or self.fallbacks.get(fb_key) or self.fallbacks.get(primary_provider, [])

        # If it's a list, treat normally. If it's a dict, use keys.
        if isinstance(fb_list, dict):
            # Sort dict keys by weight descending as default ordering
            fb_keys_sorted = list(fb_list.keys())
            fb_keys_sorted.sort(key=lambda k: fb_list[k], reverse=True)
            fb_list = fb_keys_sorted

        # Check if model/primary_provider is a known provider or model path
        is_known = (
            "/" in model
            or primary_provider.upper() in PROVIDER_REGISTRY
            or (self.key_manager and (
                primary_provider.lower() in self.key_manager._keys
                or primary_provider.lower() in [p.lower() for p in self.key_manager.list_providers()]
            ))
        )

        candidates = []
        if is_known or not fb_list:
            candidates.append((primary_provider, primary_model))

        for fb in fb_list:
            candidates.append(parse_model(fb))

        return self._apply_strategy(candidates, model, strategy=current_strategy)

    def _apply_strategy(self, candidates: List[Tuple[str, str]], model: str, strategy: Optional[RoutingStrategy] = None) -> List[Tuple[str, str]]:
        current_strategy = strategy or self.strategy
        if current_strategy == RoutingStrategy.LOWEST_LATENCY:
            candidates.sort(key=lambda t: self.latency.get(t[0]))

        elif current_strategy == RoutingStrategy.ROUND_ROBIN:
            with self._lock:
                if not candidates:
                    return candidates
                idx = self._rr_index.get(model, 0) % len(candidates)
                candidates = candidates[idx:] + candidates[:idx]
                self._rr_index[model] = (idx + 1) % len(candidates)

        elif current_strategy == RoutingStrategy.COST_OPTIMIZED:
            candidates.sort(key=lambda t: self._input_cost(t[1] or t[0]))

        elif current_strategy in (RoutingStrategy.LEAST_BUSY, RoutingStrategy.USAGE_BASED) and self.key_manager:
            # Sort providers with fewest recorded requests first
            candidates.sort(key=lambda t: sum(r.total_requests for r in self.key_manager._keys.get(t[0].lower(), [])))

        # Resilient Circuit Breaker & Health Filter:
        # Prioritize candidates with healthy/active keys across all strategies,
        # ensuring circuit-broken providers do not waste attempts ahead of healthy ones.
        if self.key_manager:
            candidates.sort(key=lambda t: not self.key_manager.has_active_keys(t[0]))

        return candidates

    def _input_cost(self, model_name: str) -> float:
        """
        Look up the input cost (USD/1K tokens) for a model using the same
        partial-key match as client._get_pricing.
        Unknown models sort last (float inf).
        """
        name_lower = model_name.lower()
        for key, price in self.pricing.items():
            if key in name_lower:
                return price.get("input", float("inf"))
        return float("inf")

    def record_latency(self, provider: str, latency_ms: float):
        self.latency.record(provider, latency_ms)

    def remove_provider(self, provider: str) -> None:
        """Remove references to a provider from fallbacks and groups."""
        p_lower = provider.lower()
        with self._lock:
            # 1. Remove rules where provider is the key
            keys_to_remove = [k for k in self.fallbacks if k.lower() == p_lower or k.lower().startswith(f"{p_lower}/")]
            for k in keys_to_remove:
                del self.fallbacks[k]

            # 2. Remove provider from target fallback chains
            for k, val in list(self.fallbacks.items()):
                if isinstance(val, list):
                    self.fallbacks[k] = [
                        target for target in val
                        if parse_model(target)[0] != p_lower
                    ]
                elif isinstance(val, dict):
                    self.fallbacks[k] = {
                        target: w for target, w in val.items()
                        if parse_model(target)[0] != p_lower
                    }

        # 3. Prune provider models from dynamic groups
        if hasattr(self, "groups") and self.groups and hasattr(self.groups, "remove_provider"):
            self.groups.remove_provider(p_lower)

    async def load(self) -> None:
        """Load fallbacks, strategy, and aliases from storage if configured."""
        if hasattr(self, "storage") and self.storage:
            config = await self.storage.get_config("router")
            if config and config.value:
                with self._lock:
                    if "fallbacks" in config.value:
                        self.fallbacks = config.value["fallbacks"]
                    if "strategy" in config.value:
                        try:
                            self.strategy = RoutingStrategy(config.value["strategy"])
                        except Exception:
                            pass
                    if "aliases" in config.value:
                        self.aliases = config.value["aliases"]
                logger.info("Loaded router configuration from storage.")

    async def save(self) -> None:
        """Save current fallbacks, strategy, and aliases to storage if configured."""
        if hasattr(self, "storage") and self.storage:
            with self._lock:
                val = {
                    "fallbacks": self.fallbacks,
                    "strategy": self.strategy.value,
                    "aliases": self.aliases,
                }
            await self.storage.save_config("router", val)
            logger.info("Saved router configuration to storage.")

