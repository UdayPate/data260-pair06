import Card from "react-bootstrap/Card";
import Col from "react-bootstrap/Col";
import Row from "react-bootstrap/Row";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import { useAuth } from "../context/AuthContext";
import { useAsync } from "../hooks/useAsync";
import { loadCompanyStats, loadStudentStats } from "../services/dashboardService";

function StatCard({ id, value, label }) {
  return (
    <Col md={4} className="mb-3">
      <Card className="h-100 text-center" data-testid={`stat-${id}`}>
        <Card.Body>
          <div className="display-5 fw-semibold">{value}</div>
          <Card.Text className="text-muted mb-0">{label}</Card.Text>
        </Card.Body>
      </Card>
    </Col>
  );
}

export default function Home() {
  const { user } = useAuth();
  const isStudent = user.role === "student";
  const { data, loading, error, reload } = useAsync(
    () => (isStudent ? loadStudentStats() : loadCompanyStats()),
    [isStudent]
  );

  return (
    <>
      <h1 className="h3">Welcome back, {user.name}</h1>
      <p className="text-muted mb-4">{isStudent ? "Student dashboard" : "Company dashboard"}</p>

      {loading && <Loading label="Loading your dashboard…" />}
      <ErrorAlert message={error} onRetry={reload} />

      {data && (
        <Row>
          {isStudent ? (
            <>
              <StatCard id="applications" value={data.applications} label="Job applications" />
              <StatCard id="events" value={data.events} label="Upcoming events registered" />
              <Col md={4} className="mb-3">
                <Card className="h-100 border-primary" data-testid="assistant-card">
                  <Card.Body>
                    <Card.Title>AI Assistant</Card.Title>
                    <Card.Text className="text-muted mb-0">
                      Ask for jobs and events that fit you. The chat window arrives in a later step.
                    </Card.Text>
                  </Card.Body>
                </Card>
              </Col>
            </>
          ) : (
            <>
              <StatCard id="jobs" value={data.jobs} label="Job postings" />
              <StatCard id="events" value={data.events} label="Events posted" />
            </>
          )}
        </Row>
      )}
    </>
  );
}
