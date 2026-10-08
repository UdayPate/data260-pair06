import { render } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { AuthProvider } from "../context/AuthContext";
import api, { STORAGE_KEY } from "../services/api";

// A fake server: tests tell it what to answer, e.g. mock.onGet("/auth/me").reply(200, {...}).
// It plugs into the same Axios instance the app uses, so the real interceptors, services,
// context and pages all run; only the network is replaced.
export const mock = new MockAdapter(api);

export const ROUTER_FLAGS = { v7_startTransition: true, v7_relativeSplatPath: true };

export const STUDENT = { id: 1, role: "student", name: "Ada Lovelace" };
export const COMPANY = { id: 7, role: "company", name: "Acme Corp" };

// Pretend this person logged in earlier (their session is in localStorage).
export function storeSession(user, token = "token-123") {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ token, user }));
}

// What POST /auth/login and the signup endpoints answer.
export const tokenReply = (user, token = "token-123") => ({
  access_token: token,
  token_type: "bearer",
  role: user.role,
  user_id: user.id,
  name: user.name,
});

export function mockMe(user) {
  mock.onGet("/auth/me").reply(200, { role: user.role, id: user.id, name: user.name, email: "x@example.com" });
}

export function mockDashboard(role, numbers = {}) {
  const page = (total) => [200, { items: [], total, page: 1, page_size: 1, total_pages: total }];
  if (role === "student") {
    mock.onGet("/applications/mine").reply(...page(numbers.applications ?? 11));
    mock.onGet("/events/registered").reply(...page(numbers.events ?? 2));
  } else {
    mock.onGet("/jobs/mine").reply(...page(numbers.jobs ?? 3));
    mock.onGet("/events/mine").reply(...page(numbers.events ?? 5));
  }
}

export function renderApp(route = "/") {
  return render(
    <MemoryRouter initialEntries={[route]} future={ROUTER_FLAGS}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>
  );
}
