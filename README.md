# CloudCare — Full-Stack Hackathon Build

AI-Powered Cloud Cost Optimization & Resource Intelligence Platform
Prepared for Smart Horizon 2026 — Problem ID SH-FIN-03 — Team Alpha, PCCOE Pune

This is a **working full-stack scaffold**: Next.js + TypeScript frontend,
Python (FastAPI) backend, MongoDB for storage. It runs today with mock data
(landing page → login → dashboard with charts, agent feed, resource table).
Everywhere the real integration (AWS, MongoDB, LLM) isn't wired in yet, you'll
find a `PLACEHOLDER` or `TODO` comment explaining exactly what to do.

```
cloudcare-fullstack/
├── frontend/          Next.js 14 (App Router) + TypeScript + Tailwind
├── backend/           FastAPI + Pydantic, MongoDB via motor
└── docker-compose.yml Runs frontend + backend + a local MongoDB together
```

---

## 1. Quick start (fastest way to see it running)

You need Node.js 18+, Python 3.11+, and either Docker OR a local MongoDB.

### Option A — Docker (easiest, includes MongoDB)

```bash
cd cloudcare-fullstack
cp backend/.env.example backend/.env
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend docs (Swagger UI): http://localhost:8000/docs

### Option B — Run frontend and backend manually

**Backend:**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```
Backend runs at http://localhost:8000 — visit `/docs` for interactive API docs.

**Frontend (separate terminal):**
```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```
Frontend runs at http://localhost:3000.

The frontend dashboard currently uses its own mock data
(`frontend/lib/mockData.ts`) and does **not** yet call the backend — see
section 3 below for how to connect them.

---

## 2. What already works today (no setup needed)

- Landing page: hero, animated 7-stage pipeline, feature slider, team, contact form
- Login page: accepts any User ID / Password (demo mode)
- Dashboard: KPI cards, cost trend chart, resource health donut, agent
  activity feed, resource table, "What's next" onboarding panel — all mock data
- Backend API with the same shapes, running independently, with interactive
  docs at `/docs` — resources, agent activity, recommendations
  (approve/execute), forecasts, savings, a demo login endpoint, and stubs for
  cloud-account validation and starting a run
- A real, working **policy engine** (`backend/app/services/policy/engine.py`)
  implementing the safety matrix from the blueprint — production resources
  can never auto-execute
- A real, working **idle-detection rule** (`backend/app/services/analyzer/rules.py`)
- A real **LangGraph pipeline wiring** (`backend/app/services/orchestrator/graph.py`)
  — the 6-node graph runs, but each node currently returns mock data

---

## 3. Placeholder checklist — what to fill in before/after judging

Everything below is marked with `PLACEHOLDER` or `TODO` comments in the
code. Rough priority order if you're short on time:

### Must-do for a stronger demo
- [ ] **Connect frontend to backend.** Currently `frontend/lib/mockData.ts`
      is used directly. Replace those imports with `fetch()` calls to
      `process.env.NEXT_PUBLIC_API_BASE_URL` (already set up in
      `.env.local.example`). Start with `KpiCards.tsx` and `ResourceTable.tsx`.
- [ ] **MongoDB Atlas.** Create a free cluster at mongodb.com/cloud/atlas,
      get a connection string, put it in `backend/.env` as `MONGODB_URI`.
      Run `python -m scripts.seed` from `backend/` to load the mock data in.
- [ ] **Point routers at Mongo instead of mock_data.py.** Each router
      (`backend/app/routers/*.py`) has a `# TODO: replace with Mongo query`
      comment showing exactly what to change.

### Nice-to-have if time allows
- [ ] **Real AWS sandbox account.** Create a free-tier AWS account, launch a
      few small EC2 instances, create a read-only IAM role. Put the role ARN
      + external ID in `backend/.env`. Then implement
      `backend/app/services/collector/ec2.py` and `cloudwatch.py`.
- [ ] **Real LLM call for the Decision agent.** Get an OpenRouter API key,
      put it in `backend/.env` as `OPENROUTER_API_KEY`, then replace the
      mock logic in `backend/app/services/orchestrator/nodes.py::decide()`
      with a real constrained-JSON LLM call.
- [ ] **Real auth.** Replace `backend/app/routers/auth.py`'s "accept
      anything" logic with real password verification against a `users`
      collection in MongoDB, and issue a real JWT (the libraries are already
      in `requirements.txt`).

### Can wait until after the hackathon
- [ ] Real executor (`backend/app/services/executor/actions.py`) — actually
      calling `ec2.stop_instances()`
- [ ] Real verifier (`backend/app/services/verifier/health.py`) — post-action
      health + savings check
- [ ] WebSocket live event stream for the Agent Activity feed (blueprint 11.3)
- [ ] Deployment: Vercel for the frontend, Render/Railway/ECS for the
      backend, Atlas for MongoDB

---

## 4. Pushing this to GitHub with Copilot in VS Code

1. Unzip this project on your PC and open the `cloudcare-fullstack` folder in VS Code.
2. Install the GitHub Copilot + GitHub Pull Requests extensions if you haven't already, and sign in.
3. Open a terminal in VS Code and initialize git:
   ```bash
   cd cloudcare-fullstack
   git init
   git add .
   git commit -m "Initial full-stack CloudCare scaffold"
   ```
4. Create a new (empty) repo on GitHub, then:
   ```bash
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git branch -M main
   git push -u origin main
   ```
5. Double-check `backend/.env` and `frontend/.env.local` are **not** staged
   (they're in `.gitignore` already) — only the `.env.example` /
   `.env.local.example` files should be committed.
6. From here, use Copilot Chat in VS Code to help fill in each `TODO` —
   point it at the specific file (e.g. `backend/app/services/collector/ec2.py`)
   and ask it to implement the function per the docstring; the docstrings
   are written to give Copilot enough context to do this well.

---

## 5. Judge-facing notes

This scaffold matches the architecture in the submitted blueprint:
5 agents (Monitor, Analyzer, Decision, Supervisor, Executor) communicating
through one shared state object, a deterministic policy engine that can't be
overridden by the LLM, and a template-mapped executor that never runs
free-form commands. If you're asked "is this real code or just a mockup" —
the policy engine, the idle-detection rule, and the LangGraph wiring are
real and testable today; the AWS/LLM/Mongo integrations are placeholders
with a clear, documented path to finishing them.

---

## 6. Team & Folder Ownership
| Agent | Service Path | Description |
|---|---|---|
| Monitor | `backend/app/services/aws` & `collector/` | Deterministic telemetry & AWS signal collector |
| Analyzer | `backend/app/services/analyzer/` | Finding generator & rule classifier |
| Policy/Supervisor | `backend/app/services/policy/` | Policy engine & approval guardrails |
| Executor | `backend/app/services/executor/` | Safe automated execution node |
| Orchestrator | `backend/app/services/orchestrator/` | Agent workflow graph & supervisor |
| Frontend | `frontend/` | Next.js 14 Dashboard & Agent UI controls |

