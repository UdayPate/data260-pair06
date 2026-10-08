import Badge from "react-bootstrap/Badge";

// The coloured label for an application's status. Used by both students and companies.
const STYLES = {
  Pending: { bg: "warning", text: "dark" },
  Reviewed: { bg: "info", text: "dark" },
  Declined: { bg: "danger", text: "white" },
};

export default function StatusBadge({ status }) {
  const style = STYLES[status] ?? { bg: "secondary", text: "white" };
  return (
    <Badge bg={style.bg} text={style.text} className="fw-semibold">
      {status}
    </Badge>
  );
}
