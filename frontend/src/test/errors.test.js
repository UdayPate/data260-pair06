import { describe, expect, it } from "vitest";
import { getErrorMessage } from "../utils/errors";

const withResponse = (status, data) => ({ response: { status, data } });

describe("getErrorMessage", () => {
  it("uses a plain message from the server", () => {
    expect(getErrorMessage(withResponse(401, { detail: "Invalid email or password" }))).toBe("Invalid email or password");
  });

  it("turns validation errors into one readable sentence per field", () => {
    const error = withResponse(422, {
      detail: [
        { loc: ["body", "password"], msg: "Value error, Password must be at least 8 characters long" },
        { loc: ["body", "college"], msg: "String should have at least 1 character" },
      ],
    });
    expect(getErrorMessage(error)).toBe(
      "password: Password must be at least 8 characters long; college: String should have at least 1 character"
    );
  });

  it("explains that the server cannot be reached", () => {
    expect(getErrorMessage({ message: "Network Error", request: {} })).toMatch(/cannot reach the server/i);
  });

  it("explains a timeout", () => {
    expect(getErrorMessage({ code: "ECONNABORTED", message: "timeout of 15000ms exceeded" })).toMatch(/too long/i);
  });

  it("passes the server's safe 500 message through, and has its own text when there is none", () => {
    expect(getErrorMessage(withResponse(500, { detail: "A database error occurred" }))).toBe("A database error occurred");
    expect(getErrorMessage(withResponse(500, {}))).toMatch(/server had a problem/i);
  });

  it("falls back to a generic sentence", () => {
    expect(getErrorMessage(new Error("boom"))).toBe("Something went wrong. Please try again.");
    expect(getErrorMessage(withResponse(400, {}), "Custom fallback")).toBe("Custom fallback");
  });
});
