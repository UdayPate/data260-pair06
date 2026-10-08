import Spinner from "react-bootstrap/Spinner";

// A centered spinner. role="status" lets screen readers announce it.
export default function Loading({ label = "Loading…" }) {
  return (
    <div className="d-flex flex-column align-items-center justify-content-center py-5 text-muted">
      <Spinner animation="border" role="status" aria-label={label} />
      <div className="mt-2">{label}</div>
    </div>
  );
}
