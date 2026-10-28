import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, Pencil, Plus, Trash2 } from "lucide-react";
import { useData } from "../hooks/useData";
import { api, errorMessage } from "../services/api";
import { PageHeader, ErrorNotice, Badge, Empty } from "../components/UI";
import type { Agent, Tool } from "../types";
const defaultTools = [
  "http_fetch",
  "html_parser",
  "link_discovery",
  "ai_extraction",
  "validation",
  "database_storage",
  "csv_export",
  "json_export",
];
export default function Agents() {
  const agents = useData<Agent[]>("agents", "/api/agents");
  const tools = useData<Tool[]>("tools", "/api/tools");
  const qc = useQueryClient();
  const [editing, setEditing] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [provider, setProvider] = useState("deterministic");
  const [model, setModel] = useState("rules-v1");
  const [selected, setSelected] = useState(defaultTools);
  const [enabled, setEnabled] = useState(true);
  const [notice, setNotice] = useState("");
  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name,
        description,
        enabled,
        agent_type: "web_scraper",
        configuration: { provider, model, temperature: 0, tools: selected },
      };
      return editing
        ? api.put(`/api/agents/${editing}`, body)
        : api.post("/api/agents", body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      setNotice("Agent configuration saved.");
      setEditing(null);
      setName("");
      setDescription("");
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/api/agents/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
  function edit(a: Agent) {
    setEditing(a.id);
    setName(a.name);
    setDescription(a.description);
    setProvider(a.configuration.provider);
    setModel(a.configuration.model);
    setSelected(a.configuration.tools);
    setEnabled(a.enabled);
    setNotice("");
  }
  function submit(e: FormEvent) {
    e.preventDefault();
    save.mutate();
  }
  return (
    <>
      <PageHeader
        eyebrow="AGENT LIBRARY"
        title="Purpose-built intelligence."
        description="Configure once. Run focused, repeatable tasks whenever you need them."
      />
      <div className="builder-grid">
        <form className="panel form-panel" onSubmit={submit}>
          <div className="section-title">
            <span className="step-number">01</span>
            <div>
              <h2>{editing ? "Edit agent" : "Create an agent"}</h2>
              <p>Define its identity and capabilities</p>
            </div>
          </div>
          <label>
            Agent name
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Company intelligence agent"
              maxLength={120}
            />
          </label>
          <label>
            Description
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What will this agent help you discover?"
            />
          </label>
          <label>
            Agent type
            <select>
              <option>Web scraping agent</option>
            </select>
          </label>
          <div className="form-row">
            <label>
              LLM provider
              <select
                aria-label="LLM provider"
                value={provider}
                onChange={(e) => {
                  setProvider(e.target.value);
                  setModel(
                    e.target.value === "deterministic"
                      ? "rules-v1"
                      : e.target.value === "openai"
                        ? "gpt-4.1-mini"
                        : "llama3.2",
                  );
                }}
              >
                <option value="deterministic">
                  Deterministic · no API key
                </option>
                <option value="openai">OpenAI</option>
                <option value="ollama">Ollama · backend configured</option>
              </select>
            </label>
            <label>
              Model
              <input
                required
                value={model}
                onChange={(e) => setModel(e.target.value)}
              />
            </label>
          </div>
          {provider === "ollama" && (
            <p className="notice">
              Enter a model available from your configured Ollama provider. Its URL
              and credentials are configured on the backend. Local mode uses JSON
              Schema output; Cloud mode requests JSON in the prompt and validates
              its fields and source evidence on the backend.
            </p>
          )}
          <label className="check-label">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            Agent enabled
          </label>
          <div className="field-label">Available tools</div>
          <div className="tool-grid">
            {tools.data?.map((tool) => (
              <label key={tool.name} className="tool-option">
                <input
                  type="checkbox"
                  checked={selected.includes(tool.name)}
                  onChange={(e) =>
                    setSelected(
                      e.target.checked
                        ? [...selected, tool.name]
                        : selected.filter((t) => t !== tool.name),
                    )
                  }
                />
                <span>
                  {tool.name.replaceAll("_", " ")}
                  <small>{tool.permission}</small>
                </span>
              </label>
            ))}
          </div>
          {save.isError && <ErrorNotice message={errorMessage(save.error)} />}{" "}
          {notice && (
            <div className="notice success">
              <Check size={16} />
              {notice}
            </div>
          )}
          <button className="button primary" disabled={save.isPending}>
            <Plus size={16} />
            {save.isPending
              ? "Saving…"
              : editing
                ? "Save configuration"
                : "Create agent"}
          </button>
        </form>
        <section>
          <div className="list-heading">
            <h2>Your agents</h2>
            <span>{agents.data?.length || 0} total</span>
          </div>
          {agents.isError && (
            <ErrorNotice message={errorMessage(agents.error)} />
          )}{" "}
          {remove.isError && (
            <ErrorNotice message={errorMessage(remove.error)} />
          )}{" "}
          {agents.data?.length ? (
            agents.data.map((agent) => (
              <article className="panel agent-card" key={agent.id}>
                <div className="agent-card-top">
                  <div className="agent-icon">
                    <Bot size={22} />
                  </div>
                  <Badge status={agent.enabled ? "enabled" : "disabled"} />
                </div>
                <h3>{agent.name}</h3>
                <p>{agent.description || "Reusable web intelligence agent"}</p>
                <div className="agent-meta">
                  {agent.configuration.provider} <span>·</span>{" "}
                  {agent.configuration.model}
                </div>
                <div className="agent-card-actions">
                  <button
                    className="button secondary"
                    onClick={() => edit(agent)}
                  >
                    <Pencil size={14} />
                    Edit configuration
                  </button>
                  <button
                    aria-label={`Delete ${agent.name}`}
                    className="icon-link danger"
                    onClick={() => remove.mutate(agent.id)}
                    disabled={remove.isPending}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </article>
            ))
          ) : (
            <Empty title="Make your first agent">
              A reusable configuration keeps your tools and model ready.
            </Empty>
          )}
        </section>
      </div>
    </>
  );
}
