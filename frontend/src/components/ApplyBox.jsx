import { useState } from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Card from "react-bootstrap/Card";
import Form from "react-bootstrap/Form";
import { applyToJob } from "../services/jobService";
import { getErrorMessage } from "../utils/errors";
import { checkResumeFile, formatDate } from "../utils/format";
import StatusBadge from "./StatusBadge";

// The right-hand box on a job page. It shows ONE of three things:
//   already applied  -> your status
//   deadline passed  -> "closed"
//   otherwise        -> resume upload + Apply button
export default function ApplyBox({ job, onApplied }) {
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (job.my_application) {
    return (
      <Card>
        <Card.Body>
          <Card.Title as="h2" className="h6">Your application</Card.Title>
          <StatusBadge status={job.my_application.status} />
          <p className="text-muted small mt-2 mb-0">Applied on {formatDate(job.my_application.applied_at)}</p>
        </Card.Body>
      </Card>
    );
  }

  if (job.is_expired) {
    return (
      <Alert variant="secondary" className="mb-0">
        Applications closed on {formatDate(job.deadline)}.
      </Alert>
    );
  }

  async function submit(e) {
    e.preventDefault();
    const problem = checkResumeFile(file);
    if (problem) return setError(problem);
    setBusy(true);
    setError("");
    try {
      await applyToJob(job.id, file);
      onApplied();                       // reload the job: it now has my_application
    } catch (err) {
      setError(getErrorMessage(err));
      setBusy(false);
    }
  }

  return (
    <Card>
      <Card.Body>
        <Card.Title as="h2" className="h6">Apply</Card.Title>
        <Form onSubmit={submit} noValidate>
          <Form.Group controlId="resume" className="mb-3">
            <Form.Label>Resume (PDF, up to 5 MB)</Form.Label>
            <Form.Control
              type="file"
              accept="application/pdf,.pdf"
              onChange={(e) => {
                setFile(e.target.files[0] ?? null);
                setError("");
              }}
            />
          </Form.Group>
          {error && <Alert variant="danger" role="alert">{error}</Alert>}
          <Button type="submit" disabled={busy} className="w-100">
            {busy ? "Sending…" : "Apply"}
          </Button>
        </Form>
      </Card.Body>
    </Card>
  );
}
