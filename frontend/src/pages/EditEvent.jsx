import { useState } from "react";
import Alert from "react-bootstrap/Alert";
import Card from "react-bootstrap/Card";
import { Link, useParams } from "react-router-dom";
import ErrorAlert from "../components/ErrorAlert";
import EventForm from "../components/EventForm";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import { useAsync } from "../hooks/useAsync";
import { getEvent } from "../services/eventService";
import { updateEvent } from "../services/companyService";
import { getOptions } from "../services/metaService";

export default function EditEvent() {
  const { id } = useParams();
  const [saved, setSaved] = useState(false);
  const { data, loading, error, reload } = useAsync(() => Promise.all([getEvent(id), getOptions()]), [id]);
  return (
    <>
      <Link to="/company/events" className="d-inline-block mb-3">← My events</Link>
      <PageHeader title="Edit event" subtitle="Students who already registered stay registered." />
      {loading && <Loading label="Loading event…" />}
      <ErrorAlert message={error} onRetry={reload} />
      {data && (
        <Card><Card.Body>
          {saved && <Alert variant="success" role="status">Event saved. <Link to={`/events/${id}`}>View it</Link></Alert>}
          <EventForm event={data[0]} options={data[1]} submitLabel="Save changes"
            onSubmit={async (payload) => { await updateEvent(id, payload); setSaved(true); window.scrollTo?.(0, 0); }} />
        </Card.Body></Card>
      )}
    </>
  );
}
