import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { buildParams } from "../pages/JobSearch";
import { resetOptionsCache } from "../services/metaService";
import { STUDENT, mock, mockDashboard, mockMe, renderApp, storeSession } from "./helpers";

const OPTIONS = {
  cities: ["San Jose", "Sunnyvale", "Mountain View"],
  job_categories: ["full_time", "part_time", "on_campus", "internship"],
};

const job = (over = {}) => ({
  id: 1, title: "Data Analyst Intern", company: { id: 5, name: "Acme", profile_pic_url: null },
  city: "San Jose", state: "CA", is_remote: false, category: "internship",
  salary_min: 30, salary_max: 40, pay_period: "hourly", salary_display: "$30–$40/hr",
  posting_date: "2026-10-01", deadline: "2027-01-15", is_expired: false, skills: ["Python", "SQL"], ...over,
});

const page = (items, extra = {}) => ({ items, total: items.length, page: 1, page_size: 10, total_pages: 1, ...extra });

function login() {
  resetOptionsCache();
  storeSession(STUDENT);
  mockMe(STUDENT);
  mockDashboard("student");
  mock.onGet("/meta/options").reply(200, OPTIONS);
}

describe("buildParams", () => {
  const base = { q: "", category: [], city: [], is_remote: false, min_salary: "", salary_unit: "hourly",
                 skills: "", skills_match: "any", sort: "newest", include_expired: false };
  it("leaves out everything that is empty", () => {
    expect(buildParams(base, 1)).toEqual({ page: 1, page_size: 10, sort: "newest" });
  });
  it("sends the pay unit together with the amount, and splits skills", () => {
    const p = buildParams({ ...base, q: " data ", min_salary: "25", skills: "Python, , SQL ", skills_match: "all",
                            city: ["San Jose"], category: ["internship"], is_remote: true }, 2);
    expect(p).toMatchObject({ q: "data", min_salary: 25, salary_unit: "hourly", skills: ["Python", "SQL"],
                              skills_match: "all", city: ["San Jose"], category: ["internship"], is_remote: true, page: 2 });
  });
});

describe("Job search page", () => {
  it("lists jobs and shows how many were found", async () => {
    login();
    mock.onGet("/jobs").reply(200, page([job(), job({ id: 2, title: "Backend Intern", is_remote: true })]));
    renderApp("/jobs");
    expect(await screen.findAllByTestId("job-card")).toHaveLength(2);
    expect(screen.getByTestId("result-count")).toHaveTextContent("2 jobs found");
    expect(screen.getByRole("link", { name: "Data Analyst Intern" })).toHaveAttribute("href", "/jobs/1");
    expect(screen.getAllByText("$30–$40/hr")).toHaveLength(2);
  });

  it("sends the filters as repeated keys, the way FastAPI wants", async () => {
    const user = userEvent.setup();
    login();
    mock.onGet("/jobs").reply(200, page([job()]));
    renderApp("/jobs");
    await screen.findAllByTestId("job-card");

    await user.type(screen.getByLabelText("Title or company"), "data");
    await user.click(await screen.findByLabelText("San Jose"));
    await user.click(screen.getByLabelText("Sunnyvale"));
    await user.click(screen.getByLabelText("Internship"));
    await user.click(screen.getByRole("button", { name: "Search" }));

    await screen.findByTestId("result-count");
    const last = mock.history.get.filter((r) => r.url === "/jobs").pop();
    expect(last.params).toMatchObject({ q: "data", city: ["San Jose", "Sunnyvale"], category: ["internship"], page: 1 });
    // the actual address Axios builds: repeated keys, not city[]=
    const finalUrl = new URLSearchParams(
      (await import("axios")).default.getUri({ url: "/jobs", params: last.params, paramsSerializer: last.paramsSerializer })
        .split("?")[1]
    );
    expect(finalUrl.getAll("city")).toEqual(["San Jose", "Sunnyvale"]);
  });

  it("shows an empty state, and Clear filters brings the list back", async () => {
    const user = userEvent.setup();
    login();
    mock.onGet("/jobs").reply((c) => [200, page(c.params.q ? [] : [job()])]);
    renderApp("/jobs");
    await user.type(await screen.findByLabelText("Title or company"), "zzz");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("No jobs match your search")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findAllByTestId("job-card")).toHaveLength(1);
  });

  it("moves between pages", async () => {
    const user = userEvent.setup();
    login();
    mock.onGet("/jobs").reply((config) => {
      const p = config.params.page;
      return [200, page([job({ id: p, title: `Job on page ${p}` })], { page: p, total: 12, total_pages: 2 })];
    });
    renderApp("/jobs");
    expect(await screen.findByText("Job on page 1")).toBeInTheDocument();
    expect(screen.getByTestId("page-indicator")).toHaveTextContent("Page 1 of 2");
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Job on page 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("shows an error with a working Try again button", async () => {
    const user = userEvent.setup();
    login();
    mock.onGet("/jobs").replyOnce(500, {}).onGet("/jobs").reply(200, page([job()]));
    renderApp("/jobs");
    expect(await screen.findByText(/server had a problem/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findAllByTestId("job-card")).toHaveLength(1);
  });
});

const company = { id: 5, name: "Acme", location: "San Jose", state: "CA", industry: "Software", description: "We build things.",
                  contact_email: null, contact_phone: null, website: null, profile_pic_url: null };
const detail = (over = {}) => ({ ...job(), company, description: "Work on data pipelines every day.",
                                  contact_email: "jobs@acme.com", posted_days_ago: 7, my_application: null, ...over });
const pdf = (name = "cv.pdf", type = "application/pdf") => new File(["%PDF-1.4 hello"], name, { type });

describe("Job details and applying", () => {
  it("shows the job and the company", async () => {
    login();
    mock.onGet("/jobs/1").reply(200, detail());
    renderApp("/jobs/1");
    expect(await screen.findByRole("heading", { name: "Data Analyst Intern" })).toBeInTheDocument();
    expect(screen.getByText("Work on data pipelines every day.")).toBeInTheDocument();
    expect(within(screen.getByTestId("company-card")).getByText("About Acme")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply" })).toBeInTheDocument();
  });

  it("uploads the PDF as the 'resume' field and then shows the status", async () => {
    const user = userEvent.setup();
    login();
    mock.onGet("/jobs/1").replyOnce(200, detail())
      .onGet("/jobs/1").reply(200, detail({ my_application: { id: 9, status: "Pending", applied_at: "2026-10-08T10:00:00" } }));
    mock.onPost("/jobs/1/apply").reply(201, { id: 9, status: "Pending" });
    renderApp("/jobs/1");

    await user.upload(await screen.findByLabelText(/resume/i), pdf());
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(await screen.findByText("Your application")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply" })).not.toBeInTheDocument();
    const body = mock.history.post.find((r) => r.url === "/jobs/1/apply").data;
    expect(body).toBeInstanceOf(FormData);
    expect(body.get("resume").name).toBe("cv.pdf");
  });

  it("refuses a non-PDF or a missing file without calling the server", async () => {
    const user = userEvent.setup({ applyAccept: false });
    login();
    mock.onGet("/jobs/1").reply(200, detail());
    renderApp("/jobs/1");
    await screen.findByRole("button", { name: "Apply" });

    await user.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/choose your resume/i);

    await user.upload(screen.getByLabelText(/resume/i), new File(["x"], "cv.docx", { type: "text/plain" }));
    await user.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/must be a pdf/i);
    expect(mock.history.post).toHaveLength(0);
  });

  it("shows the server's reason when applying fails", async () => {
    const user = userEvent.setup();
    login();
    mock.onGet("/jobs/1").reply(200, detail());
    mock.onPost("/jobs/1/apply").reply(409, { detail: "You have already applied to this job" });
    renderApp("/jobs/1");
    await user.upload(await screen.findByLabelText(/resume/i), pdf());
    await user.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("You have already applied to this job");
    expect(screen.getByRole("button", { name: "Apply" })).toBeEnabled();   // can try again
  });

  it("shows 'closed' instead of the form after the deadline", async () => {
    login();
    mock.onGet("/jobs/1").reply(200, detail({ is_expired: true, deadline: "2026-01-01" }));
    renderApp("/jobs/1");
    expect(await screen.findByText(/applications closed on/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply" })).not.toBeInTheDocument();
  });

  it("shows an error for a job that does not exist", async () => {
    login();
    mock.onGet("/jobs/99").reply(404, { detail: "Job not found" });
    renderApp("/jobs/99");
    expect(await screen.findByText("Job not found")).toBeInTheDocument();
  });
});

describe("My applications", () => {
  const app = (id, status, title) => ({ id, status, applied_at: "2026-10-05T09:00:00", resume_url: `/applications/${id}/resume`,
    job: { id: id + 10, title, company_id: 5, company_name: "Acme", city: "San Jose", is_remote: false,
           category: "internship", deadline: "2027-01-01", is_expired: false } });

  it("lists applications and filters by status", async () => {
    const user = userEvent.setup();
    login();
    mock.onGet("/applications/mine").reply((config) =>
      config.params.status === "Reviewed"
        ? [200, page([app(2, "Reviewed", "Reviewed Role")])]
        : [200, page([app(1, "Pending", "Pending Role"), app(2, "Reviewed", "Reviewed Role")])]);
    renderApp("/applications");

    expect(await screen.findAllByTestId("application-card")).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "Reviewed" }));
    await screen.findByText("Reviewed Role");
    expect(screen.queryByText("Pending Role")).not.toBeInTheDocument();
    const last = mock.history.get.filter((r) => r.url === "/applications/mine").pop();
    expect(last.params.status).toBe("Reviewed");
  });

  it("shows a friendly message when there are none", async () => {
    login();
    mock.onGet("/applications/mine").reply(200, page([]));
    renderApp("/applications");
    expect(await screen.findByText("No applications yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Find jobs" })).toHaveAttribute("href", "/jobs");
  });
});

describe("Access", () => {
  it("keeps companies off the student job search", async () => {
    const { COMPANY } = await import("./helpers");
    storeSession(COMPANY);
    mockMe(COMPANY);
    mockDashboard("company");
    renderApp("/jobs");
    expect(await screen.findByText("Company dashboard")).toBeInTheDocument();
  });
});
