# AGENTS.md — VeloRoute AI Gateway & Routing Engine

This file follows the portable `AGENTS.md` specification for coding agents (Claude Code, Cursor, Codex, Cline, Aider, Windsurf, OpenCode, and MCP-compatible agents).

## 1. Architecture Overview
- **Package Root**: `veloroute/`
- **Core Client**: `veloroute/client.py` (`VeloRoute` async/sync client, multi-provider routing, semantic & exact caching, slash-command directives).
- **Routing & Resilience**:
  - `veloroute/core/router.py`: `Router`, `RoutingStrategy` (`round_robin`, `least_latency`, `cost`, `priority`, `smart`, `kv_affinity`, `hedging`, `quality`, `flagship`), `ComplexityClassifier`, `QualityTracker`, `parse_slash_command`.
  - `veloroute/core/stream.py`: `StreamResilienceManager` (mid-stream failover, exponential backoff with jitter, parallel speculative `hedging` execution).
  - `veloroute/core/keys.py`: `KeyManager` (round-robin rotation, cooldown recovery, circuit breaker state machine).
- **Security & Guardrails**:
  - `veloroute/core/guardrail.py`: `GuardrailManager` (Tier-0 deterministic regex secret/PII scrubbing + Shannon entropy detection + lossless response unmasking).
  - `veloroute/core/injection.py`: `InjectionGuard` (weighted heuristic prompt injection & jailbreak shield).
- **Context Optimization & Prompts**:
  - `veloroute/core/context_optimizer.py`: `ContextOptimizer` (ANSI stripping, whitespace normalization, AST Python skeletonizer, Caveman terse mode).
  - `veloroute/core/prompts.py`: `PromptRegistry` (versioned Jinja-style templates, quality auditing, `.cursorrules` / `CLAUDE.md` / `AGENTS.md` rule exporter).
  - `veloroute/core/mcp.py`: `MCPRegistry` (built-in & custom HTTP MCP tools, RTK output compression, security posture auditing, SSE transport).
- **Gateway & Web UI**:
  - `veloroute/ui/app.py` & `veloroute/ui/routes/`: FastAPI OpenAI-compatible (`/v1/chat/completions`, `/v1/responses`, `/v1/embeddings`), Anthropic-compatible (`/v1/messages`), Gemini-compatible (`/v1beta/models/{model}:generateContent`), Ollama-compatible (`/api/chat`, `/api/generate`, `/api/tags`), and Admin REST API (`/api/v1/*`).
- **Frontend Landing & Dashboard**:
  - `website/`: Next.js 15+ App Router, React 19, Tailwind CSS 4, static prerendering.

## 2. Universal Agent Standards & Rule Map
All coding agents operating on this repository must strictly adhere to the project's modular rules:

| Domain | Cursor Rule (`.cursor/rules/`) | Claude Code Rule (`.claude/rules/`) | Key Principles |
| :--- | :--- | :--- | :--- |
| **Next.js & React** | `nextjs-react.mdc` | `nextjs-react.md` | Server Components by default; leaf `'use client'`; parallel `Promise.all` fetching; Zod-validated Server Actions; zero CLS. |
| **Python & FastAPI** | `python-fastapi.mdc` | `python-fastapi.md` | Zero blocking calls in `async def`; Pydantic v2 schemas; clean layer separation; standard error envelopes. |
| **Security & OWASP** | `security-owasp.mdc` | `security.md` | Zero hardcoded credentials; constant-time token comparison; parameterized SQL; SSRF protection; prompt injection defense. |
| **Testing & Quality** | `testing-quality.mdc` | `testing.md` | 100% deterministic tests; zero mock flakiness; all 219+ unit tests must pass; never weaken or skip assertions. |

## 3. Development & Verification Commands
- **Run full unit test suite**:
  ```powershell
  .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
  ```
- **Run Next.js website build & lint**:
  ```powershell
  cd website
  npm run lint
  npm run build
  ```
- **Run CLI diagnostics**:
  ```powershell
  .\.venv\Scripts\python.exe -m veloroute.cli doctor
  .\.venv\Scripts\python.exe -m veloroute.cli recipes
  ```
- **Start Web UI & Gateway Server**:
  ```powershell
  .\.venv\Scripts\python.exe -m veloroute.cli ui --host 127.0.0.1 --port 8000
  ```

## 4. Coding Conventions & Guardrails
- Maintain zero mandatory heavy ML dependencies in the core path; keep heuristics deterministic, fast, and thread-safe.
- Use exclusively `VeloRoute` / `veloroute` branding across all code, tests, comments, and UI templates.
- Ensure every UI control in `veloroute/ui/templates/pages/` is backed by a real FastAPI route in `veloroute/ui/routes/`.
- All automated PR reviews and static security scans are enforced via `.github/workflows/semgrep.yml` and `.github/workflows/ai-code-review.yml`.
