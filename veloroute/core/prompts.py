"""
Prompt Registry & Template Hub
==============================
Enterprise prompt management with versioning, system instructions,
and {{variable}} interpolation. Inspired by Portkey Prompt Hub & Traceloop.

Usage::

    from veloroute.core.prompts import PromptRegistry

    registry = PromptRegistry()

    # Register a versioned prompt template
    registry.set(
        name="code_refactor",
        template="Refactor the following {{language}} code for {{goal}}:\n\n```{{language}}\n{{code}}\n```",
        system_prompt="You are a principal software engineer specialized in {{language}}.",
        version="v1",
        model="mock/mock-fast",
        description="Production code refactoring template",
    )

    # Render variables into chat messages ready for LLM execution
    messages = registry.render_messages("code_refactor", language="Python", goal="speed and readability", code="def f(): pass")
"""
from __future__ import annotations
import re
import time
from typing import Any, Dict, List, Optional, Tuple


class PromptVersion:
    """A single versioned snapshot of a named prompt template."""
    __slots__ = (
        "name", "version", "template", "system_prompt", "description",
        "model", "temperature", "max_tokens", "created_at"
    )

    def __init__(
        self,
        name: str,
        version: str,
        template: str,
        system_prompt: str = "",
        description: str = "",
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        self.name = name
        self.version = version
        self.template = template
        self.system_prompt = system_prompt
        self.description = description
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.created_at = time.time()

    def _interpolate(self, text: str, kwargs: Dict[str, Any]) -> str:
        def replacer(match: re.Match) -> str:
            var = match.group(1).strip()
            if var not in kwargs:
                raise KeyError(
                    f"Prompt '{self.name}' v{self.version} requires variable "
                    f"'{{{{ {var} }}}}' — not provided."
                )
            return str(kwargs[var])

        return re.sub(r"\{\{(.+?)\}\}", replacer, text)

    def render(self, **kwargs: Any) -> str:
        """Interpolate {{variable}} placeholders in the user template."""
        return self._interpolate(self.template, kwargs)

    def render_system(self, **kwargs: Any) -> str:
        """Interpolate {{variable}} placeholders in the system prompt."""
        if not self.system_prompt:
            return ""
        return self._interpolate(self.system_prompt, kwargs)

    def render_messages(self, **kwargs: Any) -> List[Dict[str, str]]:
        """Return full OpenAI-compatible chat messages list."""
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.render_system(**kwargs)})
        messages.append({"role": "user", "content": self.render(**kwargs)})
        return messages

    def variables(self) -> List[str]:
        """Return unique list of required template variables across user and system prompts."""
        vars_found: List[str] = []
        full_text = f"{self.system_prompt} {self.template}"
        for m in re.findall(r"\{\{(.+?)\}\}", full_text):
            cleaned = m.strip()
            if cleaned and cleaned not in vars_found:
                vars_found.append(cleaned)
        return vars_found

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "template": self.template,
            "system_prompt": self.system_prompt,
            "description": self.description,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "variables": self.variables(),
            "created_at": self.created_at,
        }


class PromptRegistry:
    """
    Prompt template registry supporting versions, system prompts, and variable substitution.
    """

    def __init__(self):
        # _store: {name → {version → PromptVersion}}
        self._store: Dict[str, Dict[str, PromptVersion]] = {}
        # _latest: {name → version_str}
        self._latest: Dict[str, str] = {}
        self._seed_default_templates()

    def _seed_default_templates(self):
        """Seed useful templates out-of-the-box."""
        self.set(
            name="code_refactor",
            template="Refactor the following {{language}} code for {{goal}}:\n\n```{{language}}\n{{code}}\n```",
            system_prompt="You are a Principal Software Architect. Output only the optimized code with concise docstrings.",
            version="v1",
            model="mock/mock-fast",
            description="Production code optimization and refactoring prompt",
        )
        self.set(
            name="smart_summarizer",
            template="Provide a {{style}} summary of the following document:\n\n{{text}}",
            system_prompt="You are an expert executive editor. Summarize with crisp clarity.",
            version="v1",
            model="mock/mock-fast",
            description="Executive and bulleted text summarizer",
        )
        self.set(
            name="sql_generator",
            template="Write an optimized {{dialect}} SQL query for the following requirement:\n\nSchema: {{schema}}\nTask: {{requirement}}",
            system_prompt="You are a Senior Database Administrator. Write performant, indexed, production-ready SQL.",
            version="v1",
            model="mock/mock-fast",
            description="Natural language to SQL query generation",
        )
        self.set(
            name="chain_of_thought_reasoner",
            template="Problem: {{problem}}\nConstraints: {{constraints}}\n\nBreak this down step-by-step, verify intermediate assumptions, and provide the final verified solution.",
            system_prompt="You are a rigorous analytical reasoning engine. Think step-by-step from first principles before stating your conclusion.",
            version="v1",
            model="mock/mock-smart",
            description="Step-by-step Chain-of-Thought analytical decomposition blueprint",
        )
        self.set(
            name="react_tool_agent",
            template="Objective: {{objective}}\nAvailable Tools: {{tools}}\nContext: {{context}}\n\nFollow the Thought -> Action -> Observation loop to accomplish the objective safely.",
            system_prompt="You are a deterministic ReAct autonomous agent. Never fabricate tool outputs; validate parameters before invoking any tool.",
            version="v1",
            model="mock/mock-smart",
            description="Structured ReAct (Reason + Act) tool-calling agent blueprint",
        )
        self.set(
            name="gsd_no_fluff_executor",
            template="Task: {{task}}\nDeliverable Format: {{format}}",
            system_prompt="Direct execution mode (GSD): zero preamble, zero apologies, zero filler. Output only the exact requested artifact.",
            version="v1",
            model="mock/mock-fast",
            description="High-density zero-fluff direct execution prompt (GSD / Caveman terse mode)",
        )
        self.set(
            name="humanizer_natural_writer",
            template="Rewrite the following draft in a natural, authentic human voice for {{audience}} while preserving every factual claim:\n\n{{draft}}",
            system_prompt="You are a seasoned human editor. Eliminate robotic AI cliches ('delve', 'testament', 'tapestry', 'moreover'), vary sentence cadence, and write with clarity.",
            version="v1",
            model="mock/mock-fast",
            description="Anti-AI-slop natural prose humanizer and style refiner",
        )
        self.set(
            name="solid_security_reviewer",
            template="Audit the following {{language}} code for OWASP Top 10 vulnerabilities, SSRF, injection flaws, and SOLID principle violations:\n\n```{{language}}\n{{code}}\n```",
            system_prompt="You are a Principal Application Security Engineer. Report severity (Critical/High/Medium/Low), exact line impact, and drop-in remediation code.",
            version="v1",
            model="mock/mock-smart",
            description="OWASP security vulnerability & SOLID architecture code auditor",
        )
        self.set(
            name="first_principles_architect",
            template="System Requirement: {{requirement}}\nScale & SLA Targets: {{sla}}\n\nDesign the architecture from first principles: bottlenecks, data model, failure modes, and trade-offs.",
            system_prompt="You are a Distinguished Distributed Systems Architect. Challenge fragile assumptions and justify every component choice.",
            version="v1",
            model="mock/mock-smart",
            description="First-principles system design and trade-off analysis blueprint",
        )

    # ── Write ────────────────────────────────────────────────────────────────

    def set(
        self,
        name: str,
        template: str,
        system_prompt: str = "",
        version: str = "v1",
        description: str = "",
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> PromptVersion:
        """Register or update a named + versioned prompt template."""
        clean_name = str(name).strip()
        clean_version = str(version).strip() or "v1"
        pv = PromptVersion(
            name=clean_name,
            version=clean_version,
            template=template,
            system_prompt=system_prompt,
            description=description,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if clean_name not in self._store:
            self._store[clean_name] = {}
        self._store[clean_name][clean_version] = pv
        self._latest[clean_name] = clean_version
        return pv

    # ── Read ─────────────────────────────────────────────────────────────────

    def get(self, name: str, version: Optional[str] = None) -> PromptVersion:
        """Retrieve a PromptVersion by name and optional version."""
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
        """Retrieve and render user template with variables."""
        return self.get(prompt_name, version).render(**kwargs)

    def render_messages(self, prompt_name: str, version: Optional[str] = None, **kwargs: Any) -> List[Dict[str, str]]:
        """Retrieve and render chat messages with variables."""
        return self.get(prompt_name, version).render_messages(**kwargs)

    def list(self, name: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all prompt versions, latest first."""
        results = []
        names = [name] if name else list(self._store.keys())
        for n in sorted(names):
            # Sort versions latest first
            for pv in reversed(list(self._store.get(n, {}).values())):
                results.append(pv.to_dict())
        return results

    def list_prompts_overview(self) -> List[Dict[str, Any]]:
        """Return latest version of each prompt for hub overview."""
        overview = []
        for name, versions in self._store.items():
            latest_v = self._latest.get(name)
            if latest_v and latest_v in versions:
                pv = versions[latest_v]
                data = pv.to_dict()
                data["version_count"] = len(versions)
                data["all_versions"] = list(versions.keys())
                overview.append(data)
        return overview

    def analyze_prompt(self, template: str, system_prompt: str = "") -> Dict[str, Any]:
        """
        Analyze a prompt template for structural clarity, role framing, variable
        parameterization, token efficiency, and prompt-injection resistance.
        """
        tpl = (template or "").strip()
        sys_p = (system_prompt or "").strip()
        combined = f"{sys_p}\n{tpl}".strip()
        words = combined.split()
        est_tokens = max(1, int(len(words) * 1.3)) if words else 0
        vars_found = [m.strip() for m in re.findall(r"\{\{(.+?)\}\}", combined) if m.strip()]

        score = 50
        suggestions: List[str] = []
        strengths: List[str] = []

        if sys_p:
            score += 15
            strengths.append("Dedicated system persona/instruction separated from user payload")
        else:
            suggestions.append("Add a System Prompt to separate behavioral rules from untrusted user input.")

        if vars_found:
            score += 15
            strengths.append(f"Parameterized with {len(set(vars_found))} dynamic variable(s): {', '.join(sorted(set(vars_found)))}")
        else:
            suggestions.append("Use {{variable}} placeholders to make the prompt reusable across inputs.")

        if re.search(r"\b(output|format|json|markdown|step-by-step|concise|only)\b", combined, re.IGNORECASE):
            score += 10
            strengths.append("Explicit output format or constraint directive detected")
        else:
            suggestions.append("Specify an explicit output constraint (e.g. JSON schema, Markdown sections, or word limit).")

        if re.search(r"(```|###|<[a-zA-Z0-9_-]+>|input:|context:|task:)", tpl, re.IGNORECASE):
            score += 10
            strengths.append("Delimiters/structural markers isolate data from instructions (anti-injection)")
        else:
            suggestions.append("Wrap untrusted {{variables}} in delimiters (e.g. ``` or XML tags) to harden against indirect prompt injection.")

        fluff_matches = re.findall(
            r"\b(please\s+kindly|if\s+you\s+don't\s+mind|i\s+was\s+wondering\s+if|as\s+much\s+as\s+possible)\b",
            combined,
            re.IGNORECASE,
        )
        if fluff_matches:
            score -= min(15, len(fluff_matches) * 5)
            suggestions.append("Remove conversational filler phrases to save tokens and sharpen instruction adherence.")

        score = max(0, min(100, score))
        grade = "A+" if score >= 90 else ("A" if score >= 80 else ("B" if score >= 65 else "C"))

        return {
            "score": score,
            "grade": grade,
            "estimated_tokens": est_tokens,
            "variables": sorted(set(vars_found)),
            "has_system_prompt": bool(sys_p),
            "strengths": strengths,
            "suggestions": suggestions,
        }

    def export_ide_rules(self, name: str, format_type: str = "cursorrules") -> Dict[str, Any]:
        """Export a prompt template as portable IDE agent rules (.cursorrules, CLAUDE.md, AGENTS.md)."""
        pv = self.get(name)
        fmt = (format_type or "cursorrules").lower().strip()
        filename = ".cursorrules" if fmt == "cursorrules" else ("CLAUDE.md" if fmt == "claude" else "AGENTS.md")
        content = (
            f"# {pv.name} ({pv.version}) — Exported from VeloRoute Prompt Hub\n"
            f"# Description: {pv.description or 'Enterprise AI Agent Rulebook'}\n\n"
            f"## System Persona & Guardrails\n"
            f"{pv.system_prompt or 'Follow project conventions and verify all changes.'}\n\n"
            f"## Execution Blueprint\n"
            f"{pv.template}\n"
        )
        return {
            "name": pv.name,
            "version": pv.version,
            "format": fmt,
            "filename": filename,
            "content": content,
        }

    def delete(self, name: str, version: Optional[str] = None) -> int:
        """Delete a specific version or all versions of a prompt."""
        if name not in self._store:
            return 0
        if version is not None:
            deleted = 1 if self._store[name].pop(version, None) else 0
            if not self._store[name]:
                del self._store[name]
                del self._latest[name]
            elif self._latest.get(name) == version:
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
