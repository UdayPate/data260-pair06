import { useState } from "react";
import Badge from "react-bootstrap/Badge";
import Card from "react-bootstrap/Card";
import { Link, useParams } from "react-router-dom";
import Avatar from "../components/Avatar";
import EmptyState from "../components/EmptyState";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import Pagination from "../components/Pagination";
import { useAsync } from "../hooks/useAsync";
import { getEvent } from "../services/eventService";
import { getEventRegistrations } from "../services/companyService";
import { formatDateTime } from "../utils/format";

export default function EventRegistrations() {
  const { id } = useParams();
  const [page, setPage] = useState(1);
  const event = useAsync(() => getEvent(id), [id]);
  const { data, loading, error, reload } = useAsync(() => getEventRegistrations(id, { page, page_size: 10 }), [id, page]);

  return (
    <>
      <Link to="/company/events" className="d-inline-block mb-3">← My events</Link>
      <PageHeader title={event.data ? `Registered: ${event.data.name}` : "Registered students"}
        subtitle={data ? `${data.total} ${data.total === 1 ? "student" : "students"}` : undefined} />
      {loading && <Loading label="Loading registrations…" />}
      <ErrorAlert message={error} onRetry={reload} />
      {data && (data.items.length === 0 ? (
        <EmptyState title="Nobody has registered yet">Students will appear here when they sign up.</EmptyState>
      ) : (
        <>
          {data.items.map(({ student: s, registered_at }) => (
            <Card className="mb-3" key={s.id} data-testid="registration-card">
              <Card.Body className="d-flex gap-3">
                <Avatar name={s.name} src={s.profile_pic_url} size={52} decorative />
                <div>
                  <Card.Title as="h2" className="h5 mb-1"><Link to={`/students/${s.id}`}>{s.name}</Link></Card.Title>
                  <div className="text-muted">{s.college}{s.major ? ` · ${s.major}` : ""} · <a href={`mailto:${s.email}`}>{s.email}</a></div>
                  <div className="text-muted small">Registered {formatDateTime(registered_at)}</div>
                  <div className="mt-2 d-flex flex-wrap gap-1">
                    {s.skills.map((k) => <Badge key={k} bg="light" text="dark" className="border">{k}</Badge>)}
                  </div>
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
