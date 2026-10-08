import { screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProtectedRoute, PublicOnlyRoute } from "../components/ProtectedRoute";
import { AuthProvider } from "../context/AuthContext";
import { STORAGE_KEY } from "../services/api";
import { COMPANY, ROUTER_FLAGS, STUDENT, mock, mockDashboard, mockMe, renderApp, storeSession } from "./helpers";

describe("sessions and protected pages", () => {
  it("sends a visitor who is not logged in to the sign-in page", async () => {
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("restores a stored session after checking it with the server", async () => {
    storeSession(STUDENT);
    mockMe({ ...STUDENT, name: "Ada L. (updated)" });
    mockDashboard("student");
    renderApp("/");
    expect(await screen.findByText(/Welcome back, Ada L\. \(updated\)/)).toBeInTheDocument();
    expect(mock.history.get[0].url).toBe("/auth/me");
    expect(mock.history.get[0].headers.Authorization).toBe("Bearer token-123");
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)).user.name).toBe("Ada L. (updated)");   // refreshed
  });

  it("signs out and explains when the stored token has expired", async () => {
    storeSession(STUDENT);
    mock.onGet("/auth/me").reply(401, { detail: "Invalid or expired token" });
    renderApp("/");
    expect(await screen.findByText(/your session has expired/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("keeps the session when the server is merely unreachable", async () => {
    storeSession(STUDENT);
    mock.onGet("/auth/me").networkError();
    mock.onGet("/applications/mine").networkError();
    mock.onGet("/events/registered").networkError();
    renderApp("/");
    expect(await screen.findByText(/cannot reach the server/i)).toBeInTheDocument();
    expect(screen.getByText(/Welcome back, Ada Lovelace/)).toBeInTheDocument();     // still logged in
    expect(screen.queryByText(/session has expired/i)).not.toBeInTheDocument();
    expect(localStorage.getItem(STORAGE_KEY)).not.toBeNull();
  });

  it("shows 'page not found' for unknown addresses", async () => {
    renderApp("/no/such/page");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });

  it("keeps logged-in people out of the sign-in page", async () => {
    storeSession(COMPANY);
    mockMe(COMPANY);
    mockDashboard("company");
    renderApp("/login");
    expect(await screen.findByText(/Welcome back, Acme Corp/)).toBeInTheDocument();
  });
});

describe("ProtectedRoute roles", () => {
  function renderRoutes(route) {
    return render(
      <MemoryRouter initialEntries={[route]} future={ROUTER_FLAGS}>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<div>HOME PAGE</div>} />
            <Route path="/login" element={<PublicOnlyRoute><div>LOGIN PAGE</div></PublicOnlyRoute>} />
            <Route path="/company-only" element={<ProtectedRoute role="company"><div>COMPANY AREA</div></ProtectedRoute>} />
            <Route path="/student-only" element={<ProtectedRoute role="student"><div>STUDENT AREA</div></ProtectedRoute>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );
  }

  it("lets the right role in", async () => {
    storeSession(COMPANY);
    mockMe(COMPANY);
    renderRoutes("/company-only");
    expect(await screen.findByText("COMPANY AREA")).toBeInTheDocument();
  });

  it("sends the wrong role Home", async () => {
    storeSession(STUDENT);
    mockMe(STUDENT);
    renderRoutes("/company-only");
    expect(await screen.findByText("HOME PAGE")).toBeInTheDocument();
    expect(screen.queryByText("COMPANY AREA")).not.toBeInTheDocument();
  });

  it("sends a visitor to the login page", async () => {
    renderRoutes("/student-only");
    expect(await screen.findByText("LOGIN PAGE")).toBeInTheDocument();
  });
});
