import { useEffect, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Card from "react-bootstrap/Card";
import Form from "react-bootstrap/Form";
import { selectSubmission, submitApplication } from "../store/applicationsSlice";
import { checkResumeFile, formatDate } from "../utils/format";
import StatusBadge from "./StatusBadge";

const POLL_MS = 1500;   // how often to ask again while the application is being saved
const MAX_POLLS = 10;   // then stop asking (about 15 seconds)

// The right-hand box on a job page. It shows ONE of four things:
//   already applied  -> your status
//   just applied     -> "received": the server answers 202 Accepted and a background worker saves the application
//                       a moment later, so we ask again every 1.5 seconds until it shows up.
//                       The progress (sending / received / failed) is kept in the Redux applications slice, so it
//                       survives leaving this page and coming back.
//   deadline passed  -> "closed"
//   otherwise        -> resume upload + Apply button
export default function ApplyBox({ job, onApplied }) {
  const [file, setFile] = useState(null);
  const [fileError, setFileError] = useState("");                  // a problem with the chosen file (checked here, never sent)
  const dispatch = useDispatch();
  const submission = useSelector(selectSubmission(job.id));       // { status, error } from the applications slice
  const busy = submission.status === "sending";
  const received = submission.status === "received";
  const error = fileError || (submission.status === "failed" ? submission.error : "");
  const polls = useRef(0);

  useEffect(() => {
    if (!received || job.my_application || polls.current >= MAX_POLLS) return undefined;
    const timer = setTimeout(() => {
      polls.current += 1;
      onApplied();                       // reload the job: has the worker saved the application yet?
    }, POLL_MS);
    return () => clearTimeout(timer);
  }, [received, job, onApplied]);

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

  if (received) {
    return polls.current >= MAX_POLLS ? (
      <Alert variant="secondary" className="mb-0">
        We received your application, but it is taking longer than usual to appear. Check My applications in a moment.
      </Alert>
    ) : (
      <Card>
        <Card.Body>
          <Card.Title as="h2" className="h6">Your application</Card.Title>
          <p className="text-muted small mb-0">We received your application and are saving it. This page updates by itself.</p>
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
    if (problem) return setFileError(problem);
    setFileError("");
    // 202 Accepted: the application is queued, a worker saves it
    const result = await dispatch(submitApplication({ jobId: job.id, file }));
    if (submitApplication.fulfilled.match(result)) onApplied();   // reload the job: it has my_application as soon as the worker is done
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
                setFileError("");
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
