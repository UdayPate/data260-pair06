import Button from "react-bootstrap/Button";

// "Previous / Page 2 of 7 / Next". Hidden when everything fits on one page.
export default function Pagination({ page, totalPages, onChange }) {
  if (!totalPages || totalPages <= 1) return null;
  return (
    <nav aria-label="Pages" className="d-flex justify-content-center align-items-center gap-3 my-4">
      <Button variant="outline-primary" size="sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        Previous
      </Button>
      <span data-testid="page-indicator">
        Page {page} of {totalPages}
      </span>
      <Button variant="outline-primary" size="sm" disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
        Next
      </Button>
    </nav>
  );
}
