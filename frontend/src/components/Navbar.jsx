import Badge from "react-bootstrap/Badge";
import Button from "react-bootstrap/Button";
import Container from "react-bootstrap/Container";
import Nav from "react-bootstrap/Nav";
import Navbar from "react-bootstrap/Navbar";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { NAV_LINKS } from "../navigation";

// The top bar. Collapses into a menu button on phones (the `expand="md"` part).
export default function AppNavbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const links = user ? NAV_LINKS[user.role] ?? [] : [];

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <Navbar bg="dark" data-bs-theme="dark" expand="md" className="mb-4">
      <Container>
        <Navbar.Brand as={Link} to="/">
          Handshake Clone
        </Navbar.Brand>
        <Navbar.Toggle aria-controls="main-nav" />
        <Navbar.Collapse id="main-nav">
          <Nav className="me-auto">
            {links.map((link) => (
              <Nav.Link key={link.to} as={NavLink} to={link.to} end={link.end}>
                {link.label}
              </Nav.Link>
            ))}
          </Nav>
          <Nav className="align-items-md-center">
            {user ? (
              <>
                <Navbar.Text className="me-md-3">
                  {user.name} <Badge bg="secondary">{user.role}</Badge>
                </Navbar.Text>
                <Button variant="outline-light" size="sm" onClick={handleLogout}>
                  Sign out
                </Button>
              </>
            ) : (
              <>
                <Nav.Link as={NavLink} to="/login">
                  Sign in
                </Nav.Link>
                <Nav.Link as={NavLink} to="/signup">
                  Sign up
                </Nav.Link>
              </>
            )}
          </Nav>
        </Navbar.Collapse>
      </Container>
    </Navbar>
  );
}
