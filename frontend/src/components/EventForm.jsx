import { useState } from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Col from "react-bootstrap/Col";
import Form from "react-bootstrap/Form";
import Row from "react-bootstrap/Row";
import { getErrorMessage } from "../utils/errors";
import ChipInput from "./ChipInput";

const NEW_EVENT = { name: "", description: "", event_datetime: "", location: "", city: "", all_majors: true, majors: [] };

function fromEvent(e) {
  const all = e.eligible_majors.includes("All");
  return { name: e.name, description: e.description, event_datetime: e.event_datetime.slice(0, 16), location: e.location,
           city: e.city, all_majors: all, majors: all ? [] : e.eligible_majors };
}

export function toEventPayload(f) {
  return {
    name: f.name.trim(), description: f.description.trim(), location: f.location.trim(), city: f.city.trim(),
    // <input type="datetime-local"> gives "2027-02-10T17:30"; the server wants seconds too
    event_datetime: f.event_datetime.length === 16 ? `${f.event_datetime}:00` : f.event_datetime,
    eligible_majors: f.all_majors ? ["All"] : f.majors,
  };
}

export function validateEvent(f) {
  const problems = [];
  if (!f.name.trim()) problems.push("Event name is required.");
  if (f.description.trim().length < 10) problems.push("The description needs at least 10 characters.");
  if (!f.location.trim()) problems.push("Location is required.");
  if (!f.city.trim()) problems.push("City is required.");
  if (!f.event_datetime) problems.push("Choose the date and time.");
  else if (new Date(f.event_datetime) <= new Date()) problems.push("The event must be in the future.");
  if (!f.all_majors && f.majors.length === 0) problems.push('Add at least one major, or choose "Open to all majors".');
  return problems;
}

// Used for both "Post an event" (event = null) and "Edit event".
export default function EventForm({ event, options, onSubmit, submitLabel }) {
  const [form, setForm] = useState(() => (event ? fromEvent(event) : NEW_EVENT));
  const [problems, setProblems] = useState([]);
  const [serverError, setServerError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setServerError("");
    const found = validateEvent(form);
    setProblems(found);
    if (found.length) return;
    setBusy(true);
    try {
      await onSubmit(toEventPayload(form));
    } catch (err) {
      setServerError(getErrorMessage(err));
      setBusy(false);
    }
  }

  return (
    <Form onSubmit={submit} noValidate aria-label="Event form">
      <Form.Group className="mb-3" controlId="ev-name"><Form.Label>Event name</Form.Label>
        <Form.Control value={form.name} onChange={set("name")} maxLength={200} /></Form.Group>
      <Form.Group className="mb-3" controlId="ev-desc"><Form.Label>Description</Form.Label>
        <Form.Control as="textarea" rows={5} maxLength={5000} value={form.description} onChange={set("description")} /></Form.Group>
      <Row>
        <Col md={4}><Form.Group className="mb-3" controlId="ev-when"><Form.Label>Date and time</Form.Label>
          <Form.Control type="datetime-local" value={form.event_datetime} onChange={set("event_datetime")} /></Form.Group></Col>
        <Col md={5}><Form.Group className="mb-3" controlId="ev-where"><Form.Label>Location</Form.Label>
          <Form.Control value={form.location} onChange={set("location")} maxLength={255} placeholder="Venue or address" /></Form.Group></Col>
        <Col md={3}><Form.Group className="mb-3" controlId="ev-city"><Form.Label>City</Form.Label>
          <Form.Control list="event-cities" value={form.city} onChange={set("city")} maxLength={100} />
          <datalist id="event-cities">{(options?.cities ?? []).map((c) => <option key={c} value={c} />)}</datalist></Form.Group></Col>
      </Row>
      <Form.Check id="ev-all" className="mb-2" label="Open to all majors" checked={form.all_majors}
        onChange={(e) => setForm({ ...form, all_majors: e.target.checked })} />
      {!form.all_majors && (
        <ChipInput label="Eligible majors" values={form.majors} max={10} suggestions={options?.majors ?? []}
          placeholder="e.g. Computer Science" onChange={(majors) => setForm({ ...form, majors })} />
      )}
      {problems.length > 0 && (
        <Alert variant="danger" role="alert" className="mt-3"><ul className="mb-0">{problems.map((p) => <li key={p}>{p}</li>)}</ul></Alert>
      )}
      {serverError && <Alert variant="danger" role="alert" className="mt-3">{serverError}</Alert>}
      <div className="mt-3"><Button type="submit" disabled={busy}>{busy ? "Saving…" : submitLabel}</Button></div>
    </Form>
  );
}
