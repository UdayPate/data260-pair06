import Card from "react-bootstrap/Card";
import { Link, useNavigate } from "react-router-dom";
import ErrorAlert from "../components/ErrorAlert";
import JobForm from "../components/JobForm";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import { useAsync } from "../hooks/useAsync";
import { getOptions } from "../services/metaService";
import { createJob } from "../services/postingService";

export default function PostJob() {
  const navigate = useNavigate();
  const options = useAsync(getOptions, []);
  return (
    <>
      <Link to="/company/jobs" className="d-inline-block mb-3">← My job postings</Link>
      <PageHeader title="Post a job" subtitle="Students will see it as soon as you save." />
      {options.loading && <Loading label="Loading…" />}
      <ErrorAlert message={options.error} onRetry={options.reload} />
      {options.data && (
        <Card><Card.Body>
          <JobForm options={options.data} submitLabel="Post job"
            onSubmit={async (payload) => {
              const job = await createJob(payload);
              navigate(`/jobs/${job.id}`);
            }} />
        </Card.Body></Card>
      )}
    </>
  );
}
