---
paths:
  - "veloroute/**"
  - "**/*.py"
  - "tests/**"
---

# Python Clean Architecture & Async FastAPI (Claude Code)

- **Non-Blocking Async**:
  - Never call blocking synchronous I/O (`time.sleep()`, synchronous `requests`, blocking DB queries) in `async def` endpoints or coroutines.
  - Use `await asyncio.sleep()`, `httpx.AsyncClient`, or `await asyncio.to_thread(...)`.
  - For synchronous CPU-heavy or legacy functions, declare standard `def` endpoints so FastAPI routes them to its worker thread pool.
- **Layer Separation**:
  - `veloroute/ui/routes/` and `veloroute/gateway/`: API transport layer.
  - `veloroute/core/`: Domain routing, resilience, key management, and guardrails (pure business logic, zero Starlette/FastAPI dependencies).
  - `veloroute/storage/`: Persistence layer.
- **Pydantic v2 Models**:
  - Use strict Pydantic models with `Field(...)` constraints for all request bodies and return models.
- **Error Handling**:
  - Return standardized JSON error envelopes `{"error": {"code": str, "message": str}}`.
