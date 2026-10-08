import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";

// Shows an error message, with a "Try again" button when onRetry is given.
export default function ErrorAlert({ message, onRetry }) {
  if (!message) return null;
  return (
    <Alert variant="danger" className="d-flex justify-content-between align-items-center">
      <span>{message}</span>
      {onRetry && (
        <Button variant="outline-danger" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </Alert>
  );
}
