import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { COMPANY, STUDENT, mock, mockDashboard, mockMe, renderApp, storeSession } from "./helpers";

describe("Home dashboard", () => {
  it("shows a student's numbers and the AI assistant card", async () => {
    storeSession(STUDENT);
    mockMe(STUDENT);
    mockDashboard("student", { applications: 11, events: 2 });
    renderApp("/");

    expect(await screen.findByText("Student dashboard")).toBeInTheDocument();
    expect(await screen.findByTestId("stat-applications")).toHaveTextContent("11");
    expect(screen.getByTestId("stat-applications")).toHaveTextContent("Job applications");
    expect(screen.getByTestId("stat-events")).toHaveTextContent("2");
    expect(screen.getByTestId("assistant-card")).toHaveTextContent("AI Assistant");
    // it asked for just the totals, from the student endpoints
    expect(mock.history.get.map((r) => r.url)).toEqual(expect.arrayContaining(["/applications/mine", "/events/registered"]));
    expect(mock.history.get.find((r) => r.url === "/applications/mine").params).toEqual({ page_size: 1 });
  });

  it("shows a company's numbers and no assistant card", async () => {
    storeSession(COMPANY);
    mockMe(COMPANY);
    mockDashboard("company", { jobs: 3, events: 5 });
    renderApp("/");

    expect(await screen.findByText("Company dashboard")).toBeInTheDocument();
    expect(await screen.findByTestId("stat-jobs")).toHaveTextContent("3");
    expect(screen.getByTestId("stat-events")).toHaveTextContent("5");
    expect(screen.queryByTestId("assistant-card")).not.toBeInTheDocument();
    expect(mock.history.get.map((r) => r.url)).toEqual(expect.arrayContaining(["/jobs/mine", "/events/mine"]));
  });

  it("shows zero as a number, not as an empty box", async () => {
    storeSession(STUDENT);
    mockMe(STUDENT);
    mockDashboard("student", { applications: 0, events: 0 });
    renderApp("/");
    expect(await screen.findByTestId("stat-applications")).toHaveTextContent("0");
  });

  it("shows a spinner while loading", async () => {
    storeSession(STUDENT);
    mockMe(STUDENT);
    mock.onGet("/applications/mine").reply(() => new Promise(() => {}));   // never answers
    mock.onGet("/events/registered").reply(() => new Promise(() => {}));
    renderApp("/");
    expect(await screen.findByRole("status", { name: /loading your dashboard/i })).toBeInTheDocument();
  });

  it("shows an error with a working 'Try again' button", async () => {
    const user = userEvent.setup();
    storeSession(STUDENT);
    mockMe(STUDENT);
    mock.onGet("/applications/mine").replyOnce(500, {}).onGet("/applications/mine").reply(200, { total: 4, items: [] });
    mock.onGet("/events/registered").reply(200, { total: 1, items: [] });
    mock.onGet("/students/me/activity").reply(200, []);   // the heatmap on the same page works, so only one 'Try again'
    renderApp("/");

    expect(await screen.findByText(/server had a problem/i)).toBeInTheDocument();
    expect(screen.queryByTestId("stat-applications")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByTestId("stat-applications")).toHaveTextContent("4");
    expect(screen.queryByText(/server had a problem/i)).not.toBeInTheDocument();
  });

  it("signs the user out if the token expires while using the app", async () => {
    storeSession(STUDENT);
    mockMe(STUDENT);
    mock.onGet("/applications/mine").reply(401, { detail: "Invalid or expired token" });
    mock.onGet("/events/registered").reply(401, { detail: "Invalid or expired token" });
    renderApp("/");
    expect(await screen.findByText(/your session has expired/i)).toBeInTheDocument();
    expect(within(screen.getByRole("navigation")).queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
  });
});
