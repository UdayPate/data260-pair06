import { useState } from "react";
import Card from "react-bootstrap/Card";
import Nav from "react-bootstrap/Nav";
import { Link } from "react-router-dom";
import EmptyState from "../components/EmptyState";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import Pagination from "../components/Pagination";
import StatusBadge from "../components/StatusBadge";
import { useAsync } from "../hooks/useAsync";
import { getMyApplications } from "../services/jobService";
import { categoryLabel, formatDate } from "../utils/format";

const TABS = ["All", "Pending", "Reviewed", "Declined"];

export default function MyApplications() {
  const [tab, setTab] = useState("All");
  const [page, setPage] = useState(1);
  const { data, loading, error, reload } = useAsync(
    () => getMyApplications({ page, page_size: 10, ...(tab !== "All" ? { status: tab } : {}) }),
    [tab, page]
  );

  return (
    <>
      <PageHeader title="My applications" subtitle="Everything you have applied to, with its current status." />
      <Nav variant="pills" className="mb-3" activeKey={tab} onSelect={(k) => { setTab(k); setPage(1); }}>
        {TABS.map((t) => (
          <Nav.Item key={t}>
            <Nav.Link eventKey={t}>{t}</Nav.Link>
          </Nav.Item>
        ))}
      </Nav>

      {loading && <Loading label="Loading applications…" />}
      <ErrorAlert message={error} onRetry={reload} />
      {data && (data.items.length === 0 ? (
        <EmptyState
          title={tab === "All" ? "No applications yet" : `No ${tab.toLowerCase()} applications`}
          action={tab === "All" ? <Link to="/jobs" className="btn btn-primary">Find jobs</Link> : null}
        >
          {tab === "All" ? "When you apply to a job it will show up here." : "Nothing with this status."}
        </EmptyState>
      ) : (
        <>
          {data.items.map((a) => (
            <Card className="mb-3" key={a.id} data-testid="application-card">
              <Card.Body className="d-flex justify-content-between flex-wrap gap-2">
                <div>
                  <Card.Title as="h2" className="h5 mb-1">
                    <Link to={`/jobs/${a.job.id}`}>{a.job.title}</Link>
                  </Card.Title>
                  <div className="text-muted">
                    {a.job.company_name} · {a.job.city}
                    {a.job.is_remote ? " · Remote OK" : ""} · {categoryLabel(a.job.category)}
                  </div>
                  <div className="text-muted small">Applied {formatDate(a.applied_at)}</div>
                </div>
                <div className="align-self-center"><StatusBadge status={a.status} /></div>
              </Card.Body>
            </Card>
          ))}
          <Pagination page={data.page} totalPages={data.total_pages} onChange={setPage} />
        </>
      ))}
    </>
  );
}
