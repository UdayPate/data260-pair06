import { useState } from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Col from "react-bootstrap/Col";
import Form from "react-bootstrap/Form";
import Row from "react-bootstrap/Row";
import { getErrorMessage } from "../utils/errors";
import { categoryLabel } from "../utils/format";
import ChipInput from "./ChipInput";

const today = () => new Date().toISOString().slice(0, 10);
const blank = (v) => v ?? "";

const NEW_JOB = {
  title: "", description: "", category: "internship", city: "", state: "", is_remote: false,
  salary_min: "", salary_max: "", pay_period: "hourly", posting_date: "", deadline: "", contact_email: "", skills: [],
};

function fromJob(j) {
  return {
    title: j.title, description: j.description, category: j.category, city: j.city, state: blank(j.state),
    is_remote: j.is_remote, salary_min: blank(j.salary_min), salary_max: blank(j.salary_max), pay_period: j.pay_period,
    posting_date: j.posting_date, deadline: j.deadline, contact_email: blank(j.contact_email), skills: j.skills,
  };
}

// Form strings -> what the server expects. On create an empty posting date means "today" (leave it out).
export function toJobPayload(f, creating) {
  const payload = {
    title: f.title.trim(), description: f.description.trim(), category: f.category, city: f.city.trim(),
    state: f.state.trim(), is_remote: f.is_remote, salary_min: Number(f.salary_min), salary_max: Number(f.salary_max),
    pay_period: f.pay_period, deadline: f.deadline, contact_email: f.contact_email.trim(), skills: f.skills,
  };
  if (!creating || f.posting_date) payload.posting_date = f.posting_date;
  if (creating) {                       // the create endpoint does not accept blanks for these
    if (!payload.state) delete payload.state;
    if (!payload.contact_email) delete payload.contact_email;
  }
  return payload;
}

export function validateJob(f, creating) {
  const problems = [];
  if (!f.title.trim()) problems.push("Job title is required.");
  if (f.description.trim().length < 10) problems.push("The description needs at least 10 characters.");
  if (!f.city.trim()) problems.push("City is required.");
  if (f.salary_min === "" || f.salary_max === "") problems.push("Enter the lowest and highest pay.");
  else {
    const min = Number(f.salary_min), max = Number(f.salary_max);
    const cap = f.pay_period === "hourly" ? 500 : 1_000_000;
    if (min < 0 || max < 0) problems.push("Pay cannot be negative.");
    if (min > max) problems.push("The lowest pay cannot be higher than the highest pay.");
    if (max > cap) problems.push(`The highest pay is too high for ${f.pay_period} pay (limit ${cap.toLocaleString()}).`);
  }
  if (!f.deadline) problems.push("Choose the last day to apply.");
  else {
    const start = f.posting_date || today();
    if (f.deadline < start) problems.push("The deadline cannot be before the posting date.");
    if (creating && f.deadline < today()) problems.push("The deadline must be today or later.");
  }
  if (f.contact_email.trim() && !/^\S+@\S+\.\S+$/.test(f.contact_email.trim())) problems.push("Enter a valid contact email.");
  return problems;
}

// Used for both "Post a job" (job = null) and "Edit job" (job = the existing posting).
export default function JobForm({ job, options, onSubmit, submitLabel }) {
  const creating = !job;
  const [form, setForm] = useState(() => (job ? fromJob(job) : NEW_JOB));
  const [problems, setProblems] = useState([]);
  const [serverError, setServerError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setServerError("");
    const found = validateJob(form, creating);
    setProblems(found);
    if (found.length) return;
    setBusy(true);
    try {
      await onSubmit(toJobPayload(form, creating));
    } catch (err) {
      setServerError(getErrorMessage(err));
      setBusy(false);
    }
  }

  return (
    <Form onSubmit={submit} noValidate aria-label="Job form">
      <Row>
        <Col md={8}><Form.Group className="mb-3" controlId="j-title"><Form.Label>Job title</Form.Label>
          <Form.Control value={form.title} onChange={set("title")} maxLength={150} /></Form.Group></Col>
        <Col md={4}><Form.Group className="mb-3" controlId="j-category"><Form.Label>Type of job</Form.Label>
          <Form.Select value={form.category} onChange={set("category")}>
            {(options?.job_categories ?? ["full_time", "part_time", "on_campus", "internship"]).map((c) => (
              <option key={c} value={c}>{categoryLabel(c)}</option>
            ))}
          </Form.Select></Form.Group></Col>
      </Row>
      <Form.Group className="mb-3" controlId="j-desc"><Form.Label>Description</Form.Label>
        <Form.Control as="textarea" rows={6} maxLength={5000} value={form.description} onChange={set("description")} /></Form.Group>
      <Row>
        <Col md={5}><Form.Group className="mb-3" controlId="j-city"><Form.Label>City</Form.Label>
          <Form.Control list="job-cities" value={form.city} onChange={set("city")} maxLength={100} />
          <datalist id="job-cities">{(options?.cities ?? []).map((c) => <option key={c} value={c} />)}</datalist></Form.Group></Col>
        <Col md={3}><Form.Group className="mb-3" controlId="j-state"><Form.Label>State</Form.Label>
          <Form.Control value={form.state} onChange={set("state")} maxLength={100} placeholder="CA" /></Form.Group></Col>
        <Col md={4} className="d-flex align-items-center">
          <Form.Check id="j-remote" label="Remote is possible" checked={form.is_remote}
            onChange={(e) => setForm({ ...form, is_remote: e.target.checked })} /></Col>
      </Row>
      <Row>
        <Col md={3}><Form.Group className="mb-3" controlId="j-min"><Form.Label>Lowest pay</Form.Label>
          <Form.Control type="number" min="0" value={form.salary_min} onChange={set("salary_min")} /></Form.Group></Col>
        <Col md={3}><Form.Group className="mb-3" controlId="j-max"><Form.Label>Highest pay</Form.Label>
          <Form.Control type="number" min="0" value={form.salary_max} onChange={set("salary_max")} /></Form.Group></Col>
        <Col md={3}><Form.Group className="mb-3" controlId="j-period"><Form.Label>Paid</Form.Label>
          <Form.Select value={form.pay_period} onChange={set("pay_period")}>
            <option value="hourly">per hour</option><option value="yearly">per year</option>
          </Form.Select></Form.Group></Col>
      </Row>
      <Row>
        <Col md={4}><Form.Group className="mb-3" controlId="j-posted"><Form.Label>Posting date</Form.Label>
          <Form.Control type="date" value={form.posting_date} onChange={set("posting_date")} />
          {creating && <Form.Text>Leave empty to post today.</Form.Text>}</Form.Group></Col>
        <Col md={4}><Form.Group className="mb-3" controlId="j-deadline"><Form.Label>Apply by</Form.Label>
          <Form.Control type="date" value={form.deadline} onChange={set("deadline")} /></Form.Group></Col>
        <Col md={4}><Form.Group className="mb-3" controlId="j-email"><Form.Label>Contact email</Form.Label>
          <Form.Control type="email" value={form.contact_email} onChange={set("contact_email")} />
          <Form.Text>Defaults to your company contact email.</Form.Text></Form.Group></Col>
      </Row>
      <ChipInput label="Skills wanted" values={form.skills} placeholder="Type a skill, press Enter"
        suggestions={Object.values(options?.skills_by_area ?? {}).flat()} onChange={(skills) => setForm({ ...form, skills })} />

      {problems.length > 0 && (
        <Alert variant="danger" role="alert"><ul className="mb-0">{problems.map((p) => <li key={p}>{p}</li>)}</ul></Alert>
      )}
      {serverError && <Alert variant="danger" role="alert">{serverError}</Alert>}
      <Button type="submit" disabled={busy}>{busy ? "Saving…" : submitLabel}</Button>
    </Form>
  );
}
