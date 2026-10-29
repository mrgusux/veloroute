"""
PII & Secrets Guardrail Middleware
===================================
A reversible, highly efficient PII and high-entropy secret guardrail.
Masks SSNs, emails, credit cards, IPs, and API keys/tokens before they leave
the gateway, and unmasks them dynamically when the response returns.
"""
from __future__ import annotations
import re
import math
from typing import Dict

def calculate_entropy(s: str) -> float:
    """Calculate Shannon Entropy of a string to detect randomized secrets/keys."""
    if not s:
        return 0.0
    entropy = 0.0
    for x in set(s):
        p_x = s.count(x) / len(s)
        entropy += - p_x * math.log2(p_x)
    return entropy


class GuardrailManager:
    """
    Manages client-side safety guardrails including pattern matching and
    entropy analysis to dynamically scrub PII and secrets in-flight.
    """

    def __init__(self, entropy_threshold: float = 3.8):
        self.entropy_threshold = entropy_threshold
        self.mask_to_secret: Dict[str, str] = {}
        self.secret_to_mask: Dict[str, str] = {}
        self.counter = 0

    def _get_placeholder(self, classification: str, secret: str) -> str:
        if secret in self.secret_to_mask:
            return self.secret_to_mask[secret]
        self.counter += 1
        placeholder = f"[{classification.upper()}_{self.counter}]"
        self.mask_to_secret[placeholder] = secret
        self.secret_to_mask[secret] = placeholder
        return placeholder

    def mask_prompt(self, prompt: str) -> str:
        """Scan and replace all sensitive secrets and PII with placeholders."""
        # 1. Mask standard PII patterns via Regex
        patterns = {
            "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
            "CREDIT_CARD": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
            "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            "IP_ADDRESS": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
        }

        masked = prompt
        for label, regex_str in patterns.items():
            matches = re.findall(regex_str, masked)
            for m in set(matches):
                ph = self._get_placeholder(label, m)
                masked = masked.replace(m, ph)

        # 2. Mask potential high entropy secrets/tokens
        words = re.findall(r"\b[A-Za-z0-9\-_.]{12,}\b", masked)
        for w in set(words):
            # Skip existing placeholders
            if (w.startswith("[") and w.endswith("]")) or any(w in ph for ph in self.mask_to_secret):
                continue
            if calculate_entropy(w) > self.entropy_threshold:
                ph = self._get_placeholder("SECRET_KEY", w)
                masked = masked.replace(w, ph)

        return masked

    def unmask_response(self, response: str) -> str:
        """Restore original values in place of placeholder mask tokens."""
        unmasked = response
        for placeholder, secret in self.mask_to_secret.items():
            unmasked = unmasked.replace(placeholder, secret)
        return unmasked
