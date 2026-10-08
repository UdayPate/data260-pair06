import Card from "react-bootstrap/Card";
import { Link, useNavigate } from "react-router-dom";
import ErrorAlert from "../components/ErrorAlert";
import EventForm from "../components/EventForm";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import { useAsync } from "../hooks/useAsync";
import { createEvent } from "../services/companyService";
import { getOptions } from "../services/metaService";

export default function PostEvent() {
  const navigate = useNavigate();
  const options = useAsync(getOptions, []);
  return (
    <>
      <Link to="/company/events" className="d-inline-block mb-3">← My events</Link>
      <PageHeader title="Post an event" subtitle="Students from the majors you choose can register." />
      {options.loading && <Loading label="Loading…" />}
      <ErrorAlert message={options.error} onRetry={options.reload} />
      {options.data && (
        <Card><Card.Body>
          <EventForm options={options.data} submitLabel="Post event"
            onSubmit={async (payload) => { const ev = await createEvent(payload); navigate(`/events/${ev.id}`); }} />
        </Card.Body></Card>
      )}
    </>
  );
}
