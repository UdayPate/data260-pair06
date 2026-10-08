import { useState } from "react";
import Badge from "react-bootstrap/Badge";
import Card from "react-bootstrap/Card";
import Nav from "react-bootstrap/Nav";
import { Link, useParams } from "react-router-dom";
import Avatar from "../components/Avatar";
import EmptyState from "../components/EmptyState";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import Pagination from "../components/Pagination";
import StatusBadge from "../components/StatusBadge";
import { useAsync } from "../hooks/useAsync";
import { getJob } from "../services/jobService";
import { getApplicants } from "../services/postingService";
import { formatDate } from "../utils/format";

const TABS = ["All", "Pending", "Reviewed", "Declined"];

export default function Applicants() {
  const { id } = useParams();
  const [tab, setTab] = useState("All");
  const [page, setPage] = useState(1);
  const job = useAsync(() => getJob(id), [id]);
  const { data, loading, error, reload } = useAsync(
    () => getApplicants(id, { page, page_size: 10, ...(tab !== "All" ? { status: tab } : {}) }), [id, tab, page]);

  return (
    <>
      <Link to="/company/jobs" className="d-inline-block mb-3">← My job postings</Link>
      <PageHeader title={job.data ? `Applicants: ${job.data.title}` : "Applicants"}
        subtitle={data ? `${data.total} ${data.total === 1 ? "applicant" : "applicants"}${tab !== "All" ? ` (${tab.toLowerCase()})` : ""}` : undefined} />
      <Nav variant="pills" className="mb-3" activeKey={tab} onSelect={(k) => { setTab(k); setPage(1); }}>
        {TABS.map((t) => <Nav.Item key={t}><Nav.Link eventKey={t}>{t}</Nav.Link></Nav.Item>)}
      </Nav>
      {loading && <Loading label="Loading applicants…" />}
      <ErrorAlert message={error} onRetry={reload} />
      {data && (data.items.length === 0 ? (
        <EmptyState title={tab === "All" ? "No applicants yet" : `No ${tab.toLowerCase()} applicants`}>
          {tab === "All" ? "They will appear here when students apply." : "Nothing with this status."}
        </EmptyState>
      ) : (
        <>
          {data.items.map((a) => (
            <Card className="mb-3" key={a.id} data-testid="applicant-card">
              <Card.Body className="d-flex gap-3 justify-content-between flex-wrap">
                <div className="d-flex gap-3">
                  <Avatar name={a.student.name} url={a.student.profile_pic_url} size={52} />
                  <div>
                    <Card.Title as="h2" className="h5 mb-1"><Link to={`/company/applications/${a.id}`}>{a.student.name}</Link></Card.Title>
                    <div className="text-muted">
                      {a.student.college}{a.student.major ? ` · ${a.student.major}` : ""}
                      {a.student.cgpa != null ? ` · GPA ${a.student.cgpa}` : ""}
                    </div>
                    <div className="text-muted small">Applied {formatDate(a.applied_at)}</div>
                    <div className="mt-2 d-flex flex-wrap gap-1">
                      {a.student.skills.map((s) => <Badge key={s} bg="light" text="dark" className="border">{s}</Badge>)}
                    </div>
                  </div>
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
