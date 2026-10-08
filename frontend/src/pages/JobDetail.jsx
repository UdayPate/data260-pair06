import Badge from "react-bootstrap/Badge";
import Card from "react-bootstrap/Card";
import Col from "react-bootstrap/Col";
import Row from "react-bootstrap/Row";
import { Link, useParams } from "react-router-dom";
import ApplyBox from "../components/ApplyBox";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import { useAuth } from "../context/AuthContext";
import { useAsync } from "../hooks/useAsync";
import { getJob } from "../services/jobService";
import { categoryLabel, formatDate } from "../utils/format";

export default function JobDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const { data: job, loading, error, reload } = useAsync(() => getJob(id), [id]);

  if (loading && !job) return <Loading label="Loading job…" />;
  if (error) return <ErrorAlert message={error} onRetry={reload} />;
  if (!job) return null;

  const company = job.company;
  return (
    <>
      <Link to="/jobs" className="d-inline-block mb-3">← Back to jobs</Link>
      <Row>
        <Col lg={8} className="mb-4">
          <h1 className="h3">{job.title}</h1>
          <p className="text-muted">
            {company.name} · {job.city}
            {job.state ? `, ${job.state}` : ""}
            {job.is_remote ? " · Remote OK" : ""}
          </p>
          <div className="d-flex flex-wrap gap-1 mb-3">
            <Badge bg="primary">{categoryLabel(job.category)}</Badge>
            {job.skills.map((s) => (
              <Badge key={s} bg="light" text="dark" className="border">{s}</Badge>
            ))}
          </div>
          <dl className="row mb-4">
            <dt className="col-sm-3">Pay</dt>
            <dd className="col-sm-9">{job.salary_display}</dd>
            <dt className="col-sm-3">Posted</dt>
            <dd className="col-sm-9">
              {formatDate(job.posting_date)} ({job.posted_days_ago} {job.posted_days_ago === 1 ? "day" : "days"} ago)
            </dd>
            <dt className="col-sm-3">Apply by</dt>
            <dd className="col-sm-9">{formatDate(job.deadline)}{job.is_expired ? " (closed)" : ""}</dd>
            {job.contact_email && (
              <>
                <dt className="col-sm-3">Contact</dt>
                <dd className="col-sm-9"><a href={`mailto:${job.contact_email}`}>{job.contact_email}</a></dd>
              </>
            )}
          </dl>
          <h2 className="h5">About the job</h2>
          <p style={{ whiteSpace: "pre-line" }}>{job.description}</p>
        </Col>

        <Col lg={4}>
          {user.role === "student" && (
            <div className="mb-3">
              <ApplyBox job={job} onApplied={reload} />
            </div>
          )}
          <Card data-testid="company-card">
            <Card.Body>
              <Card.Title as="h2" className="h6">About {company.name}</Card.Title>
              {company.industry && <div className="text-muted small mb-2">{company.industry}</div>}
              {company.description && <p className="small">{company.description}</p>}
              <div className="small">
                {company.location}
                {company.state ? `, ${company.state}` : ""}
              </div>
              {company.website && (
                <div className="small"><a href={company.website} target="_blank" rel="noreferrer">{company.website}</a></div>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </>
  );
}
