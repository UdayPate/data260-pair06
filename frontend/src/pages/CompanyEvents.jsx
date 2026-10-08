import { useState } from "react";
import Badge from "react-bootstrap/Badge";
import Card from "react-bootstrap/Card";
import Form from "react-bootstrap/Form";
import { Link } from "react-router-dom";
import EmptyState from "../components/EmptyState";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import Pagination from "../components/Pagination";
import { useAsync } from "../hooks/useAsync";
import { getMyEvents } from "../services/companyService";
import { formatDateTime } from "../utils/format";

export default function CompanyEvents() {
  const [showPast, setShowPast] = useState(true);
  const [page, setPage] = useState(1);
  const { data, loading, error, reload } = useAsync(
    () => getMyEvents({ page, page_size: 10, include_past: showPast }), [page, showPast]);

  return (
    <>
      <PageHeader title="My events" subtitle="Events you host, and who signed up."
        actions={<Link to="/company/events/new" className="btn btn-primary">Post an event</Link>} />
      <Form.Check id="past" className="mb-3" label="Show past events" checked={showPast}
        onChange={(e) => { setShowPast(e.target.checked); setPage(1); }} />
      {loading && <Loading label="Loading your events…" />}
      <ErrorAlert message={error} onRetry={reload} />
      {data && (data.items.length === 0 ? (
        <EmptyState title="No events yet" action={<Link to="/company/events/new" className="btn btn-primary">Post your first event</Link>}>
          Students can register as soon as you post.
        </EmptyState>
      ) : (
        <>
          {data.items.map((ev) => (
            <Card className="mb-3" key={ev.id} data-testid="company-event-card">
              <Card.Body className="d-flex justify-content-between flex-wrap gap-3">
                <div>
                  <Card.Title as="h2" className="h5 mb-1"><Link to={`/events/${ev.id}`}>{ev.name}</Link></Card.Title>
                  <div className="text-muted">{formatDateTime(ev.event_datetime)} · {ev.location}, {ev.city}</div>
                  <div className="mt-2 d-flex flex-wrap gap-1">
                    {ev.is_past && <Badge bg="secondary">Past</Badge>}
                    {ev.eligible_majors.map((m) => <Badge key={m} bg="light" text="dark" className="border">{m}</Badge>)}
                  </div>
                </div>
                <div className="text-md-end">
                  <div className="fs-4 fw-bold" aria-label={`${ev.registration_count} registered`}>{ev.registration_count}</div>
                  <div className="text-muted small mb-2">registered</div>
                  <Link to={`/company/events/${ev.id}/registrations`} className="btn btn-sm btn-primary me-2">Registered students</Link>
                  <Link to={`/company/events/${ev.id}/edit`} className="btn btn-sm btn-outline-secondary">Edit</Link>
                </div>
              </Card.Body>
            </Card>
          ))}
          <Pagination page={data.page} totalPages={data.total_pages} onChange={setPage} />
        </>
      ))}
    </>
  );
}
