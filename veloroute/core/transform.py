"""Gateway Transformation & Custom Middleware Engine (inspired by Envoy AI Gateway & Bifrost).

Supports:
1. Model Rewriting / Aliasing rules (with glob pattern matching)
2. Upstream Request Header Injection
3. Downstream Response Header Stripping / Fingerprint protection
4. Response Content Keyword Redaction & Compliance Masking
"""
from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("veloroute.transform")


@dataclass
class TransformRule:
    id: str
    name: str
    rule_type: str  # "model_rewrite" | "inject_header" | "strip_header" | "response_redact"
    match_pattern: str
    replacement: str = ""
    enabled: bool = True
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TransformManager:
    """Enterprise Transformation & Middleware Manager."""

    def __init__(self, persistence_path: Optional[str] = None):
        self._rules: Dict[str, TransformRule] = {}
        self.persistence_path = persistence_path or os.environ.get(
            "VELOROUTE_TRANSFORMS_PATH", "transforms.json"
        )
        self._load_defaults()
        self._load()

    def _load_defaults(self):
        """Default privacy and security rules."""
        default_rules = [
            TransformRule(
                id="sec-strip-server",
                name="Strip Server Header",
                rule_type="strip_header",
                match_pattern="server",
                replacement="",
                enabled=True,
                description="Prevent server fingerprinting to external clients",
            ),
            TransformRule(
                id="sec-strip-openai-org",
                name="Strip OpenAI Org Header",
                rule_type="strip_header",
                match_pattern="openai-organization",
                replacement="",
                enabled=True,
                description="Hide internal OpenAI organization IDs from end users",
            ),
            TransformRule(
                id="sec-strip-upstream-ray",
                name="Strip Cloudflare Ray ID",
                rule_type="strip_header",
                match_pattern="cf-ray",
                replacement="",
                enabled=True,
                description="Remove CDN tracking headers",
            ),
        ]
        for r in default_rules:
            self._rules[r.id] = r

    def _load(self):
        try:
            p = Path(self.persistence_path)
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                for item in data:
                    rule = TransformRule(**item)
                    self._rules[rule.id] = rule
        except Exception as e:
            logger.debug(f"Failed to load transforms from {self.persistence_path}: {e}")

    def _save(self):
        try:
            p = Path(self.persistence_path)
            data = [r.to_dict() for r in self._rules.values()]
            content = json.dumps(data, indent=2)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(asyncio.to_thread(p.write_text, content, encoding="utf-8"))
            except RuntimeError:
                p.write_text(content, encoding="utf-8")
        except Exception as e:
            logger.debug(f"Failed to save transforms to {self.persistence_path}: {e}")

    async def save_async(self):
        try:
            p = Path(self.persistence_path)
            data = [r.to_dict() for r in self._rules.values()]
            content = json.dumps(data, indent=2)
            await asyncio.to_thread(p.write_text, content, encoding="utf-8")
        except Exception as e:
            logger.debug(f"Failed to save transforms to {self.persistence_path}: {e}")

    def add_rule(self, rule: TransformRule) -> TransformRule:
        self._rules[rule.id] = rule
        self._save()
        return rule

    def get_rule(self, rule_id: str) -> Optional[TransformRule]:
        if rule_id in self._rules:
            return self._rules[rule_id]
        for r in self._rules.values():
            if r.name == rule_id:
                return r
        return None

    def remove_rule(self, rule_id: str) -> bool:
        if rule_id in self._rules:
            del self._rules[rule_id]
            self._save()
            return True
        for k, r in list(self._rules.items()):
            if r.name == rule_id:
                del self._rules[k]
                self._save()
                return True
        return False

    def list_rules(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._rules.values()]

    def transform_model(self, model: str) -> str:
        """Apply model rewrite rules (glob and exact matches)."""
        if not model:
            return model
        current = model.strip()
        for r in self._rules.values():
            if not r.enabled or r.rule_type != "model_rewrite":
                continue
            pat = r.match_pattern.strip()
            if fnmatch.fnmatch(current.lower(), pat.lower()) or current.lower() == pat.lower():
                return r.replacement.strip()
        return current

    def transform_request_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Inject configured headers into upstream requests."""
        out = dict(headers)
        for r in self._rules.values():
            if not r.enabled or r.rule_type != "inject_header":
                continue
            if r.match_pattern:
                out[r.match_pattern] = r.replacement
        return out

    def transform_response_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Strip sensitive or fingerprinting response headers."""
        out = dict(headers)
        for r in self._rules.values():
            if not r.enabled or r.rule_type != "strip_header":
                continue
            pat = r.match_pattern.strip().lower()
            keys_to_remove = [k for k in out if k.lower() == pat or fnmatch.fnmatch(k.lower(), pat)]
            for k in keys_to_remove:
                del out[k]
        return out

    def transform_response_text(self, text: str) -> str:
        """Apply response redaction rules to assistant text."""
        if not text:
            return text
        current = text
        for r in self._rules.values():
            if not r.enabled or r.rule_type != "response_redact":
                continue
            pat = r.match_pattern
            if not pat:
                continue
            replacement = r.replacement if r.replacement is not None else "[REDACTED]"
            try:
                current = re.sub(re.escape(pat), replacement, current, flags=re.IGNORECASE)
            except Exception:
                pass
        return current

    def test_transform(
        self,
        test_type: str,
        input_value: str,
        header_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Interactive test sandbox for transformations."""
        if test_type == "model":
            transformed = self.transform_model(input_value)
            return {
                "test_type": "model",
                "original": input_value,
                "transformed": transformed,
                "modified": transformed != input_value,
            }
        elif test_type == "redact":
            transformed = self.transform_response_text(input_value)
            return {
                "test_type": "redact",
                "original": input_value,
                "transformed": transformed,
                "modified": transformed != input_value,
            }
        elif test_type == "header_inject":
            h = {header_key or "X-Default": input_value}
            transformed_h = self.transform_request_headers(h)
            return {
                "test_type": "header_inject",
                "original": h,
                "transformed": transformed_h,
                "modified": len(transformed_h) > len(h),
            }
        elif test_type == "header_strip":
            h = {input_value: "example-value", "Content-Type": "application/json"}
            transformed_h = self.transform_response_headers(h)
            return {
                "test_type": "header_strip",
                "original": h,
                "transformed": transformed_h,
                "modified": input_value not in transformed_h,
            }
        return {"error": "Invalid test_type"}
