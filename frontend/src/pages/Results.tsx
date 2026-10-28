import { Modal } from "../components/Modal";
import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Download, ExternalLink, Search, X } from "lucide-react";
import { useData } from "../hooks/useData";
import { download, errorMessage } from "../services/api";
import {
  Badge,
  Empty,
  ErrorNotice,
  Loading,
  PageHeader,
} from "../components/UI";
import type { Job, RecordRow } from "../types";
export default function Results() {
  const { id } = useParams();
  const jobs = useData<Job[]>("jobs", "/api/scraping/jobs");
  const records = useData<RecordRow[]>(
    "results",
    `/api/scraping/jobs/${id}/results`,
    undefined,
    !!id,
  );
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [detail, setDetail] = useState<RecordRow | null>(null);
  const [error, setError] = useState("");
  async function save(format: "csv" | "json") {
    try {
      await download(id!, format);
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  if (!id)
    return (
      <>
        <PageHeader
          eyebrow="DATA EXPLORER"
          title="Answers, with receipts."
          description="Choose an execution to explore its extracted records and source evidence."
        />
        <section className="panel result-chooser">
          {jobs.data?.filter((j) => j.context.records).length ? (
            jobs.data
              .filter((j) => j.context.records)
              .map((j) => (
                <Link key={j.id} to={`/results/${j.id}`}>
                  <span>{j.input_data.url}</span>
                  <Badge status={j.status} />
                  <span>{j.context.records} records →</span>
                </Link>
              ))
          ) : (
            <Empty title="No extracted records yet">
              Run your first agent to build an evidence-backed dataset.
            </Empty>
          )}
        </section>
      </>
    );
  const keys = Array.from(
    new Set((records.data || []).flatMap((r) => Object.keys(r.extracted_data))),
  );
  const filtered = (records.data || []).filter(
    (r) =>
      JSON.stringify(r.extracted_data)
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (filter === "all" ||
        (filter === "complete"
          ? Object.values(r.extracted_data).every((v) => v !== null)
          : Object.values(r.extracted_data).some((v) => v === null))),
  );
  return (
    <>
      <PageHeader
        eyebrow={`RESULTS / ${id.slice(0, 8).toUpperCase()}`}
        title="From pages to possibilities."
        description="Structured records, validated against the original source."
        action={
          <div className="inline-actions">
            <button className="button secondary" onClick={() => save("csv")}>
              <Download size={15} />
              CSV
            </button>
            <button className="button primary" onClick={() => save("json")}>
              <Download size={15} />
              JSON
            </button>
          </div>
        }
      />
      {error && <ErrorNotice message={error} />}
      <section className="panel">
        <div className="results-toolbar">
          <div className="search-input">
            <Search size={17} />
            <input
              aria-label="Search results"
              placeholder="Search records…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select
            aria-label="Filter records"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">All records</option>
            <option value="complete">All fields populated</option>
            <option value="missing">Has missing fields</option>
          </select>
          <span>{filtered.length} records</span>
        </div>
        {records.isError ? (
          <ErrorNotice message={errorMessage(records.error)} />
        ) : records.isLoading ? (
          <Loading />
        ) : filtered.length ? (
          <div className="table-scroll">
            <table className="results-table">
              <thead>
                <tr>
                  {keys.map((k) => (
                    <th key={k}>{k.replaceAll("_", " ")}</th>
                  ))}
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => (
                  <tr key={row.id}>
                    {keys.map((k) => (
                      <td key={k}>
                        {row.extracted_data[k] === null ? (
                          <span className="null">null</span>
                        ) : k === "source_url" ? (
                          <a
                            href={row.source_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Source
                            <ExternalLink size={13} />
                          </a>
                        ) : (
                          row.extracted_data[k]
                        )}
                      </td>
                    ))}
                    <td>
                      <button
                        className="text-button"
                        onClick={() => setDetail(row)}
                      >
                        View details →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No matching records">
            Adjust your filters, or check the execution for progress and errors.
          </Empty>
        )}
      </section>
      <Link className="back-link" to={`/jobs/${id}`}>
        ← Back to execution
      </Link>
      {detail && (
        <Modal label="Record evidence" onClose={() => setDetail(null)}>
          <div className="panel-heading">
            <h2>Source evidence</h2>
            <button
              aria-label="Close details"
              autoFocus
              className="icon-link"
              onClick={() => setDetail(null)}
            >
              <X size={20} />
            </button>
          </div>
          <div className="evidence-content">
            {keys.map((k) => (
              <div className="evidence-row" key={k}>
                <label>{k}</label>
                <strong>{detail.extracted_data[k] ?? "null"}</strong>
                <blockquote>
                  {detail.evidence[k] || "No evidence found in the source."}
                </blockquote>
              </div>
            ))}
            <a href={detail.source_url} target="_blank" rel="noreferrer">
              Open original page
              <ExternalLink size={14} />
            </a>
          </div>
        </Modal>
      )}
    </>
  );
}
