import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { mock } from "./helpers";

// Runs after every test: close the rendered screen, forget fake server answers,
// and empty the browser storage so tests never affect each other.
afterEach(() => {
  cleanup();
  mock.reset();
  localStorage.clear();
});
