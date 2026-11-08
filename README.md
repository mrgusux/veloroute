<div align="center">

# ⚡ VeloRoute

**Enterprise Universal AI Gateway, High-Availability LLM Routing & Token-Saviour Optimization Engine**

[![CI](https://github.com/mrgusux/veloroute/actions/workflows/ci.yml/badge.svg)](https://github.com/mrgusux/veloroute/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://www.python.org/downloads/)
[![Docker Ready](https://img.shields.io/badge/docker-multi--stage%20slim-2496ED.svg?logo=docker&logoColor=white)](https://github.com/mrgusux/veloroute)
[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fmrgusux%2Fveloroute&root-directory=website)
[![Next.js 15](https://img.shields.io/badge/Next.js-15%20App%20Router-black.svg?logo=nextdotjs&logoColor=white)](https://github.com/mrgusux/veloroute/tree/main/website)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests Passing](https://img.shields.io/badge/tests-219%20passed-brightgreen.svg)](https://github.com/mrgusux/veloroute)
[![Code Coverage](https://img.shields.io/badge/coverage-99%25-success.svg)](https://github.com/mrgusux/veloroute)
[![Architecture: Zero Heavy ML](https://img.shields.io/badge/architecture-Zero--Heavy--ML-orange.svg)](https://github.com/mrgusux/veloroute)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/mrgusux/veloroute/pulls)

*A blazingly fast, multi-provider AI gateway engineered for production reliability, radical token cost reduction, instant mid-stream failover, and zero vendor lock-in.*

[Landing Page](website/) • [Key Features](#key-features) • [Architecture](#architecture) • [Docker & K8s Quickstart](#docker--kubernetes-quickstart) • [Local Quickstart](#local-python-quickstart) • [SDK Integration](#sdk-integration) • [Routing Strategies](#routing-strategies) • [CLI & Dashboard](#cli--dashboard)


</div>

---

## 🌟 Executive Overview

**VeloRoute** is a unified, high-throughput reverse proxy and intelligent routing gateway designed for mission-critical generative AI workloads. It seamlessly converts API formats across major LLM ecosystems (**OpenAI, Anthropic Claude, Google Gemini, Ollama, Groq, DeepSeek, AWS Bedrock, and self-hosted models**), while eliminating downtime through automated key rotation, circuit breakers, parallel speculative hedging, and mid-stream failover.

With its built-in **Token-Saviour Suite**, VeloRoute drastically cuts inference bills through exact & semantic caching, AST code skeletonization, and terse context compression—all running purely on deterministic, microsecond heuristics with **zero heavy ML runtimes**.

---

## 🏗️ Architecture

```
                    ┌────────────────────────────────────────────────────────┐
                    │                 Client Applications                    │
                    │   OpenAI SDK  •  Anthropic SDK  •  Cursor  •  LangChain │
                    └───────────────────────────┬────────────────────────────┘
                                                │ HTTP / SSE Stream
                                                ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                                 VeloRoute AI Gateway                                     │
│                                                                                          │
│  ┌───────────────────────┐  ┌─────────────────────────┐  ┌────────────────────────────┐  │
│  │ Compatibility Layer   │  │ Security & Guardrails   │  │ Token-Saviour Engine       │  │
│  │ • /v1/chat/completions│  │ • PII / Secret Scrubbing│  │ • Exact & Semantic Caching  │  │
│  │ • /v1/messages        │  │ • InjectionGuard Shield │  │ • Context AST Skeletonizer │  │
│  │ • /v1beta/models/*    │  │ • Virtual Key Quotas    │  │ • Whitespace / Caveman Mode│  │
│  │ • /api/chat & /tags   │  │ • Lossless Unmasking    │  │ • RTK MCP Output Trimmer   │  │
│  └───────────┬───────────┘  └────────────┬────────────┘  └─────────────┬──────────────┘  │
│              │                           │                             │                 │
│              ▼                           ▼                             ▼                 │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ Model Routing & Resilience Engine                                                  │  │
│  │ • KV-Affinity • Smart Latency • Cost-Aware • Speculative Hedging • Flagship Tier   │  │
│  │ • Sentinel Circuit Breakers (Trip/Cooldown/Half-Open) • Round-Robin Key Manager   │  │
│  └───────────────────────────────────────┬────────────────────────────────────────────┘  │
└──────────────────────────────────────────┼───────────────────────────────────────────────┘
                                           │ Dynamic Multiplexing
        ┌──────────────────────────────────┼──────────────────────────────────┐
        ▼                                  ▼                                  ▼
┌─────────────────┐               ┌─────────────────┐               ┌─────────────────┐
│  OpenAI API     │               │  Anthropic API  │               │ Google Gemini   │
│  gpt-4o, o1     │               │  claude-3-5-*   │               │ gemini-2.0-*    │
└─────────────────┘               └─────────────────┘               └─────────────────┘
        ▼                                  ▼                                  ▼
┌─────────────────┐               ┌─────────────────┐               ┌─────────────────┐
│  Groq / Cerebras│               │  Ollama / Local │               │ DeepSeek / VLLM │
│  Llama-3.3-70B  │               │  Mistral, Qwen  │               │ deepseek-r1     │
└─────────────────┘               └─────────────────┘               └─────────────────┘
```

---

## 🚀 Key Features

### 1. 🌐 Universal Multi-Provider AI Gateway
- **Drop-in Compatible**: Full wire-level compatibility for `/v1/chat/completions`, `/v1/embeddings`, `/v1/models`, Anthropic `/v1/messages`, Google Gemini `/v1beta/models/*`, and Ollama `/api/chat`, `/api/generate`, `/api/tags`.
- **Zero-Code Switchover**: Point existing apps to `http://localhost:8000/v1` without modifying a single line of SDK code.
- **Dynamic Model Transformation**: Real-time cross-protocol translation between OpenAI messages, Anthropic structured blocks, and Gemini parts.

### 2. ⚡ KV-Affinity & Intelligent Routing
- **`kv_affinity`**: Pins requests with identical system prompts or large context prefixes to the same provider key/backend to maximize hardware KV-cache hits and prompt cache discounts.
- **`smart`**: Dynamically routes lightweight requests to budget engines (e.g. `gpt-4o-mini`) and deep analytical queries to flagship models (`o1`, `claude-3-5-sonnet`).
- **`least_latency` & `hedging`**: Dispatches requests across the lowest-latency endpoints or issues speculative parallel hedged queries with automatic cancellations.
- **`cost` & `priority`**: Tiered fallback chains with priority tiering and real-time cost-per-million optimization.

### 3. 💰 Token-Saviour Suite
- **Exact & Semantic Caching**: Instant sub-millisecond retrieval with TTL support and cosine similarity clustering for repetitive queries.
- **AST Python Skeletonizer**: Compresses large Python context files down to signatures and docstrings, slashing context tokens by up to 70%.
- **Whitespace & ANSI Trimmer**: Strips terminal codes and redundant indentations.
- **Caveman Mode**: Instructs models into ultra-terse, high-density outputs for agent workflows.

### 4. 🛡️ Sentinel Circuit Breaker & Key Rotation
- **Multi-Key Load Balancing**: Spreads request load across pools of API keys per provider.
- **Health State Machine**: Auto-tracks 5xx server faults and 429 rate limits, transitioning keys through `OPEN`, `HALF_OPEN`, and `CLOSED` states with exponential backoff and randomized jitter.
- **Auth Guard**: Automatically deactivates invalid credentials on HTTP 401 without taking down remaining provider keys.

### 5. 🔒 Zero-Trust Guardrails & Security
- **Tier-0 Deterministic Scrubbing**: Real-time redaction of sensitive credentials (API tokens, private keys, AWS secrets) and PII with lossless unmasking on return.
- **Shannon Entropy Detector**: Detects high-entropy random keys even if unseen in regex patterns.
- **InjectionGuard**: Weighted heuristic scanning against prompt injection, privilege escalation, and jailbreak attempts.
- **Virtual Keys**: Mint multi-tenant virtual keys with strict budget limits ($/day), auto-pausing, model access allowlists, and key rotation.

### 6. 🧩 Universal MCP Gateway
- Connect standard **Model Context Protocol (MCP)** servers over HTTP and SSE.
- Built-in tool compression with RTK token savings and security posture audits.

### 7. 📊 Observability & Web Dashboard
- **Prometheus Metrics**: Exposes `/metrics` with request counts, token consumption, latency histograms, and circuit breaker trip counters.
- **Real-Time Latency Matrix**: Continuously benchmarks provider TTFT (time-to-first-token) and end-to-end response times.
- **Modern Glassmorphic UI**: Includes an interactive Playground, Virtual Key Manager, Providers & Keys Manager, Model Matrix, and Real-Time Telemetry.

---

## 📦 Quickstart

### 🐳 Option A: 1-Command Docker Run (Fastest)

Launch the gateway and live web dashboard instantly using the multi-stage unprivileged Docker image:

```bash
docker run -d \
  --name veloroute \
  -p 8000:8000 \
  -v veloroute_data:/data \
  -e OPENAI_API_KEY="sk-..." \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  ghcr.io/mrgusux/veloroute:latest
```

The gateway and dashboard are now live at **`http://localhost:8000`** with automated healthcheck probes on `/health`.

---

### 🐳 Option B: Docker Compose (Production Ready)

Clone the repository and launch with volume persistence and auto-restart:

```bash
git clone https://github.com/mrgusux/veloroute.git
cd veloroute
cp .env.example .env
# Edit .env with your provider API keys
docker compose up -d
```

View container logs and status:
```bash
docker compose ps
docker compose logs -f
```

---

### ☸️ Option C: Enterprise Kubernetes

Deploy VeloRoute to your Kubernetes cluster (EKS, GKE, AKS, or bare-metal):

```bash
# Apply ConfigMap, PVC, Deployment, and Service
kubectl apply -f deploy/k8s/
```

Verify pod health:
```bash
kubectl get pods -l app.kubernetes.io/name=veloroute
kubectl get svc veloroute
```

---

### ▲ Option D: Next.js Landing Page on Vercel

The production Next.js landing page lives in `website/` and is optimized for free instant Vercel deployment:

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fmrgusux%2Fveloroute&root-directory=website)

Or run locally:
```bash
cd website
npm install
npm run dev
# Open http://localhost:3000
```

---

### 🐍 Option E: Local Python Quickstart

#### 1. Installation

```bash
# Clone the repository
git clone https://github.com/mrgusux/veloroute.git
cd veloroute

# Create and activate virtual environment
python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Install dependencies in editable mode
pip install -e .
```

#### 2. Configure Environment

Copy the example configuration:

```bash
cp .env.example .env
```

Add your provider keys to `.env` or set them via CLI / UI:

```env
OPENAI_API_KEYS=sk-proj-...,sk-proj-...
ANTHROPIC_API_KEYS=sk-ant-...
GROQ_API_KEYS=gsk-...
GEMINI_API_KEYS=AIzaSy...
```

#### 3. Launch VeloRoute

Start the UI and Gateway Server:

```bash
veloroute ui --host 127.0.0.1 --port 8000
```

*(On Windows, you can simply double-click `menu.bat` or `dashboard.bat`)*


Dashboard will be live at: **`http://127.0.0.1:8000`**

---

## 🔌 SDK Integration

### OpenAI SDK (Python)

Simply redirect `base_url` to VeloRoute:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key="sk-velo-virtual-key" # or any string if require_api_key is 0
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a senior software architect."},
        {"role": "user", "content": "Explain KV-cache optimization in 3 bullet points."}
    ],
    temperature=0.7,
)

print(response.choices[0].message.content)
```

### Anthropic SDK (Python)

Works seamlessly with Anthropic Messages API:

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://127.0.0.1:8000",
    api_key="sk-velo-virtual-key"
)

message = client.messages.create(
    model="claude-3-5-sonnet",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Hello VeloRoute!"}
    ]
)
print(message.content[0].text)
```

### Native VeloRoute Client

For programmatic high-level resilience and fallback chains:

```python
import asyncio
from veloroute import VeloRoute, RoutingStrategy

async def main():
    client = VeloRoute(
        strategy=RoutingStrategy.SMART,
        fallbacks={
            "gpt-4o": ["claude-3-5-sonnet", "gemini-1.5-pro", "groq/llama-3.3-70b-versatile"],
        },
        auto_trim_context=True,
    )

    response = await client.chat_complete(
        model="gpt-4o",
        messages=[{"role": "user", "content": "/save-tokens Optimize this database query: SELECT * FROM users;"}],
    )
    print(response.choices[0].message.content)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## ⚡ Slash Command Directives

Prefix your user messages or prompts with inline directives to override gateway behavior on the fly:

| Directive | Description |
|-----------|-------------|
| `/smart` | Enables automatic complexity evaluation to dynamically route query to the optimal model tier. |
| `/fast` | Forces the `least_latency` routing strategy across available endpoints. |
| `/cost` | Minimizes inference spend by routing through the cheapest model with capable context length. |
| `/flagship` | Forces execution through elite reasoning models (`gpt-4o`, `claude-3-5-sonnet`, `o1`). |
| `/save-tokens` | Activates aggressive AST skeletonization, whitespace trimming, and context optimization. |
| `/caveman` | Forces ultra-terse, zero-filler, bullet-dense model completions. |

---

## 💻 CLI Commands

VeloRoute includes a complete CLI management tool:

```powershell
# Diagnostics and quick verification
veloroute doctor
veloroute recipes

# Provider & Key Management
veloroute providers add openai sk-proj-1,sk-proj-2
veloroute providers add deepseek sk-ds-1 --base-url https://api.deepseek.com/v1
veloroute keys list
veloroute keys remove openai sk-proj-1

# Dynamic Provider Ping & Upstream Models
veloroute ping
veloroute models

# Proxy Configuration
veloroute proxy set http://127.0.0.1:8080
veloroute proxy show
veloroute proxy clear

# Launch Gateway Server
veloroute ui --port 8000
```

---

## ⚙️ Configuration & Environment Variables

| Variable | Description | Default |
|---|---|---|
| `VELOROUTE_UI_HOST` | Web Dashboard and Gateway bind host | `127.0.0.1` |
| `VELOROUTE_UI_PORT` | Web Dashboard and Gateway bind port | `8000` |
| `VELOROUTE_STORAGE_BACKEND` | Storage backend (`sqlite`, `postgres`, `mongo`, `redis`) | `sqlite` |
| `VELOROUTE_STORAGE_URL` | SQLAlchemy storage URL | `sqlite+aiosqlite:///./veloroute.db` |
| `VELOROUTE_PROXY` | Outbound proxy for all upstream LLM requests | `None` |
| `VELOROUTE_REQUIRE_API_KEY` | Enforce virtual API key on `/v1/*` endpoints (`1` or `0`) | `0` |
| `VELOROUTE_KEY_PEPPER` | Salt pepper string for virtual key SHA256 hashes | `""` |
| `VELOROUTE_CORS_ORIGINS` | Trusted origins for CORS (comma-separated) | `""` |
| `VELOROUTE_USER_ADMIN` | Dashboard admin username | `admin` |
| `VELOROUTE_USER_ADMIN_PASSWORD` | Dashboard admin password | `admin` |

---

## 🧪 Testing

The repository comes with a comprehensive, zero-mock and real-scenario test suite with **219 unit and integration tests**:

```bash
# Run all unit and integration tests
python -m unittest discover -s tests -p "test_*.py"

# Test specific subsystem
python -m unittest tests.test_all_new_features
python -m unittest tests.test_veloroute_rebranding
python -m unittest tests.test_gateway_security
```

---

## 🤝 Contributing

Contributions are warmly welcomed! Please read our [features catalog](features.md) and feel free to submit pull requests:

1. Fork the Project (`https://github.com/mrgusux/veloroute`)
2. Create your Feature Branch (`git checkout -b feat/amazing-feature`)
3. Run the test suite (`python -m unittest discover -s tests -p "test_*.py"`)
4. Commit your changes (`git commit -m 'feat: add amazing feature'`)
5. Push to the Branch (`git push origin feat/amazing-feature`)
6. Open a Pull Request

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more information.

---

<div align="center">
  Crafted with precision by <a href="https://github.com/mrgusux">Mr. Gusu (@mrgusux)</a> and the VeloRoute open-source community.
</div>
