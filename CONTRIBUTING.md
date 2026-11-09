# Contributing to VeloRoute

We welcome contributions to **VeloRoute**! Whether you are improving LLM routing strategies, optimizing prompt tokenizers, adding provider adapters, or refining the Next.js frontend, thank you for your support.

## Development Environment Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/mrgusux/veloroute.git
   cd veloroute
   ```

2. **Set up Python (FastAPI Engine)**:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate   # Windows
   pip install -e ".[dev]"
   ```

3. **Set up Frontend Website (Next.js 16)**:
   ```bash
   cd website
   npm install
   npm run dev
   ```

## Running the Verification Suite

All PRs must pass the test suites before merge:
- **Python Unit Tests**:
  ```bash
  python -m unittest discover -s tests -p "test_*.py"
  ```
- **Next.js Lint & Typecheck**:
  ```bash
  cd website
  npm run lint
  npm run build
  ```

## Engineering Principles

- **Zero Heavy ML Dependencies**: Keep heuristics fast, deterministic, and thread-safe.
- **Strict Concurrency**: Zero blocking I/O calls inside `async def` routes. Use `asyncio.to_thread` for disk access.
- **OWASP Best Practices**: Constant-time token comparisons (`secrets.compare_digest`), URL validation before making outbound requests, and sanitized error envelopes.
- **Conventional Commits**: Format commit messages as `feat:`, `fix:`, `docs:`, `perf:`, `test:`, or `refactor:`.
