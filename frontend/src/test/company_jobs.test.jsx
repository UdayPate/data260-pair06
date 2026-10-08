import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { toJobPayload, validateJob } from "../components/JobForm";
import { resetOptionsCache } from "../services/metaService";
import { COMPANY, STUDENT, mock, mockDashboard, mockMe, renderApp, storeSession } from "./helpers";

const OPTIONS = { cities: ["San Jose", "Sunnyvale"], job_categories: ["full_time", "part_time", "on_campus", "internship"],
                  skills_by_area: { Data: ["Python", "SQL"] } };
const mini = { id: 7, name: "Acme Corp", profile_pic_url: null };
const posting = (over = {}) => ({ id: 1, title: "Data Intern", company: mini, city: "San Jose", state: "CA", is_remote: false,
  category: "internship", salary_min: 30, salary_max: 40, pay_period: "hourly", salary_display: "$30–$40/hr",
  posting_date: "2026-10-01", deadline: "2027-01-15", is_expired: false, skills: ["Python"], applicant_count: 3, ...over });
const page = (items, extra = {}) => ({ items, total: items.length, page: 1, page_size: 10, total_pages: 1, ...extra });
const student = (over = {}) => ({ id: 20, name: "Eve Adams", email: "eve@sjsu.edu", college: "SJSU", major: "Data Science", degree: "MS",
  graduation_year: 2027, cgpa: 3.9, city: "San Jose", state: "CA", profile_pic_url: null, skills: ["Python", "SQL"], ...over });
const applicant = (id, status, over = {}) => ({ id, status, applied_at: "2026-10-05T09:00:00", resume_url: `/applications/${id}/resume`,
  student: student(over) });

function loginCompany() {
  resetOptionsCache();
  storeSession(COMPANY);
  mockMe(COMPANY);
  mockDashboard("company");
  mock.onGet("/meta/options").reply(200, OPTIONS);
}
beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:resume-1");     // jsdom has no object URLs
  URL.revokeObjectURL = vi.fn();
});

describe("job form helpers", () => {
  const ok = { title: "T", description: "A long enough text", category: "internship", city: "San Jose", state: "", is_remote: false,
    salary_min: "20", salary_max: "30", pay_period: "hourly", posting_date: "", deadline: "2999-01-01", contact_email: "", skills: [] };
  it("accepts a good form", () => expect(validateJob(ok, true)).toEqual([]));
  it("catches the common mistakes", () => {
    expect(validateJob({ ...ok, salary_min: "50", salary_max: "30" }, true)[0]).toMatch(/lowest pay/);
    expect(validateJob({ ...ok, salary_max: "900" }, true)[0]).toMatch(/too high/);
    expect(validateJob({ ...ok, deadline: "2020-01-01" }, true).join(" ")).toMatch(/today or later/);
    expect(validateJob({ ...ok, description: "short" }, true)[0]).toMatch(/10 characters/);
    expect(validateJob({ ...ok, deadline: "" }, true)[0]).toMatch(/last day/);
  });
  it("leaves out blank optional fields on create but sends them on edit so they can be cleared", () => {
    const create = toJobPayload(ok, true);
    expect(create).not.toHaveProperty("state");
    expect(create).not.toHaveProperty("contact_email");
    expect(create).not.toHaveProperty("posting_date");
    expect(create.salary_min).toBe(20);
    const edit = toJobPayload({ ...ok, posting_date: "2026-10-01" }, false);
    expect(edit).toMatchObject({ state: "", contact_email: "", posting_date: "2026-10-01" });
  });
});

describe("My postings", () => {
  it("lists postings with applicant counts and links", async () => {
    loginCompany();
    mock.onGet("/jobs/mine").reply(200, page([posting(), posting({ id: 2, title: "Old Role", is_expired: true, applicant_count: 1 })]));
    renderApp("/company/jobs");
    const cards = await screen.findAllByTestId("posting-card");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).getByLabelText("3 applicants")).toBeInTheDocument();
    expect(within(cards[0]).getByRole("link", { name: "View applicants" })).toHaveAttribute("href", "/company/jobs/1/applicants");
    expect(within(cards[0]).getByRole("link", { name: "Edit" })).toHaveAttribute("href", "/company/jobs/1/edit");
    expect(within(cards[1]).getByText(/Closed/)).toBeInTheDocument();
  });
  it("shows an empty state with a Post button", async () => {
    loginCompany();
    mock.onGet("/jobs/mine").reply(200, page([]));
    renderApp("/company/jobs");
    expect(await screen.findByText("No job postings yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Post your first job" })).toHaveAttribute("href", "/company/jobs/new");
  });
  it("keeps students out", async () => {
    resetOptionsCache();
    storeSession(STUDENT); mockMe(STUDENT); mockDashboard("student");
    renderApp("/company/jobs");
    expect(await screen.findByText("Student dashboard")).toBeInTheDocument();
  });
});

describe("Post a job", () => {
  async function fill(user) {
    await user.type(await screen.findByLabelText("Job title"), "Data Intern");
    await user.type(screen.getByLabelText("Description"), "Work on pipelines every day.");
    await user.type(screen.getByLabelText("City"), "San Jose");
    await user.type(screen.getByLabelText("Lowest pay"), "30");
    await user.type(screen.getByLabelText("Highest pay"), "40");
    await user.type(screen.getByLabelText("Apply by"), "2999-01-01");
  }
  it("posts the job and opens it", async () => {
    const user = userEvent.setup();
    loginCompany();
    mock.onPost("/jobs").reply(201, { ...posting(), id: 55, company: { ...OPTIONS, id: 7, name: "Acme", location: "SJ", state: null, industry: null,
      description: null, contact_email: null, contact_phone: null, website: null, profile_pic_url: null }, description: "x", contact_email: null,
      posted_days_ago: 0, my_application: null });
    mock.onGet("/jobs/55").reply(200, { ...posting({ id: 55 }), company: { id: 7, name: "Acme", location: "SJ", state: null, industry: null, description: null,
      contact_email: null, contact_phone: null, website: null, profile_pic_url: null }, description: "Work on pipelines every day.",
      contact_email: null, posted_days_ago: 0, my_application: null });
    renderApp("/company/jobs/new");
    await fill(user);
    await user.type(screen.getByLabelText("Skills wanted"), "Python{Enter}");
    await user.click(screen.getByRole("button", { name: "Post job" }));
    expect(await screen.findByRole("heading", { name: "Data Intern" })).toBeInTheDocument();
    const body = JSON.parse(mock.history.post.find((r) => r.url === "/jobs").data);
    expect(body).toMatchObject({ title: "Data Intern", salary_min: 30, salary_max: 40, pay_period: "hourly", deadline: "2999-01-01",
                                 category: "internship", skills: ["Python"] });
    expect(body).not.toHaveProperty("company_id");
  });
  it("stops an invalid form before calling the server", async () => {
    const user = userEvent.setup();
    loginCompany();
    renderApp("/company/jobs/new");
    await user.click(await screen.findByRole("button", { name: "Post job" }));
    expect(await screen.findByText("Job title is required.")).toBeInTheDocument();
    expect(mock.history.post).toHaveLength(0);
  });
  it("shows the server's reason when it refuses", async () => {
    const user = userEvent.setup();
    loginCompany();
    mock.onPost("/jobs").reply(422, { detail: "salary_max is unrealistically high for hourly pay (limit 500)" });
    renderApp("/company/jobs/new");
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Post job" }));
    expect(await screen.findByText(/unrealistically high/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Post job" })).toBeEnabled();
  });
});

describe("Edit a job", () => {
  const full = () => ({ ...posting(), company: { id: 7, name: "Acme", location: "SJ", state: null, industry: null, description: null,
    contact_email: null, contact_phone: null, website: null, profile_pic_url: null }, description: "Original description text",
    contact_email: "jobs@acme.com", posted_days_ago: 7, my_application: null });
  it("loads the job, saves only through PATCH and shows a confirmation", async () => {
    const user = userEvent.setup();
    loginCompany();
    mock.onGet("/jobs/1").reply(200, full());
    mock.onPatch("/jobs/1").reply(200, full());
    window.scrollTo = vi.fn();
    renderApp("/company/jobs/1/edit");
    const title = await screen.findByLabelText("Job title");
    expect(title).toHaveValue("Data Intern");
    expect(screen.getByLabelText("Lowest pay")).toHaveValue(30);
    await user.clear(title);
    await user.type(title, "Senior Data Intern");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText(/Job saved/)).toBeInTheDocument();
    const body = JSON.parse(mock.history.patch[0].data);
    expect(body.title).toBe("Senior Data Intern");
    expect(body.posting_date).toBe("2026-10-01");
  });
});

describe("Applicants", () => {
  it("lists applicants and filters by status", async () => {
    const user = userEvent.setup();
    loginCompany();
    mock.onGet("/jobs/1").reply(200, { ...posting(), company: { id: 7 } });
    mock.onGet("/jobs/1/applications").reply((c) => c.params.status === "Reviewed"
      ? [200, page([applicant(2, "Reviewed", { name: "Reviewed Person" })])]
      : [200, page([applicant(1, "Pending"), applicant(2, "Reviewed", { name: "Reviewed Person" })])]);
    renderApp("/company/jobs/1/applicants");
    expect(await screen.findAllByTestId("applicant-card")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Eve Adams" })).toHaveAttribute("href", "/company/applications/1");
    expect(screen.getAllByText(/GPA 3.9/).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Reviewed" }));
    await screen.findByText("Reviewed Person");
    expect(screen.queryByRole("link", { name: "Eve Adams" })).not.toBeInTheDocument();
  });
  it("says so when nobody has applied", async () => {
    loginCompany();
    mock.onGet("/jobs/1").reply(200, { ...posting(), company: { id: 7 } });
    mock.onGet("/jobs/1/applications").reply(200, page([]));
    renderApp("/company/jobs/1/applicants");
    expect(await screen.findByText("No applicants yet")).toBeInTheDocument();
  });
  it("shows an error for a posting that is not yours", async () => {
    loginCompany();
    mock.onGet("/jobs/9").reply(200, { ...posting({ id: 9 }), company: { id: 8 } });
    mock.onGet("/jobs/9/applications").reply(404, { detail: "Job not found" });
    renderApp("/company/jobs/9/applicants");
    expect(await screen.findByText("Job not found")).toBeInTheDocument();
  });
});

describe("Applicant detail", () => {
  const detail = (status = "Pending") => ({ ...applicant(5, status), student: { ...student(), phone: "(408) 555-0123", country: "USA",
    career_objective: "Build data tools", experience: [{ id: 1, title: "Analyst Intern", company: "Acme", start_date: "2025-06-01", end_date: null, description: "Dashboards" }] },
    job: { id: 1, title: "Data Intern", company_id: 7, company_name: "Acme Corp", city: "San Jose", is_remote: false, category: "internship",
           deadline: "2027-01-15", is_expired: false } });

  it("shows the full profile, the resume, and changes the status", async () => {
    const user = userEvent.setup();
    loginCompany();
    mock.onGet("/applications/5").replyOnce(200, detail("Pending")).onGet("/applications/5").reply(200, detail("Reviewed"));
    mock.onGet("/applications/5/resume").reply(200, new Blob(["%PDF-1.4"], { type: "application/pdf" }));
    mock.onPatch("/applications/5/status").reply(200, applicant(5, "Reviewed"));
    renderApp("/company/applications/5");

    expect(await screen.findByRole("heading", { name: "Eve Adams" })).toBeInTheDocument();
    expect(screen.getByText("eve@sjsu.edu")).toBeInTheDocument();
    expect(screen.getByText("(408) 555-0123")).toBeInTheDocument();
    expect(screen.getByText("Analyst Intern")).toBeInTheDocument();
    expect(screen.queryByText(/birth/i)).not.toBeInTheDocument();           // companies never see date of birth
    const frame = await screen.findByTitle("Resume");
    expect(frame).toHaveAttribute("src", "blob:resume-1");
    expect(mock.history.get.find((r) => r.url === "/applications/5/resume").responseType).toBe("blob");

    await user.click(screen.getByRole("button", { name: "Reviewed" }));
    expect(JSON.parse(mock.history.patch[0].data)).toEqual({ status: "Reviewed" });
    expect(await screen.findByRole("button", { name: "Reviewed" })).toBeDisabled();       // now the current status
    expect(screen.getByRole("button", { name: "Pending" })).toBeEnabled();
  });

  it("shows the reason when the resume cannot be loaded", async () => {
    loginCompany();
    mock.onGet("/applications/5").reply(200, detail());
    mock.onGet("/applications/5/resume").reply(404, new Blob([JSON.stringify({ detail: "Resume file not found" })]));
    renderApp("/company/applications/5");
    expect(await screen.findByText("Resume file not found")).toBeInTheDocument();
  });

  it("shows an error for an application that is not yours", async () => {
    loginCompany();
    mock.onGet("/applications/9").reply(404, { detail: "Application not found" });
    renderApp("/company/applications/9");
    expect(await screen.findByText("Application not found")).toBeInTheDocument();
  });
});

describe("Student: view my own resume", () => {
  it("opens the resume in a window", async () => {
    const user = userEvent.setup();
    resetOptionsCache();
    storeSession(STUDENT); mockMe(STUDENT); mockDashboard("student");
    mock.onGet("/applications/mine").reply(200, page([{ id: 4, status: "Pending", applied_at: "2026-10-05T09:00:00", resume_url: "/applications/4/resume",
      job: { id: 1, title: "Data Intern", company_id: 7, company_name: "Acme", city: "San Jose", is_remote: false, category: "internship",
             deadline: "2027-01-01", is_expired: false } }]));
    mock.onGet("/applications/4/resume").reply(200, new Blob(["%PDF"], { type: "application/pdf" }));
    renderApp("/applications");
    await user.click(await screen.findByRole("button", { name: "View resume" }));
    expect(await screen.findByTitle("Resume")).toHaveAttribute("src", "blob:resume-1");
  });
});
