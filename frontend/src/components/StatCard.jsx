import Card from "react-bootstrap/Card";
import Col from "react-bootstrap/Col";

// One big number with a label, used on the dashboards. `tone` picks the accent colour.
export default function StatCard({ id, value, label, tone = "blue" }) {
  return (
    <Col md={4} className="mb-3">
      <Card className={`stat-card stat-${tone} h-100`} data-testid={`stat-${id}`}>
        <Card.Body className="ps-4">
          <div className="stat-value">{value}</div>
          <Card.Text className="text-muted mb-0">{label}</Card.Text>
        </Card.Body>
      </Card>
    </Col>
  );
}
