"""
Claude Code CLI Prompt Sizer & Agent Dispatcher
================================================
TypeSafe Task Sizing and Model Dispatch Hook inspired by
TechPreacher__jev_router (Repo 218), affaan-m__ecc (Repo 005),
and google-gemini__gemini-cli (Repo 081).

Analyzes user prompt and task complexity in-flight and routes coding
tasks across a 4-tier model hierarchy (Haiku -> Sonnet -> Sonnet 3.7 -> Opus)
saving cost and latency on simple tasks while reserving top reasoning
models for complex engineering problems.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from veloroute.utils import count_tokens


class TaskTier(str, Enum):
    XS = "XS"   # Trivial, typo, basic query, formatting
    S  = "S"    # Single function, localized bugfix, unit test
    M  = "M"    # Multi-file refactor, architecture, async concurrency
    L  = "L"    # Deep reasoning, distributed systems, formal verification, full codebase overhaul


# Model dispatch mappings per tier
DEFAULT_TIER_MODELS = {
    TaskTier.XS: {
        "anthropic": "claude-3-haiku-20240307",
        "openai": "gpt-4o-mini",
        "deepseek": "deepseek-chat",
        "gemini": "gemini-1.5-flash",
    },
    TaskTier.S: {
        "anthropic": "claude-3-5-sonnet-20241022",
        "openai": "gpt-4o",
        "deepseek": "deepseek-chat",
        "gemini": "gemini-1.5-pro",
    },
    TaskTier.M: {
        "anthropic": "claude-3-7-sonnet-latest",
        "openai": "gpt-4o",
        "deepseek": "deepseek-chat",
        "gemini": "gemini-1.5-pro",
    },
    TaskTier.L: {
        "anthropic": "claude-3-opus-20240229",
        "openai": "o1",
        "deepseek": "deepseek-reasoner",
        "gemini": "gemini-1.5-pro",
    },
}

# Signal keywords with complexity weight
_COMPLEXITY_SIGNALS = {
    # High complexity signals (+2.0 to +3.5)
    r"\b(distributed system|consensus|raft|paxos|byzantine|deadlock|race condition)\b": 3.2,
    r"\b(formal verification|compiler optimization|ast transform|bytecode|kernel)\b": 3.0,
    r"\b(architecture design|system architecture|microservices|domain-driven)\b": 2.5,
    r"\b(security audit|vulnerability assessment|cve|zero-day|cryptographic|penetration)\b": 2.5,
    r"\b(refactor (entire|whole|all)|codebase migration|re-architect)\b": 2.8,
    r"\b(benchmark optimization|memory leak|profiling|zero-copy|simd)\b": 2.4,

    # Medium complexity signals (+1.0 to +1.8)
    r"\b(unit test|test suite|mock|asyncio|coroutine|hashing|bcrypt|jwt|encryption)\b": 1.6,
    r"\b(database migration|schema design|indexing strategy|sqlalchemy|prisma)\b": 1.5,
    r"\b(rest api|graphql|fastapi|websocket|reverse proxy|gateway)\b": 1.2,
    r"\b(debug|investigate error|traceback|fix bug|exception handling)\b": 1.3,
    r"\b(dockerfile|kubernetes|helm|ci/cd|github actions)\b": 1.1,

    # Low complexity / reduction signals (-1.0 to -2.0)
    r"\b(fix typo|spelling|rename variable|formatting|pep8|prettier)\b": -1.8,
    r"\b(what is|explain concept|what does .+ mean|summarize)\b": -1.0,
    r"\b(hello|hi|hey|thanks|thank you|who are you)\b": -2.5,
}


@dataclass
class SizingResult:
    """Outcome of prompt sizing and task classification."""
    prompt: str
    tokens: int
    complexity_score: float
    tier: TaskTier
    recommended_model: str
    recommended_provider: str
    rationale: str
    signals_detected: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier": self.tier.value,
            "complexity_score": round(self.complexity_score, 2),
            "recommended_model": self.recommended_model,
            "recommended_provider": self.recommended_provider,
            "estimated_tokens": self.tokens,
            "rationale": self.rationale,
            "signals_detected": self.signals_detected,
            "timestamp": self.timestamp,
        }

    def to_claude_code_hook_response(self) -> Dict[str, Any]:
        """Format response strictly compatible with Claude Code UserPromptSubmit hook."""
        return {
            "decision": "proceed",
            "tier": self.tier.value,
            "complexity_score": round(self.complexity_score, 2),
            "model_override": self.recommended_model,
            "estimated_tokens": self.tokens,
            "rationale": self.rationale,
            "metadata": {
                "source": "veloroute-prompt-sizer",
                "signals": self.signals_detected,
            },
        }


class PromptSizer:
    """
    Intelligent Task Sizing Engine for Claude Code, Cursor, and Developer CLI agents.
    """

    def __init__(self, preferred_provider: str = "anthropic"):
        self.preferred_provider = preferred_provider

    def analyze_complexity(
        self,
        prompt: str,
        context: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> SizingResult:
        """
        Evaluate task complexity and assign optimal model tier.
        """
        target_provider = (provider or self.preferred_provider).lower()
        if not prompt or not prompt.strip():
            model = DEFAULT_TIER_MODELS[TaskTier.XS].get(target_provider, "claude-3-haiku-20240307")
            return SizingResult(
                prompt="",
                tokens=0,
                complexity_score=0.0,
                tier=TaskTier.XS,
                recommended_model=model,
                recommended_provider=target_provider,
                rationale="Empty prompt defaults to lightweight XS tier.",
            )

        full_text = f"{prompt}\n{context}" if context else prompt
        tokens = count_tokens(full_text)

        # Baseline score derived from token volume (0.5 to 3.0)
        if tokens < 40:
            score = 1.0
        elif tokens < 150:
            score = 2.0
        elif tokens < 500:
            score = 3.5
        elif tokens < 1500:
            score = 5.0
        else:
            score = 6.5

        # Code block density check
        code_blocks = re.findall(r"```[\s\S]*?```", full_text)
        if len(code_blocks) >= 3:
            score += 2.0
        elif len(code_blocks) >= 1:
            score += 1.0

        # Multi-file path references check (e.g. src/auth/jwt.py)
        file_paths = re.findall(r"\b[A-Za-z0-9_\-\./]+\.[a-zA-Z0-9]{1,6}\b", full_text)
        if len(file_paths) >= 4:
            score += 1.5

        # Pattern match signals
        detected_signals: List[str] = []
        lower_text = full_text.lower()
        for pattern, weight in _COMPLEXITY_SIGNALS.items():
            if re.search(pattern, lower_text):
                score += weight
                detected_signals.append(pattern)

        # Clamp score between 0.0 and 10.0
        score = max(0.0, min(10.0, score))

        # Classify Tier
        if score < 2.2:
            tier = TaskTier.XS
            rationale = "Trivial or localized query; routed to high-speed, cost-efficient model."
        elif score < 4.8:
            tier = TaskTier.S
            rationale = "Standard single-component task; routed to flagship coding workhorse."
        elif score < 7.8:
            tier = TaskTier.M
            rationale = "Substantial multi-component or architectural engineering task; routed to top coding model."
        else:
            tier = TaskTier.L
            rationale = "Deep cognitive complexity, full-system overhaul or formal reasoning; routed to frontier tier."

        tier_map = DEFAULT_TIER_MODELS.get(tier, DEFAULT_TIER_MODELS[TaskTier.S])
        recommended_model = tier_map.get(target_provider) or tier_map.get("anthropic", "claude-3-5-sonnet-20241022")

        return SizingResult(
            prompt=prompt[:200] + ("..." if len(prompt) > 200 else ""),
            tokens=tokens,
            complexity_score=score,
            tier=tier,
            recommended_model=recommended_model,
            recommended_provider=target_provider,
            rationale=rationale,
            signals_detected=detected_signals,
        )

    def handle_hook_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle Claude Code CLI UserPromptSubmit or external agent hook request.
        """
        prompt = payload.get("prompt") or payload.get("user_prompt") or payload.get("message") or ""
        context = payload.get("context") or payload.get("cwd") or ""
        provider = payload.get("provider") or self.preferred_provider

        result = self.analyze_complexity(prompt, context=context, provider=provider)
        return result.to_claude_code_hook_response()
