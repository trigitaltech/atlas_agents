# API reference

Base path: `/api`. OpenAPI: `/openapi.json`. Interactive docs: `/docs`. Application endpoints require `Authorization: Bearer <API_TOKEN>` when configured. Health remains public.

| Method | Route | Behavior |
| --- | --- | --- |
| POST | `/api/agents` | Create agent; 201 |
| GET | `/api/agents` | Latest 200 agents |
| GET | `/api/agents/{id}` | Agent configuration |
| PUT | `/api/agents/{id}` | Replace validated configuration |
| DELETE | `/api/agents/{id}` | Delete agent without history; 204 or 409 |
| POST | `/api/scraping/jobs` | Validate policy, persist, enqueue; 202 |
| GET | `/api/scraping/jobs` | Latest jobs; `agent_id`, `limit` (1–200), `offset` |
| GET | `/api/scraping/jobs/{id}` | Job, counters/context, persisted executions |
| GET | `/api/scraping/jobs/{id}/results` | Data, source, evidence, validation status |
| POST | `/api/scraping/jobs/{id}/cancel` | Idempotently cancel queued/running job |
| GET | `/api/scraping/jobs/{id}/export?format=csv` | Formula-safe CSV attachment |
| GET | `/api/scraping/jobs/{id}/export?format=json` | JSON attachment; default format |
| GET | `/api/health` | Database/Redis readiness; 200 or 503 |
| GET | `/api/tools` | Tool names, permissions, schemas, timeouts |
| GET | `/api/models` | Provider configuration and suggested IDs; no live discovery |
| GET | `/api/settings` | Non-secret server policy |
| GET | `/api/stats` | Database-backed dashboard counts |

Scraping submissions require `authorization_confirmed: true` as a strict boolean. Missing/false confirmation returns 403; strings/numbers/null return 422. Initial scope is only the validated target hostname, even when other static entries exist. Cross-host redirects stop with `context.error_code=redirect_authorization_required` and `context.authorization_required_hostname`. After explicit approval submit a new job with the same original URL, `additional_authorized_domains`, and `authorization_source_job_id` referencing that failed job. The backend checks the reference and observed destination; arbitrary hostname lists are rejected. Existing `allowed_domains` only narrows the scope. Legacy queued jobs without confirmation fail closed. [Scope map and complete examples](PER_EXECUTION_AUTHORIZATION.md).

Agent updates use the complete `AgentInput`; omitted optional values revert to defaults. Disabling an agent blocks new jobs. Existing jobs retain their configuration snapshot. Agents with history cannot be hard-deleted. Cancellation updates status immediately; the worker cooperatively stops at the next checkpoint. In-flight HTTP or provider calls may complete before it observes cancellation. Completed/failed/cancelled jobs remain terminal on repeated cancellation.

Lifecycle: `queued → running → completed | failed | cancelled`, or `queued → cancelled`. Queue handoff failure returns 503 and retains a failed job in history. Duplicate task delivery cannot claim a job twice. A worker crash is reconciled after the configured deadline plus 30 seconds on status/history reads. Submit a new job to rerun failed work.

Request body and response shapes are defined in generated OpenAPI. Example request/results are in the README. Invalid requests return:

```json
{"error":{"code":422,"message":"Request validation failed","details":[{"field":"body.url","message":"Use a public HTTP(S) URL without credentials or custom ports"}]}}
```

Other application errors use the same `error.code`/`error.message` envelope. 401 indicates an access-token issue, 403 missing/invalid crawl authorization or a disabled export permission, 404 a missing resource, 409 a disabled agent or retained history, and 503 unavailable queue/readiness. There is no public endpoint for changing secrets or running arbitrary registered tools.
