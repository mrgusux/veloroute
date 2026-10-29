"""
Prompt Registry
===============
Storage-backed prompt management with versioning.
Prompts are named templates stored in-memory (or optionally persisted).
Templates support {{variable}} interpolation.

Usage::

    from llmcycle.core.prompts import PromptRegistry

    registry = PromptRegistry()

    # Register a versioned prompt template
    registry.set("summarizer", "Summarize the following in {{style}}: {{text}}", version="v1")
    registry.set("summarizer", "Provide a {{style}} summary of: {{text}}", version="v2")

    # Render the latest version
    rendered = registry.render("summarizer", style="bullet-point", text="Some long article...")

    # Render a specific version
    rendered_v1 = registry.render("summarizer", version="v1", style="short", text="...")

    # List all prompts and versions
    all_prompts = registry.list()
"""
from __future__ import annotations
import re
import time
from typing import Any, Dict, List, Optional, Tuple


class PromptVersion:
    """A single versioned snapshot of a named prompt template."""
    __slots__ = ("name", "version", "template", "description", "created_at")

    def __init__(
        self,
        name: str,
        version: str,
        template: str,
        description: str = "",
    ):
        self.name        = name
        self.version     = version
        self.template    = template
        self.description = description
        self.created_at  = time.time()

    def render(self, **kwargs: Any) -> str:
        """
        Interpolate {{variable}} placeholders in the template.

        Raises:
            KeyError: if a required variable is missing from kwargs.
        """
        def replacer(match: re.Match) -> str:
            var = match.group(1).strip()
            if var not in kwargs:
                raise KeyError(
                    f"Prompt '{self.name}' v{self.version} requires variable "
                    f"'{{{{ {var} }}}}' — not provided."
                )
            return str(kwargs[var])

        return re.sub(r"\{\{(.+?)\}\}", replacer, self.template)

    def variables(self) -> List[str]:
        """Return the list of required template variables."""
        return [m.strip() for m in re.findall(r"\{\{(.+?)\}\}", self.template)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "template": self.template,
            "description": self.description,
            "variables": self.variables(),
            "created_at": self.created_at,
        }


class PromptRegistry:
    """
    In-memory (optionally persistent) prompt template registry.

    Supports:
      - Named, versioned prompt templates with {{variable}} interpolation
      - Listing all prompts + versions
      - Fetching a specific version or the latest one
      - Deleting prompt versions

    For persistence, pass a storage-compatible dict/backend or
    call save() / load() with a JSON file path.

    Usage::

        from llmcycle.core.prompts import PromptRegistry

        reg = PromptRegistry()
        reg.set(
            "translate",
            "Translate the following text to {{language}}:\\n\\n{{text}}",
            version="v1",
            description="Basic translation prompt",
        )

        prompt = reg.render("translate", language="French", text="Hello world")
        print(prompt)  # → "Translate the following text to French: Hello world"
    """

    def __init__(self):
        # _store: {name → {version → PromptVersion}}
        self._store: Dict[str, Dict[str, PromptVersion]] = {}
        # _latest: {name → version_str}  (last registered wins)
        self._latest: Dict[str, str] = {}

    # ── Write ────────────────────────────────────────────────────────────────

    def set(
        self,
        name: str,
        template: str,
        version: str = "v1",
        description: str = "",
    ) -> PromptVersion:
        """Register or update a named + versioned prompt template."""
        pv = PromptVersion(name=name, version=version, template=template, description=description)
        if name not in self._store:
            self._store[name] = {}
        self._store[name][version] = pv
        self._latest[name] = version  # track latest as last registered
        return pv

    # ── Read ─────────────────────────────────────────────────────────────────

    def get(self, name: str, version: Optional[str] = None) -> PromptVersion:
        """
        Retrieve a PromptVersion by name and optional version.
        If version is None, returns the latest registered version.

        Raises:
            KeyError: if the prompt or version does not exist.
        """
        if name not in self._store:
            raise KeyError(f"Prompt '{name}' not found in registry.")
        versions = self._store[name]
        v = version or self._latest.get(name)
        if v not in versions:
            raise KeyError(
                f"Prompt '{name}' version '{v}' not found. "
                f"Available: {list(versions.keys())}"
            )
        return versions[v]

    def render(self, prompt_name: str, version: Optional[str] = None, **kwargs: Any) -> str:
        """
        Retrieve and render a prompt template, substituting all {{variables}}.

        Args:
            prompt_name: Prompt name (registered via set()).
            version:     Optional specific version. Defaults to the latest.
            **kwargs:    Template variable values to interpolate.

        Returns:
            Rendered prompt string.
        """
        return self.get(prompt_name, version).render(**kwargs)

    def list(self, name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all prompts and versions in the registry.

        Args:
            name: Optional filter — returns only versions for this prompt.
        """
        results = []
        names = [name] if name else list(self._store.keys())
        for n in names:
            for pv in self._store.get(n, {}).values():
                results.append(pv.to_dict())
        return results

    def delete(self, name: str, version: Optional[str] = None) -> int:
        """
        Delete a specific version or all versions of a prompt.

        Returns:
            Number of versions deleted.
        """
        if name not in self._store:
            return 0
        if version is not None:
            deleted = 1 if self._store[name].pop(version, None) else 0
            if not self._store[name]:
                del self._store[name]
                del self._latest[name]
            elif self._latest.get(name) == version:
                # Point latest to most recently added remaining version
                self._latest[name] = list(self._store[name])[-1]
            return deleted
        count = len(self._store[name])
        del self._store[name]
        del self._latest[name]
        return count

    def __len__(self) -> int:
        return sum(len(v) for v in self._store.values())

    def __repr__(self) -> str:
        return f"PromptRegistry({len(self)} versions across {len(self._store)} prompts)"
