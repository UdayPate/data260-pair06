import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { STORAGE_KEY } from "../services/api";
import { COMPANY, STUDENT, mock, mockDashboard, renderApp, tokenReply } from "./helpers";

async function fillStudent(user, overrides = {}) {
  const v = { name: "Ada Lovelace", email: "Ada@Example.com", password: "Secret123", college: "SJSU", ...overrides };
  if (v.name) await user.type(screen.getByLabelText("Full name"), v.name);
  if (v.email) await user.type(screen.getByLabelText("Email"), v.email);
  if (v.password) await user.type(screen.getByLabelText("Password"), v.password);
  if (v.college) await user.type(screen.getByLabelText("College"), v.college);
}

const submit = (user) => user.click(screen.getByRole("button", { name: "Create account" }));

describe("Signup page", () => {
  it("shows student fields by default and company fields after switching", async () => {
    const user = userEvent.setup();
    renderApp("/signup");
    expect(screen.getByLabelText("Full name")).toBeInTheDocument();
    expect(screen.getByLabelText("College")).toBeInTheDocument();
    expect(screen.queryByLabelText("Location")).not.toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "Company" }));
    expect(screen.getByLabelText("Company name")).toBeInTheDocument();
    expect(screen.getByLabelText("Location")).toBeInTheDocument();
    expect(screen.queryByLabelText("College")).not.toBeInTheDocument();
  });

  it("asks for every missing field without calling the server", async () => {
    const user = userEvent.setup();
    renderApp("/signup");
    await submit(user);
    expect(await screen.findByText("Name is required")).toBeInTheDocument();
    expect(screen.getByText("Email is required")).toBeInTheDocument();
    expect(screen.getByText(/at least 8 characters long/i)).toBeInTheDocument();
    expect(screen.getByText("College name is required")).toBeInTheDocument();
    expect(mock.history.post).toHaveLength(0);
  });

  it.each([
    ["too short", "short1", /at least 8 characters long/i],
    ["only letters", "allletters", /at least one letter and one digit/i],
    ["only digits", "12345678", /at least one letter and one digit/i],
    ["longer than 72 bytes", "a1".repeat(40), /at most 72 bytes/i],
  ])("rejects a password that is %s", async (_label, password, message) => {
    const user = userEvent.setup();
    renderApp("/signup");
    await fillStudent(user, { password });
    await submit(user);
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(mock.history.post).toHaveLength(0);
  });

  it("creates a student account and logs the student in", async () => {
    const user = userEvent.setup();
    mock.onPost("/auth/student/signup").reply(201, tokenReply(STUDENT, "new-token"));
    mockDashboard("student", { applications: 0, events: 0 });
    renderApp("/signup");
    await fillStudent(user, { name: "  Ada Lovelace  " });
    await submit(user);

    expect(await screen.findByText(/Welcome back, Ada Lovelace/)).toBeInTheDocument();
    expect(JSON.parse(mock.history.post[0].data)).toEqual({
      name: "Ada Lovelace", email: "ada@example.com", password: "Secret123", college: "SJSU",
    });
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)).token).toBe("new-token");
  });

  it("creates a company account with a location", async () => {
    const user = userEvent.setup();
    mock.onPost("/auth/company/signup").reply(201, tokenReply(COMPANY));
    mockDashboard("company");
    renderApp("/signup");
    await user.click(screen.getByRole("radio", { name: "Company" }));
    await user.type(screen.getByLabelText("Company name"), "Acme Corp");
    await user.type(screen.getByLabelText("Email"), "hr@acme.com");
    await user.type(screen.getByLabelText("Password"), "Secret123");
    await user.type(screen.getByLabelText("Location"), "San Jose");
    await submit(user);

    expect(await screen.findByText(/Welcome back, Acme Corp/)).toBeInTheDocument();
    expect(JSON.parse(mock.history.post[0].data)).toEqual({
      name: "Acme Corp", email: "hr@acme.com", password: "Secret123", location: "San Jose",
    });
  });

  it("shows the server's message when the email is already registered", async () => {
    const user = userEvent.setup();
    mock.onPost("/auth/student/signup").reply(409, { detail: "An account with this email already exists" });
    renderApp("/signup");
    await fillStudent(user);
    await submit(user);
    expect(await screen.findByText("An account with this email already exists")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create account" })).toBeEnabled();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("turns the server's validation errors into readable text", async () => {
    const user = userEvent.setup();
    mock.onPost("/auth/student/signup").reply(422, {
      detail: [{ loc: ["body", "college"], msg: "String should have at most 100 characters" }],
    });
    renderApp("/signup");
    await fillStudent(user);
    await submit(user);
    expect(await screen.findByText("college: String should have at most 100 characters")).toBeInTheDocument();
  });

  it("keeps what was typed when switching between Student and Company", async () => {
    const user = userEvent.setup();
    renderApp("/signup");
    await user.type(screen.getByLabelText("Email"), "keep@example.com");
    await user.click(screen.getByRole("radio", { name: "Company" }));
    expect(screen.getByLabelText("Email")).toHaveValue("keep@example.com");
  });
});
