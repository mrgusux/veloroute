"""
Lightweight, dependency-free observability primitives.
=====================================================

Provides a small Prometheus-compatible metrics registry used by the client
and the dashboard API.  No ``prometheus_client`` dependency is required.

Metric families emitted by VeloRoute:

* ``veloroute_requests_total``          counter   provider/model/status
* ``veloroute_request_duration_ms``     histogram provider/model/status
* ``veloroute_tokens_total``            counter   provider/model/kind
* ``veloroute_errors_total``            counter   provider/error_type
* ``veloroute_fallbacks_total``         counter   provider
* ``veloroute_cache_hits_total``        counter   kind
* ``veloroute_gateway_requests_total``  counter   result
* ``veloroute_providers_configured``    gauge     -
* ``veloroute_virtual_keys``            gauge     state

The registry is intentionally process-local and in-memory.  Scrape ``/metrics``
with Prometheus or any OpenMetrics-compatible collector.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, Iterable, List, Optional, Tuple

Labels = Optional[Dict[str, str]]
_LabelKey = Tuple[Tuple[str, str], ...]

_LATENCY_BUCKETS = (
    5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1_000.0,
    2_500.0, 5_000.0, 10_000.0, 30_000.0, 60_000.0,
)

_HELP = {
    "veloroute_requests_total": "Total LLM requests by provider, model and terminal status.",
    "veloroute_request_duration_ms": "End-to-end LLM request latency in milliseconds.",
    "veloroute_streaming_ttft_ms": "Time to first token in milliseconds for streaming requests.",
    "veloroute_tokens_total": "Total prompt/completion tokens consumed.",
    "veloroute_errors_total": "Total failed attempts by error class.",
    "veloroute_fallbacks_total": "Requests that succeeded only after a failed attempt.",
    "veloroute_cache_hits_total": "Prompt and semantic cache hits.",
    "veloroute_gateway_requests_total": "Virtual-key gateway authorization outcomes.",
    "veloroute_mcp_tool_calls_total": "Total MCP tool calls by tool name and status.",
    "veloroute_complexity_routing_total": "Complexity-based model routing decisions by tier.",
    "veloroute_providers_configured": "Number of configured upstream providers.",
    "veloroute_virtual_keys": "Number of virtual keys by state.",
    "veloroute_up": "VeloRoute gateway live status indicator (1 = up).",
}

_COUNTERS = {
    "veloroute_requests_total",
    "veloroute_tokens_total",
    "veloroute_errors_total",
    "veloroute_fallbacks_total",
    "veloroute_cache_hits_total",
    "veloroute_gateway_requests_total",
    "veloroute_mcp_tool_calls_total",
    "veloroute_complexity_routing_total",
}
_GAUGES = {"veloroute_providers_configured", "veloroute_virtual_keys", "veloroute_up"}
_HISTOGRAMS = {"veloroute_request_duration_ms", "veloroute_streaming_ttft_ms"}


def _label_key(labels: Labels) -> _LabelKey:
    if not labels:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _escape_label(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )


def _format_labels(key: _LabelKey, extra: Optional[Tuple[str, str]] = None) -> str:
    pairs = list(key)
    if extra:
        pairs.append(extra)
    if not pairs:
        return ""
    inner = ",".join(f'{k}="{_escape_label(v)}"' for k, v in pairs)
    return "{" + inner + "}"


class _Histogram:
    __slots__ = ("buckets", "counts", "sum", "count")

    def __init__(self, buckets: Iterable[float]):
        self.buckets = tuple(sorted(float(b) for b in buckets))
        self.counts: List[int] = [0] * len(self.buckets)
        self.sum = 0.0
        self.count = 0

    def observe(self, value: float) -> None:
        value = float(value)
        self.sum += value
        self.count += 1
        for i, bucket in enumerate(self.buckets):
            if value <= bucket:
                self.counts[i] += 1


class MetricsRegistry:
    """Thread-safe in-memory metrics registry with Prometheus text output."""

    def __init__(self):
        self._lock = threading.Lock()
        self._counters: Dict[Tuple[str, _LabelKey], float] = {}
        self._gauges: Dict[Tuple[str, _LabelKey], float] = {}
        self._histograms: Dict[Tuple[str, _LabelKey], _Histogram] = {}
        self._recent_traces: List[Dict[str, object]] = []
        self.started_at = time.time()
        self.set_gauge("veloroute_up", 1.0)

    def _normalize_name(self, name: str) -> str:
        return name

    # ── recording ────────────────────────────────────────────────────────
    def inc_counter(self, name: str, labels: Labels = None, value: float = 1.0) -> None:
        name = self._normalize_name(name)
        key = (name, _label_key(labels))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + float(value)

    def set_gauge(self, name: str, value: float, labels: Labels = None) -> None:
        name = self._normalize_name(name)
        key = (name, _label_key(labels))
        with self._lock:
            self._gauges[key] = float(value)

    def inc_gauge(self, name: str, value: float = 1.0, labels: Labels = None) -> None:
        name = self._normalize_name(name)
        key = (name, _label_key(labels))
        with self._lock:
            self._gauges[key] = self._gauges.get(key, 0.0) + float(value)

    def observe_histogram(
        self,
        name: str,
        value: float,
        labels: Labels = None,
        buckets: Optional[Iterable[float]] = None,
    ) -> None:
        name = self._normalize_name(name)
        key = (name, _label_key(labels))
        with self._lock:
            hist = self._histograms.get(key)
            if hist is None:
                hist = _Histogram(buckets or _LATENCY_BUCKETS)
                self._histograms[key] = hist
            hist.observe(value)

    def record_request(
        self,
        *,
        provider: str,
        model: str,
        status: str,
        latency_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        error_type: Optional[str] = None,
        fallback_used: bool = False,
    ) -> None:
        """Convenience wrapper recording one request across all families."""
        labels = {"provider": provider or "unknown", "model": model or "unknown"}
        self.inc_counter("veloroute_requests_total", {**labels, "status": status})
        self.observe_histogram(
            "veloroute_request_duration_ms",
            latency_ms,
            {**labels, "status": status},
        )
        if prompt_tokens:
            self.inc_counter(
                "veloroute_tokens_total",
                {**labels, "kind": "prompt"},
                prompt_tokens,
            )
        if completion_tokens:
            self.inc_counter(
                "veloroute_tokens_total",
                {**labels, "kind": "completion"},
                completion_tokens,
            )
        if error_type:
            self.inc_counter(
                "veloroute_errors_total",
                {"provider": provider or "unknown", "error_type": error_type},
            )
        if fallback_used:
            self.inc_counter(
                "veloroute_fallbacks_total",
                {"provider": provider or "unknown"},
            )
        with self._lock:
            self._recent_traces.insert(
                0,
                {
                    "id": f"trace-{int(time.time() * 1000)}-{len(self._recent_traces)}",
                    "created_at": time.time(),
                    "provider": provider or "unknown",
                    "model": model or "unknown",
                    "status": status,
                    "latency_ms": round(float(latency_ms), 2),
                    "prompt_tokens": int(prompt_tokens or 0),
                    "completion_tokens": int(completion_tokens or 0),
                    "total_tokens": int((prompt_tokens or 0) + (completion_tokens or 0)),
                    "fallback_used": bool(fallback_used),
                    "error": error_type,
                    "is_cached": False,
                },
            )
            if len(self._recent_traces) > 250:
                self._recent_traces = self._recent_traces[:250]

    def inc_cache_hit(self, kind: str = "prompt") -> None:
        self.inc_counter("veloroute_cache_hits_total", {"kind": kind})

    def observe_ttft(self, model: str, provider: str, ttft_ms: float) -> None:
        """Record time-to-first-token in milliseconds for streaming inference."""
        self.observe_histogram(
            "veloroute_streaming_ttft_ms",
            ttft_ms,
            {"model": model or "unknown", "provider": provider or "unknown"},
        )

    def inc_mcp_call(self, tool_name: str, status: str = "success") -> None:
        """Record MCP tool execution."""
        self.inc_counter(
            "veloroute_mcp_tool_calls_total",
            {"tool": tool_name or "unknown", "status": status},
        )

    def inc_complexity_decision(self, tier: str, model: str) -> None:
        """Record complexity router decision (e.g. tier='strong' or 'weak')."""
        self.inc_counter(
            "veloroute_complexity_routing_total",
            {"tier": tier, "model": model or "unknown"},
        )

    # ── introspection ───────────────────────────────────────────────────
    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return {
                "started_at": self.started_at,
                "counters": {
                    f"{name}{_format_labels(key)}": value
                    for (name, key), value in self._counters.items()
                },
                "gauges": {
                    f"{name}{_format_labels(key)}": value
                    for (name, key), value in self._gauges.items()
                },
                "histograms": {
                    f"{name}{_format_labels(key)}": {
                        "count": hist.count,
                        "sum": hist.sum,
                    }
                    for (name, key), hist in self._histograms.items()
                },
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self.started_at = time.time()

    # ── Prometheus exposition ───────────────────────────────────────────
    def render(self) -> str:
        lines: List[str] = []
        with self._lock:
            counters = sorted(
                (name, key, value) for (name, key), value in self._counters.items()
            )
            gauges = sorted(
                (name, key, value) for (name, key), value in self._gauges.items()
            )
            histograms = sorted(
                (
                    name,
                    key,
                    tuple(hist.buckets),
                    tuple(hist.counts),
                    hist.sum,
                    hist.count,
                )
                for (name, key), hist in self._histograms.items()
            )

        declared = set()
        for name, key, value in counters:
            if name not in declared:
                declared.add(name)
                lines.append(f"# HELP {name} {_HELP.get(name, name)}")
                lines.append(f"# TYPE {name} counter")
            lines.append(f"{name}{_format_labels(key)} {self._fmt(value)}")

        for name, key, value in gauges:
            if name not in declared:
                declared.add(name)
                lines.append(f"# HELP {name} {_HELP.get(name, name)}")
                lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name}{_format_labels(key)} {self._fmt(value)}")

        for name, key, buckets, counts, total, count in histograms:
            if name not in declared:
                declared.add(name)
                lines.append(f"# HELP {name} {_HELP.get(name, name)}")
                lines.append(f"# TYPE {name} histogram")
            for bucket, bucket_count in zip(buckets, counts):
                lines.append(
                    f"{name}_bucket{_format_labels(key, ('le', self._fmt(bucket)))} {bucket_count}"
                )
            lines.append(
                f"{name}_bucket{_format_labels(key, ('le', '+Inf'))} {count}"
            )
            lines.append(f"{name}_sum{_format_labels(key)} {self._fmt(total)}")
            lines.append(f"{name}_count{_format_labels(key)} {count}")

        return "\n".join(lines) + ("\n" if lines else "")

    @staticmethod
    def _fmt(value: float) -> str:
        if float(value).is_integer():
            return str(int(value))
        return f"{value:.6f}".rstrip("0").rstrip(".")


# Process-wide singleton.  Import this, do not instantiate per request.
METRICS = MetricsRegistry()


def get_metrics() -> MetricsRegistry:
    return METRICS


__all__ = ["MetricsRegistry", "METRICS", "get_metrics"]
