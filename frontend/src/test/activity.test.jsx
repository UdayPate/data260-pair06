import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import ActivityHeatmap from "../components/ActivityHeatmap";
import { COMPANY, STUDENT, mock, mockDashboard, mockMe, renderApp, storeSession } from "./helpers";

// A fixed "today" (Friday 9 Oct 2026) so the calendar is the same on every machine.
// The calendar starts on Sunday 5 Oct 2025, so it shows 370 days up to today.
const TODAY = new Date(2026, 9, 9);
const ACTIVITY = [
  { date: "2026-09-01", count: 1 },
  { date: "2026-09-10", count: 2 },
  { date: "2026-09-14", count: 3 },
  { date: "2026-09-20", count: 5 },
];

const renderHeatmap = () => render(<ActivityHeatmap today={TODAY} />);

describe("Application activity heatmap", () => {
  it("asks for the days the calendar covers and draws one square per day up to today", async () => {
    mock.onGet("/students/me/activity").reply(200, ACTIVITY);
    renderHeatmap();

    expect(await screen.findAllByTestId("heat-cell")).toHaveLength(370);
    const request = mock.history.get.find((r) => r.url === "/students/me/activity");
    expect(request.params).toEqual({ days: 370 });
    // first square is Sunday 5 Oct 2025, last is today
    const cells = screen.getAllByTestId("heat-cell");
    expect(cells[0]).toHaveAttribute("data-date", "2025-10-05");
    expect(cells[369]).toHaveAttribute("data-date", "2026-10-09");
  });

  it("puts the count in each square's text and shades it 0, 1, 2 or 3+", async () => {
    mock.onGet("/students/me/activity").reply(200, ACTIVITY);
    renderHeatmap();
    await screen.findAllByTestId("heat-cell");

    const one = screen.getByTitle("1 application on Sep 1, 2026");
    const two = screen.getByTitle("2 applications on Sep 10, 2026");
    const three = screen.getByTitle("3 applications on Sep 14, 2026");
    const five = screen.getByTitle("5 applications on Sep 20, 2026");
    const none = screen.getByTitle("No applications on Sep 15, 2026");
    expect(one).toHaveClass("heat-1");
    expect(two).toHaveClass("heat-2");
    expect(three).toHaveClass("heat-3");
    expect(five).toHaveClass("heat-3"); // "3+" shares the darkest shade
    expect(none).toHaveClass("heat-0");
    // the same text is the accessible name, so colour is never the only signal
    expect(three).toHaveAccessibleName("3 applications on Sep 14, 2026");
    expect(screen.getByRole("img", { name: "1 application on Sep 1, 2026" })).toBe(one);
  });

  it("shows the total, month names and the Less / More legend", async () => {
    mock.onGet("/students/me/activity").reply(200, ACTIVITY);
    renderHeatmap();
    await screen.findAllByTestId("heat-cell");

    expect(screen.getByTestId("heatmap-total")).toHaveTextContent("11 applications since Oct 5, 2025");
    const card = screen.getByTestId("activity-heatmap");
    expect(within(card).getAllByText("Oct")).toHaveLength(2); // Oct 2025 and Oct 2026
    ["Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"].forEach((m) =>
      expect(within(card).getByText(m)).toBeInTheDocument()
    );
    expect(within(card).getByText(/^Less/)).toBeInTheDocument();
    expect(within(card).getByText(/More$/)).toBeInTheDocument();
  });

  it("shows the day's text under the calendar when a square is tapped", async () => {
    const user = userEvent.setup();
    mock.onGet("/students/me/activity").reply(200, ACTIVITY);
    renderHeatmap();
    await screen.findAllByTestId("heat-cell");

    expect(screen.getByTestId("heatmap-selected")).toHaveTextContent(/tap or hover a square/i);
    await user.click(screen.getByTitle("3 applications on Sep 14, 2026"));
    expect(screen.getByTestId("heatmap-selected")).toHaveTextContent("3 applications on Sep 14, 2026");
  });

  it("with no applications every square is empty and the total is 0", async () => {
    mock.onGet("/students/me/activity").reply(200, []);
    renderHeatmap();
    const cells = await screen.findAllByTestId("heat-cell");
    expect(cells.every((c) => c.classList.contains("heat-0"))).toBe(true);
    expect(screen.getByTestId("heatmap-total")).toHaveTextContent("0 applications since Oct 5, 2025");
  });

  it("shows a spinner while loading", async () => {
    mock.onGet("/students/me/activity").reply(() => new Promise(() => {}));
    renderHeatmap();
    expect(await screen.findByRole("status", { name: /loading your activity/i })).toBeInTheDocument();
    expect(screen.queryByTestId("heat-cell")).not.toBeInTheDocument();
  });

  it("shows an error with a working 'Try again' button", async () => {
    const user = userEvent.setup();
    mock.onGet("/students/me/activity").replyOnce(500, {}).onGet("/students/me/activity").reply(200, ACTIVITY);
    renderHeatmap();

    expect(await screen.findByText(/server had a problem/i)).toBeInTheDocument();
    expect(screen.queryByTestId("heat-cell")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findAllByTestId("heat-cell")).toHaveLength(370);
    expect(screen.queryByText(/server had a problem/i)).not.toBeInTheDocument();
  });

  it("scrolls sideways inside its own box instead of widening the page", async () => {
    mock.onGet("/students/me/activity").reply(200, []);
    const { container } = renderHeatmap();
    await screen.findAllByTestId("heat-cell");
    expect(container.querySelector(".heatmap-scroll")).toContainElement(container.querySelector(".heatmap-grid"));
  });
});

describe("Heatmap on the Home page", () => {
  it("is shown to a student under the stat cards", async () => {
    storeSession(STUDENT);
    mockMe(STUDENT);
    mockDashboard("student", { applications: 4, events: 1, activity: [{ date: "2026-10-01", count: 2 }] });
    renderApp("/");

    const stat = await screen.findByTestId("stat-applications");
    const heatmap = await screen.findByTestId("activity-heatmap");
    expect(await within(heatmap).findAllByTestId("heat-cell")).not.toHaveLength(0);
    // the heatmap comes after the stat cards, and before the assistant chat
    expect(stat.compareDocumentPosition(heatmap) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(heatmap.compareDocumentPosition(screen.getByTestId("assistant-card")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(mock.history.get.map((r) => r.url)).toContain("/students/me/activity");
  });

  it("is not shown to a company, and nothing is requested", async () => {
    storeSession(COMPANY);
    mockMe(COMPANY);
    mockDashboard("company", { jobs: 3, events: 5 });
    renderApp("/");

    expect(await screen.findByTestId("stat-jobs")).toBeInTheDocument();
    expect(screen.queryByTestId("activity-heatmap")).not.toBeInTheDocument();
    expect(mock.history.get.map((r) => r.url)).not.toContain("/students/me/activity");
  });

  it("an activity error does not hide the stat cards", async () => {
    storeSession(STUDENT);
    mockMe(STUDENT);
    mockDashboard("student", { applications: 4, events: 1 });
    mock.onGet("/students/me/activity").reply(500, {});   // later handler replaces the one from mockDashboard
    renderApp("/");

    expect(await screen.findByTestId("stat-applications")).toHaveTextContent("4");
    expect(await within(screen.getByTestId("activity-heatmap")).findByText(/server had a problem/i)).toBeInTheDocument();
  });
});
