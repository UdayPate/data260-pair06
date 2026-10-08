// Shown instead of a blank page when a list has nothing in it
// (e.g. "No jobs match your search"), with an optional button to do something about it.
export default function EmptyState({ title, children, action }) {
  return (
    <div className="empty-state">
      <h2>{title}</h2>
      {children && <p className="mb-3">{children}</p>}
      {action}
    </div>
  );
}
