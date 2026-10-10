import { useState } from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Form from "react-bootstrap/Form";
import Spinner from "react-bootstrap/Spinner";
import { Link } from "react-router-dom";
import AuthLayout from "../components/AuthLayout";
import RoleToggle from "../components/RoleToggle";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../hooks/useTheme";
import { getErrorMessage } from "../utils/errors";

const EMAIL_PATTERN = /^\S+@\S+\.\S+$/;

// The same password rules the backend enforces, so people see the problem before sending.
function passwordProblem(password) {
  if (password.length < 8) return "Password must be at least 8 characters long";
  if (new TextEncoder().encode(password).length > 72) return "Password must be at most 72 bytes long";
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) return "Password must contain at least one letter and one digit";
  return null;
}

const EMPTY = { name: "", email: "", password: "", college: "", location: "" };

export default function Signup() {
  const { signup } = useAuth();
  const [role, setRole] = useState("student");
  useTheme(role); // the page takes the colours of the chosen account type
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const isCompany = role === "company";
  const update = (field) => (event) => setForm((f) => ({ ...f, [field]: event.target.value }));

  function validate() {
    const found = {};
    const name = form.name.trim();
    if (!name) found.name = isCompany ? "Company name is required" : "Name is required";
    else if (name.length > 100) found.name = "Name must be 100 characters or fewer";
    if (!form.email.trim()) found.email = "Email is required";
    else if (!EMAIL_PATTERN.test(form.email.trim())) found.email = "Enter a valid email address";
    const problem = passwordProblem(form.password);
    if (problem) found.password = problem;
    if (isCompany && !form.location.trim()) found.location = "Location is required";
    if (!isCompany && !form.college.trim()) found.college = "College name is required";
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
      await signup(role, form); // on success the route wrapper sends us Home
    } catch (error) {
      setServerError(getErrorMessage(error));
      setSubmitting(false);
    }
  }

  const field = (id, label, key, { help, ...props } = {}) => (
    <Form.Group className="mb-3" controlId={id}>
      <Form.Label>{label}</Form.Label>
      <Form.Control
        value={form[key]}
        onChange={update(key)}
        isInvalid={Boolean(errors[key])}
        disabled={submitting}
        {...props}
      />
      <Form.Control.Feedback type="invalid">{errors[key]}</Form.Control.Feedback>
      {help && !errors[key] && <Form.Text muted>{help}</Form.Text>}
    </Form.Group>
  );

  return (
    <AuthLayout>
        <h1 className="h3 mb-1">Create your account</h1>
        <p className="text-muted mb-4">It takes a minute. Pick the account type that fits you.</p>
        {serverError && <Alert variant="danger">{serverError}</Alert>}

        <RoleToggle value={role} onChange={setRole} disabled={submitting} />

        <Form noValidate onSubmit={handleSubmit}>
          {field("signup-name", isCompany ? "Company name" : "Full name", "name", { autoComplete: "name" })}
          {field("signup-email", "Email", "email", { type: "email", autoComplete: "username" })}
          {field("signup-password", "Password", "password", {
            type: "password",
            autoComplete: "new-password",
            help: "At least 8 characters, with a letter and a digit.",
          })}
          {isCompany
            ? field("signup-location", "Location", "location", { placeholder: "City, e.g. San Jose" })
            : field("signup-college", "College", "college", { placeholder: "e.g. San Jose State University" })}

          <Button type="submit" className="w-100" disabled={submitting}>
            {submitting ? (
              <>
                <Spinner as="span" size="sm" animation="border" aria-hidden="true" className="me-2" />
                Creating account…
              </>
            ) : (
              "Create account"
            )}
          </Button>
        </Form>

        <p className="text-center text-muted mt-3 mb-0">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
    </AuthLayout>
  );
}
