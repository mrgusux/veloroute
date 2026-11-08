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
from typing import Dict, Optional, Union

def calculate_entropy(s: str) -> float:
    """Calculate Shannon Entropy of a string to detect randomized secrets/keys."""
    if not s:
        return 0.0
    entropy = 0.0
    for x in set(s):
        p_x = s.count(x) / len(s)
        entropy += - p_x * math.log2(p_x)
    return entropy


class MaskedResult(str):
    """
    Subclass of str representing the masked text, carrying the isolated
    session token map so callers can either treat it as a string or unpack it:
        masked_text, session_dict = guard.mask_prompt(...)
    """
    session_dict: Dict[str, str]

    def __new__(cls, text: str, session_dict: Optional[Dict[str, str]] = None):
        obj = super().__new__(cls, text)
        obj.session_dict = dict(session_dict) if session_dict is not None else {}
        return obj

    @property
    def token_map(self) -> Dict[str, str]:
        return self.session_dict

    def __iter__(self):
        # Enables tuple unpacking: masked_text, session_dict = guard.mask_prompt(...)
        yield self
        yield self.session_dict


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

    def clear(self) -> None:
        """Reset internal mask state."""
        self.mask_to_secret.clear()
        self.secret_to_mask.clear()
        self.counter = 0

    def _get_placeholder(
        self,
        classification: str,
        secret: str,
        session: Dict[str, str],
        is_isolated: bool = False,
    ) -> str:
        # Check if already mapped in current request session
        for ph, sec in session.items():
            if sec == secret:
                return ph
        # Backwards compatibility for un-isolated single-call mode
        if not is_isolated and secret in self.secret_to_mask:
            ph = self.secret_to_mask[secret]
            session[ph] = secret
            return ph

        self.counter += 1
        placeholder = f"[{classification.upper()}_{self.counter}]"
        session[placeholder] = secret
        if not is_isolated:
            self.mask_to_secret[placeholder] = secret
            self.secret_to_mask[secret] = placeholder
        return placeholder

    def mask_prompt(self, prompt: str, session_dict: Optional[Dict[str, str]] = None) -> MaskedResult:
        """
        Scan and replace all sensitive secrets and PII with placeholders.
        Returns a MaskedResult carrying the per-request isolated session mapping,
        which can also be unpacked as (masked_text, session_dict).
        """
        is_isolated = session_dict is not None
        session = session_dict if session_dict is not None else {}
        if not prompt:
            return MaskedResult(prompt or "", session)

        # 1. Tier-0 explicit secret & PII patterns (deterministic signatures before entropy scan)
        patterns = [
            ("PRIVATE_KEY", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
            ("JWT_TOKEN", r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
            ("ANTHROPIC_KEY", r"\bsk-ant-[A-Za-z0-9_-]{12,}\b"),
            ("API_KEY", r"\b(?:sk|vr|rk|pk)-(?:proj-|live-|test-|prod-)?[A-Za-z0-9_-]{12,}\b"),
            ("GITHUB_TOKEN", r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
            ("AWS_ACCESS_KEY", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
            ("SLACK_TOKEN", r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
            ("SSN", r"\b\d{3}-\d{2}-\d{4}\b"),
            ("CREDIT_CARD", r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),
            ("EMAIL", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
            ("IP_ADDRESS", r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
            ("IPV6_ADDRESS", r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"),
        ]

        masked = prompt
        for label, regex_str in patterns:
            matches = re.findall(regex_str, masked)
            # Sort longest first so prefixes never partially replace longer tokens
            for m in sorted(set(matches), key=len, reverse=True):
                if m in session or any(m in ph for ph in session):
                    continue
                ph = self._get_placeholder(label, m, session, is_isolated=is_isolated)
                masked = masked.replace(m, ph)

        # 2. Mask potential high entropy secrets/tokens
        words = re.findall(r"\b[A-Za-z0-9\-_.]{12,}\b", masked)
        for w in sorted(set(words), key=len, reverse=True):
            # Skip existing placeholders
            if (w.startswith("[") and w.endswith("]")) or any(w in ph for ph in session):
                continue
            if calculate_entropy(w) > self.entropy_threshold:
                ph = self._get_placeholder("SECRET_KEY", w, session, is_isolated=is_isolated)
                masked = masked.replace(w, ph)

        return MaskedResult(masked, session)

    def unmask_response(self, response: str, session_dict: Optional[Dict[str, str]] = None) -> str:
        """
        Restore original values in place of placeholder mask tokens.
        If session_dict is provided, strictly unmasks tokens from that isolated session.
        If omitted, checks response.session_dict or falls back to instance dictionary for backwards compatibility.
        """
        if not response:
            return response
        mapping = session_dict
        if mapping is None and hasattr(response, "session_dict") and response.session_dict:
            mapping = response.session_dict
        if mapping is None:
            mapping = self.mask_to_secret

        unmasked = response
        for placeholder, secret in mapping.items():
            unmasked = unmasked.replace(placeholder, secret)
        return unmasked
