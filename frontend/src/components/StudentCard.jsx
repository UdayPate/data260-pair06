import Badge from "react-bootstrap/Badge";
import Card from "react-bootstrap/Card";
import { Link } from "react-router-dom";
import Avatar from "./Avatar";

// One student in the directory. Students see a limited card (no email or GPA); companies see
// more. The server decides what to send, so we just show whatever fields are present.
export default function StudentCard({ student }) {
  return (
    <Card className="mb-3" data-testid="student-card">
      <Card.Body className="d-flex gap-3">
        <Avatar name={student.name} src={student.profile_pic_url} size={56} decorative />
        <div>
        <Card.Title as="h2" className="h5 mb-1">
          <Link to={`/students/${student.id}`}>{student.name}</Link>
        </Card.Title>
        <div className="text-muted">
          {student.college}
          {student.major ? ` · ${student.major}` : ""}
          {student.degree ? ` (${student.degree})` : ""}
          {student.graduation_year ? ` · Class of ${student.graduation_year}` : ""}
        </div>
        {student.email && <div className="small text-muted">{student.email}{student.cgpa != null ? ` · GPA ${student.cgpa}` : ""}</div>}
        <div className="mt-2 d-flex flex-wrap gap-1">
          {student.skills.map((s) => <Badge key={s} bg="light" text="dark" className="border">{s}</Badge>)}
        </div>
        </div>
      </Card.Body>
    </Card>
  );
}
