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

## 2. Development & Verification Commands
- **Run full unit test suite**:
  ```powershell
  .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
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

## 3. Coding Conventions
- Maintain zero mandatory heavy ML dependencies in the core path; keep heuristics deterministic, fast, and thread-safe.
- Use exclusively `VeloRoute` / `veloroute` branding across all code, tests, comments, and UI templates.
- Ensure every UI control in `veloroute/ui/templates/pages/` is backed by a real FastAPI route in `veloroute/ui/routes/`.
