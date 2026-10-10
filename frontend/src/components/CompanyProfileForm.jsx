import { useState } from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Col from "react-bootstrap/Col";
import Form from "react-bootstrap/Form";
import Row from "react-bootstrap/Row";
import { useAuth } from "../context/AuthContext";
import { updateMyCompany, uploadCompanyLogo } from "../services/companyService";
import { getErrorMessage } from "../utils/errors";
import PictureUploader from "./PictureUploader";

const blank = (v) => v ?? "";

function toForm(c) {
  return { name: c.name, email: c.email, location: c.location, state: blank(c.state), industry: blank(c.industry),
           description: blank(c.description), contact_email: blank(c.contact_email),
           contact_phone: blank(c.contact_phone), website: blank(c.website) };
}

export function validateCompany(f) {
  const problems = [];
  if (!f.name.trim()) problems.push("Company name is required.");
  if (!f.location.trim()) problems.push("City is required.");
  if (!/^\S+@\S+\.\S+$/.test(f.email.trim())) problems.push("Enter a valid login email.");
  if (f.contact_email.trim() && !/^\S+@\S+\.\S+$/.test(f.contact_email.trim())) problems.push("Enter a valid contact email.");
  if (f.website.trim() && !/^https?:\/\/\S+$/i.test(f.website.trim())) problems.push("The website must start with http:// or https://.");
  return problems;
}

export default function CompanyProfileForm({ company }) {
  const { updateUserName } = useAuth();
  const [form, setForm] = useState(() => toForm(company));
  const [logo, setLogo] = useState(company.profile_pic_url);
  const [problems, setProblems] = useState([]);
  const [serverError, setServerError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const set = (field) => (e) => { setForm({ ...form, [field]: e.target.value }); setSaved(false); };

  async function submit(e) {
    e.preventDefault();
    setSaved(false);
    setServerError("");
    const found = validateCompany(form);
    setProblems(found);
    if (found.length) return;
    setBusy(true);
    try {
      const payload = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim()]));
      const updated = await updateMyCompany(payload);    // blank optional fields are cleared by the server
      setForm(toForm(updated));
      updateUserName(updated.name);
      setSaved(true);
    } catch (err) {
      setServerError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Form onSubmit={submit} noValidate aria-label="Company profile form">
      <PictureUploader name={form.name} url={logo} kind="company" onUploaded={setLogo} upload={uploadCompanyLogo} label="Company logo" />
      <Row>
        <Col md={6}><Form.Group className="mb-3" controlId="c-name"><Form.Label>Company name</Form.Label>
          <Form.Control value={form.name} onChange={set("name")} maxLength={100} /></Form.Group></Col>
        <Col md={6}><Form.Group className="mb-3" controlId="c-email"><Form.Label>Login email</Form.Label>
          <Form.Control type="email" value={form.email} onChange={set("email")} /></Form.Group></Col>
        <Col md={5}><Form.Group className="mb-3" controlId="c-city"><Form.Label>City</Form.Label>
          <Form.Control value={form.location} onChange={set("location")} maxLength={100} /></Form.Group></Col>
        <Col md={3}><Form.Group className="mb-3" controlId="c-state"><Form.Label>State</Form.Label>
          <Form.Control value={form.state} onChange={set("state")} maxLength={100} /></Form.Group></Col>
        <Col md={4}><Form.Group className="mb-3" controlId="c-industry"><Form.Label>Industry</Form.Label>
          <Form.Control value={form.industry} onChange={set("industry")} maxLength={100} /></Form.Group></Col>
      </Row>
      <Form.Group className="mb-3" controlId="c-desc"><Form.Label>About the company</Form.Label>
        <Form.Control as="textarea" rows={4} maxLength={3000} value={form.description} onChange={set("description")} /></Form.Group>
      <Row>
        <Col md={4}><Form.Group className="mb-3" controlId="c-contact"><Form.Label>Contact email</Form.Label>
          <Form.Control type="email" value={form.contact_email} onChange={set("contact_email")} />
          <Form.Text>Shown to students.</Form.Text></Form.Group></Col>
        <Col md={4}><Form.Group className="mb-3" controlId="c-phone"><Form.Label>Contact phone</Form.Label>
          <Form.Control value={form.contact_phone} onChange={set("contact_phone")} placeholder="(408) 555-0123" /></Form.Group></Col>
        <Col md={4}><Form.Group className="mb-3" controlId="c-web"><Form.Label>Website</Form.Label>
          <Form.Control value={form.website} onChange={set("website")} placeholder="https://" /></Form.Group></Col>
      </Row>
      {problems.length > 0 && (
        <Alert variant="danger" role="alert"><ul className="mb-0">{problems.map((p) => <li key={p}>{p}</li>)}</ul></Alert>
      )}
      {serverError && <Alert variant="danger" role="alert">{serverError}</Alert>}
      {saved && <Alert variant="success" role="status">Company profile saved.</Alert>}
      <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save profile"}</Button>
    </Form>
  );
}
