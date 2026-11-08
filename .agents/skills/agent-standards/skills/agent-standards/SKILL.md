---
name: agent-standards
description: |
  Elite engineering standards and architectural best practices synthesized from virastack/ai, awesome-cursorrules, agentic-skills, and industry benchmarks. MANDATORY for React 19, Next.js 15/16 App Router, Tailwind CSS 4, Python Async FastAPI, Clean Architecture, and OWASP Top 10 Security.
  Trigger immediately for: React components, Next.js routes/layouts, Server Actions, Server Components vs Client Components, FastAPI endpoints, Pydantic models, async Python concurrency, database access, OWASP security audits, input validation, authentication/authorization, secret handling, and automated code review.
---

# Agent Standards & Universal Engineering Rules

This skill provides an authoritative, production-grade standard for full-stack web and backend engineering, synthesized from elite agent configurations (`virastack/ai`, `sickn33/agentic-awesome-skills`, `Kristories/awesome-guidelines`, `PatrickJS/awesome-cursorrules`, and `qodo-ai/pr-agent`).

---

## 1. Core Architectural Principles & Clean Code

- **Zero-Slop Code**: Every single line of code must serve a concrete purpose. No unnecessary wrapper functions, no redundant abstractions, no fake placeholders (`// TODO: implement later`), and no speculative features.
- **Strict Typing**:
  - TypeScript: Enable `strict: true`, avoid `any` (use `unknown` with type guards or discriminated unions), and enforce exhaustive pattern matching.
  - Python: Use strict type hints (`typing.Optional`, `list[str]`, `dict[str, Any]`, `Literal`, `Union`), and Pydantic v2 schemas for all input/output boundaries.
- **Layered Architecture (Separation of Concerns)**:
  1. **Transport Layer**: HTTP routing, request parsing, header validation, serialization (FastAPI router / Next.js route handlers).
  2. **Application Layer**: Orchestration, workflow coordination, business logic execution, transactions.
  3. **Domain & Data Layer**: Core entities, data storage access, external API clients, invariant validation.
- **Fail Fast & Explicit Errors**: Reject invalid inputs at the edge with descriptive 4xx errors; never swallow exceptions with bare `except:` or empty `catch {}` blocks.

---

## 2. React 19 & Next.js 15/16 App Router Standards

### Component Paradigm: Server-First
- **Server Components by Default**: All components in `app/` are React Server Components (RSC) by default. Do NOT add `'use client'` unless the component strictly requires:
  - React state or lifecycle hooks (`useState`, `useReducer`, `useEffect`, `useLayoutEffect`, `useRef`).
  - Browser-only APIs (`window`, `document`, `navigator`, `localStorage`, `sessionStorage`).
  - Interactive DOM event listeners (`onClick`, `onChange`, `onSubmit`, `onKeyDown`).
- **Push Client Boundaries Down**: Keep `'use client'` components at the furthest leaf nodes of the component tree. Pass Server Components as `children` or render props into Client Components to avoid dehydrating parent subtrees.

### High-Performance Data Fetching
- **No Cascading Waterfalls**: Never chain sequential awaits for independent data sources. Always execute independent fetches concurrently using `Promise.all` or `Promise.allSettled`:
  ```typescript
  // ✅ Concurrency:
  const [userData, analyticsData] = await Promise.all([
    fetchUserData(userId),
    fetchAnalytics(userId),
  ]);
  ```
- **Streaming & Suspense**: Wrap asynchronous UI regions in `<Suspense fallback={<Skeleton />}>` so that initial HTML renders instantly and dynamic data streams as chunks become ready.

### Server Actions & Mutations
- Mark mutation functions with `'use server'` at the file or function level.
- **Mandatory Input Validation**: Always validate the action payload using a schema validator (Zod) before invoking business logic:
  ```typescript
  'use server';
  import { z } from 'zod';

  const ActionSchema = z.object({
    id: z.string().uuid(),
    status: z.enum(['active', 'paused']),
  });

  export async function updateStatusAction(formData: unknown) {
    const parsed = ActionSchema.safeParse(formData);
    if (!parsed.success) {
      return { success: false, error: parsed.error.flatten() };
    }
    // Perform database mutation
    return { success: true };
  }
  ```
- **Cache Invalidation**: Use `revalidatePath('/dashboard')` or `revalidateTag('user-profile')` immediately after successful mutations.

### Asset & Layout Optimization
- Use `next/image` with explicit `width`, `height`, and `sizes` attributes for all image assets to eliminate Cumulative Layout Shift (CLS < 0.05).
- Use `next/font` for web fonts to eliminate layout flashes (FOUT / FOIT).

---

## 3. Tailwind CSS 4 & UI/UX Design Standards

- **Semantic Tokens**: Avoid hardcoding raw colors (`#1a1a1a` or `bg-slate-900`) everywhere. Use CSS variables and semantic classes (`bg-background`, `text-foreground`, `border-border`, `bg-primary`) to guarantee seamless light/dark mode transitions.
- **Accessibility (a11y)**:
  - Text contrast ratio must meet WCAG AA (minimum 4.5:1 for regular text, 3:1 for large text).
  - All interactive elements must support keyboard focus with visible outline/ring (`focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none`).
  - Use semantic elements (`<main>`, `<nav>`, `<aside>`, `<header>`, `<article>`, `<button>`). Do not use `div` with `onClick` when a `<button>` is appropriate.
  - Icon-only buttons must provide an `aria-label` or `sr-only` text description.
- **Fluid & Responsive Layout**: Mobile-first responsive modifiers (`sm:`, `md:`, `lg:`, `xl:`). Avoid fixed heights that cause clipping when text scales or wraps.
- **Micro-Interactions**: Restrict transitions to GPU-accelerated properties (`transform`, `opacity`). Keep durations between 150ms and 250ms for snappy responsiveness.

---

## 4. Python Clean Architecture & Async FastAPI Standards

### Async Concurrency & Non-Blocking Event Loops
- **Never Block the Event Loop**: In `async def` endpoints or coroutines, NEVER call synchronous blocking I/O:
  - ❌ `time.sleep()`, `requests.get()`, `urllib.request`, standard `open()` on large files, synchronous DB drivers.
  - ✅ `await asyncio.sleep()`, `await httpx_client.get()`, `aiofiles`, or offload blocking calls using `await asyncio.to_thread(sync_func, *args)`.
- If an operation is purely CPU-bound or uses a synchronous legacy library without an async equivalent, declare the endpoint as a standard `def endpoint(...)` so FastAPI executes it in its external worker threadpool, preserving the main event loop.

### Structured Schemas & Validation (Pydantic v2)
- Declare strict request models with `Field(..., min_length=..., max_length=..., ge=..., le=...)`.
- Avoid returning raw ORM instances or unbounded dictionaries. Always define explicit `response_model` schemas to prevent unintentional data leaks (e.g., password hashes, internal foreign keys).

### Dependency Injection & Modular Wiring
- Decouple controllers from business logic using `Depends()`:
  ```python
  from fastapi import Depends, APIRouter
  from typing import Annotated

  router = APIRouter(prefix="/v1/routes")

  @router.post("/dispatch", response_model=DispatchResponse)
  async def dispatch_route(
      payload: DispatchRequest,
      router_service: Annotated[RouterService, Depends(get_router_service)],
      current_user: Annotated[User, Depends(get_current_user)],
  ):
      return await router_service.dispatch(payload, user_id=current_user.id)
  ```

### Consistent JSON Error Envelopes
- Implement a global exception handler that returns structured, predictable errors:
  ```json
  {
    "error": {
      "code": "RESOURCE_NOT_FOUND",
      "message": "The requested virtual key was not found or is inactive.",
      "status": 404,
      "details": null
    }
  }
  ```

---

## 5. Security, OWASP & Zero-Trust Guidelines

1. **SQL & Command Injection Prevention**:
   - Always use parameterized queries (prepared statements, SQLModel/SQLAlchemy ORMs). Never perform string formatting or string concatenation to build SQL statements.
   - Never pass unsanitized user inputs to shell execution commands (`os.system`, `subprocess.run(shell=True)`).
2. **Secrets & PII Masking**:
   - Never commit API keys, private certificates, passwords, or authentication tokens to Git.
   - Mask sensitive secrets in logs and HTTP error responses (e.g., `sk-velo-AqAp...`).
   - Use constant-time comparison (`secrets.compare_digest`) for API token authentication to prevent timing attacks.
3. **Cross-Site Scripting (XSS) & SSRF**:
   - Never use `dangerouslySetInnerHTML` in React or unescaped template expressions without explicit sanitization (DOMPurify).
   - In proxy/routing systems (like VeloRoute), validate destination URLs against an allowlist and restrict access to local network addresses (`127.0.0.1`, `169.254.169.254`, `localhost`, RFC1918 private ranges) unless explicitly authorized.
4. **Rate Limiting & Abuse Prevention**:
   - Apply token-bucket or sliding-window rate limiting on all public API endpoints and authentication handlers.

---

## 6. Automated Code Review Checklist (PR Agent Standards)

When reviewing or writing code, audit against this checklist before approval:
- [ ] **Functional Correctness**: Does the code satisfy the exact requirements without regressions?
- [ ] **Edge Cases**: Are empty inputs, null values, network timeouts, invalid JSON, and extreme bounds gracefully handled?
- [ ] **Concurrency & Race Conditions**: Are state mutations protected by locks or atomic database operations?
- [ ] **Resource Cleanup**: Are HTTP sessions, open file descriptors, and database connections safely closed using context managers (`with` / `async with`)?
- [ ] **Test Coverage**: Does the pull request include unit/integration tests that prove the change works?
