import { useState } from "react";
import Alert from "react-bootstrap/Alert";
import Badge from "react-bootstrap/Badge";
import Button from "react-bootstrap/Button";
import ButtonGroup from "react-bootstrap/ButtonGroup";
import Card from "react-bootstrap/Card";
import Col from "react-bootstrap/Col";
import Row from "react-bootstrap/Row";
import { Link, useParams } from "react-router-dom";
import Avatar from "../components/Avatar";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import ResumePreview from "../components/ResumePreview";
import StatusBadge from "../components/StatusBadge";
import { useAsync } from "../hooks/useAsync";
import { getApplicant, setApplicationStatus } from "../services/postingService";
import { getErrorMessage } from "../utils/errors";
import { formatDate, formatRange } from "../utils/format";

const STATUSES = ["Pending", "Reviewed", "Declined"];

export default function ApplicantDetail() {
  const { id } = useParams();
  const { data: a, loading, error, reload } = useAsync(() => getApplicant(id), [id]);
  const [busy, setBusy] = useState(false);
  const [statusError, setStatusError] = useState("");

  async function change(status) {
    setBusy(true);
    setStatusError("");
    try {
      await setApplicationStatus(id, status);
      reload();
    } catch (err) {
      setStatusError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (loading && !a) return <Loading label="Loading applicant…" />;
  if (error) return <ErrorAlert message={error} onRetry={reload} />;
  if (!a) return null;
  const s = a.student;

  return (
    <>
      <Link to={`/company/jobs/${a.job.id}/applicants`} className="d-inline-block mb-3">← Applicants for {a.job.title}</Link>
      <Row>
        <Col lg={5} className="mb-4">
          <Card className="mb-3"><Card.Body>
            <div className="d-flex gap-3 align-items-center mb-3">
              <Avatar name={s.name} src={s.profile_pic_url} size={72} decorative />
              <div>
                <h1 className="h4 mb-1">{s.name}</h1>
                <div className="text-muted">{s.college}{s.major ? ` · ${s.major}` : ""}{s.degree ? ` (${s.degree})` : ""}</div>
              </div>
            </div>
            <dl className="row small mb-3">
              <dt className="col-4">Email</dt><dd className="col-8"><a href={`mailto:${s.email}`}>{s.email}</a></dd>
              {s.phone && (<><dt className="col-4">Phone</dt><dd className="col-8">{s.phone}</dd></>)}
              {s.cgpa != null && (<><dt className="col-4">GPA</dt><dd className="col-8">{s.cgpa}</dd></>)}
              {s.graduation_year && (<><dt className="col-4">Graduates</dt><dd className="col-8">{s.graduation_year}</dd></>)}
              {(s.city || s.state) && (<><dt className="col-4">Location</dt><dd className="col-8">{[s.city, s.state, s.country].filter(Boolean).join(", ")}</dd></>)}
            </dl>
            {s.career_objective && (<><h2 className="h6">Career objective</h2><p className="small">{s.career_objective}</p></>)}
            <h2 className="h6">Skills</h2>
            <div className="d-flex flex-wrap gap-1 mb-3">
              {s.skills.length === 0 ? <span className="text-muted small">None listed</span> :
                s.skills.map((k) => <Badge key={k} bg="light" text="dark" className="border">{k}</Badge>)}
            </div>
            <h2 className="h6">Experience</h2>
            {s.experience.length === 0 ? <p className="text-muted small mb-0">None listed</p> : (
              <ul className="list-unstyled mb-0 small">
                {s.experience.map((x) => (
                  <li key={x.id} className="mb-2"><strong>{x.title}</strong> · {x.company}
                    <div className="text-muted">{formatRange(x.start_date, x.end_date)}</div>
                    {x.description && <div>{x.description}</div>}</li>
                ))}
              </ul>
            )}
          </Card.Body></Card>

          <Card><Card.Body>
            <Card.Title as="h2" className="h6">Application status</Card.Title>
            <div className="mb-2">
              <StatusBadge status={a.status} />
              <span className="text-muted small ms-2">Applied {formatDate(a.applied_at)}</span>
            </div>
            <ButtonGroup aria-label="Set status">
              {STATUSES.map((st) => (
                <Button key={st} variant={a.status === st ? "primary" : "outline-primary"} size="sm"
                  disabled={busy || a.status === st} onClick={() => change(st)}>{st}</Button>
              ))}
            </ButtonGroup>
            {statusError && <Alert variant="danger" role="alert" className="mt-3 mb-0">{statusError}</Alert>}
          </Card.Body></Card>
        </Col>
        <Col lg={7}>
          <h2 className="h5">Resume</h2>
          <ResumePreview applicationId={a.id} />
        </Col>
      </Row>
    </>
  );
}
