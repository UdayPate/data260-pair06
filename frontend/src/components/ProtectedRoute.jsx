import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Loading from "./Loading";

// Wrap a page in <ProtectedRoute> so only logged-in people can open it.
//   <ProtectedRoute>                    any logged-in user
//   <ProtectedRoute role="company">     only companies (students are sent Home)
export function ProtectedRoute({ role, children }) {
  const { isAuthenticated, checking, user } = useAuth();
  const location = useLocation();

  if (checking) return <Loading label="Checking your session…" />;
  if (!isAuthenticated) return <Navigate to="/login" replace state={{ from: location }} />;
  if (role && user.role !== role) return <Navigate to="/" replace />;
  return children;
}

// The opposite: login and signup are only for people who are NOT logged in yet.
// After logging in you land on the page you originally asked for (or Home).
export function PublicOnlyRoute({ children }) {
  const { isAuthenticated, checking } = useAuth();
  const location = useLocation();

  if (checking) return <Loading label="Checking your session…" />;
  if (isAuthenticated) return <Navigate to={location.state?.from?.pathname || "/"} replace />;
  return children;
}

export default ProtectedRoute;
