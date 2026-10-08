import { useState } from "react";
import Button from "react-bootstrap/Button";
import Card from "react-bootstrap/Card";
import Col from "react-bootstrap/Col";
import Form from "react-bootstrap/Form";
import Row from "react-bootstrap/Row";
import EmptyState from "../components/EmptyState";
import ErrorAlert from "../components/ErrorAlert";
import JobCard from "../components/JobCard";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import Pagination from "../components/Pagination";
import { useAsync } from "../hooks/useAsync";
import { searchJobs } from "../services/jobService";
import { getOptions } from "../services/metaService";
import { categoryLabel } from "../utils/format";

const EMPTY_FILTERS = {
  q: "",
  category: [],
  city: [],
  is_remote: false,
  min_salary: "",
  salary_unit: "hourly",
  skills: "",          // typed as "Python, SQL"
  skills_match: "any",
  sort: "newest",
  include_expired: false,
};

// Turns what is typed in the form into the query the server expects. Empty boxes are left out.
export function buildParams(filters, page) {
  const params = { page, page_size: 10, sort: filters.sort };
  if (filters.q.trim()) params.q = filters.q.trim();
  if (filters.category.length) params.category = filters.category;
  if (filters.city.length) params.city = filters.city;
  if (filters.is_remote) params.is_remote = true;
  if (filters.min_salary !== "" && Number(filters.min_salary) >= 0) {
    params.min_salary = Number(filters.min_salary);
    params.salary_unit = filters.salary_unit;   // the server needs the unit together with the amount
  }
  const skills = filters.skills.split(",").map((s) => s.trim()).filter(Boolean);
  if (skills.length) {
    params.skills = skills;
    params.skills_match = filters.skills_match;
  }
  if (filters.include_expired) params.include_expired = true;
  return params;
}

const toggle = (list, value) => (list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);

export default function JobSearch() {
  const [draft, setDraft] = useState(EMPTY_FILTERS);     // what is typed right now
  const [applied, setApplied] = useState(EMPTY_FILTERS); // what the results were fetched with
  const [page, setPage] = useState(1);
  const options = useAsync(getOptions, []);
  const results = useAsync(() => searchJobs(buildParams(applied, page)), [JSON.stringify(applied), page]);

  const set = (field) => (e) => setDraft({ ...draft, [field]: e.target.value });

  function submit(e) {
    e.preventDefault();
    setPage(1);
    setApplied(draft);
  }

  function clear() {
    setDraft(EMPTY_FILTERS);
    setApplied(EMPTY_FILTERS);
    setPage(1);
  }

  const categories = options.data?.job_categories ?? [];
  const cities = options.data?.cities ?? [];

  return (
    <>
      <PageHeader title="Find jobs" subtitle="Search by title or company, then narrow it down." />
      <Row>
        <Col lg={4} xl={3} className="mb-4">
          <Card>
            <Card.Body>
              <Form onSubmit={submit} aria-label="Job filters">
                <Form.Group className="mb-3" controlId="f-q">
                  <Form.Label>Title or company</Form.Label>
                  <Form.Control value={draft.q} onChange={set("q")} maxLength={100} placeholder="e.g. data analyst" />
                </Form.Group>

                <fieldset className="mb-3">
                  <legend className="form-label fs-6">Type of job</legend>
                  {categories.map((c) => (
                    <Form.Check
                      key={c}
                      id={`cat-${c}`}
                      label={categoryLabel(c)}
                      checked={draft.category.includes(c)}
                      onChange={() => setDraft({ ...draft, category: toggle(draft.category, c) })}
                    />
                  ))}
                </fieldset>

                <fieldset className="mb-3">
                  <legend className="form-label fs-6">City</legend>
                  {cities.map((c) => (
                    <Form.Check
                      key={c}
                      id={`city-${c}`}
                      label={c}
                      checked={draft.city.includes(c)}
                      onChange={() => setDraft({ ...draft, city: toggle(draft.city, c) })}
                    />
                  ))}
                  <Form.Check
                    id="f-remote"
                    className="mt-2"
                    label="Remote only"
                    checked={draft.is_remote}
                    onChange={(e) => setDraft({ ...draft, is_remote: e.target.checked })}
                  />
                </fieldset>

                <Form.Label htmlFor="f-salary">Minimum pay</Form.Label>
                <div className="d-flex gap-2 mb-3">
                  <Form.Control
                    id="f-salary"
                    type="number"
                    min="0"
                    value={draft.min_salary}
                    onChange={set("min_salary")}
                    placeholder="e.g. 25"
                  />
                  <Form.Select aria-label="Pay unit" value={draft.salary_unit} onChange={set("salary_unit")}>
                    <option value="hourly">per hour</option>
                    <option value="yearly">per year</option>
                  </Form.Select>
                </div>

                <Form.Group className="mb-3" controlId="f-skills">
                  <Form.Label>Skills (comma separated)</Form.Label>
                  <Form.Control value={draft.skills} onChange={set("skills")} placeholder="Python, SQL" />
                  <Form.Select
                    aria-label="Skills match"
                    className="mt-2"
                    value={draft.skills_match}
                    onChange={set("skills_match")}
                  >
                    <option value="any">Match any skill</option>
                    <option value="all">Match all skills</option>
                  </Form.Select>
                </Form.Group>

                <Form.Group className="mb-3" controlId="f-sort">
                  <Form.Label>Sort by</Form.Label>
                  <Form.Select value={draft.sort} onChange={set("sort")}>
                    <option value="newest">Newest first</option>
                    <option value="deadline">Closing soonest</option>
                    <option value="salary">Highest pay</option>
                  </Form.Select>
                </Form.Group>

                <Form.Check
                  id="f-expired"
                  className="mb-3"
                  label="Include closed jobs"
                  checked={draft.include_expired}
                  onChange={(e) => setDraft({ ...draft, include_expired: e.target.checked })}
                />

                <div className="d-flex gap-2">
                  <Button type="submit">Search</Button>
                  <Button type="button" variant="outline-secondary" onClick={clear}>
                    Clear
                  </Button>
                </div>
              </Form>
            </Card.Body>
          </Card>
        </Col>

        <Col lg={8} xl={9}>
          <ErrorAlert message={options.error} onRetry={options.reload} />
          {results.loading && <Loading label="Searching jobs…" />}
          <ErrorAlert message={results.error} onRetry={results.reload} />
          {results.data && (
            <>
              <p className="text-muted" data-testid="result-count">
                {results.data.total} {results.data.total === 1 ? "job" : "jobs"} found
              </p>
              {results.data.items.length === 0 ? (
                <EmptyState
                  title="No jobs match your search"
                  action={
                    JSON.stringify(applied) !== JSON.stringify(EMPTY_FILTERS) ? (
                      <Button variant="outline-primary" onClick={clear}>Clear filters</Button>
                    ) : null
                  }
                >
                  Try fewer filters or different words.
                </EmptyState>
              ) : (
                results.data.items.map((job) => <JobCard key={job.id} job={job} />)
              )}
              <Pagination page={results.data.page} totalPages={results.data.total_pages} onChange={setPage} />
            </>
          )}
        </Col>
      </Row>
    </>
  );
}
