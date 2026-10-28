# Per-execution website authorization

You can enter a different public HTTP(S) website in Web Intelligence without editing environment files. Every new execution requires an explicit authorization confirmation. The API enforces a strict JSON boolean, not just a browser checkbox, and records the exact scope in the job. This is a trusted workspace operator's attestation, not proof of website ownership or permission.

## Dashboard flow

1. Select your Ollama Cloud agent, enter the public website URL, instructions and fields.
2. Review the hostname and check **I confirm crawl authorization**. Changing the URL resets confirmation. Only that hostname is initially authorized; the apex and `www` are distinct.
3. Run the agent. Existing robots, rate, page/depth/time/token and cancellation rules still apply.
4. If a redirect needs another hostname, the execution stops before contacting it and shows **Review redirect authorization** in the monitor.
5. Follow that link, review the suggested hostname, and select its separate approval checkbox only if you are authorized to crawl it. Then confirm the entire new run and submit.

A retry creates a **new job** with fresh consent; it never widens or resumes the stopped job. Previously approved extra hostnames are shown unchecked and must be approved again if still needed. The backend binds extra approvals to the stopped job's original URL and recorded redirect hostnames. It rejects arbitrary additional-domain lists and references to an unrelated target or job. Literal non-public destinations and known internal/metadata aliases are rejected outright rather than offered for approval. A public-looking alias can still fail its DNS check after approval; approval never permits a private DNS result. DNS is still checked before every actual request, even for an explicitly approved hostname.

## API contract

All new jobs, including targets already in the static list, must send the literal boolean `authorization_confirmed: true`. Missing/false confirmation returns 403; strings such as `"true"`, numbers and null fail request validation. No job is enqueued without confirmation. Older queued jobs without confirmation fail closed and should be resubmitted after review.

Initial request:

```json
{
  "url": "https://your-authorized-site.example/",
  "authorization_confirmed": true,
  "instruction": "Extract the business description and published contact details from source text only.",
  "fields": ["company_name", "description", "business_email", "source_url"],
  "max_pages": 1,
  "max_depth": 0,
  "timeout": 120,
  "token_budget": 20000
}
```

Supply your saved Ollama Cloud `agent_id` for AI extraction. The omitted agent selects deterministic quick-run rules. No provider key is included in this body.

If the run encounters an unauthorized redirect, GET `/api/scraping/jobs/{id}` returns a failed job with context similar to:

```json
{
  "authorized_hostnames": ["your-authorized-site.example"],
  "error_code": "redirect_authorization_required",
  "authorization_required_hostname": "www.your-authorized-site.example",
  "stop_reason": "authorization_required"
}
```

After reviewing your permission, submit another job with the **same original URL**, fresh `authorization_confirmed: true`, and:

```json
{
  "authorization_source_job_id": "THE_STOPPED_JOB_UUID",
  "additional_authorized_domains": ["www.your-authorized-site.example"]
}
```

These are additional fields in the full scraping request, not a standalone API call. The referenced job must have failed specifically for redirect authorization; every extra host must be its observed destination or a previously explicitly approved host in that redirect chain. The extra list is capped at 10 exact hostnames. No wildcard, URL, path, credentials, local alias or non-public IP is accepted as a hostname.

The legacy `allowed_domains` request field remains an optional **filter**. It can narrow the confirmed scope, but cannot grant additional access. Existing static entries remain supported as targets and filter entries. They are not silently unioned into every execution's crawl scope. Thus a redirect to an entry already in the static list still requires explicit approval for this job.

## Map of the previous static gate and its replacement

| Location | Previous behavior | Current behavior |
| --- | --- | --- |
| `core/config.py:Settings.domains` | Parsed `ALLOWED_DOMAINS` as the default global scope | Unchanged static configuration; no dynamic domain writes |
| `web_scraper/schemas.py:ScrapeRequest` | Scheme/credentials/port checks; `allowed_domains` list | Shared canonical URL checks, strict consent, exact extra hosts and source-job reference |
| `services/jobs.py:submit` | Built a static policy, rejecting a new hostname before queueing | Requires consent, validates observed-redirect approvals and records target-only job scope |
| `web_scraper/agent.py:ScraperAgent.__init__` | Rebuilt policy from the static list in the worker | Rebuilds the same explicit job scope and fails closed if consent is absent |
| `core/policies.py:NetworkPolicy` | Checked membership in the server list | Exact per-job hostname membership; legacy low-level static policy remains supported |
| `web_scraper/fetcher.py:request` | Global scope, robots, throttling, DNS and pinned-IP fetch | Same controls using job scope; DNS is now resolved after waits immediately before connecting |
| `fetcher.py:manual redirects` | Rechecked redirect hostname against global list | Stops at an unapproved hostname with a structured approval request; checks every followed hop |
| `fetcher.py:check_robots` | Fetched origin robots under static policy | Uses the same job policy for robots and its redirects; 404 allows, other unavailable statuses deny |
| `crawler.py:discover` | Filtered links through static policy | Only job-scoped links survive; malformed links are skipped safely |
| `browser.py:intercept/final URL` | Reused static fetcher for HTTP(S) resources and checked final URL | Reuses job-scoped fetcher, blocks uncontrolled navigation and preserves redirect-approval reasons |
| Web Intelligence/Settings | Showed static domain entries as the practical target restriction | Web Intelligence confirms the current target; Settings retains the static configuration display |

## Network restrictions retained and strengthened

- Only HTTP port 80 and HTTPS port 443 (or their implicit defaults). Credentials in target URLs, raw whitespace/control characters, backslashes, wildcard hosts, IPv6 zones and ambiguous numeric-IP syntax are rejected.
- Hostnames are lowercased, IDNA canonicalized and normalized for an optional trailing DNS dot. Authorization compares canonical exact hosts; no suffix matching grants subdomains.
- Public IP literals may be used only if they pass the same destination checks. Localhost aliases, single-label/internal/local hostnames and non-public IPv4/IPv6 addresses are blocked.
- Every DNS answer must be public. Private, loopback, link-local, reserved, multicast, unspecified, shared-address and metadata destinations are denied; mixed public/private DNS responses fail closed. IPv4-mapped/6to4/Teredo/NAT64 transition addresses are conservatively blocked. Azure's metadata/platform IP is explicitly denied even though some IP libraries classify it globally.
- DNS is resolved afresh after robots/rate-limit waits and before each connection. The connection uses that validated IP with the original canonical Host/TLS SNI, retaining TLS verification. DNS changes after validation cannot change the pinned destination. Redirects are manual and bounded. An unapproved host is not resolved or fetched until a new confirmed execution grants it; followed hops are independently resolved.
- robots.txt, per-domain Redis rate coordination, crawl delays/request rates, response-size, page/depth/time/token/frontier limits, safe exports, cooperative cancellation and evidence validation remain enforced.
- HTTP access restrictions and recognized login/CAPTCHA/browser challenges stop with clear reasons. No login, form submission, CAPTCHA bypass or paywall workaround is attempted. Challenge detection is conservative and heuristic; it is not a universal page classifier. Script-rendered sites requiring unauthorized assets may produce missing fields or fail safely.

Browser interception remains an application-level policy, not an OS network sandbox; the existing isolated-worker/egress-firewall deployment recommendation still applies. Shared deployments also require authenticated workspace access and appropriate ingress/queue quotas. This change neither installs credentials nor changes existing secrets.

## Deploy and test

After reviewing the code, rebuild the application without editing environment files:

```sh
docker compose up --build -d --force-recreate api worker frontend
```

Automated checks:

```sh
cd backend
RUN_BROWSER_TESTS=1 .venv/bin/pytest -q
.venv/bin/python tests/browser_smoke.py
cd ../frontend
npm run build
```

Automated provider/site requests and DNS are mocked. Pytest explicitly disables live website DNS and HTTP transports, so an accidental unmocked request fails rather than using the internet. Optional PostgreSQL CI infrastructure may resolve only its dedicated database endpoint/port; all site/provider traffic remains blocked. Browser QA serves isolated API/Vite processes on loopback, fulfills fictional website content from fixtures, blocks external fonts, and exercises consent reset and observed-redirect approval. No real website is crawled and no live Ollama call is required.
