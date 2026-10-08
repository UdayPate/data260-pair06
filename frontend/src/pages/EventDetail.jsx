import { useState } from "react";
import Alert from "react-bootstrap/Alert";
import Badge from "react-bootstrap/Badge";
import Button from "react-bootstrap/Button";
import Card from "react-bootstrap/Card";
import Col from "react-bootstrap/Col";
import Row from "react-bootstrap/Row";
import { Link, useParams } from "react-router-dom";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import { useAuth } from "../context/AuthContext";
import { useAsync } from "../hooks/useAsync";
import { cancelRegistration, getEvent, registerForEvent } from "../services/eventService";
import { getErrorMessage } from "../utils/errors";
import { formatDateTime } from "../utils/format";

// The register / cancel box (students only).
function RegisterBox({ event, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run(action) {
    setBusy(true);
    setError("");
    try {
      await action(event.id);
      onChanged();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-3">
      <Card.Body>
        <Card.Title as="h2" className="h6">Registration</Card.Title>
        {event.registered ? (
          <>
            <Badge bg="success" className="mb-2">You are registered</Badge>
            {!event.is_past && (
              <div>
                <Button variant="outline-danger" size="sm" disabled={busy} onClick={() => run(cancelRegistration)}>
                  {busy ? "Working…" : "Cancel registration"}
                </Button>
              </div>
            )}
          </>
        ) : event.can_register ? (
          <Button disabled={busy} className="w-100" onClick={() => run(registerForEvent)}>
            {busy ? "Registering…" : "Register"}
          </Button>
        ) : (
          <Alert variant="secondary" className="mb-0">{event.register_blocked_reason || "Registration is not available."}</Alert>
        )}
        {error && <Alert variant="danger" role="alert" className="mt-3 mb-0">{error}</Alert>}
      </Card.Body>
    </Card>
  );
}

export default function EventDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const { data: event, loading, error, reload } = useAsync(() => getEvent(id), [id]);

  if (loading && !event) return <Loading label="Loading event…" />;
  if (error) return <ErrorAlert message={error} onRetry={reload} />;
  if (!event) return null;
  const company = event.company;

  return (
    <>
      <Link to="/events" className="d-inline-block mb-3">← Back to events</Link>
      <Row>
        <Col lg={8} className="mb-4">
          <h1 className="h3">{event.name}</h1>
          <p className="text-muted">Hosted by {company.name}</p>
          <dl className="row mb-4">
            <dt className="col-sm-3">When</dt>
            <dd className="col-sm-9">{formatDateTime(event.event_datetime)}{event.is_past ? " (past)" : ""}</dd>
            <dt className="col-sm-3">Where</dt>
            <dd className="col-sm-9">{event.location}, {event.city}</dd>
            <dt className="col-sm-3">Open to</dt>
            <dd className="col-sm-9">{event.eligible_majors.join(", ")}</dd>
            <dt className="col-sm-3">Registered</dt>
            <dd className="col-sm-9">{event.registration_count}</dd>
          </dl>
          <h2 className="h5">About the event</h2>
          <p style={{ whiteSpace: "pre-line" }}>{event.description}</p>
        </Col>
        <Col lg={4}>
          {user.role === "student" && <RegisterBox event={event} onChanged={reload} />}
          <Card data-testid="company-card">
            <Card.Body>
              <Card.Title as="h2" className="h6">About {company.name}</Card.Title>
              {company.industry && <div className="text-muted small mb-2">{company.industry}</div>}
              {company.description && <p className="small">{company.description}</p>}
              {company.website && <div className="small"><a href={company.website} target="_blank" rel="noreferrer">{company.website}</a></div>}
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </>
  );
}
