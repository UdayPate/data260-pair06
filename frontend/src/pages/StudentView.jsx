import Badge from "react-bootstrap/Badge";
import Card from "react-bootstrap/Card";
import { Link, useParams } from "react-router-dom";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import { useAsync } from "../hooks/useAsync";
import { getStudent } from "../services/studentService";
import { formatRange } from "../utils/format";

// Another student's profile. Fields the server does not send for your role (email, phone, GPA...)
// are simply absent, so they are not shown.
export default function StudentView() {
  const { id } = useParams();
  const { data: s, loading, error, reload } = useAsync(() => getStudent(id), [id]);
  if (loading && !s) return <Loading label="Loading profile…" />;
  if (error) return <ErrorAlert message={error} onRetry={reload} />;
  if (!s) return null;

  return (
    <>
      <Link to="/students" className="d-inline-block mb-3">← Back to students</Link>
      <Card>
        <Card.Body>
          <div className="d-flex gap-3 align-items-center mb-3">
            {s.profile_pic_url && (
              <img src={s.profile_pic_url} alt={`${s.name}`} width="72" height="72" className="rounded-circle" style={{ objectFit: "cover" }} />
            )}
            <div>
              <h1 className="h3 mb-1">{s.name}</h1>
              <div className="text-muted">
                {s.college}
                {s.major ? ` · ${s.major}` : ""}
                {s.degree ? ` (${s.degree})` : ""}
                {s.graduation_year ? ` · Class of ${s.graduation_year}` : ""}
              </div>
              {s.email && <div className="small">{s.email}{s.phone ? ` · ${s.phone}` : ""}</div>}
            </div>
          </div>
          {s.career_objective && (<><h2 className="h6">Career objective</h2><p>{s.career_objective}</p></>)}
          <h2 className="h6">Skills</h2>
          <div className="d-flex flex-wrap gap-1 mb-3">
            {s.skills.length === 0 ? <span className="text-muted">None listed</span> :
              s.skills.map((k) => <Badge key={k} bg="light" text="dark" className="border">{k}</Badge>)}
          </div>
          <h2 className="h6">Experience</h2>
          {s.experience.length === 0 ? <p className="text-muted">None listed</p> : (
            <ul className="list-unstyled mb-0">
              {s.experience.map((x) => (
                <li key={x.id} className="mb-2">
                  <strong>{x.title}</strong> · {x.company}
                  <div className="text-muted small">{formatRange(x.start_date, x.end_date)}</div>
                  {x.description && <div className="small">{x.description}</div>}
                </li>
              ))}
            </ul>
          )}
        </Card.Body>
      </Card>
    </>
  );
}
