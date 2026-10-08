import { useState } from "react";
import Alert from "react-bootstrap/Alert";
import Card from "react-bootstrap/Card";
import { Link, useParams } from "react-router-dom";
import ErrorAlert from "../components/ErrorAlert";
import JobForm from "../components/JobForm";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import { useAsync } from "../hooks/useAsync";
import { getJob } from "../services/jobService";
import { getOptions } from "../services/metaService";
import { updateJob } from "../services/postingService";

export default function EditJob() {
  const { id } = useParams();
  const [saved, setSaved] = useState(false);
  const { data, loading, error, reload } = useAsync(() => Promise.all([getJob(id), getOptions()]), [id]);
  return (
    <>
      <Link to="/company/jobs" className="d-inline-block mb-3">← My job postings</Link>
      <PageHeader title="Edit job" subtitle="Changes show to students straight away." />
      {loading && <Loading label="Loading job…" />}
      <ErrorAlert message={error} onRetry={reload} />
      {data && (
        <Card><Card.Body>
          {saved && <Alert variant="success" role="status">Job saved. <Link to={`/jobs/${id}`}>View it</Link></Alert>}
          <JobForm job={data[0]} options={data[1]} submitLabel="Save changes"
            onSubmit={async (payload) => {
              await updateJob(id, payload);
              setSaved(true);
              window.scrollTo?.(0, 0);
            }} />
        </Card.Body></Card>
      )}
    </>
  );
}
