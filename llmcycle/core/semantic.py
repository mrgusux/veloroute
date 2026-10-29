"""
Self-Contained Intent-Based Semantic Router
============================================
Provides high-performance, rule/phrase-based semantic classification to route
prompts dynamically to different models (e.g. reasoning vs fast cheap chat)
without needing heavy embeddings or external vector database setups.
"""
from __future__ import annotations
import re
from typing import Dict, List, Union, Callable, Optional

class SemanticRouter:
    """
    Lightweight, high-performance rule/phrase-based intent semantic router.
    Keeps the core LLMCycle codebase zero-dependency.

    Example::

        rules = {
            "complex_reasoning": [r"explain", r"why", r"how", r"prove", r"solve", r"analyze"],
            "data_extraction": [r"json", r"extract", r"parse", r"regex", r"csv", r"table"],
            "simple_chat": [] # fallback intent if no rules match
        }
        routes = {
            "complex_reasoning": "openai/gpt-4o",
            "data_extraction": "groq/llama-3.1-70b",
            "simple_chat": "openai/gpt-4o-mini"
        }
        router = SemanticRouter(rules=rules, routes=routes, default_intent="simple_chat")
        target_model = router.route("Explain how gradient descent works") # -> "openai/gpt-4o"
    """

    def __init__(
        self,
        rules: Dict[str, List[Union[str, re.Pattern]]],
        routes: Dict[str, Union[str, List[str]]],
        default_intent: str,
        custom_classifier: Optional[Callable[[str], str]] = None,
    ):
        self.routes = routes
        self.default_intent = default_intent
        self.custom_classifier = custom_classifier

        # Pre-compile regexes for high speed execution
        self.compiled_rules = {}
        for intent, patterns in rules.items():
            compiled = []
            for pat in patterns:
                if isinstance(pat, str):
                    compiled.append(re.compile(pat, re.IGNORECASE))
                else:
                    compiled.append(pat)
            self.compiled_rules[intent] = compiled

    def classify(self, prompt: str) -> str:
        """Classify user prompt to find matching intent."""
        if not prompt or not isinstance(prompt, str):
            return self.default_intent

        if self.custom_classifier:
            try:
                return self.custom_classifier(prompt)
            except Exception:
                pass

        for intent, regexes in self.compiled_rules.items():
            for rx in regexes:
                if rx.search(prompt):
                    return intent
        return self.default_intent

    def route(self, prompt: str) -> Union[str, List[str]]:
        """Determine target model or model-list based on intent."""
        intent = self.classify(prompt)
        return self.routes.get(intent, self.routes.get(self.default_intent))
