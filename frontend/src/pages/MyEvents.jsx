import { useState } from "react";
import Form from "react-bootstrap/Form";
import { Link } from "react-router-dom";
import EmptyState from "../components/EmptyState";
import ErrorAlert from "../components/ErrorAlert";
import EventCard from "../components/EventCard";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import Pagination from "../components/Pagination";
import { useAsync } from "../hooks/useAsync";
import { getRegisteredEvents } from "../services/eventService";

export default function MyEvents() {
  const [includePast, setIncludePast] = useState(false);
  const [page, setPage] = useState(1);
  const { data, loading, error, reload } = useAsync(
    () => getRegisteredEvents({ page, page_size: 10, include_past: includePast }), [page, includePast]);

  return (
    <>
      <PageHeader title="My events" subtitle="Events you have registered for." />
      <Form.Check id="my-past" className="mb-3" label="Show past events" checked={includePast}
        onChange={(e) => { setIncludePast(e.target.checked); setPage(1); }} />
      {loading && <Loading label="Loading your events…" />}
      <ErrorAlert message={error} onRetry={reload} />
      {data && (data.items.length === 0 ? (
        <EmptyState title="No events yet" action={<Link to="/events" className="btn btn-primary">Browse events</Link>}>
          When you register for an event it will show up here.
        </EmptyState>
      ) : (
        <>
          {data.items.map((ev) => <EventCard key={ev.id} event={ev} />)}
          <Pagination page={data.page} totalPages={data.total_pages} onChange={setPage} />
        </>
      ))}
    </>
  );
}
