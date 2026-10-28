import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { useData } from "../hooks/useData";
import { PageHeader, JobTable, Loading, ErrorNotice } from "../components/UI";
import { errorMessage } from "../services/api";
import type { Job } from "../types";
export default function Jobs() {
  const jobs = useData<Job[]>("jobs", "/api/scraping/jobs", 3000);
  return (
    <>
      <PageHeader
        eyebrow="EXECUTION HISTORY"
        title="Every step, accounted for."
        description="Follow your agents from their first request to the final verified record."
        action={
          <Link className="button primary" to="/scrape">
            <Plus size={16} />
            New execution
          </Link>
        }
      />
      <section className="panel">
        <div className="panel-heading">
          <h2>Latest 100 executions</h2>
          <span className="live-label">
            <i />
            Updates every 3 seconds
          </span>
        </div>
        {jobs.isError ? (
          <ErrorNotice message={errorMessage(jobs.error)} />
        ) : jobs.isLoading ? (
          <Loading />
        ) : (
          <JobTable jobs={jobs.data || []} />
        )}
      </section>
    </>
  );
}
