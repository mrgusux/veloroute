"""
Lightweight, dependency-free observability primitives.
=====================================================

Provides a small Prometheus-compatible metrics registry used by the client
and the dashboard API.  No ``prometheus_client`` dependency is required.

Metric families emitted by LLMCycle:

* ``llmcycle_requests_total``          counter   provider/model/status
* ``llmcycle_request_duration_ms``     histogram provider/model/status
* ``llmcycle_tokens_total``            counter   provider/model/kind
* ``llmcycle_errors_total``            counter   provider/error_type
* ``llmcycle_fallbacks_total``         counter   provider
* ``llmcycle_cache_hits_total``        counter   kind
* ``llmcycle_gateway_requests_total``  counter   result
* ``llmcycle_providers_configured``    gauge     -
* ``llmcycle_virtual_keys``            gauge     state

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
    "llmcycle_requests_total": "Total LLM requests by provider, model and terminal status.",
    "llmcycle_request_duration_ms": "End-to-end LLM request latency in milliseconds.",
    "llmcycle_tokens_total": "Total prompt/completion tokens consumed.",
    "llmcycle_errors_total": "Total failed attempts by error class.",
    "llmcycle_fallbacks_total": "Requests that succeeded only after a failed attempt.",
    "llmcycle_cache_hits_total": "Prompt and semantic cache hits.",
    "llmcycle_gateway_requests_total": "Virtual-key gateway authorization outcomes.",
    "llmcycle_providers_configured": "Number of configured upstream providers.",
    "llmcycle_virtual_keys": "Number of virtual keys by state.",
}

_COUNTERS = {
    "llmcycle_requests_total",
    "llmcycle_tokens_total",
    "llmcycle_errors_total",
    "llmcycle_fallbacks_total",
    "llmcycle_cache_hits_total",
    "llmcycle_gateway_requests_total",
}
_GAUGES = {"llmcycle_providers_configured", "llmcycle_virtual_keys"}
_HISTOGRAMS = {"llmcycle_request_duration_ms"}


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
        self.started_at = time.time()

    # ── recording ────────────────────────────────────────────────────────
    def inc_counter(self, name: str, labels: Labels = None, value: float = 1.0) -> None:
        key = (name, _label_key(labels))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + float(value)

    def set_gauge(self, name: str, value: float, labels: Labels = None) -> None:
        key = (name, _label_key(labels))
        with self._lock:
            self._gauges[key] = float(value)

    def inc_gauge(self, name: str, value: float = 1.0, labels: Labels = None) -> None:
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
        self.inc_counter("llmcycle_requests_total", {**labels, "status": status})
        self.observe_histogram(
            "llmcycle_request_duration_ms",
            latency_ms,
            {**labels, "status": status},
        )
        if prompt_tokens:
            self.inc_counter(
                "llmcycle_tokens_total",
                {**labels, "kind": "prompt"},
                prompt_tokens,
            )
        if completion_tokens:
            self.inc_counter(
                "llmcycle_tokens_total",
                {**labels, "kind": "completion"},
                completion_tokens,
            )
        if error_type:
            self.inc_counter(
                "llmcycle_errors_total",
                {"provider": provider or "unknown", "error_type": error_type},
            )
        if fallback_used:
            self.inc_counter(
                "llmcycle_fallbacks_total",
                {"provider": provider or "unknown"},
            )

    def inc_cache_hit(self, kind: str = "prompt") -> None:
        self.inc_counter("llmcycle_cache_hits_total", {"kind": kind})

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
