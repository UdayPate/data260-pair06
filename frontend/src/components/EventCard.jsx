import Badge from "react-bootstrap/Badge";
import Card from "react-bootstrap/Card";
import { Link } from "react-router-dom";
import { formatDateTime } from "../utils/format";

// One row in an event list.
export default function EventCard({ event }) {
  return (
    <Card className="mb-3" data-testid="event-card">
      <Card.Body>
        <div className="d-flex justify-content-between flex-wrap gap-2">
          <div>
            <Card.Title as="h2" className="h5 mb-1">
              <Link to={`/events/${event.id}`}>{event.name}</Link>
            </Card.Title>
            <div className="text-muted">{event.company.name} · {event.city}</div>
            <div className="text-muted small">{event.location}</div>
          </div>
          <div className="text-md-end">
            <div className="fw-semibold">{formatDateTime(event.event_datetime)}</div>
            <div className="text-muted small">{event.registration_count} registered</div>
          </div>
        </div>
        <div className="mt-2 d-flex flex-wrap gap-1">
          {event.registered && <Badge bg="success">Registered</Badge>}
          {event.is_past && <Badge bg="secondary">Past</Badge>}
          {event.eligible === false && <Badge bg="warning" text="dark">Not open to your major</Badge>}
          {event.eligible_majors.map((m) => (
            <Badge key={m} bg="light" text="dark" className="border">{m}</Badge>
          ))}
        </div>
      </Card.Body>
    </Card>
  );
}
