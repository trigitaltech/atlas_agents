import type { ReactNode } from "react";
import { ArrowUpRight, CircleAlert, LoaderCircle } from "lucide-react";
import { Link } from "react-router-dom";
import type { Job } from "../types";
export function Badge({ status }: { status: string }) {
  return (
    <span className={`badge ${status}`}>
      <i />
      {status.replaceAll("_", " ")}
    </span>
  );
}
export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <header className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </header>
  );
}
export function ErrorNotice({ message }: { message: string }) {
  return (
    <div role="alert" className="notice error">
      <CircleAlert size={17} />
      {message}
    </div>
  );
}
export function Loading() {
  return (
    <div className="empty">
      <LoaderCircle className="spin" />
      Loading workspace…
    </div>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-orbit">✧</div>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function JobTable({ jobs }: { jobs: Job[] }) {
  return jobs.length ? (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Execution / source</th>
            <th>Status</th>
            <th>Pages</th>
            <th>Records</th>
            <th>Created</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id}>
              <td>
                <Link className="table-link" to={`/jobs/${job.id}`}>
                  {new URL(job.input_data.url).hostname}
                  <span>{job.id.slice(0, 8)}</span>
                </Link>
              </td>
              <td>
                <Badge status={job.status} />
              </td>
              <td>{job.context.pages || 0}</td>
              <td>{job.context.records || 0}</td>
              <td className="muted">
                {new Date(job.created_at).toLocaleString()}
              </td>
              <td>
                <Link
                  aria-label="View execution"
                  to={`/jobs/${job.id}`}
                  className="icon-link"
                >
                  <ArrowUpRight size={17} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <Empty title="Your first execution starts here">
      Create an agent and run an authorized website to see its progress.
    </Empty>
  );
}
