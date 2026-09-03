# CloudCare — Multi-Cloud AI-Powered Cost Intelligence Platform

Built for **Smart Horizon 2026 — Problem ID SH-FIN-03**.

CloudCare bridges infrastructure engineering and corporate finance: a
6-node LangGraph pipeline (Monitor → Analyzer → Decision → Supervisor →
Executor → Verifier) continuously ingests AWS / GCP / Azure / on-prem
telemetry, normalizes it to the FinOps Open Cost & Usage Specification
(FOCUS 1.0), finds waste with a deterministic rule engine plus an
IsolationForest ML layer, reasons about it with an LLM constrained to
structured tool calls, gates every action behind a deterministic risk-score
policy engine, and only ever *simulates* execution unless a human — or the
policy engine itself, for low-risk dev/staging actions — explicitly
approves it.

```
apps/
  web/        Next.js 14 (App Router) + TypeScript + Tailwind — dashboard, chat UI, NextAuth
  api/        FastAPI — REST + WebSocket, JWT-validating resource server
packages/
  schemas/    Pydantic contracts shared by every service (the FOCUS schema,
              ActionProposal, PolicyDecision, ...)
services/
  adapters/   CloudAdapter per provider (aws/gcp/azure/onprem) + AES-256-GCM credential encryption
  focus/      Raw telemetry -> FOCUS 1.0 UnifiedResource normalizer + synthetic multi-cloud datasets
  collector/  Real boto3 EC2/CloudWatch/Cost Explorer calls
  analyzer/   Deterministic rules + sklearn IsolationForest (the Analyzer Agent)
  decision/   Proposal templates + optional OpenAI structured-output reasoning (the Decision Agent)
  policy/     The risk-scoring policy engine (the Supervisor Agent)
  executor/   Idempotent, audited, template-mapped simulated execution (the Executor Agent)
  verifier/   ROI ledger (the Verifier Agent)
  orchestrator/  The LangGraph StateGraph wiring all 6 nodes together
  chat/       OpenAI function-calling tools mapped onto the same agent services
infrastructure/docker/   Dockerfiles used by the root docker-compose.yml
scripts/      seed.py (demo CloudAccounts), seed_focus_sample.py (real FOCUS/CUR data), test_graph.py (e2e smoke test)
```

## Quick start

**Requirements:** Node 18+, Python 3.11+ (3.12 recommended — some pinned ML
packages don't yet ship 3.13 wheels), and either Docker or a local MongoDB.

### Option A — Docker

```bash
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.local.example apps/web/.env.local
docker compose up --build
```

- Web: http://localhost:3000 — API docs: http://localhost:8000/docs

### Option B — manual

```bash
# Backend
cd apps/api && python -m venv .venv && ../../.venv/Scripts/activate  # or source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cd ../.. && uvicorn apps.api.main:app --reload

# Frontend (separate terminal)
cd apps/web
npm install
cp .env.local.example .env.local
npm run dev
```

Run `python -m scripts.test_graph` from the repo root any time to smoke-test
the full 6-node pipeline end to end without either server running.

## What's real today vs. what's a documented placeholder

Following the honesty convention this project inherited: every "not wired
up yet" spot is a `PLACEHOLDER`/`TODO` comment explaining exactly what to
fill in, not a silent stub.

**Real and testable right now, no external credentials needed:**
- The full LangGraph 6-node pipeline (`services/orchestrator/graph.py`),
  running against synthetic multi-cloud data by default
- The deterministic analyzer rules (`services/analyzer/rules.py`) and the
  sklearn IsolationForest layer (`services/analyzer/isolation_forest.py`)
- The risk-scoring policy engine (`services/policy/engine.py`) and its
  PolicyAdapter gatekeeper — production can never auto-execute
- The idempotent, audited SimulatedExecutor — no live cloud mutation ever
  happens regardless of `EXECUTION_ENABLED`
- FOCUS 1.0 normalization across all four providers
  (`services/focus/normalizer.py`)
- NextAuth ↔ FastAPI JWT trust (Google/GitHub/Entra ID OAuth +
  email/password), with FastAPI auto-provisioning new users
- The chat orchestrator's deterministic keyword-router fallback (works
  with zero API keys) and its Generative UI approval card, wired to the
  real Executor

**Real, but degrades to a synthetic fleet until you connect a live
account:**
- `services/adapters/aws_adapter.py` — needs `AWS_READ_ROLE_ARN` +
  `AWS_EXTERNAL_ID` in `apps/api/.env` (a real boto3 EC2/CloudWatch/Cost
  Explorer path already exists in `services/collector/`)
- `services/adapters/gcp_adapter.py` / `azure_adapter.py` — need a
  CloudAccount with encrypted service-account/client-secret credentials;
  the live SDK calls are a documented `PLACEHOLDER` in each file

**Needs an API key, else degrades to deterministic-only behavior:**
- `services/decision/llm.py` — the Decision Agent's structured-output
  reasoning (`OPENAI_API_KEY`)
- `services/chat/service.py` — the chat orchestrator's real function-calling
  loop (same key)

## Team & folder ownership

| Agent | Path | Description |
|---|---|---|
| Monitor | `services/adapters/`, `services/collector/` | Multi-cloud telemetry ingestion |
| Analyzer | `services/analyzer/` | Rule engine + IsolationForest |
| Decision | `services/decision/` | Proposal templates + LLM reasoning |
| Supervisor | `services/policy/` | Risk-score policy engine |
| Executor | `services/executor/` | Idempotent simulated execution |
| Verifier | `services/verifier/` | ROI ledger |
| Orchestrator | `services/orchestrator/` | LangGraph wiring |
| Chat | `services/chat/`, `apps/web/components/chat/` | Function-calling + Generative UI |
| Frontend | `apps/web/` | Dashboard, chat, NextAuth |
