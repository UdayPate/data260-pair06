// The frame around the sign-in and sign-up forms: a coloured welcome panel on large
// screens (hidden on phones and tablets) and the form beside it.
export default function AuthLayout({ children }) {
  return (
    <div className="auth-shell">
      <aside className="auth-hero d-none d-lg-flex">
        <div>
          <div className="brand-mark brand-mark-lg" aria-hidden="true">H</div>
          <h2 className="display-6 mt-4">Find your next opportunity</h2>
          <p className="lead mb-0">Jobs, internships and campus events from companies near you.</p>
          <ul className="auth-points">
            <li>Search jobs by title, company, city and category</li>
            <li>Apply with a PDF resume in one step</li>
            <li>Register for career events that fit your major</li>
          </ul>
        </div>
      </aside>
      <div className="auth-form">{children}</div>
    </div>
  );
}
