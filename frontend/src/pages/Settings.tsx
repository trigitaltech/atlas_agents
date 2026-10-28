import { useState } from "react";
import { Check, KeyRound, Settings2, ShieldCheck } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useData } from "../hooks/useData";
import { PageHeader, ErrorNotice } from "../components/UI";
import type { Settings as SystemSettings } from "../types";
export default function Settings() {
  const settings = useData<SystemSettings>("settings", "/api/settings");
  const models = useData<{
    providers: { id: string; models: string[]; available: boolean }[];
  }>("models", "/api/models");
  const [token, setToken] = useState(
    sessionStorage.getItem("atlas_token") || "",
  );
  const [saved, setSaved] = useState(false);
  const qc = useQueryClient();
  return (
    <>
      <PageHeader
        eyebrow="WORKSPACE SETTINGS"
        title="The boundaries of good work."
        description="Review server policy and connect to your protected workspace."
      />
      <div className="settings-grid">
        <section className="panel form-panel">
          <div className="section-title">
            <span className="step-number">
              <KeyRound size={18} />
            </span>
            <div>
              <h2>Workspace access</h2>
              <p>Use the access token configured on your backend</p>
            </div>
          </div>
          <label>
            API access token
            <input
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => {
                setToken(e.target.value);
                setSaved(false);
              }}
              placeholder="Optional for local development"
            />
            <small>
              Stored in this tab’s session. LLM provider API keys stay on the
              backend.
            </small>
          </label>
          <button
            className="button primary"
            onClick={() => {
              sessionStorage.setItem("atlas_token", token);
              qc.invalidateQueries();
              setSaved(true);
            }}
          >
            Save access token
          </button>
          {saved && (
            <div className="notice success">
              <Check size={16} />
              Access token saved for this session.
            </div>
          )}
          <div className="form-divider" />
          <h2>LLM providers</h2>
          <p className="muted">
            Choose provider and model per agent in the Agent Builder.
          </p>
          {models.data?.providers.map((p) => (
            <div className="setting-row" key={p.id}>
              <span>
                {p.id}
                <small>
                  {p.models.join(", ") ||
                    "Enter an installed model in Agent Builder"}
                </small>
              </span>
              <span
                className={`provider-state ${p.available ? "available" : ""}`}
              >
                {p.id === "ollama"
                  ? "Check provider"
                  : p.available
                    ? "Configured"
                    : "Key required"}
              </span>
            </div>
          ))}
        </section>
        <section className="panel form-panel">
          <div className="section-title">
            <span className="step-number">
              <ShieldCheck size={18} />
            </span>
            <div>
              <h2>Execution policy</h2>
              <p>Managed through backend environment variables</p>
            </div>
          </div>
          {settings.isError && (
            <ErrorNotice message="Unable to load policy. Check your token and API connection." />
          )}
          <div className="setting-row">
            <span>Allowed domains</span>
            <strong>{settings.data?.allowed_domains.join(", ") || "—"}</strong>
          </div>
          {[
            ["Maximum pages", settings.data?.max_pages],
            [
              "Maximum duration",
              `${settings.data?.max_timeout ?? "—"} seconds`,
            ],
            ["Token limit", settings.data?.max_tokens],
            [
              "Per-domain interval",
              `${settings.data?.rate_interval ?? "—"} seconds`,
            ],
            [
              "JavaScript rendering",
              settings.data?.browser_enabled ? "Enabled" : "Disabled",
            ],
          ].map(([name, value]) => (
            <div className="setting-row" key={String(name)}>
              <span>{name}</span>
              <strong>{value ?? "—"}</strong>
            </div>
          ))}
          <div className="notice">
            <Settings2 size={19} />
            <span>
              Edit ALLOWED_DOMAINS, MAX_PAGES, MAX_TIMEOUT, MAX_TOKENS,
              RATE_INTERVAL, and BROWSER_ENABLED in .env, then restart the API
              and worker.
            </span>
          </div>
        </section>
      </div>
    </>
  );
}
