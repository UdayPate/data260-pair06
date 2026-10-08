import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { STORAGE_KEY } from "../services/api";
import { COMPANY, STUDENT, mock, mockDashboard, mockMe, renderApp, storeSession } from "./helpers";

describe("Navigation bar", () => {
  it("offers Sign in and Sign up to visitors", async () => {
    renderApp("/login");
    const nav = screen.getByRole("navigation");
    expect(within(nav).getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(within(nav).getByRole("link", { name: "Sign up" })).toHaveAttribute("href", "/signup");
    expect(within(nav).queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
  });

  it("shows the name and role of a logged-in student", async () => {
    storeSession(STUDENT);
    mockMe(STUDENT);
    mockDashboard("student");
    renderApp("/");
    const nav = screen.getByRole("navigation");
    expect(await within(nav).findByText("Ada Lovelace")).toBeInTheDocument();
    expect(within(nav).getByText("student")).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Home" })).toBeInTheDocument();
  });

  it("shows the company role for companies", async () => {
    storeSession(COMPANY);
    mockMe(COMPANY);
    mockDashboard("company");
    renderApp("/");
    expect(await within(screen.getByRole("navigation")).findByText("company")).toBeInTheDocument();
  });

  it("signs out: tells the server, clears the session and returns to the sign-in page", async () => {
    const user = userEvent.setup();
    storeSession(STUDENT);
    mockMe(STUDENT);
    mockDashboard("student");
    mock.onPost("/auth/logout").reply(200, { message: "Signed out." });
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(mock.history.post.map((r) => r.url)).toContain("/auth/logout");
    expect(screen.queryByText(/session has expired/i)).not.toBeInTheDocument();   // a normal sign-out is not an expiry
  });

  it("still signs out on this device when the server cannot be reached", async () => {
    const user = userEvent.setup();
    storeSession(STUDENT);
    mockMe(STUDENT);
    mockDashboard("student");
    mock.onPost("/auth/logout").networkError();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});
