import { Link } from "react-router-dom";
import {
  ArrowRight,
  ArrowUpRight,
  Bot,
  CheckCheck,
  CircleAlert,
  Globe2,
  Layers3,
  Plus,
  Radio,
  ShieldCheck,
} from "lucide-react";
import { useData } from "../hooks/useData";
import { PageHeader, JobTable, ErrorNotice, Loading } from "../components/UI";
import type { Job, Agent } from "../types";
export default function Dashboard() {
  const stats = useData<{
    agents: number;
    active: number;
    completed: number;
    failed: number;
  }>("stats", "/api/stats", 4000);
  const jobs = useData<Job[]>("jobs", "/api/scraping/jobs", 4000);
  const agents = useData<Agent[]>("agents", "/api/agents");
  const cards = [
    ["Total agents", stats.data?.agents, Bot, "Registered in your workspace"],
    ["Active executions", stats.data?.active, Radio, "Queued and running now"],
    [
      "Completed jobs",
      stats.data?.completed,
      CheckCheck,
      "Results ready to explore",
    ],
    [
      "Failed jobs",
      stats.data?.failed,
      CircleAlert,
      "Review execution details",
    ],
  ] as const;
  return (
    <>
      <PageHeader
        eyebrow="WORKSPACE OVERVIEW"
        title="Intelligence, in motion."
        description="Build focused agents. Turn the web into useful, verifiable data."
        action={
          <Link className="button primary" to="/scrape">
            <Plus size={17} /> New execution
          </Link>
        }
      />
      {stats.isError && (
        <ErrorNotice message="Cannot reach the API. Start the backend and check your access token in Settings." />
      )}
      <section className="stats-grid">
        {cards.map(([title, value, Icon, caption], i) => (
          <article className={`stat-card stat-${i}`} key={title}>
            <div className="stat-top">
              <span>{title}</span>
              <Icon size={18} />
            </div>
            <strong>{value ?? "—"}</strong>
            <p>
              <span className="stat-dot" />
              {caption}
            </p>
          </article>
        ))}
      </section>
      <section className="feature-banner">
        <div className="banner-copy">
          <span className="banner-label">
            <span /> THE WEB, STRUCTURED
          </span>
          <h2>
            A clear path from
            <br />
            website to insight.
          </h2>
          <p>
            Give your agent a source and a question.
            <br />
            Get structured answers with evidence attached.
          </p>
          <Link to="/scrape">
            Launch web intelligence <ArrowRight size={16} />
          </Link>
        </div>
        <div className="flow-illustration" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="flow-box source">
            <Globe2 />
            <span>Public sources</span>
            <small>Authorized websites</small>
          </div>
          <div className="flow-line line-one" />
          <div className="flow-core">
            <Layers3 size={37} />
          </div>
          <div className="flow-line line-two" />
          <div className="flow-box output">
            <CheckCheck />
            <span>Verified records</span>
            <small>Structured. Traceable.</small>
          </div>
          <div className="flow-chip">
            <ShieldCheck size={13} /> Evidence included
          </div>
        </div>
      </section>
      <div className="dashboard-lower">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Recent executions</h2>
              <p>Your agents’ latest activity</p>
            </div>
            <Link to="/jobs">
              View all <ArrowUpRight size={15} />
            </Link>
          </div>
          {jobs.isLoading ? (
            <Loading />
          ) : (
            <JobTable jobs={(jobs.data || []).slice(0, 5)} />
          )}
        </section>
        <aside className="panel workspace-note">
          <div className="note-icon">
            <Bot size={23} />
          </div>
          <span className="eyebrow">YOUR AGENT LIBRARY</span>
          <h2>
            Small agents.
            <br />
            Focused work.
          </h2>
          <p>
            {agents.data?.length
              ? `${agents.data.length} configured agents, ready for your next task.`
              : "Create a reusable agent with the tools and model your task needs."}
          </p>
          <Link className="button secondary" to="/agents">
            Open agent builder <ArrowUpRight size={16} />
          </Link>
          <div className="guardrail">
            <ShieldCheck size={16} />
            <span>
              Bounded by design
              <br />
              <small>Domain, page, time & token limits</small>
            </span>
          </div>
        </aside>
      </div>
    </>
  );
}
