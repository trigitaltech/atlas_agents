# Delivery verification · 28 October 2026

## Per-execution authorization update · 28 October 2026

- Final full backend suite with Chromium on macOS: **201 passed**.
- Rebuilt Linux backend suite with Chromium: **200 passed, 1 skipped** (the root `.env.example` placeholder guard is outside the backend image and passed locally).
- Production frontend/TypeScript build and full Docker rebuild/recreation: passed. API readiness is HTTP 200; PostgreSQL and Redis are healthy; worker control ping reports online.
- New request fields are present in deployed OpenAPI; a request without authorization was rejected without starting a website job.
- Browser fixture workflow passed: consent required, consent reset after target edits, unapproved cross-host redirect stopped, extra hostname initially unchecked, fresh consent and observed-source-job-bound retry succeeded. Existing results, evidence, search, CSV/JSON downloads and mobile checks also passed.
- Mocked regressions cover static and per-job scopes, strict confirmation types, arbitrary approval-list rejection, original-URL/observed-redirect binding, public hosts, private/mixed DNS answers, metadata/transition IPs, URL ambiguity, rate-wait and redirect DNS revalidation, robots rules, browser redirect reasons, access barriers, legacy jobs failing closed, cancellation and existing execution limits.
- Cloud extraction was verified on an unlisted fictional hostname with mocked provider/page content; missing/invented values remained null and source evidence was retained.
- No real website or model calls were made for this update. All website/provider traffic and DNS in pytest are mocked/blocked; browser QA uses loopback-only temporary API/Vite servers and fictional pages. Optional PostgreSQL CI infrastructure can resolve only its configured database endpoint/port; this does not enable site/provider networking.
- No environment file was edited and no API secret value was inspected or printed. The existing configuration was consumed normally by Compose to refresh the application.

See [the complete authorization-gate map, request examples and limits](PER_EXECUTION_AUTHORIZATION.md). Historical checks below describe earlier implementations.

## Live Ollama Cloud configuration check · 28 October 2026

The operator-provided credential was configured only in the gitignored project-root `.env` using hidden terminal input. Cloud mode/base were set and API, worker and frontend recreated. Example credential fields remain empty.

The credential-safe diagnostic reached Ollama Cloud and completed a real inference on a tiny fictional text fixture with `gemma4:31b`. Expected values, retained source evidence and a missing null field validated successfully. No website was fetched. API health returned HTTP 200 with PostgreSQL/Redis healthy. An enabled `Ollama Cloud Web Intelligence` agent was created/reused with provider/model only; no credential is stored in its configuration.

The credential was supplied in chat and should be revoked/rotated; replace it privately in `.env` and recreate API/worker. No credential value is included in this report.

## Ollama Cloud prompt-JSON update · 28 October 2026

- Full backend suite with real Chromium on macOS: **100 passed**.
- Fresh Linux backend image suite with Chromium: **99 passed, 1 skipped**. The skip is the root `.env.example` guard because only the backend directory is copied into that image; the guard passed on the host.
- Targeted gateway, Cloud and credential-security tests: **53 passed**.
- Dashboard browser workflow with fictional fixture pages: passed, including provider guidance, execution/results, evidence and CSV/JSON downloads.
- Production TypeScript/Vite build, Docker Compose configuration and backend/frontend image builds: passed.
- Cloud endpoint, bearer headers, absence of `format`, prompt-only JSON parsing, unsupported/missing nulls, evidence retention, safe errors/history/API data and local no-key compatibility are verified using mocks.
- No live Cloud inference or real website scrape was performed. Existing `.env` was not read for inspection or modified; `.env.example` contains empty credential placeholders only. The crawl allowlist and network access controls were not broadened.
- Images are built. Configure the key privately, set Cloud mode/base as documented, then recreate API and worker. Live Cloud account/model access remains unverified until that operator step.

See [OLLAMA.md](OLLAMA.md). Historical checks below describe earlier versions, including the former Cloud restriction; the current version supports Cloud using server-validated prompt JSON.

## Ollama integration update · 28 October 2026

This update used fixture pages and mocked providers only. No third-party scrape or model download was performed.

- Full backend suite with Chromium on macOS: 78 passed, including the example-credential guard.
- Full deployed Linux worker suite with Chromium: 77 passed before the final source-only example guard was added. That guard needs the root `.env.example`, which is intentionally outside backend Docker images.
- TypeScript/Vite production build and Docker backend/frontend image builds: passed.
- Browser dashboard workflow: passed after fixing the provider selector's accessible label. It exercises Ollama setup guidance, then uses deterministic fixture extraction for the job/results/download checks.
- Running API/frontend updated; readiness is HTTP 200 with PostgreSQL and Redis healthy.
- Local Ollama checks: no executable found on PATH, no `/Applications/Ollama.app`, no standard local model manifest directory, and port 11434 unreachable from the Mac and Docker worker. `host.docker.internal` resolves inside the worker.
- New credential-safe diagnostic reports `ConnectError` for the fixed Docker-to-Mac URL, as expected while Ollama is unavailable.
- Mocked tests verify local requests without auth, optional HTTPS bearer auth, refusal to forward redirects, structured output, natural-language instructions and selected fields, source evidence, nulls for missing/invented facts, sanitized errors and job history, exclusion of credentials from browser responses/settings exports, and rejection of per-agent credentials.
- `.env` was not opened for inspection, modified or copied. A credential found in `.env.example` was cleared; a value-matching scan found no other copies in non-runtime project source. The exposed credential needs rotation. No secret value is recorded in this report.

See [OLLAMA.md](OLLAMA.md) for the remaining operator actions. No compatible live Ollama endpoint/model was available, so live model inference remains unverified. Historical delivery checks below were performed earlier and were not repeated against real websites during this update.

Observed results from the original delivery:

| Check | Result |
| --- | --- |
| Python 3.12 pinned dependency installation and compatibility check | Passed |
| Frontend production dependency audit | 0 vulnerabilities reported |
| Backend suite on SQLite, including real Chromium | **51 passed** |
| Backend suite on PostgreSQL 17 in Linux, including real Chromium | **51 passed** |
| SQLite and PostgreSQL Alembic upgrade + drift checks | Passed; no new upgrade operations |
| TypeScript check + Vite production build | Passed |
| Docker Compose configuration, image build and startup | Passed |
| PostgreSQL and Redis readiness through frontend proxy | Healthy |
| Actual Celery worker control ping | Pong; one worker online |
| Cancellation through the actual background queue | Passed; terminal cancelled state and no stored records |
| Final rebuilt API schema and readiness | Verified; API, PostgreSQL and Redis healthy |
| Live https://example.com/ fetch | HTTP 200; robots checked; validated-IP TLS connection |
| Real API → Redis/Celery → PostgreSQL → results | Passed; one record; title and evidence both `Example Domain` |
| Isolated browser creation → execution → results → evidence | Passed |
| Browser CSV/JSON downloads and search | Passed |
| Browser mobile width/settings and private-target rejection | Passed |
| Browser JavaScript runtime errors | None observed |

The PostgreSQL suite mounted the final backend source read-only into Linux and used a separate disposable `atlas_test` database. Production workspace data was not used by the test fixtures. Both database suites use mocked website and LLM responses. The separately identified live smoke check uses example.com and the real background worker.

The full-stack browser smoke test starts temporary API and Vite servers and a temporary SQLite database. It uses a local HTML fixture and deterministic extraction, with no paid API calls. Screenshots, downloaded files, and its JSON report go to ignored `artifacts/`. The evidence dialog also received an Escape-key close check.

## Reproduce

```sh
cd backend
RUN_BROWSER_TESTS=1 .venv/bin/pytest -q
.venv/bin/python tests/browser_smoke.py
.venv/bin/alembic upgrade head
.venv/bin/alembic check
cd ../frontend
npm ci
npm run build
cd ..
docker compose config --quiet
docker compose up --build -d
docker compose exec -T worker celery -A app.workers.tasks.celery inspect ping
python3 scripts/smoke_live.py
```

The last command explicitly uses a live public website and requires network access and example.com in the allowlist. Set `API_TOKEN` in the calling shell if the workspace is protected. It creates a retained smoke-test agent/job in the running workspace.

## Not verified or implemented

- Live OpenAI/Ollama calls: integrations were tested with mocked responses, strict schemas, and token accounting. No live provider credential or local model was supplied.
- Cloud deployment, TLS ingress, SSO, multi-user isolation, or scheduled dispatch: outside this local deployment.
- Arbitrary JavaScript-heavy website compatibility: tests use controlled fixtures; rendering deliberately restricts network requests/actions.
- Resuming an interrupted LangGraph crawl: duplicate claims and stale-job recovery are tested, but interrupted crawls require explicit resubmission.

The local Compose handoff is http://localhost:8080. `docker compose down` stops it while retaining database volumes.
