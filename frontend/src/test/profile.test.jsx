import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { toPayload, validateProfile } from "../components/ProfileForm";
import { resetOptionsCache } from "../services/metaService";
import { checkImageFile, mediaUrl } from "../utils/format";
import { STUDENT, mock, mockDashboard, mockMe, renderApp, storeSession } from "./helpers";

const OPTIONS = {
  cities: ["San Jose", "Sunnyvale", "Mountain View"], majors: ["Computer Science", "Data Science"], degrees: ["BS", "MS"],
  job_categories: ["full_time", "part_time", "on_campus", "internship"],
  skills_by_area: { Data: ["Python", "SQL"] }, event_interest_options: ["Career Fair", "Tech Talk"],
  role_suggestions: ["Data Analyst", "Software Engineer"],
};
const PROFILE = {
  id: 1, name: "Ada Lovelace", email: "ada@sjsu.edu", college: "SJSU", date_of_birth: "2000-05-05", city: "San Jose",
  state: "CA", country: "USA", career_objective: "Build things", degree: "MS", major: "Computer Science",
  graduation_year: 2027, cgpa: 3.8, phone: "(408) 555-0123", profile_pic_url: null, skills: ["Python"],
  experience: [{ id: 1, title: "Intern", company: "Acme", start_date: "2025-06-01", end_date: null, description: "Dashboards" }],
};
const NO_PREFS = { saved: false, preferred_categories: [], preferred_cities: [], preferred_roles: [], min_hourly_rate: null,
                   open_to_remote: true, event_interests: [], updated_at: null };
const SAVED_PREFS = { saved: true, preferred_categories: ["internship"], preferred_cities: ["San Jose"], preferred_roles: ["Data Analyst"],
                      min_hourly_rate: 25, open_to_remote: true, event_interests: ["Career Fair"], updated_at: "2026-10-07T13:12:14" };

function open(prefs = NO_PREFS, profile = PROFILE) {
  resetOptionsCache();
  storeSession(STUDENT);
  mockMe(STUDENT);
  mockDashboard("student");
  mock.onGet("/meta/options").reply(200, OPTIONS);
  mock.onGet("/students/me").reply(200, profile);
  mock.onGet("/students/me/preferences").reply(200, prefs);
  renderApp("/profile");
}
const lastBody = (method, url) => JSON.parse(mock.history[method].filter((r) => r.url === url).pop().data);

describe("helpers", () => {
  it("builds picture addresses on the API server", () => {
    expect(mediaUrl("/media/profile_pics/a.png")).toBe("http://localhost:9060/media/profile_pics/a.png");
    expect(mediaUrl(null)).toBeNull();
  });
  it("checks picture files", () => {
    expect(checkImageFile(new File(["x"], "me.gif"))).toMatch(/PNG, JPEG or WebP/);
    expect(checkImageFile(new File([new Uint8Array(3 * 1024 * 1024)], "big.png"))).toMatch(/2 MB/);
    expect(checkImageFile(new File(["x"], "me.PNG"))).toBe("");
  });
  it("validates the profile form", () => {
    const base = { name: "A", email: "a@b.co", college: "C", cgpa: "", graduation_year: "", experience: [] };
    expect(validateProfile(base)).toEqual([]);
    expect(validateProfile({ ...base, email: "nope", cgpa: "4.5", graduation_year: "1900" })).toHaveLength(3);
    expect(validateProfile({ ...base, experience: [{ title: "", company: "X", start_date: "", end_date: "" }] })[0]).toMatch(/Experience 1/);
    expect(validateProfile({ ...base, experience: [{ title: "T", company: "X", start_date: "2025-05-01", end_date: "2025-01-01" }] })[0])
      .toMatch(/end date is before/);
  });
  it("turns blanks into what the server understands", () => {
    const p = toPayload({ name: " A ", email: "a@b.co", college: "C", date_of_birth: "", phone: "", city: "", state: "", country: "",
      degree: "", major: "", graduation_year: "", cgpa: "3.5", career_objective: " ", skills: ["Python"],
      experience: [{ title: "T", company: "X", start_date: "", end_date: "", description: " " }] });
    expect(p).toMatchObject({ name: "A", graduation_year: "", cgpa: 3.5, career_objective: "", date_of_birth: "" });
    expect(p.experience[0]).toEqual({ title: "T", company: "X", start_date: null, end_date: null, description: null });
  });
});

describe("Profile page", () => {
  it("shows the saved details", async () => {
    open();
    expect(await screen.findByLabelText("Full name")).toHaveValue("Ada Lovelace");
    expect(screen.getByLabelText("GPA")).toHaveValue(3.8);
    expect(screen.getByLabelText("Major")).toHaveValue("Computer Science");
    expect(screen.getByLabelText("Job title")).toHaveValue("Intern");
    expect(screen.getByText("Python")).toBeInTheDocument();
  });

  it("saves changes, including a new skill and experience, and updates the name in the top bar", async () => {
    const user = userEvent.setup();
    open();
    mock.onPatch("/students/me").reply((c) => [200, { ...PROFILE, ...JSON.parse(c.data), experience: PROFILE.experience, name: "Ada King" }]);
    const name = await screen.findByLabelText("Full name");
    await user.clear(name);
    await user.type(name, "Ada King");
    await user.type(screen.getByLabelText("Skills"), "SQL{Enter}");
    await user.click(screen.getByRole("button", { name: "Add experience" }));
    const forms = screen.getAllByRole("group", { name: /Experience/ });
    await user.type(within(forms[1]).getByLabelText("Job title"), "Tutor");
    await user.type(within(forms[1]).getByLabelText("Company"), "SJSU");
    await user.click(screen.getByRole("button", { name: "Save profile" }));

    expect(await screen.findByText("Profile saved.")).toBeInTheDocument();
    const body = lastBody("patch", "/students/me");
    expect(body.name).toBe("Ada King");
    expect(body.skills).toEqual(["Python", "SQL"]);
    expect(body.experience).toHaveLength(2);
    expect(body.experience[1]).toMatchObject({ title: "Tutor", company: "SJSU", end_date: null });
    expect(within(screen.getByRole("navigation")).getByText("Ada King")).toBeInTheDocument();
  });

  it("stops bad input before calling the server", async () => {
    const user = userEvent.setup();
    open();
    const name = await screen.findByLabelText("Full name");
    await user.clear(name);
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByText("Name is required.")).toBeInTheDocument();
    expect(mock.history.patch).toHaveLength(0);
  });

  it("shows the server's message, such as a taken email", async () => {
    const user = userEvent.setup();
    open();
    mock.onPatch("/students/me").reply(409, { detail: "That email is already used by another account" });
    await user.click(await screen.findByRole("button", { name: "Save profile" }));
    expect(await screen.findByText("That email is already used by another account")).toBeInTheDocument();
  });

  it("uploads a picture as the 'file' field", async () => {
    const user = userEvent.setup();
    open();
    mock.onPost("/students/me/profile-picture").reply(200, { profile_pic_url: "/media/profile_pics/new.png" });
    await user.upload(await screen.findByLabelText("Profile picture"), new File(["png"], "me.png", { type: "image/png" }));
    expect(await screen.findByAltText("Ada Lovelace profile")).toHaveAttribute("src", "http://localhost:9060/media/profile_pics/new.png");
    expect(mock.history.post[0].data.get("file").name).toBe("me.png");
  });

  it("refuses a picture that is not an image without calling the server", async () => {
    const user = userEvent.setup({ applyAccept: false });
    open();
    await user.upload(await screen.findByLabelText("Profile picture"), new File(["x"], "cv.pdf", { type: "application/pdf" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/PNG, JPEG or WebP/);
    expect(mock.history.post).toHaveLength(0);
  });

  it("shows an error with Try again when loading fails", async () => {
    resetOptionsCache();
    storeSession(STUDENT);
    mockMe(STUDENT);
    mockDashboard("student");
    mock.onGet("/meta/options").reply(200, OPTIONS);
    mock.onGet("/students/me").reply(500, {});
    mock.onGet("/students/me/preferences").reply(200, NO_PREFS);
    renderApp("/profile");
    expect(await screen.findByText(/server had a problem/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("Preferences tab", () => {
  it("says nothing is saved yet, then saves the whole set", async () => {
    const user = userEvent.setup();
    open();
    mock.onPut("/students/me/preferences").reply((c) => [200, { ...SAVED_PREFS, ...JSON.parse(c.data), saved: true }]);
    await user.click(await screen.findByRole("tab", { name: "Job & event preferences" }));
    expect(screen.getByText("You have not saved any preferences yet.")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Internship"));
    await user.click(screen.getByLabelText("San Jose", { selector: "#pcity-San\\ Jose" }));
    await user.type(screen.getByLabelText("Roles you are interested in"), "Data Analyst{Enter}");
    await user.type(screen.getByLabelText("Minimum pay (dollars per hour)"), "25");
    await user.click(screen.getByLabelText("Career Fair"));
    await user.click(screen.getByRole("button", { name: "Save preferences" }));

    expect(await screen.findByText("Preferences saved.")).toBeInTheDocument();
    expect(lastBody("put", "/students/me/preferences")).toEqual({
      preferred_categories: ["internship"], preferred_cities: ["San Jose"], preferred_roles: ["Data Analyst"],
      min_hourly_rate: 25, open_to_remote: true, event_interests: ["Career Fair"] });
    expect(screen.getByRole("button", { name: "Clear saved preferences" })).toBeInTheDocument();
  });

  it("shows saved preferences and can clear them", async () => {
    const user = userEvent.setup();
    open(SAVED_PREFS);
    mock.onDelete("/students/me/preferences").reply(204);
    await user.click(await screen.findByRole("tab", { name: "Job & event preferences" }));
    expect(screen.getByLabelText("Internship")).toBeChecked();
    expect(screen.getByLabelText("Minimum pay (dollars per hour)")).toHaveValue(25);
    expect(screen.getByText("Data Analyst")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear saved preferences" }));
    expect(await screen.findByText("Preferences cleared.")).toBeInTheDocument();
    expect(screen.getByLabelText("Internship")).not.toBeChecked();
    expect(screen.queryByRole("button", { name: "Clear saved preferences" })).not.toBeInTheDocument();
  });

  it("rejects an unrealistic pay before calling the server", async () => {
    const user = userEvent.setup();
    open();
    await user.click(await screen.findByRole("tab", { name: "Job & event preferences" }));
    await user.type(screen.getByLabelText("Minimum pay (dollars per hour)"), "900");
    await user.click(screen.getByRole("button", { name: "Save preferences" }));
    expect(await screen.findByText(/between 0 and 500/)).toBeInTheDocument();
    expect(mock.history.put).toHaveLength(0);
  });

  it("removes a role chip", async () => {
    const user = userEvent.setup();
    open(SAVED_PREFS);
    await user.click(await screen.findByRole("tab", { name: "Job & event preferences" }));
    await user.click(screen.getByRole("button", { name: "Remove Data Analyst" }));
    expect(screen.queryByText("Data Analyst", { selector: ".chip" })).not.toBeInTheDocument();
  });
});
