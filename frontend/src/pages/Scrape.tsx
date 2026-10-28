import { useState, useEffect, useRef, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight, Globe2, ShieldCheck, Sparkles } from "lucide-react";
import { useData } from "../hooks/useData";
import { api, errorMessage } from "../services/api";
import { PageHeader, ErrorNotice } from "../components/UI";
import type { Agent, Job, Settings } from "../types";
export default function Scrape() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const retryId = params.get("retry");
  const retry = useData<Job>(
    "authorization-retry",
    `/api/scraping/jobs/${encodeURIComponent(retryId || "")}`,
    undefined,
    !!retryId,
  );
  const loadedRetry = useRef<string | null>(null);
  const agents = useData<Agent[]>("agents", "/api/agents");
  const settings = useData<Settings>("settings", "/api/settings");
  const [agent, setAgent] = useState(params.get("agent") || "");
  const [url, setUrl] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [redirectHosts, setRedirectHosts] = useState<string[]>([]);
  const [approvedHosts, setApprovedHosts] = useState<string[]>([]);
  const [instruction, setInstruction] = useState(
    "Extract company information and contact details from the website.",
  );
  const [fields, setFields] = useState(
    "company_name, business_email, location, services, source_url",
  );
  const [depth, setDepth] = useState(1);
  const [pages, setPages] = useState(5);
  const [timeout, setTimeout] = useState(120);
  const [budget, setBudget] = useState(10000);
  const [format, setFormat] = useState("json");
  const [render, setRender] = useState(false);
  useEffect(() => {
    if (!retry.data || loadedRetry.current === retryId) return;
    loadedRetry.current = retryId;
    const input = retry.data.input_data;
    setAgent(retry.data.agent_id);
    setUrl(input.url);
    setInstruction(input.instruction);
    setFields(input.fields.join(", "));
    setDepth(input.max_depth ?? 1);
    setPages(input.max_pages ?? 5);
    setTimeout(input.timeout ?? 120);
    setBudget(input.token_budget ?? 10000);
    setFormat(input.output_format ?? "json");
    setRender(input.render_js ?? false);
    setRedirectHosts([
      ...new Set(
        [
          ...(input.additional_authorized_domains || []),
          retry.data.context.authorization_required_hostname,
        ].filter((host): host is string => !!host),
      ),
    ]);
    setApprovedHosts([]);
    setAuthorized(false);
  }, [retry.data, retryId]);
  let targetHost = "";
  try {
    const parsed = new URL(url);
    if (["http:", "https:"].includes(parsed.protocol))
      targetHost = parsed.hostname.replace(/\.$/, "");
  } catch {
    /* Backend validates malformed targets. */
  }
  const run = useMutation({
    mutationFn: async () =>
      (
        await api.post<Job>("/api/scraping/jobs", {
          agent_id: agent || null,
          authorization_confirmed: authorized,
          additional_authorized_domains: approvedHosts,
          authorization_source_job_id: approvedHosts.length ? retryId : null,
          url,
          instruction,
          fields: fields
            .split(",")
            .map((v) => v.trim())
            .filter(Boolean),
          max_depth: depth,
          max_pages: pages,
          timeout,
          token_budget: budget,
          output_format: format,
          render_js: render,
        })
      ).data,
    onSuccess: (job) => navigate(`/jobs/${job.id}`),
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    if (authorized) run.mutate();
  }
  return (
    <>
      <PageHeader
        eyebrow="WEB INTELLIGENCE"
        title="Give curiosity a direction."
        description="Choose a source. Describe what matters. Let your agent connect the dots."
      />
      <div className="scrape-grid">
        <form className="panel form-panel" onSubmit={submit}>
          <div className="section-title">
            <span className="step-number">
              <Globe2 size={18} />
            </span>
            <div>
              <h2>Configure an execution</h2>
              <p>Only crawl websites you are authorized to access</p>
            </div>
          </div>
          <label>
            Agent
            <select value={agent} onChange={(e) => setAgent(e.target.value)}>
              <option value="">Quick run · deterministic extraction</option>
              {agents.data
                ?.filter((a) => a.enabled)
                .map((a) => (
                  <option value={a.id} key={a.id}>
                    {a.name} · {a.configuration.provider}
                  </option>
                ))}
            </select>
          </label>
          {retry.isError && (
            <ErrorNotice message="Could not load the previous execution. Enter a new target or check your access token." />
          )}
          <label>
            Website URL
            <input
              required
              aria-label="Website URL"
              type="url"
              placeholder="https://example.com"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                setAuthorized(false);
                setRedirectHosts([]);
                setApprovedHosts([]);
              }}
            />
            <small>
              This run is scoped to{" "}
              {targetHost || "the validated target hostname"}. Other websites
              and subdomains are blocked unless separately approved for this
              run.
            </small>
          </label>
          {redirectHosts.length > 0 && (
            <section className="notice" style={{ display: "block" }}>
              <h3>Review redirect authorization</h3>
              <p>
                The previous run stopped. Select only hostnames you are
                authorized to crawl; approval applies to the new execution only.
              </p>
              {redirectHosts.map((host) => (
                <label
                  className="check-label"
                  key={host}
                  style={{ marginTop: 12 }}
                >
                  <input
                    type="checkbox"
                    checked={approvedHosts.includes(host)}
                    onChange={(e) => {
                      setApprovedHosts(
                        e.target.checked
                          ? [...approvedHosts, host]
                          : approvedHosts.filter((h) => h !== host),
                      );
                      setAuthorized(false);
                    }}
                  />
                  Authorize {host} for this execution
                </label>
              ))}
            </section>
          )}
          <label className="check-label" style={{ alignItems: "flex-start" }}>
            <input
              type="checkbox"
              required
              aria-label="I confirm crawl authorization"
              checked={authorized}
              onChange={(e) => setAuthorized(e.target.checked)}
            />
            <span>
              I confirm I am authorized to crawl {targetHost || "this site"} and
              any selected additional hostnames for this execution.
            </span>
          </label>
          <label>
            Extraction instructions
            <textarea
              required
              rows={3}
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              maxLength={4000}
            />
          </label>
          <label>
            Required output fields
            <input
              required
              value={fields}
              onChange={(e) => setFields(e.target.value)}
            />
            <small>
              Comma-separated snake_case names. Missing facts are returned as
              null.
            </small>
          </label>
          <div className="form-divider" />
          <h3>Execution boundaries</h3>
          <div className="form-row">
            <label>
              Maximum crawl depth
              <input
                type="number"
                min={0}
                max={5}
                value={depth}
                onChange={(e) => setDepth(+e.target.value)}
              />
            </label>
            <label>
              Maximum pages
              <input
                type="number"
                min={1}
                max={settings.data?.max_pages || 50}
                value={pages}
                onChange={(e) => setPages(+e.target.value)}
              />
            </label>
          </div>
          <div className="form-row">
            <label>
              Timeout (seconds)
              <input
                type="number"
                min={5}
                max={settings.data?.max_timeout || 600}
                value={timeout}
                onChange={(e) => setTimeout(+e.target.value)}
              />
            </label>
            <label>
              Token budget
              <input
                type="number"
                min={100}
                max={settings.data?.max_tokens || 20000}
                value={budget}
                onChange={(e) => setBudget(+e.target.value)}
              />
            </label>
          </div>
          <div className="form-row">
            <label>
              Preferred output
              <select
                value={format}
                onChange={(e) => setFormat(e.target.value)}
              >
                <option value="json">JSON</option>
                <option value="csv">CSV</option>
              </select>
            </label>
            <label className="check-label">
              <input
                type="checkbox"
                disabled={!settings.data?.browser_enabled}
                checked={render}
                onChange={(e) => setRender(e.target.checked)}
              />
              Render JavaScript
            </label>
          </div>
          {run.isError && <ErrorNotice message={errorMessage(run.error)} />}
          <div className="form-footer">
            <span>Bounded. Read-only. Evidence-backed.</span>
            <button
              className="button primary"
              disabled={run.isPending || !authorized || !url}
            >
              {run.isPending ? "Submitting…" : "Run agent"}
              <ArrowRight size={17} />
            </button>
          </div>
        </form>
        <aside className="scrape-aside">
          <div className="aside-art">
            <Sparkles size={32} />
            <span>
              FROM NOISE
              <br />
              TO KNOWLEDGE.
            </span>
            <div className="mini-record">
              <i /> company_name <b>Verified</b>
            </div>
            <div className="mini-record">
              <i /> business_email <b>Verified</b>
            </div>
            <div className="mini-record">
              <i /> location <em>null</em>
            </div>
          </div>
          <h3>Confidence comes from context.</h3>
          <p>
            Every populated field must match its source text. Open the evidence
            alongside your results to see exactly where it came from.
          </p>
          <div className="guardrail">
            <ShieldCheck size={20} />
            <span>
              Respectful by default
              <small>
                robots.txt, public destinations, and domain limits are checked
                before access.
              </small>
            </span>
          </div>
          <div className="notice">
            Quick runs use deterministic title and email rules. Create an OpenAI
            or Ollama agent for natural-language extraction.
          </div>
        </aside>
      </div>
    </>
  );
}
