import Card from "react-bootstrap/Card";
import Col from "react-bootstrap/Col";
import Row from "react-bootstrap/Row";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import StatCard from "../components/StatCard";
import { useAuth } from "../context/AuthContext";
import { useAsync } from "../hooks/useAsync";
import { loadCompanyStats, loadStudentStats } from "../services/dashboardService";

export default function Home() {
  const { user } = useAuth();
  const isStudent = user.role === "student";
  const { data, loading, error, reload } = useAsync(
    () => (isStudent ? loadStudentStats() : loadCompanyStats()),
    [isStudent]
  );

  return (
    <>
      <PageHeader
        title={`Welcome back, ${user.name}`}
        subtitle={isStudent ? "Student dashboard" : "Company dashboard"}
      />

      {loading && <Loading label="Loading your dashboard…" />}
      <ErrorAlert message={error} onRetry={reload} />

      {data && (
        <Row>
          {isStudent ? (
            <>
              <StatCard id="applications" value={data.applications} label="Job applications" tone="blue" />
              <StatCard id="events" value={data.events} label="Upcoming events registered" tone="green" />
              <Col md={4} className="mb-3">
                <Card className="assistant-card h-100" data-testid="assistant-card">
                  <Card.Body>
                    <Card.Title>AI Assistant</Card.Title>
                    <Card.Text className="mb-0">
                      Ask for jobs and events that fit you. The chat window arrives in a later step.
                    </Card.Text>
                  </Card.Body>
                </Card>
              </Col>
            </>
          ) : (
            <>
              <StatCard id="jobs" value={data.jobs} label="Job postings" tone="blue" />
              <StatCard id="events" value={data.events} label="Events posted" tone="orange" />
            </>
          )}
        </Row>
      )}
    </>
  );
}
