import { useState } from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Col from "react-bootstrap/Col";
import Form from "react-bootstrap/Form";
import Row from "react-bootstrap/Row";
import { useAuth } from "../context/AuthContext";
import { updateMyProfile } from "../services/profileService";
import { getErrorMessage } from "../utils/errors";
import ChipInput from "./ChipInput";
import PictureUploader from "./PictureUploader";

const blank = (v) => v ?? "";

// Server profile -> the strings the form fields hold.
function toForm(p) {
  return {
    name: p.name, email: p.email, college: p.college,
    date_of_birth: blank(p.date_of_birth), phone: blank(p.phone),
    city: blank(p.city), state: blank(p.state), country: blank(p.country),
    degree: blank(p.degree), major: blank(p.major),
    graduation_year: blank(p.graduation_year), cgpa: blank(p.cgpa),
    career_objective: blank(p.career_objective),
    skills: p.skills,
    experience: p.experience.map((e) => ({
      title: e.title, company: e.company, start_date: blank(e.start_date),
      end_date: blank(e.end_date), description: blank(e.description),
    })),
  };
}

// Form strings -> what PATCH /students/me expects. Blank text clears an optional field.
export function toPayload(f) {
  return {
    name: f.name.trim(), email: f.email.trim(), college: f.college.trim(),
    date_of_birth: f.date_of_birth, phone: f.phone.trim(), city: f.city.trim(), state: f.state.trim(),
    country: f.country.trim(), degree: f.degree, major: f.major,
    graduation_year: f.graduation_year === "" ? "" : Number(f.graduation_year),
    cgpa: f.cgpa === "" ? "" : Number(f.cgpa),
    career_objective: f.career_objective.trim(),
    skills: f.skills,
    experience: f.experience.map((e) => ({
      title: e.title.trim(), company: e.company.trim(),
      start_date: e.start_date || null, end_date: e.end_date || null,
      description: e.description.trim() || null,
    })),
  };
}

// Returns a list of problems (empty = fine). The server checks everything again.
export function validateProfile(f) {
  const problems = [];
  if (!f.name.trim()) problems.push("Name is required.");
  if (!f.college.trim()) problems.push("College is required.");
  if (!/^\S+@\S+\.\S+$/.test(f.email.trim())) problems.push("Enter a valid email address.");
  if (f.cgpa !== "" && !(Number(f.cgpa) >= 0 && Number(f.cgpa) <= 4)) problems.push("GPA must be between 0 and 4.");
  if (f.graduation_year !== "" && !(Number(f.graduation_year) >= 1990 && Number(f.graduation_year) <= 2040))
    problems.push("Graduation year must be between 1990 and 2040.");
  f.experience.forEach((e, i) => {
    if (!e.title.trim() || !e.company.trim()) problems.push(`Experience ${i + 1}: title and company are required.`);
    if (e.start_date && e.end_date && e.end_date < e.start_date)
      problems.push(`Experience ${i + 1}: the end date is before the start date.`);
  });
  return problems;
}

export default function ProfileForm({ profile, options, onProfileChanged }) {
  const { updateUserName } = useAuth();
  const [form, setForm] = useState(() => toForm(profile));
  const [picture, setPicture] = useState(profile.profile_pic_url);
  const [problems, setProblems] = useState([]);
  const [serverError, setServerError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const set = (field) => (e) => { setForm({ ...form, [field]: e.target.value }); setSaved(false); };
  const setExp = (i, field, value) => {
    setForm({ ...form, experience: form.experience.map((e, n) => (n === i ? { ...e, [field]: value } : e)) });
    setSaved(false);
  };

  async function submit(e) {
    e.preventDefault();
    setSaved(false);
    setServerError("");
    const found = validateProfile(form);
    setProblems(found);
    if (found.length) return;
    setBusy(true);
    try {
      const updated = await updateMyProfile(toPayload(form));
      setForm(toForm(updated));
      updateUserName(updated.name);
      onProfileChanged?.(updated);
      setSaved(true);
    } catch (err) {
      setServerError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const skillSuggestions = Object.values(options?.skills_by_area ?? {}).flat();

  return (
    <Form onSubmit={submit} noValidate aria-label="Profile form">
      <PictureUploader name={form.name} url={picture} onUploaded={setPicture} />

      <h2 className="h5">About you</h2>
      <Row>
        <Col md={6}><Form.Group className="mb-3" controlId="p-name"><Form.Label>Full name</Form.Label>
          <Form.Control value={form.name} onChange={set("name")} maxLength={100} /></Form.Group></Col>
        <Col md={6}><Form.Group className="mb-3" controlId="p-email"><Form.Label>Email</Form.Label>
          <Form.Control type="email" value={form.email} onChange={set("email")} /></Form.Group></Col>
        <Col md={6}><Form.Group className="mb-3" controlId="p-college"><Form.Label>College</Form.Label>
          <Form.Control value={form.college} onChange={set("college")} maxLength={100} /></Form.Group></Col>
        <Col md={6}><Form.Group className="mb-3" controlId="p-phone"><Form.Label>Phone</Form.Label>
          <Form.Control value={form.phone} onChange={set("phone")} placeholder="(408) 555-0123" /></Form.Group></Col>
        <Col md={4}><Form.Group className="mb-3" controlId="p-dob"><Form.Label>Date of birth</Form.Label>
          <Form.Control type="date" value={form.date_of_birth} onChange={set("date_of_birth")} />
          <Form.Text>Only you can see this.</Form.Text></Form.Group></Col>
        <Col md={4}><Form.Group className="mb-3" controlId="p-city"><Form.Label>City</Form.Label>
          <Form.Control value={form.city} onChange={set("city")} maxLength={100} /></Form.Group></Col>
        <Col md={2}><Form.Group className="mb-3" controlId="p-state"><Form.Label>State</Form.Label>
          <Form.Control value={form.state} onChange={set("state")} maxLength={100} /></Form.Group></Col>
        <Col md={2}><Form.Group className="mb-3" controlId="p-country"><Form.Label>Country</Form.Label>
          <Form.Control value={form.country} onChange={set("country")} maxLength={100} /></Form.Group></Col>
      </Row>

      <h2 className="h5 mt-2">Education</h2>
      <Row>
        <Col md={3}><Form.Group className="mb-3" controlId="p-degree"><Form.Label>Degree</Form.Label>
          <Form.Select value={form.degree} onChange={set("degree")}>
            <option value="">—</option>
            {(options?.degrees ?? []).map((d) => <option key={d} value={d}>{d}</option>)}
          </Form.Select></Form.Group></Col>
        <Col md={5}><Form.Group className="mb-3" controlId="p-major"><Form.Label>Major</Form.Label>
          <Form.Select value={form.major} onChange={set("major")}>
            <option value="">—</option>
            {(options?.majors ?? []).map((m) => <option key={m} value={m}>{m}</option>)}
          </Form.Select></Form.Group></Col>
        <Col md={2}><Form.Group className="mb-3" controlId="p-year"><Form.Label>Graduation year</Form.Label>
          <Form.Control type="number" value={form.graduation_year} onChange={set("graduation_year")} /></Form.Group></Col>
        <Col md={2}><Form.Group className="mb-3" controlId="p-gpa"><Form.Label>GPA</Form.Label>
          <Form.Control type="number" step="0.01" value={form.cgpa} onChange={set("cgpa")} />
          <Form.Text>Hidden from other students.</Form.Text></Form.Group></Col>
      </Row>
      <Form.Group className="mb-3" controlId="p-objective"><Form.Label>Career objective</Form.Label>
        <Form.Control as="textarea" rows={3} maxLength={2000} value={form.career_objective} onChange={set("career_objective")} /></Form.Group>

      <ChipInput label="Skills" values={form.skills} suggestions={skillSuggestions} placeholder="Type a skill, press Enter"
        onChange={(skills) => { setForm({ ...form, skills }); setSaved(false); }} />

      <h2 className="h5 mt-4">Experience</h2>
      {form.experience.map((exp, i) => (
        <fieldset key={i} className="border rounded-3 p-3 mb-3" aria-label={`Experience ${i + 1}`}>
          <Row>
            <Col md={6}><Form.Group className="mb-2" controlId={`x-title-${i}`}><Form.Label>Job title</Form.Label>
              <Form.Control value={exp.title} onChange={(e) => setExp(i, "title", e.target.value)} /></Form.Group></Col>
            <Col md={6}><Form.Group className="mb-2" controlId={`x-company-${i}`}><Form.Label>Company</Form.Label>
              <Form.Control value={exp.company} onChange={(e) => setExp(i, "company", e.target.value)} /></Form.Group></Col>
            <Col md={6}><Form.Group className="mb-2" controlId={`x-start-${i}`}><Form.Label>Start date</Form.Label>
              <Form.Control type="date" value={exp.start_date} onChange={(e) => setExp(i, "start_date", e.target.value)} /></Form.Group></Col>
            <Col md={6}><Form.Group className="mb-2" controlId={`x-end-${i}`}><Form.Label>End date</Form.Label>
              <Form.Control type="date" value={exp.end_date} onChange={(e) => setExp(i, "end_date", e.target.value)} />
              <Form.Text>Leave empty if this is your current role.</Form.Text></Form.Group></Col>
          </Row>
          <Form.Group className="mb-2" controlId={`x-desc-${i}`}><Form.Label>What you did</Form.Label>
            <Form.Control as="textarea" rows={2} maxLength={2000} value={exp.description} onChange={(e) => setExp(i, "description", e.target.value)} /></Form.Group>
          <Button variant="outline-danger" size="sm" type="button"
            onClick={() => { setForm({ ...form, experience: form.experience.filter((_, n) => n !== i) }); setSaved(false); }}>
            Remove this experience
          </Button>
        </fieldset>
      ))}
      <Button variant="outline-primary" type="button" className="mb-4" disabled={form.experience.length >= 20}
        onClick={() => { setForm({ ...form, experience: [...form.experience, { title: "", company: "", start_date: "", end_date: "", description: "" }] }); setSaved(false); }}>
        Add experience
      </Button>

      {problems.length > 0 && (
        <Alert variant="danger" role="alert"><ul className="mb-0">{problems.map((p) => <li key={p}>{p}</li>)}</ul></Alert>
      )}
      {serverError && <Alert variant="danger" role="alert">{serverError}</Alert>}
      {saved && <Alert variant="success" role="status">Profile saved.</Alert>}
      <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save profile"}</Button>
    </Form>
  );
}
