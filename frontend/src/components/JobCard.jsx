import Badge from "react-bootstrap/Badge";
import Card from "react-bootstrap/Card";
import { Link } from "react-router-dom";
import { categoryLabel, formatDate } from "../utils/format";

// One row in the job list. The whole title is a link to the details page.
export default function JobCard({ job }) {
  return (
    <Card className="mb-3 job-card" data-testid="job-card">
      <Card.Body>
        <div className="d-flex justify-content-between flex-wrap gap-2">
          <div>
            <Card.Title as="h2" className="h5 mb-1">
              <Link to={`/jobs/${job.id}`}>{job.title}</Link>
            </Card.Title>
            <div className="text-muted">
              {job.company.name} · {job.city}
              {job.state ? `, ${job.state}` : ""}
              {job.is_remote ? " · Remote OK" : ""}
            </div>
          </div>
          <div className="text-md-end">
            <div className="fw-semibold">{job.salary_display}</div>
            <div className={job.is_expired ? "text-danger small" : "text-muted small"}>
              {job.is_expired ? "Closed " : "Apply by "}
              {formatDate(job.deadline)}
            </div>
          </div>
        </div>
        <div className="mt-2 d-flex flex-wrap gap-1">
          <Badge bg="primary">{categoryLabel(job.category)}</Badge>
          {job.skills.map((s) => (
            <Badge key={s} bg="light" text="dark" className="border">
              {s}
            </Badge>
          ))}
        </div>
      </Card.Body>
    </Card>
  );
}
