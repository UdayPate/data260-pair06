import Container from "react-bootstrap/Container";
import { Route, Routes } from "react-router-dom";
import AppNavbar from "./components/Navbar";
import { ProtectedRoute, PublicOnlyRoute } from "./components/ProtectedRoute";
import Home from "./pages/Home";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import Signup from "./pages/Signup";

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
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Container>
    </>
  );
}
