# Universal Agent Standards & Engineering Rules

## 1. Zero-Slop & Production Quality
- Every file and function must be fully implemented. Never write placeholder comments, fake stub implementations, or unhandled `TODO` blocks.
- Follow Clean Architecture: Keep transport logic (FastAPI / Next.js routes), business logic (services / orchestrators), and data access (repositories / models) strictly separated.

## 2. Next.js 15+ & React 19 Standards
- Components are Server Components (RSC) by default. Use `'use client'` only at leaf nodes requiring DOM events, state, or browser APIs.
- Avoid waterfall fetches: execute independent async operations with `Promise.all`.
- Use Suspense boundaries with skeleton fallbacks for dynamic content.
- Validate Server Action inputs with Zod schemas.

## 3. Python Async & FastAPI Standards
- Never block the event loop in `async def`: use `await asyncio.to_thread` for legacy sync I/O or use native async libraries (`httpx`, `aiofiles`).
- Use Pydantic v2 schemas for all request validations and response models.
- Implement structured exception handling with standardized error envelopes.

## 4. Security & Zero-Trust
- Zero tolerance for hardcoded credentials: all secrets must be loaded from environment variables.
- Constant-time string comparison (`secrets.compare_digest`) for API key and token checks.
- Parameterized queries only—never string-interpolate SQL.
- Prevent SSRF by validating and restricting target hostnames in routing and proxying layers.
- Strip sensitive PII and API keys from logging pipelines.
