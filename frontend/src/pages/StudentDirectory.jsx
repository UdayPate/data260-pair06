import { useState } from "react";
import Button from "react-bootstrap/Button";
import Card from "react-bootstrap/Card";
import Col from "react-bootstrap/Col";
import Form from "react-bootstrap/Form";
import Row from "react-bootstrap/Row";
import EmptyState from "../components/EmptyState";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import Pagination from "../components/Pagination";
import StudentCard from "../components/StudentCard";
import { useAsync } from "../hooks/useAsync";
import { getOptions } from "../services/metaService";
import { searchStudents } from "../services/studentService";

const EMPTY = { q: "", college: "", major: "", skills: "", skills_match: "any" };

export function buildStudentParams(f, page) {
  const p = { page, page_size: 10 };
  if (f.q.trim()) p.q = f.q.trim();
  if (f.college.trim()) p.college = f.college.trim();
  if (f.major) p.major = [f.major];
  const skills = f.skills.split(",").map((s) => s.trim()).filter(Boolean);
  if (skills.length) {
    p.skills = skills;
    p.skills_match = f.skills_match;
  }
  return p;
}

// Used by students (peer view) now, and by companies in the next step.
export default function StudentDirectory() {
  const [draft, setDraft] = useState(EMPTY);
  const [applied, setApplied] = useState(EMPTY);
  const [page, setPage] = useState(1);
  const options = useAsync(getOptions, []);
  const results = useAsync(() => searchStudents(buildStudentParams(applied, page)), [JSON.stringify(applied), page]);
  const set = (field) => (e) => setDraft({ ...draft, [field]: e.target.value });
  const filtered = JSON.stringify(applied) !== JSON.stringify(EMPTY);

  function clear() {
    setDraft(EMPTY);
    setApplied(EMPTY);
    setPage(1);
  }

  return (
    <>
      <PageHeader title="Students" subtitle="Find classmates by name, college, major or skills." />
      <Row>
        <Col lg={4} xl={3} className="mb-4">
          <Card>
            <Card.Body>
              <Form onSubmit={(e) => { e.preventDefault(); setPage(1); setApplied(draft); }} aria-label="Student filters">
                <Form.Group className="mb-3" controlId="s-q">
                  <Form.Label>Name</Form.Label>
                  <Form.Control value={draft.q} onChange={set("q")} maxLength={100} placeholder="e.g. Ada" />
                </Form.Group>
                <Form.Group className="mb-3" controlId="s-college">
                  <Form.Label>College</Form.Label>
                  <Form.Control value={draft.college} onChange={set("college")} maxLength={150} placeholder="e.g. San Jose State" />
                </Form.Group>
                <Form.Group className="mb-3" controlId="s-major">
                  <Form.Label>Major</Form.Label>
                  <Form.Select value={draft.major} onChange={set("major")}>
                    <option value="">Any major</option>
                    {(options.data?.majors ?? []).map((m) => <option key={m} value={m}>{m}</option>)}
                  </Form.Select>
                </Form.Group>
                <Form.Group className="mb-3" controlId="s-skills">
                  <Form.Label>Skills (comma separated)</Form.Label>
                  <Form.Control value={draft.skills} onChange={set("skills")} placeholder="Python, SQL" />
                  <Form.Select aria-label="Skills match" className="mt-2" value={draft.skills_match} onChange={set("skills_match")}>
                    <option value="any">Match any skill</option>
                    <option value="all">Match all skills</option>
                  </Form.Select>
                </Form.Group>
                <div className="d-flex gap-2">
                  <Button type="submit">Search</Button>
                  <Button type="button" variant="outline-secondary" onClick={clear}>Clear</Button>
                </div>
              </Form>
            </Card.Body>
          </Card>
        </Col>
        <Col lg={8} xl={9}>
          <ErrorAlert message={options.error} onRetry={options.reload} />
          {results.loading && <Loading label="Searching students…" />}
          <ErrorAlert message={results.error} onRetry={results.reload} />
          {results.data && (
            <>
              <p className="text-muted" data-testid="result-count">
                {results.data.total} {results.data.total === 1 ? "student" : "students"} found
              </p>
              {results.data.items.length === 0 ? (
                <EmptyState title="No students match your search"
                  action={filtered ? <Button variant="outline-primary" onClick={clear}>Clear filters</Button> : null}>
                  Try fewer filters or a different spelling.
                </EmptyState>
              ) : (
                results.data.items.map((s) => <StudentCard key={s.id} student={s} />)
              )}
              <Pagination page={results.data.page} totalPages={results.data.total_pages} onChange={setPage} />
            </>
          )}
        </Col>
      </Row>
    </>
  );
}
