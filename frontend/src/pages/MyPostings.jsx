import { useState } from "react";
import Card from "react-bootstrap/Card";
import Form from "react-bootstrap/Form";
import { Link } from "react-router-dom";
import EmptyState from "../components/EmptyState";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import Pagination from "../components/Pagination";
import { useAsync } from "../hooks/useAsync";
import { getMyJobs } from "../services/postingService";
import { categoryLabel, formatDate } from "../utils/format";

export default function MyPostings() {
  const [showClosed, setShowClosed] = useState(true);
  const [page, setPage] = useState(1);
  const { data, loading, error, reload } = useAsync(
    () => getMyJobs({ page, page_size: 10, include_expired: showClosed }), [page, showClosed]);

  return (
    <>
      <PageHeader title="My job postings" subtitle="See who applied and edit your listings."
        actions={<Link to="/company/jobs/new" className="btn btn-primary">Post a job</Link>} />
      <Form.Check id="closed" className="mb-3" label="Show closed postings" checked={showClosed}
        onChange={(e) => { setShowClosed(e.target.checked); setPage(1); }} />
      {loading && <Loading label="Loading your postings…" />}
      <ErrorAlert message={error} onRetry={reload} />
      {data && (data.items.length === 0 ? (
        <EmptyState title="No job postings yet"
          action={<Link to="/company/jobs/new" className="btn btn-primary">Post your first job</Link>}>
          Students can apply as soon as you post.
        </EmptyState>
      ) : (
        <>
          {data.items.map((job) => (
            <Card className="mb-3" key={job.id} data-testid="posting-card">
              <Card.Body className="d-flex justify-content-between flex-wrap gap-3">
                <div>
                  <Card.Title as="h2" className="h5 mb-1"><Link to={`/jobs/${job.id}`}>{job.title}</Link></Card.Title>
                  <div className="text-muted">
                    {categoryLabel(job.category)} · {job.city}{job.is_remote ? " · Remote OK" : ""} · {job.salary_display}
                  </div>
                  <div className={job.is_expired ? "text-danger small" : "text-muted small"}>
                    {job.is_expired ? "Closed " : "Apply by "}{formatDate(job.deadline)}
                  </div>
                </div>
                <div className="text-md-end">
                  <div className="fs-4 fw-bold" aria-label={`${job.applicant_count} applicants`}>{job.applicant_count}</div>
                  <div className="text-muted small mb-2">{job.applicant_count === 1 ? "applicant" : "applicants"}</div>
                  <Link to={`/company/jobs/${job.id}/applicants`} className="btn btn-sm btn-primary me-2">View applicants</Link>
                  <Link to={`/company/jobs/${job.id}/edit`} className="btn btn-sm btn-outline-secondary">Edit</Link>
                </div>
              </Card.Body>
            </Card>
          ))}
          <Pagination page={data.page} totalPages={data.total_pages} onChange={setPage} />
        </>
      ))}
    </>
  );
}
