# Atlas · Reusable AI Agent Platform

A working, modular web intelligence platform with a FastAPI API, LangGraph agent workflow, Celery jobs, SQLAlchemy persistence, and a responsive React dashboard. The first implementation is a bounded web scraping agent. No vector database is required.

## Start with Docker

Requirements: Docker Engine/Desktop with Compose and outbound HTTPS for dependency installation. Run from this directory:

```sh
cp .env.example .env
# Edit ALLOWED_DOMAINS and optionally OPENAI_API_KEY / API_TOKEN in .env.
docker compose up --build -d
```

Open **http://localhost:8080**. Interactive API documentation: **http://localhost:8000/docs**. The API and frontend bind to loopback by default. Database and Redis ports stay inside the Compose network. The one-shot `migrate` service applies Alembic migrations before the API and worker start.

```sh
docker compose ps
docker compose logs -f api worker
docker compose down # Keeps PostgreSQL and Redis volumes
```

Quick runs work without an LLM key using deterministic title and email extraction. Other requested fields are null. For natural-language extraction, create an agent with OpenAI or Ollama in Agent Builder, then select it in Web Intelligence. The model must support the configured structured output format. OpenAI defaults to `gpt-4.1-mini`; model IDs are editable. Ollama models must be available on the configured server; Cloud models require no local installation. LLM keys never go to the frontend.

## Ollama extraction

See [docs/OLLAMA.md](docs/OLLAMA.md) for Cloud and local setup, backend-only credentials, safe diagnostics, model selection, and exact-domain authorization. Set `OLLAMA_MODE=cloud`, `OLLAMA_URL=https://ollama.com` (no `/api` suffix), and privately enter `OLLAMA_API_KEY` to use Ollama Cloud without a local installation. Cloud requests JSON in the prompt and validates fields/source evidence on the backend; it sends no JSON Schema `format`. The default `local` mode retains native schema output and needs no key for local Ollama. No model is downloaded automatically.

## Per-execution crawl authorization

Enter a public URL in Web Intelligence and check the authorization confirmation for that run. You no longer need to edit `ALLOWED_DOMAINS` for each new website. The backend accepts only the confirmed target hostname; a cross-host redirect stops and offers a separately confirmed, recorded-redirect retry. Static entries remain supported, but never silently widen a job. All new API submissions must include `authorization_confirmed: true`. See [the scope/security map and API examples](docs/PER_EXECUTION_AUTHORIZATION.md).

## Dashboard

- **Overview:** database-backed counts and recent executions.
- **Agent builder:** create/edit configurations, select provider/model, enable or disable an agent, configure tools, delete agents without history. Disable agents with history to retain their records.
- **Web intelligence:** authorize a source, specify fields and instructions, configure depth, page, time, and token boundaries, and submit a job.
- **Executions:** polling status, current step, persisted timeline, pages, records, token usage, approximate cost, errors, stopping condition, cooperative cancellation.
- **Results:** searchable/filterable records, source links, evidence details, JSON and formula-safe CSV downloads.
- **Settings:** workspace bearer token, provider readiness, and server execution policy. Provider/model/tools are editable per agent. Security limits and domains are environment-managed, not writable from the browser.

## Local development

Python 3.12+ and Node 22+ are required. Python dependencies are pinned in `backend/requirements.txt`; frontend dependencies are locked in `frontend/package-lock.json`.

```sh
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium # Only needed for browser rendering and browser tests
alembic upgrade head
QUEUE_EAGER=true uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api` to port 8000. `QUEUE_EAGER=true` runs jobs synchronously in the submitting process and uses process-local throttling; use it for local development only. Normal mode uses Redis and a Celery worker. To develop with those services, start Compose, use a host-reachable PostgreSQL connection (or the default local SQLite database), and run:

```sh
# With a Redis server reachable at REDIS_URL:
celery -A app.workers.tasks.celery worker --loglevel=INFO --concurrency=2
```

For local settings, put `.env` in the backend working directory or export environment variables. Root `.env` is consumed by Docker Compose; it is not implicitly loaded by commands run inside `backend/`. Use `OLLAMA_URL=http://localhost:11434` for local execution; Docker Desktop uses `http://host.docker.internal:11434`. Linux deployments need an explicit reachable Ollama address.

## Example API flow

If `API_TOKEN` is set, send `Authorization: Bearer <token>` on all application endpoints. `/api/health` remains public. The dashboard stores only this workspace token in tab-scoped session storage. It never requests an OpenAI key.

Create an AI-enabled agent:

```sh
curl -X POST http://localhost:8000/api/agents \
  -H 'Content-Type: application/json' \
  -d '{"name":"Company intelligence","configuration":{"provider":"openai","model":"gpt-4.1-mini","temperature":0,"tools":["http_fetch","html_parser","link_discovery","ai_extraction","validation","database_storage","csv_export","json_export"]}}'
```

Copy the returned `id` into `agent_id` below. Omit `agent_id` for a deterministic quick run:

```sh
curl -X POST http://localhost:8000/api/scraping/jobs \
  -H 'Content-Type: application/json' \
  -d '{"authorization_confirmed":true,"agent_name":"Company intelligence","url":"https://example.com","instruction":"Extract company information from this website","fields":["company_name","business_email","location","source_url"],"max_depth":1,"max_pages":3,"timeout":120,"token_budget":10000,"allowed_domains":["example.com"],"output_format":"json"}'
```

Submission returns **202 Accepted** with a job ID and `queued` status (eager mode may already return a terminal state). Poll `/api/scraping/jobs/{id}`. Fetch `/results` or `/export?format=csv` when ready. Partial records from a failed or cancelled job remain inspectable.

Fixture-backed result example (illustrative; not a claim about example.com):

```json
{
  "source_url": "https://example.com/",
  "extracted_data": {
    "company_name": "Acme Labs",
    "business_email": "hello@acme.test",
    "location": null,
    "source_url": "https://example.com/"
  },
  "evidence": {
    "company_name": "Acme Labs",
    "business_email": "hello@acme.test",
    "source_url": "https://example.com/"
  },
  "validation_status": "validated"
}
```

The preferred `output_format` is retained with the request; both download formats remain available when the respective export tool is enabled.

API route reference: [docs/API.md](docs/API.md). Complete source inventory: [docs/FILES.md](docs/FILES.md).

## Architecture and extension points

```text
React → FastAPI → PostgreSQL job → Redis/Celery worker
                                      ↓
                             LangGraph initialize → visit → bounded loop → END
                                      ↓
                      policy → robots → pinned HTTP / restricted browser
                                      ↓
                          parse → extract → validate → deduplicate → store
```

`backend/app/agents/base_agent.py` defines the agent protocol. Add a new implementation and register its factory in `core/orchestrator.py`, then extend the agent input discriminator and frontend builder. Existing job persistence and monitoring can be reused. `core/tool_registry.py` holds named tools with distinct Pydantic input/output schemas, execution functions, permissions, and timeouts. Server policy is enforced independently of tool selection. There is no arbitrary tool execution API exposed to the browser.

The extraction planner is deterministic and bounded; it preserves user instructions and fields in the execution context. Link discovery uses breadth-first internal navigation. Natural-language instructions guide field extraction, not arbitrary browser actions. Versioned extraction instructions live in `prompts.py`. The LLM gateway uses HTTPX for OpenAI and Ollama and validates responses with Pydantic. OpenAI uses a closed, strict JSON Schema for the requested fields.

The six database tables are `agents`, `agent_jobs`, `scraped_pages`, `extracted_records`, `agent_executions`, and `agent_schedules`. Migrations use explicit Alembic operations. Agent configurations are snapshotted at submission so edits cannot change queued work. Workers atomically claim queued jobs, making duplicate deliveries harmless. Crashed work is marked failed when job status/history is read after its deadline; it is never automatically rerun with possible duplicate provider charges. Checkpoints retain task context, pages, records, and history; this MVP does not resume a partially completed LangGraph frontier.

Logs are JSON with OpenTelemetry-compatible severity/timestamp/body fields and job IDs. Trace/span IDs are included if an operator installs/configures an OpenTelemetry SDK. No OTLP exporter or tracing backend is bundled.

## Verification

```sh
cd backend
.venv/bin/pytest -q
RUN_BROWSER_TESTS=1 .venv/bin/pytest -q
.venv/bin/python tests/browser_smoke.py
.venv/bin/alembic upgrade head
.venv/bin/alembic check
cd ../frontend
npm run build
```

The browser smoke test requires frontend dependencies and a Playwright Chromium installation. It starts isolated temporary API and Vite servers, creates a temporary SQLite database, mocks website fetching, and exercises creation → execution → persisted results → evidence → CSV/JSON downloads. It also checks responsive width, mobile settings, private-target rejection, and JavaScript runtime errors. Screenshots and its JSON report go to ignored `artifacts/`. It shuts its servers down automatically.

Unit/API tests cover URL validation, non-public DNS and mixed DNS answers, validated-IP connections and TLS SNI, redirect restrictions, robots rules and delays, response size limits, parsing, missing information, evidence rejection, deduplication, time/page/depth limits, cancellation, job claims, queue failures, agent configuration snapshots, stale-job recovery, bearer authentication, typed tool permissions, mocked OpenAI/Ollama output, usage accounting, persistence, and exports. Browser tests use local fixtures, not third-party sites or paid APIs.

See [docs/VALIDATION.md](docs/VALIDATION.md) for the actual checks performed during delivery. CI runs backend tests, migration checks, and the frontend production build. Local tests default to SQLite; set `TEST_DATABASE_URL` to a disposable PostgreSQL database to exercise the same suite on PostgreSQL. Tests drop and recreate their schema, so this URL must point to a dedicated test database.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./platform.db` | SQLAlchemy database URL; Compose overrides with PostgreSQL/psycopg |
| `POSTGRES_PASSWORD` | `atlas_local` | Local Compose database password |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker/result backend and shared domain throttle |
| `ALLOWED_DOMAINS` | `example.com` | Existing static exact-host entries and legacy filters; new confirmed executions use target-only job scopes |
| `API_TOKEN` | empty | Optional shared workspace bearer token; configure before network exposure |
| `OPENAI_API_KEY` | empty | Backend-only OpenAI credential |
| `OLLAMA_URL` | local host or Docker host | Native Ollama root/prefix before `/api/chat`; use `http://host.docker.internal:11434` for Mac-hosted Ollama from Docker |
| `OLLAMA_MODE` | `local` | `cloud` for official Ollama Cloud with prompt JSON and server-side validation; `local` retains native JSON Schema |
| `OLLAMA_API_KEY` | empty | Backend-only bearer credential; required in Cloud mode, optional for native-schema HTTPS servers |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed browser origins |
| `MAX_PAGES` | 50 | Server maximum pages per execution |
| `MAX_TIMEOUT` | 600 | Server maximum execution seconds |
| `MAX_TOKENS` | 20000 | Server maximum requested token budget |
| `MAX_RESPONSE_BYTES` | 2000000 | Decompressed HTTP and rendered-document size bound |
| `RATE_INTERVAL` | 1.0 | Minimum seconds between requests per domain (robots can increase it) |
| `BROWSER_ENABLED` | false | Opt in to restricted Playwright rendering |
| `QUEUE_EAGER` | false | Development/test synchronous mode |
| `INPUT_COST_PER_MILLION` | 0 | Operator-supplied model input price |
| `OUTPUT_COST_PER_MILLION` | 0 | Operator-supplied model output price |
| `VITE_API_URL` | empty | Optional frontend build-time API base; same-origin proxy is preferred |
| `API_PROXY_TARGET` | `http://127.0.0.1:8000` | Vite development proxy target |

Request limits: 0–5 depth, 1–50 pages, 5–600 seconds, up to 30 snake_case fields. Every new request requires strict `authorization_confirmed: true`, including static targets. A job starts with its validated target hostname only. Redirect hostnames and `www` require explicit observed-redirect approval bound to a stopped job; the retry gets a new job ID. `allowed_domains` is a legacy filter that cannot add hosts. Confirmation is operator attestation, not proof of external permission. See [per-execution authorization](docs/PER_EXECUTION_AUTHORIZATION.md).

Token budgeting reserves a conservative UTF-8 byte bound for prompts/schema plus output tokens before calls, and counts worst-case timed-out/retried attempts. Provider-reported usage replaces successful-call estimates. This is a conservative execution bound, not a provider billing guarantee. Costs are approximate and unknown when prices are not configured; use one price pair appropriate to the selected model or extend the gateway with a per-model price map.

## Security and operational limits

See [docs/SECURITY.md](docs/SECURITY.md) for threat boundaries and deployment requirements. This is a production-oriented MVP for a trusted, single workspace, not a multi-tenant SaaS release. It provides shared-token access, not user accounts or RBAC. It has no API ingress rate limiter, queue quota, scheduler runner, automatic deployment, or full browser egress sandbox. `agent_schedules` is migrated for future use, but schedules are not executed. Do not configure schedules expecting unattended runs.

JavaScript rendering must be enabled on the server and in the agent's tool list. The browser blocks forms, non-GET requests, popups, service workers, websockets, and uncontrolled subsequent navigations; all permitted HTTP(S) resources go through the network policy and robots checks. This intentionally breaks sites that require login, POST APIs, cross-domain assets, or complex browser behavior. Such sites fail rather than bypassing their restrictions. Missing evidence becomes null. Evidence proves the text was present on the source, not that the source is factually true.

## Recommended next steps

1. Add an identity provider, workspace ownership, RBAC, queue quotas, and ingress rate limits for shared deployment.
2. Enforce container/network egress policy, resource quotas, TLS ingress, backups, and secret management before public hosting.
3. Add operator-reviewed per-model pricing, provider model discovery, and custom typed extraction schemas where needed.
4. Add a transactional outbox for stronger queue handoff guarantees and resumable crawl checkpoints for expensive jobs.
5. Add schedule dispatch only when its task-template and timezone semantics are specified; extend the existing agent factory with the next concrete agent type.
