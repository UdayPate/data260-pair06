import { beforeEach, describe, expect, it, vi } from "vitest";
import api, { STORAGE_KEY, readStoredSession, setUnauthorizedHandler } from "../services/api";
import { mock, storeSession, STUDENT } from "./helpers";

describe("API client", () => {
  const onUnauthorized = vi.fn();
  beforeEach(() => {
    onUnauthorized.mockReset();
    setUnauthorizedHandler(onUnauthorized);
  });

  it("sends the login token with every request", async () => {
    storeSession(STUDENT, "abc.def.ghi");
    mock.onGet("/ping").reply((config) => [200, { auth: config.headers.Authorization }]);
    const { data } = await api.get("/ping");
    expect(data.auth).toBe("Bearer abc.def.ghi");
  });

  it("sends no token when nobody is logged in", async () => {
    mock.onGet("/ping").reply((config) => [200, { auth: config.headers.Authorization ?? null }]);
    const { data } = await api.get("/ping");
    expect(data.auth).toBeNull();
  });

  it("tells the app to sign out when the server answers 401", async () => {
    mock.onGet("/jobs/mine").reply(401, { detail: "Invalid or expired token" });
    await expect(api.get("/jobs/mine")).rejects.toBeTruthy();
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("does NOT sign out for a wrong password (401 from the login form)", async () => {
    mock.onPost("/auth/login").reply(401, { detail: "Invalid email or password" });
    await expect(api.post("/auth/login", {})).rejects.toBeTruthy();
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("does not sign out for other errors", async () => {
    mock.onGet("/x").reply(403, { detail: "Students only" });
    await expect(api.get("/x")).rejects.toBeTruthy();
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("treats damaged stored data as 'not logged in'", () => {
    localStorage.setItem(STORAGE_KEY, "{not json");
    expect(readStoredSession()).toBeNull();
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: "t" }));   // no user
    expect(readStoredSession()).toBeNull();
  });
});
