import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { buildEventParams } from "../pages/EventSearch";
import { buildStudentParams } from "../pages/StudentDirectory";
import { resetOptionsCache } from "../services/metaService";
import { STUDENT, mock, mockDashboard, mockMe, renderApp, storeSession } from "./helpers";

const OPTIONS = { cities: ["San Jose", "Sunnyvale"], majors: ["Computer Science", "Data Science"], job_categories: [] };
const company = { id: 5, name: "Acme", location: "San Jose", state: "CA", industry: "Software", description: "We build.",
                  contact_email: null, contact_phone: null, website: null, profile_pic_url: null };
const event = (over = {}) => ({
  id: 1, name: "Career Fair", company: { id: 5, name: "Acme", profile_pic_url: null }, event_datetime: "2027-02-10T17:30:00",
  location: "Student Union", city: "San Jose", eligible_majors: ["Computer Science"], registration_count: 12,
  is_past: false, eligible: true, registered: false, ...over });
const page = (items, extra = {}) => ({ items, total: items.length, page: 1, page_size: 10, total_pages: 1, ...extra });
const eventDetail = (over = {}) => ({ ...event(), company, description: "Meet recruiters from many companies.",
  can_register: true, register_blocked_reason: null, ...over });

function login() {
  resetOptionsCache();
  storeSession(STUDENT);
  mockMe(STUDENT);
  mockDashboard("student");
  mock.onGet("/meta/options").reply(200, OPTIONS);
}

describe("query builders", () => {
  it("events: leaves out empty filters", () => {
    expect(buildEventParams({ q: "", city: [], date_from: "", date_to: "", major: "", include_past: false }, 1))
      .toEqual({ page: 1, page_size: 10 });
    expect(buildEventParams({ q: " fair ", city: ["San Jose"], date_from: "2027-01-01", date_to: "2027-02-01",
                              major: "Data Science", include_past: true }, 3))
      .toEqual({ page: 3, page_size: 10, q: "fair", city: ["San Jose"], date_from: "2027-01-01",
                 date_to: "2027-02-01", major: "Data Science", include_past: true });
  });
  it("students: major is sent as a list and skills are split", () => {
    expect(buildStudentParams({ q: "", college: "", major: "Data Science", skills: "Python, SQL,", skills_match: "all" }, 1))
      .toEqual({ page: 1, page_size: 10, major: ["Data Science"], skills: ["Python", "SQL"], skills_match: "all" });
  });
});

describe("Event search", () => {
  it("lists events with their badges", async () => {
    login();
    mock.onGet("/events").reply(200, page([event(), event({ id: 2, name: "Tech Talk", registered: true, eligible: false })]));
    renderApp("/events");
    expect(await screen.findAllByTestId("event-card")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Career Fair" })).toHaveAttribute("href", "/events/1");
    expect(screen.getByText("Registered")).toBeInTheDocument();
    expect(screen.getByText("Not open to your major")).toBeInTheDocument();
  });

  it("sends the chosen filters", async () => {
    const user = userEvent.setup();
    login();
    mock.onGet("/events").reply(200, page([event()]));
    renderApp("/events");
    await screen.findAllByTestId("event-card");
    await user.click(await screen.findByLabelText("Sunnyvale"));
    await user.selectOptions(screen.getByLabelText("Open to major"), "Data Science");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByTestId("result-count");
    const last = mock.history.get.filter((r) => r.url === "/events").pop();
    expect(last.params).toMatchObject({ city: ["Sunnyvale"], major: "Data Science", page: 1 });
  });

  it("blocks a search whose 'To' date is before 'From'", async () => {
    const user = userEvent.setup();
    login();
    mock.onGet("/events").reply(200, page([event()]));
    renderApp("/events");
    await screen.findAllByTestId("event-card");
    await user.type(screen.getByLabelText("From"), "2027-03-01");
    await user.type(screen.getByLabelText("To"), "2027-02-01");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText(/must not be before/i)).toBeInTheDocument();
    expect(mock.history.get.filter((r) => r.url === "/events")).toHaveLength(1);   // no second request
  });

  it("shows an empty state", async () => {
    login();
    mock.onGet("/events").reply(200, page([]));
    renderApp("/events");
    expect(await screen.findByText("No events match your search")).toBeInTheDocument();
  });
});

describe("Event details and registration", () => {
  it("registers and then shows the registered state", async () => {
    const user = userEvent.setup();
    login();
    mock.onGet("/events/1").replyOnce(200, eventDetail())
      .onGet("/events/1").reply(200, eventDetail({ registered: true, can_register: false, registration_count: 13 }));
    mock.onPost("/events/1/register").reply(201, {});
    renderApp("/events/1");
    await user.click(await screen.findByRole("button", { name: "Register" }));
    expect(await screen.findByText("You are registered")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel registration" })).toBeInTheDocument();
    expect(mock.history.post.map((r) => r.url)).toEqual(["/events/1/register"]);
  });

  it("cancels a registration", async () => {
    const user = userEvent.setup();
    login();
    mock.onGet("/events/1").replyOnce(200, eventDetail({ registered: true, can_register: false }))
      .onGet("/events/1").reply(200, eventDetail());
    mock.onDelete("/events/1/register").reply(204);
    renderApp("/events/1");
    await user.click(await screen.findByRole("button", { name: "Cancel registration" }));
    expect(await screen.findByRole("button", { name: "Register" })).toBeInTheDocument();
    expect(mock.history.delete).toHaveLength(1);
  });

  it("explains why registration is not possible", async () => {
    login();
    mock.onGet("/events/1").reply(200, eventDetail({ can_register: false,
      register_blocked_reason: "This event is open to Data Science majors only (your major: Computer Science)" }));
    renderApp("/events/1");
    expect(await screen.findByText(/open to Data Science majors only/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Register" })).not.toBeInTheDocument();
  });

  it("shows the server's message when registering fails", async () => {
    const user = userEvent.setup();
    login();
    mock.onGet("/events/1").reply(200, eventDetail());
    mock.onPost("/events/1/register").reply(409, { detail: "You are already registered for this event" });
    renderApp("/events/1");
    await user.click(await screen.findByRole("button", { name: "Register" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("You are already registered for this event");
  });

  it("does not offer cancelling a past event", async () => {
    login();
    mock.onGet("/events/1").reply(200, eventDetail({ registered: true, is_past: true, can_register: false }));
    renderApp("/events/1");
    expect(await screen.findByText("You are registered")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel registration" })).not.toBeInTheDocument();
  });
});

describe("My events", () => {
  it("lists registered events and can include past ones", async () => {
    const user = userEvent.setup();
    login();
    mock.onGet("/events/registered").reply((c) =>
      [200, page(c.params.include_past ? [event(), event({ id: 3, name: "Old Talk", is_past: true })] : [event()])]);
    renderApp("/events/registered");
    expect(await screen.findAllByTestId("event-card")).toHaveLength(1);
    await user.click(screen.getByLabelText("Show past events"));
    expect(await screen.findByText("Old Talk")).toBeInTheDocument();
  });

  it("shows a friendly message when empty", async () => {
    login();
    mock.onGet("/events/registered").reply(200, page([]));
    renderApp("/events/registered");
    expect(await screen.findByText("No events yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse events" })).toHaveAttribute("href", "/events");
  });
});

const peer = (over = {}) => ({ id: 20, name: "Eve Adams", college: "SJSU", major: "Data Science", degree: "MS",
  graduation_year: 2027, profile_pic_url: null, skills: ["Python", "SQL"], ...over });

describe("Student directory", () => {
  it("lists students without private fields", async () => {
    login();
    mock.onGet("/students").reply(200, page([peer(), peer({ id: 21, name: "Sam Lee" })]));
    renderApp("/students");
    expect(await screen.findAllByTestId("student-card")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Eve Adams" })).toHaveAttribute("href", "/students/20");
    expect(screen.queryByText(/GPA/)).not.toBeInTheDocument();
  });

  it("searches with repeated major/skills keys", async () => {
    const user = userEvent.setup();
    login();
    mock.onGet("/students").reply(200, page([peer()]));
    renderApp("/students");
    await screen.findAllByTestId("student-card");
    await user.type(screen.getByLabelText("Skills (comma separated)"), "Python, SQL");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByTestId("result-count");
    const last = mock.history.get.filter((r) => r.url === "/students").pop();
    expect(last.params).toMatchObject({ skills: ["Python", "SQL"], skills_match: "any" });
  });

  it("opens one student's limited profile", async () => {
    login();
    mock.onGet("/students/20").reply(200, { ...peer(), career_objective: "Build data tools",
      experience: [{ id: 1, title: "Analyst Intern", company: "Acme", start_date: "2025-06-01", end_date: null, description: "Dashboards" }] });
    renderApp("/students/20");
    expect(await screen.findByRole("heading", { name: "Eve Adams" })).toBeInTheDocument();
    expect(screen.getByText("Build data tools")).toBeInTheDocument();
    expect(screen.getByText("Analyst Intern")).toBeInTheDocument();
    expect(screen.getByText(/Jun 2025 – Present/)).toBeInTheDocument();
    expect(screen.queryByText(/@/)).not.toBeInTheDocument();      // no email shown to a peer
  });

  it("shows a message for a student that does not exist", async () => {
    login();
    mock.onGet("/students/99").reply(404, { detail: "Student not found" });
    renderApp("/students/99");
    expect(await screen.findByText("Student not found")).toBeInTheDocument();
  });
});
