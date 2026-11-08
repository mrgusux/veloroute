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
from collections import deque
from enum import Enum
from typing import Any, List, Dict, Optional, Tuple

from veloroute.utils import parse_model

logger = logging.getLogger(__name__)


import re
from dataclasses import dataclass, field


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
    COMPLEXITY     = "complexity"      # intelligent weak vs strong model routing based on query complexity (RouteLLM style)
    KV_AFFINITY    = "kv_affinity"     # route requests with identical prefix/system prompt to same provider to maximize KV cache hits
    PREFIX_CACHE   = "prefix_cache"    # alias for kv_affinity
    HEDGING        = "hedging"         # speculative parallel execution across top 2 candidates, returning fastest winner (pLLM style)
    QUALITY        = "quality"         # empirical user-feedback / reward-guided routing (Learning-To-Route / TensorZero style)
    FLAGSHIP       = "flagship"        # prioritize strongest / highest-capability models first (/smart, /reason)


_SLASH_DIRECTIVE_RE = re.compile(
    r"^\s*/(fast|cheap|smart|reason|hedge|kv|terse|quality)(?:\s+([\s\S]*))?$",
    re.IGNORECASE,
)


def parse_slash_command(text: Optional[str]) -> Tuple[str, Dict[str, Any]]:
    """
    Parse leading slash-command routing directives (FreeRouter / OpenRouter style).
    Supported prefixes:
      /fast    -> strategy=LOWEST_LATENCY
      /cheap   -> strategy=COST_OPTIMIZED
      /smart   -> strategy=FLAGSHIP, complexity_threshold=0.0 (force strong model)
      /reason  -> strategy=FLAGSHIP, complexity_threshold=0.0 (force strong/reasoning model)
      /hedge   -> strategy=HEDGING (parallel speculative race)
      /kv      -> strategy=KV_AFFINITY
      /quality -> strategy=QUALITY (highest empirical user feedback score)
      /terse   -> terse=True (apply ContextOptimizer prompt compression + concise instruction)
    Returns (cleaned_text, metadata_dict). If no directive matches, returns (original_text, {}).
    """
    if not text or not isinstance(text, str):
        return text or "", {}
    m = _SLASH_DIRECTIVE_RE.match(text)
    if not m:
        return text, {}
    cmd = m.group(1).lower()
    rest = (m.group(2) or "").strip()
    if not rest:
        # Bare command with no actual prompt body: leave untouched so user doesn't send empty prompt
        return text, {}

    meta: Dict[str, Any] = {"directive": f"/{cmd}"}
    if cmd == "fast":
        meta["strategy"] = RoutingStrategy.LOWEST_LATENCY
    elif cmd == "cheap":
        meta["strategy"] = RoutingStrategy.COST_OPTIMIZED
    elif cmd in ("smart", "reason"):
        meta["strategy"] = RoutingStrategy.FLAGSHIP
        meta["complexity_threshold"] = 0.0
    elif cmd == "hedge":
        meta["strategy"] = RoutingStrategy.HEDGING
    elif cmd == "kv":
        meta["strategy"] = RoutingStrategy.KV_AFFINITY
    elif cmd == "quality":
        meta["strategy"] = RoutingStrategy.QUALITY
    elif cmd == "terse":
        meta["terse"] = True
    return rest, meta


class QualityTracker:
    """
    Empirical model/provider quality tracker backed by user feedback signals
    (Learning-To-Route / TensorZero style). Maintains EMA quality score in [0.0, 1.0].
    """

    def __init__(self, alpha: float = 0.25):
        self.alpha = alpha
        self._lock = threading.Lock()
        self._records: Dict[str, Dict[str, Any]] = {}
        self._recent: deque = deque(maxlen=100)

    def record(self, target: str, score: float, comment: str = "", trace_id: str = "") -> Dict[str, Any]:
        key = (target or "unknown").strip().lower()
        clamped = max(0.0, min(1.0, float(score)))
        now = time.time()
        with self._lock:
            rec = self._records.get(key)
            if not rec:
                rec = {
                    "target": target,
                    "ema_score": clamped,
                    "thumbs_up": 1 if clamped >= 0.5 else 0,
                    "thumbs_down": 0 if clamped >= 0.5 else 1,
                    "total": 1,
                    "updated_at": now,
                }
                self._records[key] = rec
            else:
                rec["ema_score"] = round(self.alpha * clamped + (1.0 - self.alpha) * rec["ema_score"], 4)
                if clamped >= 0.5:
                    rec["thumbs_up"] += 1
                else:
                    rec["thumbs_down"] += 1
                rec["total"] += 1
                rec["updated_at"] = now
            event = {
                "target": target,
                "score": clamped,
                "ema_score": rec["ema_score"],
                "comment": (comment or "")[:300],
                "trace_id": trace_id,
                "timestamp": now,
            }
            self._recent.appendleft(event)
            return dict(rec)

    def get_score(self, provider: str, model: str = "") -> float:
        """Return empirical quality score in [0.0, 1.0]; defaults to 0.5 neutral."""
        with self._lock:
            full = f"{provider}/{model}".lower() if model else provider.lower()
            if full in self._records:
                return float(self._records[full]["ema_score"])
            if model and model.lower() in self._records:
                return float(self._records[model.lower()]["ema_score"])
            if provider.lower() in self._records:
                return float(self._records[provider.lower()]["ema_score"])
            return 0.5

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            items = sorted(self._records.values(), key=lambda r: (r["ema_score"], r["total"]), reverse=True)
            return {
                "models": [dict(x) for x in items],
                "recent": list(self._recent)[:25],
                "total_feedback": sum(x["total"] for x in items),
            }

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {k: dict(v) for k, v in self._records.items()}

    def from_dict(self, data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            return
        with self._lock:
            for k, v in data.items():
                if isinstance(v, dict) and "ema_score" in v:
                    self._records[str(k).lower()] = dict(v)


@dataclass
class ComplexityPair:
    """Pair of strong (reasoning/flagship) and weak (fast/cheap) models for complexity routing."""
    strong_model: str
    weak_model: str
    threshold: float = 0.5
    name: Optional[str] = None


class ComplexityEvaluator:
    """
    Evaluates prompt and message complexity for intelligent routing between
    cheap/fast models and expensive/reasoning flagship models (RouteLLM / SaveRouter / Martian style).
    Produces a normalized complexity score between 0.0 and 1.0.
    """
    _REASONING_PATTERNS = [
        re.compile(r"\b(prove|proof|derive|derivation|theorem|axiom|contradiction|irrational|mathematical|math)\b", re.IGNORECASE),
        re.compile(r"\b(step[- ]by[- ]step|think[- ]through|chain[- ]of[- ]thought|reasoning|computational)\b", re.IGNORECASE),
        re.compile(r"\b(algorithm\w*|complexity|big[- ]o|asymptotic|recurrence|backtracking|dynamic\s+programming|memoization|dijkstra)\b", re.IGNORECASE),
        re.compile(r"\b(architect\w*|system[- ]design|distributed|scalability|transformer|attention|tensor|multi[- ]head)\b", re.IGNORECASE),
        re.compile(r"\b(root[- ]cause|diagnose|post[- ]mortem|debug|traceback|deadlock|concurrency|mutex|multi[- ]thread\w*|lock[- ]free|atomic|hazard\s+pointers?|memory\s+fences?|compare[- ]and[- ]swap)\b", re.IGNORECASE),
        re.compile(r"\b(compiler|allocat\w*|register|heuristic\w*|graph|node\w*|tree\w*|pipeline|database)\b", re.IGNORECASE),
        re.compile(r"\b(critique|evaluate|counter[- ]argument|fallacy|tradeoffs)\b", re.IGNORECASE),
        re.compile(r"\b(optimize|refactor|benchmark|profil(e|ing))\b", re.IGNORECASE),
        re.compile(r"\b(formal|calculus|differential|integral|matrix|eigen)\b", re.IGNORECASE),
    ]

    _CODE_PATTERNS = [
        re.compile(r"```[a-zA-Z0-9_-]*\n", re.IGNORECASE),
        re.compile(r"\b(def|class|async\s+def|import|from\s+\w+\s+import|func|package|impl|pub\s+fn)\b"),
        re.compile(r"(?:\b(c\+\+|c#)|\b(python|javascript|typescript|rust|golang|code|function|implement\w*|script|heap|priority\s+queue|queue|stack)\b)", re.IGNORECASE),
        re.compile(r"\b(select\s+.+\s+from\s+.+\s+where|insert\s+into|alter\s+table)\b", re.IGNORECASE),
        re.compile(r"[{};]\s*\n"),
    ]

    _SIMPLE_PATTERNS = [
        re.compile(r"^(hi|hello|hey|greetings|good\s+(morning|evening|afternoon)|sup|yo)[\s.!]*$", re.IGNORECASE),
        re.compile(r"^(what is|who is|when was|capital of|define)\s+[\w\s]{1,30}\??$", re.IGNORECASE),
        re.compile(r"^(translate\s+.+\s+to\s+\w+)$", re.IGNORECASE),
    ]

    def evaluate(
        self,
        prompt: Optional[Union[str, List[Dict[str, Any]]]] = None,
        messages: Optional[List[Any]] = None,
    ) -> float:
        """
        Evaluate complexity of prompt and/or message list.
        Returns a score in [0.0, 1.0].
        """
        text_parts: List[str] = []
        msg_count = 0
        has_multimodal = False
        if isinstance(prompt, list) and not messages:
            messages = prompt
            prompt = None

        if messages:
            msg_count = len(messages)
            for m in messages:
                if isinstance(m, dict):
                    content = m.get("content")
                else:
                    content = getattr(m, "content", None)
                if isinstance(content, str):
                    if content.strip():
                        text_parts.append(content.strip())
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            ptype = part.get("type")
                            if ptype == "text":
                                t = part.get("text")
                                if isinstance(t, str) and t.strip():
                                    text_parts.append(t.strip())
                            elif ptype in ("image_url", "input_audio", "document"):
                                has_multimodal = True
                        elif isinstance(part, str) and part.strip():
                            text_parts.append(part.strip())
        if isinstance(prompt, str) and prompt.strip():
            text_parts.append(prompt.strip())

        full_text = "\n".join(text_parts).strip()
        if not full_text:
            return 0.5 if has_multimodal else 0.1

        # Check for simple greeting / low-complexity matches (unless multimodal)
        if not has_multimodal:
            for p in self._SIMPLE_PATTERNS:
                if p.match(full_text):
                    return 0.1

        score = 0.2  # baseline for standard questions
        if has_multimodal:
            score += 0.3  # multimodal queries require capable multimodal models

        # Length factor (up to 0.25)
        words = len(full_text.split())
        length_factor = min(0.25, (words / 300.0) * 0.25)
        score += length_factor

        # Reasoning keyword factor (up to 0.45)
        reasoning_hits = sum(len(p.findall(full_text)) for p in self._REASONING_PATTERNS)
        score += min(0.45, reasoning_hits * 0.12)

        # Code syntax factor (up to 0.35)
        code_hits = sum(len(p.findall(full_text)) for p in self._CODE_PATTERNS)
        score += min(0.35, code_hits * 0.10)

        # Multi-turn conversation depth factor (up to 0.15)
        if msg_count > 3:
            score += min(0.15, (msg_count - 3) * 0.03)

        return max(0.0, min(1.0, round(score, 3)))


class LatencyTracker:
    """Per-provider EWMA latency tracking with percentiles and SLA availability."""
    ALPHA = 0.3  # smoothing factor

    def __init__(self, history_len: int = 50):
        self._latencies: Dict[str, float] = {}
        self._history: Dict[str, deque] = {}
        self._success_counts: Dict[str, int] = {}
        self._error_counts: Dict[str, int] = {}
        self._history_len = history_len
        self._lock = threading.Lock()

    def record(self, provider: str, latency_ms: float, success: bool = True):
        p = provider.lower()
        with self._lock:
            if p not in self._history:
                self._history[p] = deque(maxlen=self._history_len)
                self._success_counts[p] = 0
                self._error_counts[p] = 0

            if success:
                self._success_counts[p] += 1
                if latency_ms > 0:
                    self._history[p].append(latency_ms)
                    prev = self._latencies.get(p, latency_ms)
                    self._latencies[p] = self.ALPHA * latency_ms + (1 - self.ALPHA) * prev
            else:
                self._error_counts[p] += 1
                self._history[p].append(0.0)

    def get(self, provider: str) -> float:
        return self._latencies.get(provider.lower(), 999999.0)

    def all(self) -> Dict[str, float]:
        return dict(self._latencies)

    def get_matrix(self, provider: str) -> Dict[str, Any]:
        p = provider.lower()
        with self._lock:
            ewma = self._latencies.get(p, 0.0)
            hist = [x for x in self._history.get(p, []) if x > 0]
            succ = self._success_counts.get(p, 0)
            err = self._error_counts.get(p, 0)
            total = succ + err

            avail = round((succ / total * 100.0), 2) if total > 0 else 100.0

            if hist:
                sorted_hist = sorted(hist)
                n = len(sorted_hist)
                p50 = sorted_hist[int(n * 0.50)]
                p95_idx = min(int(n * 0.95), n - 1)
                p95 = sorted_hist[p95_idx]
                min_lat = sorted_hist[0]
                max_lat = sorted_hist[-1]
            else:
                p50 = ewma
                p95 = ewma
                min_lat = ewma
                max_lat = ewma

            status = "healthy" if avail >= 95.0 else ("degraded" if avail >= 80.0 else "down")

            return {
                "provider": p,
                "ewma_latency_ms": round(ewma, 1),
                "p50_latency_ms": round(p50, 1),
                "p95_latency_ms": round(p95, 1),
                "min_latency_ms": round(min_lat, 1),
                "max_latency_ms": round(max_lat, 1),
                "sample_count": total,
                "success_count": succ,
                "error_count": err,
                "availability_pct": avail,
                "status": status,
                "recent_samples": [round(x, 1) for x in hist[-10:]],
            }

    def get_all_matrix(self) -> List[Dict[str, Any]]:
        with self._lock:
            provs = set(list(self._latencies.keys()) + list(self._history.keys()))
        return [self.get_matrix(p) for p in sorted(provs)]


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
        from veloroute.core.groups import GroupManager
        if isinstance(groups, dict) or groups is None:
            self.groups = GroupManager(groups)
        else:
            self.groups = groups
            
        self.key_manager = key_manager
        self.latency   = LatencyTracker()
        self.quality   = QualityTracker()
        self.complexity_evaluator = ComplexityEvaluator()
        self.complexity_pairs: Dict[str, ComplexityPair] = {}
        self._rr_index: Dict[str, int] = {}
        self._prefix_cache: Dict[str, Tuple[str, float]] = {}
        self._lock     = threading.Lock()
        self.storage   = None

    def register_complexity_pair(
        self,
        name: str,
        strong: Optional[str] = None,
        weak: Optional[str] = None,
        threshold: float = 0.5,
        *,
        strong_model: Optional[str] = None,
        fast_model: Optional[str] = None,
        weak_model: Optional[str] = None,
    ) -> ComplexityPair:
        """Register a pair of strong (reasoning/flagship) and weak (cheap/fast) models for complexity routing."""
        s = strong or strong_model or ""
        w = weak or fast_model or weak_model or ""
        pair = ComplexityPair(
            strong_model=s,
            weak_model=w,
            threshold=threshold,
            name=name,
        )
        with self._lock:
            self.complexity_pairs[name] = pair
        return pair

    def get_complexity_pair(self, name: str) -> Optional[ComplexityPair]:
        """Get a registered complexity pair by name."""
        with self._lock:
            return self.complexity_pairs.get(name)

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

    def get_route(
        self,
        model: str,
        strategy: Optional[RoutingStrategy] = None,
        prompt: Optional[str] = None,
        messages: Optional[List[Any]] = None,
        threshold: Optional[float] = None,
    ) -> List[Tuple[str, str]]:
        """
        Returns ordered list of (provider, model) tuples to try.
        Input model format: "provider/model" or just "model", or an alias,
        or a RouteLLM complexity router specification (e.g. "router-complexity-0.5", "router-mf-0.12").
        """
        current_strategy = strategy or self.strategy
        model = self.resolve_model(model)

        # 1. Complexity Pair or RouteLLM Router match
        is_routellm = model.startswith("router-")
        is_named_pair = model in self.complexity_pairs
        if is_named_pair or is_routellm:
            thresh = threshold
            if is_named_pair:
                pair = self.complexity_pairs[model]
                strong, weak = pair.strong_model, pair.weak_model
                if thresh is None:
                    thresh = pair.threshold
            else:
                parts = model.split("-")
                parsed_t = None
                try:
                    parsed_t = float(parts[-1])
                except (ValueError, IndexError):
                    pass
                if thresh is None:
                    thresh = parsed_t if parsed_t is not None else 0.5

                default_pair = self.complexity_pairs.get("default")
                if default_pair:
                    strong, weak = default_pair.strong_model, default_pair.weak_model
                else:
                    strong = "openai/gpt-4o"
                    weak = "groq/llama-3.1-8b"

            if current_strategy == RoutingStrategy.FLAGSHIP:
                candidates = [parse_model(strong), parse_model(weak)]
                return candidates
            score = self.complexity_evaluator.evaluate(prompt=prompt, messages=messages)
            if score >= thresh:
                candidates = [parse_model(strong), parse_model(weak)]
            else:
                candidates = [parse_model(weak), parse_model(strong)]
            return candidates

        complexity_score = None
        if current_strategy == RoutingStrategy.COMPLEXITY:
            complexity_score = self.complexity_evaluator.evaluate(prompt=prompt, messages=messages)

        prefix_hash = None
        if current_strategy in (RoutingStrategy.KV_AFFINITY, RoutingStrategy.PREFIX_CACHE, "kv_affinity", "prefix_cache"):
            import hashlib
            prefix_content = ""
            if messages:
                for m in messages:
                    role = m.get("role", "") if isinstance(m, dict) else getattr(m, "role", "")
                    content = m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
                    if role == "system" or not prefix_content:
                        prefix_content = str(content)[:4096]
                        if role == "system":
                            break
            elif prompt:
                prefix_content = str(prompt)[:4096]
            if prefix_content:
                prefix_hash = hashlib.sha256(prefix_content.encode("utf-8")).hexdigest()

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
                return self._apply_strategy(
                    candidates,
                    model,
                    strategy=current_strategy,
                    complexity_score=complexity_score,
                    threshold=threshold if threshold is not None else 0.5,
                    prefix_hash=prefix_hash,
                )

        # Handle groups
        if model in self.groups:
            candidates = [parse_model(m) for m in self.groups.get(model)]
            return self._apply_strategy(
                candidates,
                model,
                strategy=current_strategy,
                complexity_score=complexity_score,
                threshold=threshold if threshold is not None else 0.5,
                prefix_hash=prefix_hash,
            )

        from veloroute.providers.registry import PROVIDER_REGISTRY

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

        return self._apply_strategy(
            candidates,
            model,
            strategy=current_strategy,
            complexity_score=complexity_score,
            threshold=threshold if threshold is not None else 0.5,
            prefix_hash=prefix_hash,
        )

    def _apply_strategy(
        self,
        candidates: List[Tuple[str, str]],
        model: str,
        strategy: Optional[RoutingStrategy] = None,
        complexity_score: Optional[float] = None,
        threshold: float = 0.5,
        prefix_hash: Optional[str] = None,
    ) -> List[Tuple[str, str]]:
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

        elif current_strategy == RoutingStrategy.FLAGSHIP:
            candidates.sort(key=lambda t: self._input_cost(t[1] or t[0]), reverse=True)

        elif current_strategy == RoutingStrategy.QUALITY:
            # Sort candidates by highest empirical user feedback quality score first, then fastest latency
            candidates.sort(
                key=lambda t: (-self.quality.get_score(t[0], t[1] or ""), self.latency.get(t[0]))
            )

        elif current_strategy == RoutingStrategy.COMPLEXITY:
            score = complexity_score if complexity_score is not None else 0.5
            if score >= threshold:
                candidates.sort(key=lambda t: self._input_cost(t[1] or t[0]), reverse=True)
            else:
                candidates.sort(key=lambda t: self._input_cost(t[1] or t[0]))

        elif current_strategy in (RoutingStrategy.LEAST_BUSY, RoutingStrategy.USAGE_BASED) and self.key_manager:
            # Sort providers with fewest recorded requests first
            candidates.sort(key=lambda t: sum(r.total_requests for r in self.key_manager._keys.get(t[0].lower(), [])))

        elif current_strategy in (RoutingStrategy.KV_AFFINITY, RoutingStrategy.PREFIX_CACHE, "kv_affinity", "prefix_cache") and prefix_hash:
            now = time.time()
            with self._lock:
                # Evict expired entries if cache is growing
                if len(self._prefix_cache) > 100:
                    expired_keys = [k for k, (_, ts) in self._prefix_cache.items() if now - ts > 3600.0]
                    for k in expired_keys:
                        self._prefix_cache.pop(k, None)

                cached = self._prefix_cache.get(prefix_hash)
                if cached:
                    cached_prov, ts = cached
                    if now - ts <= 3600.0:
                        self._prefix_cache[prefix_hash] = (cached_prov, now)
                        idx = next((i for i, c in enumerate(candidates) if c[0].lower() == cached_prov.lower()), -1)
                        if idx >= 0:
                            matched = candidates.pop(idx)
                            candidates.insert(0, matched)
                    else:
                        self._prefix_cache.pop(prefix_hash, None)
                        if candidates:
                            self._prefix_cache[prefix_hash] = (candidates[0][0], now)
                elif candidates:
                    if len(self._prefix_cache) >= 1000:
                        oldest_key = min(self._prefix_cache.keys(), key=lambda k: self._prefix_cache[k][1])
                        self._prefix_cache.pop(oldest_key, None)
                    self._prefix_cache[prefix_hash] = (candidates[0][0], now)

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
        Unknown models sort with median default pricing.
        """
        name_lower = model_name.lower()
        for key, price in self.pricing.items():
            if key in name_lower:
                return price.get("input", 0.001)
        return 0.001

    def record_latency(self, provider: str, latency_ms: float):
        self.latency.record(provider, latency_ms)

    def record_feedback(self, target: str, score: float, comment: str = "", trace_id: str = "") -> Dict[str, Any]:
        """Record user quality feedback (thumbs-up=1.0 / thumbs-down=0.0 or continuous [0..1])."""
        return self.quality.record(target=target, score=score, comment=comment, trace_id=trace_id)

    def get_feedback_stats(self) -> Dict[str, Any]:
        """Return empirical quality rankings and recent feedback events."""
        return self.quality.stats()

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

    def to_dict(self) -> Dict[str, Any]:
        """Serialize router configuration to a dictionary."""
        with self._lock:
            return {
                "fallbacks": dict(self.fallbacks),
                "strategy": self.strategy.value,
                "aliases": dict(self.aliases),
                "complexity_pairs": {
                    k: {"strong": v.strong_model, "weak": v.weak_model, "threshold": v.threshold}
                    for k, v in self.complexity_pairs.items()
                },
                "quality_scores": self.quality.to_dict(),
            }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Load router configuration from a dictionary."""
        with self._lock:
            if "fallbacks" in data and isinstance(data["fallbacks"], dict):
                self.fallbacks = dict(data["fallbacks"])
            if "strategy" in data:
                try:
                    self.strategy = RoutingStrategy(data["strategy"])
                except Exception:
                    pass
            if "aliases" in data and isinstance(data["aliases"], dict):
                self.aliases = dict(data["aliases"])
            if "complexity_pairs" in data and isinstance(data["complexity_pairs"], dict):
                for k, v in data["complexity_pairs"].items():
                    if isinstance(v, dict):
                        self.complexity_pairs[k] = ComplexityPair(
                            strong_model=v.get("strong", ""),
                            weak_model=v.get("weak", ""),
                            threshold=v.get("threshold", 0.5),
                            name=k,
                        )
            if "quality_scores" in data and isinstance(data["quality_scores"], dict):
                self.quality.from_dict(data["quality_scores"])

    async def load(self) -> None:
        """Load fallbacks, strategy, and aliases from storage if configured."""
        if hasattr(self, "storage") and self.storage:
            config = await self.storage.get_config("router")
            if config and config.value:
                self.from_dict(config.value)
                logger.info("Loaded router configuration from storage.")

    async def save(self) -> None:
        """Save current fallbacks, strategy, and aliases to storage if configured."""
        if hasattr(self, "storage") and self.storage:
            val = self.to_dict()
            await self.storage.save_config("router", val)
            logger.info("Saved router configuration to storage.")

