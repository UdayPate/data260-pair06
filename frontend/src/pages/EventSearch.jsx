import { useState } from "react";
import Button from "react-bootstrap/Button";
import Card from "react-bootstrap/Card";
import Col from "react-bootstrap/Col";
import Form from "react-bootstrap/Form";
import Row from "react-bootstrap/Row";
import EmptyState from "../components/EmptyState";
import ErrorAlert from "../components/ErrorAlert";
import EventCard from "../components/EventCard";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import Pagination from "../components/Pagination";
import { useAsync } from "../hooks/useAsync";
import { searchEvents } from "../services/eventService";
import { getOptions } from "../services/metaService";

const EMPTY = { q: "", city: [], date_from: "", date_to: "", major: "", include_past: false };

export function buildEventParams(f, page) {
  const p = { page, page_size: 10 };
  if (f.q.trim()) p.q = f.q.trim();
  if (f.city.length) p.city = f.city;
  if (f.date_from) p.date_from = f.date_from;
  if (f.date_to) p.date_to = f.date_to;
  if (f.major) p.major = f.major;
  if (f.include_past) p.include_past = true;
  return p;
}

const toggle = (list, v) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

export default function EventSearch() {
  const [draft, setDraft] = useState(EMPTY);
  const [applied, setApplied] = useState(EMPTY);
  const [page, setPage] = useState(1);
  const options = useAsync(getOptions, []);
  const results = useAsync(() => searchEvents(buildEventParams(applied, page)), [JSON.stringify(applied), page]);
  const set = (field) => (e) => setDraft({ ...draft, [field]: e.target.value });
  const dateProblem = draft.date_from && draft.date_to && draft.date_from > draft.date_to;
  const filtered = JSON.stringify(applied) !== JSON.stringify(EMPTY);

  function submit(e) {
    e.preventDefault();
    if (dateProblem) return;
    setPage(1);
    setApplied(draft);
  }
  function clear() {
    setDraft(EMPTY);
    setApplied(EMPTY);
    setPage(1);
  }

  return (
    <>
      <PageHeader title="Events" subtitle="Career fairs, talks and workshops, earliest first." />
      <Row>
        <Col lg={4} xl={3} className="mb-4">
          <Card>
            <Card.Body>
              <Form onSubmit={submit} aria-label="Event filters">
                <Form.Group className="mb-3" controlId="e-q">
                  <Form.Label>Event name</Form.Label>
                  <Form.Control value={draft.q} onChange={set("q")} maxLength={100} placeholder="e.g. career fair" />
                </Form.Group>
                <fieldset className="mb-3">
                  <legend className="form-label fs-6">City</legend>
                  {(options.data?.cities ?? []).map((c) => (
                    <Form.Check key={c} id={`ecity-${c}`} label={c} checked={draft.city.includes(c)}
                      onChange={() => setDraft({ ...draft, city: toggle(draft.city, c) })} />
                  ))}
                </fieldset>
                <Form.Group className="mb-3" controlId="e-major">
                  <Form.Label>Open to major</Form.Label>
                  <Form.Select value={draft.major} onChange={set("major")}>
                    <option value="">Any major</option>
                    {(options.data?.majors ?? []).map((m) => <option key={m} value={m}>{m}</option>)}
                  </Form.Select>
                </Form.Group>
                <Form.Group className="mb-3" controlId="e-from">
                  <Form.Label>From</Form.Label>
                  <Form.Control type="date" value={draft.date_from} onChange={set("date_from")} />
                </Form.Group>
                <Form.Group className="mb-3" controlId="e-to">
                  <Form.Label>To</Form.Label>
                  <Form.Control type="date" value={draft.date_to} onChange={set("date_to")} isInvalid={!!dateProblem} />
                  <Form.Control.Feedback type="invalid">"To" must not be before "From".</Form.Control.Feedback>
                </Form.Group>
                <Form.Check id="e-past" className="mb-3" label="Include past events" checked={draft.include_past}
                  onChange={(e) => setDraft({ ...draft, include_past: e.target.checked })} />
                <div className="d-flex gap-2">
                  <Button type="submit">Search</Button>
                  <Button type="button" variant="outline-secondary" onClick={clear}>Clear</Button>
                </div>
              </Form>
            </Card.Body>
          </Card>
        </Col>
        <Col lg={8} xl={9}>
          <ErrorAlert message={options.error} onRetry={options.reload} />
          {results.loading && <Loading label="Searching events…" />}
          <ErrorAlert message={results.error} onRetry={results.reload} />
          {results.data && (
            <>
              <p className="text-muted" data-testid="result-count">
                {results.data.total} {results.data.total === 1 ? "event" : "events"} found
              </p>
              {results.data.items.length === 0 ? (
                <EmptyState title="No events match your search"
                  action={filtered ? <Button variant="outline-primary" onClick={clear}>Clear filters</Button> : null}>
                  Try a wider date range or fewer filters.
                </EmptyState>
              ) : (
                results.data.items.map((ev) => <EventCard key={ev.id} event={ev} />)
              )}
              <Pagination page={results.data.page} totalPages={results.data.total_pages} onChange={setPage} />
            </>
          )}
        </Col>
      </Row>
    </>
  );
}
