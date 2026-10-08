import { useState } from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Form from "react-bootstrap/Form";
import { clearPreferences, savePreferences } from "../services/profileService";
import { getErrorMessage } from "../utils/errors";
import { categoryLabel } from "../utils/format";
import ChipInput from "./ChipInput";

const toggle = (list, v) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

function toForm(p) {
  return {
    preferred_categories: p.preferred_categories, preferred_cities: p.preferred_cities,
    preferred_roles: p.preferred_roles, min_hourly_rate: p.min_hourly_rate ?? "",
    open_to_remote: p.open_to_remote, event_interests: p.event_interests,
  };
}

// What the AI assistant uses to answer "find me a job in MY city". Saving replaces the whole set.
export default function PreferencesForm({ prefs, options }) {
  const [form, setForm] = useState(() => toForm(prefs));
  const [isSaved, setIsSaved] = useState(prefs.saved);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const change = (patch) => { setForm({ ...form, ...patch }); setMessage(""); };

  async function submit(e) {
    e.preventDefault();
    setError("");
    const rate = form.min_hourly_rate;
    if (rate !== "" && !(Number(rate) >= 0 && Number(rate) <= 500)) return setError("Minimum pay must be between 0 and 500 dollars per hour.");
    setBusy(true);
    try {
      const saved = await savePreferences({ ...form, min_hourly_rate: rate === "" ? null : Number(rate) });
      setForm(toForm(saved));
      setIsSaved(true);
      setMessage("Preferences saved.");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function forget() {
    setError("");
    setBusy(true);
    try {
      await clearPreferences();
      setForm(toForm({ preferred_categories: [], preferred_cities: [], preferred_roles: [], min_hourly_rate: null,
                       open_to_remote: true, event_interests: [] }));
      setIsSaved(false);
      setMessage("Preferences cleared.");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Form onSubmit={submit} noValidate aria-label="Preferences form">
      <p className="text-muted">
        {isSaved ? "These guide your AI assistant's job and event suggestions." : "You have not saved any preferences yet."}
      </p>

      <fieldset className="mb-3">
        <legend className="form-label fs-6">Kinds of jobs</legend>
        {(options?.job_categories ?? []).map((c) => (
          <Form.Check inline key={c} id={`pc-${c}`} label={categoryLabel(c)} checked={form.preferred_categories.includes(c)}
            onChange={() => change({ preferred_categories: toggle(form.preferred_categories, c) })} />
        ))}
      </fieldset>

      <fieldset className="mb-3">
        <legend className="form-label fs-6">Preferred cities</legend>
        {(options?.cities ?? []).map((c) => (
          <Form.Check inline key={c} id={`pcity-${c}`} label={c} checked={form.preferred_cities.includes(c)}
            onChange={() => change({ preferred_cities: toggle(form.preferred_cities, c) })} />
        ))}
        <Form.Check id="p-remote" className="mt-2" label="Open to remote jobs" checked={form.open_to_remote}
          onChange={(e) => change({ open_to_remote: e.target.checked })} />
      </fieldset>

      <ChipInput label="Roles you are interested in" values={form.preferred_roles} max={10}
        suggestions={options?.role_suggestions ?? []} placeholder="e.g. Data Analyst"
        onChange={(preferred_roles) => change({ preferred_roles })} />

      <Form.Group className="mb-3" controlId="p-rate" style={{ maxWidth: 260 }}>
        <Form.Label>Minimum pay (dollars per hour)</Form.Label>
        <Form.Control type="number" min="0" max="500" value={form.min_hourly_rate}
          onChange={(e) => change({ min_hourly_rate: e.target.value })} placeholder="e.g. 25" />
      </Form.Group>

      <fieldset className="mb-4">
        <legend className="form-label fs-6">Event interests</legend>
        {(options?.event_interest_options ?? []).map((o) => (
          <Form.Check inline key={o} id={`pe-${o}`} label={o} checked={form.event_interests.includes(o)}
            onChange={() => change({ event_interests: toggle(form.event_interests, o) })} />
        ))}
      </fieldset>

      {error && <Alert variant="danger" role="alert">{error}</Alert>}
      {message && <Alert variant="success" role="status">{message}</Alert>}
      <div className="d-flex gap-2">
        <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save preferences"}</Button>
        {isSaved && <Button type="button" variant="outline-danger" disabled={busy} onClick={forget}>Clear saved preferences</Button>}
      </div>
    </Form>
  );
}
