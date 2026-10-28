# Ollama Cloud and local extraction

Atlas supports two explicit backend modes. Both use the native Ollama chat API, per-scrape instructions and selected fields, server-side Pydantic validation, and exact source-evidence checks. No key belongs in Agent Builder or browser code.

## Ollama Cloud: no local installation

Privately edit the existing project-root `.env` and add/update:

```env
OLLAMA_MODE=cloud
OLLAMA_URL=https://ollama.com
OLLAMA_API_KEY=YOUR_KEY_ENTERED_LOCALLY
```

Replace the key placeholder locally. Do not paste it into chat or put it in `.env.example`. Do not overwrite the rest of `.env`. The example file keeps `OLLAMA_API_KEY=` empty.

**The base is `https://ollama.com`, without `/api`.** Atlas appends `/api/chat`, producing exactly `https://ollama.com/api/chat`. Cloud mode requires this exact HTTPS origin and a nonempty backend key; a base ending in `/api` or `/api/chat` is rejected rather than producing `/api/api/chat`. Local mode pointed at the official Cloud origin is rejected with an instruction to set `OLLAMA_MODE=cloud`; no silent mode switching occurs.

Build the updated code and recreate the API/worker:

```sh
cd /Users/anupamde/Desktop/agent_environment/ai-agent-platform
docker compose up --build -d --force-recreate api worker
```

If you also want the updated Agent Builder help text, run `docker compose up --build -d frontend`. For later environment-only edits use `docker compose up -d --force-recreate api worker`. A plain restart does not reload changed Compose environment variables. Existing Compose `env_file` handling already supplies backend settings; no Compose modification is needed.

Open http://localhost:8080 → Agent Builder, select **Ollama · backend configured**, enter an available Cloud **API model ID**, retain `ai_extraction` plus the default scraping/validation/storage tools, and save. Use the model name returned by Ollama Cloud's `/api/tags` or its API model listing, not an assumed local CLI `-cloud` alias. The official Cloud documentation currently demonstrates `gemma4:31b`; availability and permissions depend on your account. Models run remotely and need no download.

Test the configured connection without accessing a website:

```sh
docker compose exec -T worker python -m app.services.ollama_check
```

Then replace `MODEL_ID` below with an available API model ID:

```sh
docker compose exec -T worker python -m app.services.ollama_check --model MODEL_ID
```

The first command calls only `/api/tags` and reports model counts. The second also sends a tiny fictional text fixture for an inference call, which may consume Cloud quota. It checks JSON parsing, source quotes, and a missing null field. Neither command downloads a model or crawls a website. Neither prints credentials, endpoint values, upstream bodies, or model-list contents.

## How Cloud extraction works

The backend sends `model`, `messages`, `stream: false`, and bounded generation options with an `Authorization: Bearer ...` header. It does **not** send `format` or OpenAI `response_format` in Cloud mode. Ollama Cloud currently lacks native JSON Schema output, so Atlas instead puts the selected-fields schema and explicit JSON-only instructions inside the prompt.

The requested answer has this shape:

```json
{"fields":{"company_name":{"value":"A verbatim company name","evidence":"A verbatim source quote containing that name"},"phone":{"value":null,"evidence":null}}}
```

Atlas parses exactly one JSON object (optionally surrounded by one complete JSON Markdown fence). It does not search explanatory prose for a JSON substring. Invalid/truncated JSON, duplicate keys, NaN/Infinity, or a wrong envelope fail safely with a sanitized provider error. Only requested fields survive; missing fields, unsupported value types, missing evidence, and unmatched source quotes become null. Fields remain string-or-null. Valid fields retain their matching quotes.

Prompt instructions do not guarantee a model will return JSON or obey the schema. This is server-validated prompt JSON, not provider-constrained generation. No malformed-output repair loop, invented fallback data, or relaxation of evidence requirements is used. Choose a model able to follow JSON instructions. Malformed output may require a new job or another model.

The gateway validates Cloud evidence against the exact cleaned text it sent to the model. The scraping workflow applies the same evidence rule again before persistence. `source_url` is supplied from trusted crawl metadata, never accepted as an invented model URL. Results → View details exposes the retained quotes. Evidence establishes source provenance, not factual truth.

## Local/native-schema mode remains supported

The default is `OLLAMA_MODE=local`. For Ollama running on a Mac while Atlas runs in Docker Desktop:

```env
OLLAMA_MODE=local
OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_API_KEY=
```

For Atlas directly on the Mac use `http://localhost:11434`. Local mode continues sending `format` as a JSON Schema. Local unauthenticated HTTP needs no key. Compatible self-hosted native-schema servers can still use an optional bearer key over HTTPS. A server offering only OpenAI-compatible `/v1/chat/completions` is not compatible with this provider branch.

Ollama's Mac app, listening interface/firewall and model installation are operator-controlled. Atlas downloads nothing. Do not broaden a local listener automatically. No wildcard browser origin is needed because the backend calls Ollama. The gateway's 30-second HTTP timeout and tools' 45-second deadline are separate from the overall job timeout; warm a local model if cold starts exceed those limits.

## Credentials and errors

`OLLAMA_API_KEY` remains a backend `SecretStr` excluded from Settings representation/serialization. Cloud requires it; local mode may leave it empty. Nonempty keys are sent only over HTTPS, never in URLs, agent configurations, frontend data, prompts, or logs. URL userinfo, query and fragment are rejected. Redirects are not followed, preventing credential forwarding to another host. Authentication, transport, JSON/schema and reflected-credential errors become static safe job errors. `.env` stays gitignored and outside Docker build contexts; a regression test keeps credential fields in `.env.example` empty. Do not display environment dumps or unredacted Compose configuration. Rotate any credential previously exposed in files, terminal output or chat.

Cloud inference transmits the bounded cleaned page text and your extraction instruction to Ollama Cloud. No website authentication cookies or scraping credentials are supplied. `API_TOKEN` protects Atlas itself and `OPENAI_API_KEY` belongs to OpenAI; neither replaces `OLLAMA_API_KEY`.

## Authorize a website for each execution

Enter the authorized public URL in Web Intelligence, select your saved Ollama agent, provide instructions/fields, and confirm crawl authorization for that run. You no longer need to edit `ALLOWED_DOMAINS` for each website. The scope starts with only the canonical target hostname. A redirect to a different hostname stops; use the monitor's **Review redirect authorization** action to explicitly approve its recorded destination and start a new job. Approval does not bypass public-DNS, robots or access-restriction checks. No wildcard scope is used and no domains are written into environment files.

Existing static entries remain usable, but do not implicitly grant external links or redirects. The API requires `authorization_confirmed: true`; extra approvals also require the stopped job's `authorization_source_job_id`. See [per-execution authorization](PER_EXECUTION_AUTHORIZATION.md) for the complete flow, backward compatibility and security gate map.

Begin with one page, depth zero, JavaScript rendering off, and bounded time/token settings. Login, CAPTCHA and paywall restrictions are not bypassed. Extraction currently considers up to 12,000 cleaned characters per page, further trimmed by token budget, with at most 2,048 output tokens per call. Missing or unsupported facts remain null with the same source-evidence validation.

## Verification

```sh
cd backend
.venv/bin/pytest -q tests/test_llm.py tests/test_ollama_cloud.py tests/test_ollama_security.py
RUN_BROWSER_TESTS=1 .venv/bin/pytest -q
```

Cloud tests mock provider traffic and fixture pages. They verify the exact endpoint/Bearer header, omission of `format`, prompt schema, strict JSON parsing, nulls for unsupported/invented facts, source evidence, persistence, safe errors and browser responses. Existing tests retain local no-key behavior and crawling protections. No live Cloud inference, model download, or real website scrape is required. Do not run `scripts/smoke_live.py` without separately authorizing its target.

Official references checked for this implementation: [Cloud chat endpoint, response and API model names](https://docs.ollama.com/cloud), [Bearer authentication](https://docs.ollama.com/api/authentication), [native chat request options](https://docs.ollama.com/api/chat), [Cloud structured-output limitation](https://docs.ollama.com/capabilities/structured-outputs).
