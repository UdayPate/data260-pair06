import { useState } from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Card from "react-bootstrap/Card";
import Form from "react-bootstrap/Form";
import Spinner from "react-bootstrap/Spinner";
import { Link } from "react-router-dom";
import RoleToggle from "../components/RoleToggle";
import { useAuth } from "../context/AuthContext";
import { getErrorMessage } from "../utils/errors";

const EMAIL_PATTERN = /^\S+@\S+\.\S+$/;

export default function Login() {
  const { login, sessionExpired } = useAuth();
  const [role, setRole] = useState("student");
  const [form, setForm] = useState({ email: "", password: "" });
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const update = (field) => (event) => setForm((f) => ({ ...f, [field]: event.target.value }));

  function validate() {
    const found = {};
    if (!form.email.trim()) found.email = "Email is required";
    else if (!EMAIL_PATTERN.test(form.email.trim())) found.email = "Enter a valid email address";
    if (!form.password) found.password = "Password is required";
    return found;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setServerError(null);
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    try {
      await login({ ...form, role }); // on success the route wrapper sends us to the right page
    } catch (error) {
      setServerError(getErrorMessage(error));
      setSubmitting(false);
    }
  }

  return (
    <Card className="mx-auto" style={{ maxWidth: 460 }}>
      <Card.Body className="p-4">
        <h1 className="h3 mb-3">Sign in</h1>
        {sessionExpired && <Alert variant="warning">Your session has expired. Please sign in again.</Alert>}
        {serverError && <Alert variant="danger">{serverError}</Alert>}

        <RoleToggle value={role} onChange={setRole} disabled={submitting} />

        <Form noValidate onSubmit={handleSubmit}>
          <Form.Group className="mb-3" controlId="login-email">
            <Form.Label>Email</Form.Label>
            <Form.Control
              type="email"
              autoComplete="username"
              value={form.email}
              onChange={update("email")}
              isInvalid={Boolean(errors.email)}
              disabled={submitting}
            />
            <Form.Control.Feedback type="invalid">{errors.email}</Form.Control.Feedback>
          </Form.Group>

          <Form.Group className="mb-3" controlId="login-password">
            <Form.Label>Password</Form.Label>
            <Form.Control
              type="password"
              autoComplete="current-password"
              value={form.password}
              onChange={update("password")}
              isInvalid={Boolean(errors.password)}
              disabled={submitting}
            />
            <Form.Control.Feedback type="invalid">{errors.password}</Form.Control.Feedback>
          </Form.Group>

          <Button type="submit" className="w-100" disabled={submitting}>
            {submitting ? (
              <>
                <Spinner as="span" size="sm" animation="border" aria-hidden="true" className="me-2" />
                Signing in…
              </>
            ) : (
              "Sign in"
            )}
          </Button>
        </Form>

        <p className="text-center text-muted mt-3 mb-0">
          New here? <Link to="/signup">Create an account</Link>
        </p>
      </Card.Body>
    </Card>
  );
}
