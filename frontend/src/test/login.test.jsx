import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { STORAGE_KEY } from "../services/api";
import { COMPANY, STUDENT, mock, mockDashboard, renderApp, tokenReply } from "./helpers";

async function fillAndSubmit(user, email = "Ada@Example.com", password = "Secret123") {
  if (email) await user.type(screen.getByLabelText("Email"), email);
  if (password) await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("Login page", () => {
  it("asks for the missing fields without calling the server", async () => {
    const user = userEvent.setup();
    renderApp("/login");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Email is required")).toBeInTheDocument();
    expect(screen.getByText("Password is required")).toBeInTheDocument();
    expect(mock.history.post).toHaveLength(0);
  });

  it("rejects a badly formed email before sending", async () => {
    const user = userEvent.setup();
    renderApp("/login");
    await fillAndSubmit(user, "not-an-email");
    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(mock.history.post).toHaveLength(0);
  });

  it("logs a student in and shows the home page", async () => {
    const user = userEvent.setup();
    mock.onPost("/auth/login").reply(200, tokenReply(STUDENT, "abc"));
    mockDashboard("student", { applications: 11, events: 2 });
    renderApp("/login");
    await fillAndSubmit(user);

    expect(await screen.findByText(/Welcome back, Ada Lovelace/)).toBeInTheDocument();
    expect(JSON.parse(mock.history.post[0].data)).toEqual({ email: "ada@example.com", password: "Secret123", role: "student" });
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY))).toEqual({ token: "abc", user: STUDENT });
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("logs a company in when the Company switch is selected", async () => {
    const user = userEvent.setup();
    mock.onPost("/auth/login").reply(200, tokenReply(COMPANY));
    mockDashboard("company");
    renderApp("/login");
    await user.click(screen.getByRole("radio", { name: "Company" }));
    await fillAndSubmit(user, "hr@acme.com");

    expect(await screen.findByText(/Welcome back, Acme Corp/)).toBeInTheDocument();
    expect(JSON.parse(mock.history.post[0].data).role).toBe("company");
  });

  it("shows the server's message for a wrong password and stays on the page", async () => {
    const user = userEvent.setup();
    mock.onPost("/auth/login").reply(401, { detail: "Invalid email or password" });
    renderApp("/login");
    await fillAndSubmit(user, "ada@example.com", "WrongPass1");

    expect(await screen.findByText("Invalid email or password")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(screen.queryByText(/session has expired/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();            // can try again
  });

  it("explains when the server cannot be reached", async () => {
    const user = userEvent.setup();
    mock.onPost("/auth/login").networkError();
    renderApp("/login");
    await fillAndSubmit(user);
    expect(await screen.findByText(/cannot reach the server/i)).toBeInTheDocument();
  });

  it("shows a busy button while waiting and blocks double-clicks", async () => {
    const user = userEvent.setup();
    let release;
    mock.onPost("/auth/login").reply(() => new Promise((resolve) => { release = () => resolve([200, tokenReply(STUDENT)]); }));
    mockDashboard("student");
    renderApp("/login");
    await fillAndSubmit(user);

    const busy = await screen.findByRole("button", { name: /signing in/i });
    expect(busy).toBeDisabled();
    expect(screen.getByLabelText("Email")).toBeDisabled();
    release();
    expect(await screen.findByText(/Welcome back/)).toBeInTheDocument();
    expect(mock.history.post).toHaveLength(1);
  });

  it("links to the signup page", async () => {
    renderApp("/login");
    expect(screen.getByRole("link", { name: "Create an account" })).toHaveAttribute("href", "/signup");
  });
});
