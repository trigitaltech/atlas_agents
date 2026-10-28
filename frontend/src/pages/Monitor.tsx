import { useParams, Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  Clock3,
  ExternalLink,
  FileStack,
  Hash,
  Square,
  Workflow,
} from "lucide-react";
import { useData } from "../hooks/useData";
import { api, errorMessage } from "../services/api";
import { Badge, PageHeader, Loading, ErrorNotice } from "../components/UI";
import type { Job } from "../types";
export default function Monitor() {
  const { id } = useParams();
  const query = useData<Job>("job", `/api/scraping/jobs/${id}`, 1500);
  const qc = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => api.post(`/api/scraping/jobs/${id}/cancel`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["job"] }),
  });
  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorNotice message={errorMessage(query.error)} />;
  const job = query.data!;
  const active = ["queued", "running"].includes(job.status);
  const elapsed = job.started_at
    ? Math.max(
        0,
        Math.round(
          ((job.completed_at
            ? new Date(job.completed_at).getTime()
            : Date.now()) -
            new Date(job.started_at).getTime()) /
            1000,
        ),
      )
    : 0;
  return (
    <>
      <PageHeader
        eyebrow={`EXECUTION / ${job.id.slice(0, 8).toUpperCase()}`}
        title="Work you can follow."
        description={job.input_data.url}
        action={
          <div className="inline-actions">
            <Badge status={job.status} />
            {active ? (
              <button
                className="button secondary danger"
                onClick={() => cancel.mutate()}
                disabled={cancel.isPending}
              >
                <Square size={14} />
                Cancel job
              </button>
            ) : (
              <Link className="button primary" to={`/results/${id}`}>
                View results
                <ArrowRight size={16} />
              </Link>
            )}
          </div>
        }
      />
      {job.error_message && <ErrorNotice message={job.error_message} />}{" "}
      {job.context.error_code === "redirect_authorization_required" && (
        <div className="notice" style={{ display: "block" }}>
          <p>
            The destination{" "}
            <strong>{job.context.authorization_required_hostname}</strong> is
            outside this execution's authorized scope. No request was made to
            that hostname. Review your authorization before starting a new
            execution.
          </p>
          <Link className="button secondary" to={`/scrape?retry=${job.id}`}>
            Review redirect authorization
          </Link>
        </div>
      )}
      {cancel.isError && <ErrorNotice message={errorMessage(cancel.error)} />}
      <section className="stats-grid">
        {[
          [FileStack, "Pages visited", job.context.pages || 0],
          [Hash, "Verified records", job.context.records || 0],
          [Clock3, "Execution duration", `${elapsed}s`],
          [Workflow, "Current step", job.context.step || "queued"],
        ].map(([Icon, label, value]) => {
          const I = Icon as typeof FileStack;
          return (
            <article className="stat-card" key={String(label)}>
              <div className="stat-top">
                <span>{String(label)}</span>
                <I size={18} />
              </div>
              <strong className={label === "Current step" ? "step-value" : ""}>
                {String(value)}
              </strong>
            </article>
          );
        })}
      </section>
      <div className="monitor-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Execution timeline</h2>
              <p>Persisted checkpoints from the agent workflow</p>
            </div>
            {active && (
              <span className="live-label">
                <i />
                Live
              </span>
            )}
          </div>
          <div className="timeline">
            {job.executions?.length ? (
              job.executions.map((step) => (
                <div className="timeline-row" key={step.id}>
                  <span className="timeline-check">
                    <Check size={14} />
                  </span>
                  <div>
                    <h3>{step.step_name}</h3>
                    <p>
                      {step.error_message ||
                        new Date(step.created_at).toLocaleTimeString()}
                    </p>
                  </div>
                  <span>
                    {step.duration_ms ? `${step.duration_ms} ms` : step.status}
                  </span>
                </div>
              ))
            ) : (
              <p className="muted">
                Waiting for a worker to pick up this execution.
              </p>
            )}
          </div>
        </section>
        <aside className="panel detail-panel">
          <h2>Task context</h2>
          <label>Instructions</label>
          <p>{job.input_data.instruction}</p>
          <label>Authorized hostnames for this job</label>
          <div className="tags">
            {job.context.authorized_hostnames?.map((host) => (
              <span key={host}>{host}</span>
            ))}
          </div>
          <label>Requested fields</label>
          <div className="tags">
            {job.input_data.fields.map((f) => (
              <span key={f}>{f}</span>
            ))}
          </div>
          <label>Source</label>
          <a href={job.input_data.url} target="_blank" rel="noreferrer">
            Open website
            <ExternalLink size={14} />
          </a>
          <label>Tokens / estimated cost</label>
          <p>
            {job.context.tokens || 0} /{" "}
            {job.context.approximate_cost
              ? `$${job.context.approximate_cost.toFixed(6)}`
              : "Pricing not configured or no LLM usage"}
          </p>
          {job.context.stop_reason && (
            <>
              <label>Stopping condition</label>
              <p>{job.context.stop_reason.replaceAll("_", " ")}</p>
            </>
          )}
        </aside>
      </div>
    </>
  );
}
