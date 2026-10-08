// The title area at the top of every page: a heading, an optional subtitle, and optional
// buttons on the right (e.g. "Post a job").
export default function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="page-header d-flex flex-wrap justify-content-between align-items-end gap-2">
      <div>
        <h1 className="h3">{title}</h1>
        {subtitle && <p className="text-muted mb-0">{subtitle}</p>}
      </div>
      {actions && <div className="d-flex gap-2">{actions}</div>}
    </div>
  );
}
