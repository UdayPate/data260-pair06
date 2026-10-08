import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="text-center py-5">
      <h1 className="h3">Page not found</h1>
      <p className="text-muted">That address doesn't match anything here.</p>
      <Link to="/">Go to the home page</Link>
    </div>
  );
}
