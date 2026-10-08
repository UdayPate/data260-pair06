import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { validateCompany } from "../components/CompanyProfileForm";
import { toEventPayload, validateEvent } from "../components/EventForm";
import { resetOptionsCache } from "../services/metaService";
import { COMPANY, STUDENT, mock, mockDashboard, mockMe, renderApp, storeSession } from "./helpers";

const OPTIONS = { cities: ["San Jose"], majors: ["Computer Science", "Data Science"], job_categories: [], degrees: ["BS", "MS"] };
const page = (items, extra = {}) => ({ items, total: items.length, page: 1, page_size: 10, total_pages: 1, ...extra });
const mini = { id: 7, name: "Acme Corp", profile_pic_url: null };
const COMPANY_PROFILE = { id: 7, name: "Acme Corp", email: "hr@acme.com", location: "San Jose", state: "CA", industry: "Software",
  description: "We build things.", contact_email: "jobs@acme.com", contact_phone: null, website: "https://acme.com", profile_pic_url: null };
const event = (over = {}) => ({ id: 3, name: "Career Fair", company: mini, event_datetime: "2027-02-10T17:30:00", location: "Student Union",
  city: "San Jose", eligible_majors: ["Computer Science"], registration_count: 4, is_past: false, ...over });

function loginCompany() {
  resetOptionsCache();
  storeSession(COMPANY); mockMe(COMPANY); mockDashboard("company");
  mock.onGet("/meta/options").reply(200, OPTIONS);
}

describe("helpers", () => {
  it("validates the company form", () => {
    const ok = { name: "A", email: "a@b.co", location: "SJ", contact_email: "", website: "" };
    expect(validateCompany(ok)).toEqual([]);
    expect(validateCompany({ ...ok, website: "acme.com", contact_email: "x" })).toHaveLength(2);
  });
  it("validates the event form", () => {
    const ok = { name: "E", description: "Long enough text", event_datetime: "2999-01-01T10:00", location: "Hall", city: "SJ", all_majors: true, majors: [] };
    expect(validateEvent(ok)).toEqual([]);
    expect(validateEvent({ ...ok, event_datetime: "2000-01-01T10:00" })[0]).toMatch(/future/);
    expect(validateEvent({ ...ok, all_majors: false })[0]).toMatch(/at least one major/);
  });
  it("builds the event payload with seconds and the right majors", () => {
    const base = { name: " E ", description: " text text text ", event_datetime: "2027-02-10T17:30", location: "Hall", city: "SJ", all_majors: false, majors: ["Data Science"] };
    expect(toEventPayload(base)).toEqual({ name: "E", description: "text text text", event_datetime: "2027-02-10T17:30:00",
      location: "Hall", city: "SJ", eligible_majors: ["Data Science"] });
    expect(toEventPayload({ ...base, all_majors: true }).eligible_majors).toEqual(["All"]);
  });
});

describe("Company profile", () => {
  it("loads, saves with blanks cleared, and updates the top bar", async () => {
    const user = userEvent.setup();
    loginCompany();
    mock.onGet("/companies/me").reply(200, COMPANY_PROFILE);
    mock.onPatch("/companies/me").reply((c) => [200, { ...COMPANY_PROFILE, ...JSON.parse(c.data) }]);
    renderApp("/company/profile");
    const name = await screen.findByLabelText("Company name");
    expect(name).toHaveValue("Acme Corp");
    await user.clear(name);
    await user.type(name, "Acme Inc");
    await user.clear(screen.getByLabelText("Website"));
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByText("Company profile saved.")).toBeInTheDocument();
    const body = JSON.parse(mock.history.patch[0].data);
    expect(body).toMatchObject({ name: "Acme Inc", website: "", contact_phone: "", location: "San Jose" });
    expect(within(screen.getByRole("navigation")).getByText("Acme Inc")).toBeInTheDocument();
  });
  it("uploads the logo to the company address", async () => {
    const user = userEvent.setup();
    loginCompany();
    mock.onGet("/companies/me").reply(200, COMPANY_PROFILE);
    mock.onPost("/companies/me/profile-picture").reply(200, { profile_pic_url: "/media/profile_pics/c.png" });
    renderApp("/company/profile");
    await user.upload(await screen.findByLabelText("Company logo"), new File(["x"], "logo.png", { type: "image/png" }));
    expect(await screen.findByAltText("Acme Corp profile")).toHaveAttribute("src", "http://localhost:9060/media/profile_pics/c.png");
  });
  it("blocks a bad website", async () => {
    const user = userEvent.setup();
    loginCompany();
    mock.onGet("/companies/me").reply(200, COMPANY_PROFILE);
    renderApp("/company/profile");
    const site = await screen.findByLabelText("Website");
    await user.clear(site);
    await user.type(site, "acme.com");
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByText(/must start with http/)).toBeInTheDocument();
    expect(mock.history.patch).toHaveLength(0);
  });
});

describe("Company events", () => {
  it("lists my events with counts and links", async () => {
    loginCompany();
    mock.onGet("/events/mine").reply(200, page([event(), event({ id: 4, name: "Old Talk", is_past: true, registration_count: 0 })]));
    renderApp("/company/events");
    const cards = await screen.findAllByTestId("company-event-card");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).getByLabelText("4 registered")).toBeInTheDocument();
    expect(within(cards[0]).getByRole("link", { name: "Registered students" })).toHaveAttribute("href", "/company/events/3/registrations");
    expect(within(cards[1]).getByText("Past")).toBeInTheDocument();
  });

  it("posts an event for chosen majors", async () => {
    const user = userEvent.setup();
    loginCompany();
    mock.onPost("/events").reply(201, { ...event({ id: 9 }), company: { ...COMPANY_PROFILE }, description: "d", can_register: null });
    mock.onGet("/events/9").reply(200, { ...event({ id: 9, name: "New Fair" }), company: { ...COMPANY_PROFILE }, description: "Details here", can_register: null });
    renderApp("/company/events/new");
    await user.type(await screen.findByLabelText("Event name"), "New Fair");
    await user.type(screen.getByLabelText("Description"), "Meet our recruiters here.");
    await user.type(screen.getByLabelText("Date and time"), "2999-05-05T10:00");
    await user.type(screen.getByLabelText("Location"), "Student Union");
    await user.type(screen.getByLabelText("City"), "San Jose");
    await user.click(screen.getByLabelText("Open to all majors"));
    await user.type(screen.getByLabelText("Eligible majors"), "Data Science{Enter}");
    await user.click(screen.getByRole("button", { name: "Post event" }));
    expect(await screen.findByRole("heading", { name: "New Fair" })).toBeInTheDocument();
    expect(JSON.parse(mock.history.post.find((r) => r.url === "/events").data)).toEqual({
      name: "New Fair", description: "Meet our recruiters here.", event_datetime: "2999-05-05T10:00:00",
      location: "Student Union", city: "San Jose", eligible_majors: ["Data Science"] });
  });

  it("refuses a past date without calling the server", async () => {
    const user = userEvent.setup();
    loginCompany();
    renderApp("/company/events/new");
    await user.click(await screen.findByRole("button", { name: "Post event" }));
    expect(await screen.findByText("Event name is required.")).toBeInTheDocument();
    expect(mock.history.post).toHaveLength(0);
  });

  it("edits an event", async () => {
    const user = userEvent.setup();
    loginCompany();
    window.scrollTo = vi.fn();
    mock.onGet("/events/3").reply(200, { ...event(), company: COMPANY_PROFILE, description: "Original text here", can_register: null });
    mock.onPatch("/events/3").reply(200, {});
    renderApp("/company/events/3/edit");
    const name = await screen.findByLabelText("Event name");
    expect(name).toHaveValue("Career Fair");
    expect(screen.getByLabelText("Date and time")).toHaveValue("2027-02-10T17:30");
    expect(screen.getByLabelText("Open to all majors")).not.toBeChecked();
    expect(screen.getByText("Computer Science", { selector: ".chip" })).toBeInTheDocument();
    await user.clear(name);
    await user.type(name, "Spring Career Fair");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText(/Event saved/)).toBeInTheDocument();
    expect(JSON.parse(mock.history.patch[0].data)).toMatchObject({ name: "Spring Career Fair", eligible_majors: ["Computer Science"] });
  });

  it("lists registered students with their emails", async () => {
    loginCompany();
    mock.onGet("/events/3").reply(200, { ...event(), company: COMPANY_PROFILE, description: "x", can_register: null });
    mock.onGet("/events/3/registrations").reply(200, page([{ registered_at: "2026-10-06T12:00:00",
      student: { id: 20, name: "Eve Adams", email: "eve@sjsu.edu", college: "SJSU", major: "Data Science", degree: "MS", graduation_year: 2027,
                 cgpa: 3.9, city: "San Jose", state: "CA", profile_pic_url: null, skills: ["Python"] } }]));
    renderApp("/company/events/3/registrations");
    expect(await screen.findByRole("link", { name: "Eve Adams" })).toHaveAttribute("href", "/students/20");
    expect(screen.getByRole("link", { name: "eve@sjsu.edu" })).toBeInTheDocument();
    expect(await screen.findByText(/Registered: Career Fair/)).toBeInTheDocument();
  });

  it("shows a message when nobody registered, and an error for someone else's event", async () => {
    loginCompany();
    mock.onGet("/events/3").reply(200, { ...event(), company: COMPANY_PROFILE, description: "x", can_register: null });
    mock.onGet("/events/3/registrations").reply(200, page([]));
    mock.onGet("/events/8").reply(200, { ...event({ id: 8 }), company: COMPANY_PROFILE, description: "x", can_register: null });
    mock.onGet("/events/8/registrations").reply(403, { detail: "You can only manage your own events" });
    renderApp("/company/events/3/registrations");
    expect(await screen.findByText("Nobody has registered yet")).toBeInTheDocument();
  });
});

describe("Company sees the students directory", () => {
  it("shows email and GPA to companies", async () => {
    loginCompany();
    mock.onGet("/students").reply(200, page([{ id: 20, name: "Eve Adams", email: "eve@sjsu.edu", college: "SJSU", major: "Data Science", degree: "MS",
      graduation_year: 2027, cgpa: 3.9, city: "San Jose", state: "CA", profile_pic_url: null, skills: ["Python"] }]));
    renderApp("/students");
    expect(await screen.findByText(/eve@sjsu.edu · GPA 3.9/)).toBeInTheDocument();
    expect(screen.getByText(/Find candidates/)).toBeInTheDocument();
  });
  it("keeps the student events pages away from companies", async () => {
    loginCompany();
    renderApp("/events/registered");
    expect(await screen.findByText("Company dashboard")).toBeInTheDocument();
  });
  it("keeps students away from company pages", async () => {
    resetOptionsCache();
    storeSession(STUDENT); mockMe(STUDENT); mockDashboard("student");
    renderApp("/company/events");
    expect(await screen.findByText("Student dashboard")).toBeInTheDocument();
  });
});
