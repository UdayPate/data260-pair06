import Row from "react-bootstrap/Row";
import ActivityHeatmap from "../components/ActivityHeatmap";
import CareerScene from "../components/CareerScene";
import ChatWindow from "../components/ChatWindow";
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
      {isStudent && <CareerScene />}

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
            </>
          ) : (
            <>
              <StatCard id="jobs" value={data.jobs} label="Job postings" tone="blue" />
              <StatCard id="events" value={data.events} label="Events posted" tone="orange" />
            </>
          )}
        </Row>
      )}

      {isStudent && <ActivityHeatmap />}

      {isStudent && <ChatWindow />}
    </>
  );
}
