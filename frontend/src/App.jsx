import Container from "react-bootstrap/Container";
import { Route, Routes } from "react-router-dom";
import AppNavbar from "./components/Navbar";
import { ProtectedRoute, PublicOnlyRoute } from "./components/ProtectedRoute";
import ApplicantDetail from "./pages/ApplicantDetail";
import Applicants from "./pages/Applicants";
import EditJob from "./pages/EditJob";
import MyPostings from "./pages/MyPostings";
import PostJob from "./pages/PostJob";
import EventDetail from "./pages/EventDetail";
import EventSearch from "./pages/EventSearch";
import Home from "./pages/Home";
import JobDetail from "./pages/JobDetail";
import JobSearch from "./pages/JobSearch";
import Login from "./pages/Login";
import MyApplications from "./pages/MyApplications";
import MyEvents from "./pages/MyEvents";
import Profile from "./pages/Profile";
import NotFound from "./pages/NotFound";
import Signup from "./pages/Signup";
import StudentDirectory from "./pages/StudentDirectory";
import StudentView from "./pages/StudentView";

// Every screen of the app is listed here. Later steps add their routes to this list.
export default function App() {
  return (
    <>
      <AppNavbar />
      <Container className="pb-5">
        <Routes>
          <Route path="/login" element={<PublicOnlyRoute><Login /></PublicOnlyRoute>} />
          <Route path="/signup" element={<PublicOnlyRoute><Signup /></PublicOnlyRoute>} />
          <Route path="/" element={<ProtectedRoute><Home /></ProtectedRoute>} />
          <Route path="/jobs" element={<ProtectedRoute role="student"><JobSearch /></ProtectedRoute>} />
          <Route path="/jobs/:id" element={<ProtectedRoute><JobDetail /></ProtectedRoute>} />
          <Route path="/applications" element={<ProtectedRoute role="student"><MyApplications /></ProtectedRoute>} />
          <Route path="/events" element={<ProtectedRoute role="student"><EventSearch /></ProtectedRoute>} />
          <Route path="/events/registered" element={<ProtectedRoute role="student"><MyEvents /></ProtectedRoute>} />
          <Route path="/events/:id" element={<ProtectedRoute><EventDetail /></ProtectedRoute>} />
          <Route path="/students" element={<ProtectedRoute role="student"><StudentDirectory /></ProtectedRoute>} />
          <Route path="/students/:id" element={<ProtectedRoute><StudentView /></ProtectedRoute>} />
          <Route path="/profile" element={<ProtectedRoute role="student"><Profile /></ProtectedRoute>} />
          <Route path="/company/jobs" element={<ProtectedRoute role="company"><MyPostings /></ProtectedRoute>} />
          <Route path="/company/jobs/new" element={<ProtectedRoute role="company"><PostJob /></ProtectedRoute>} />
          <Route path="/company/jobs/:id/edit" element={<ProtectedRoute role="company"><EditJob /></ProtectedRoute>} />
          <Route path="/company/jobs/:id/applicants" element={<ProtectedRoute role="company"><Applicants /></ProtectedRoute>} />
          <Route path="/company/applications/:id" element={<ProtectedRoute role="company"><ApplicantDetail /></ProtectedRoute>} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Container>
    </>
  );
}
