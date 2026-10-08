// Dropdown choices (cities, categories, majors...) from GET /meta/options.
// They never change while the app is open, so we ask once and remember the answer.
import api from "./api";

let cached = null;

export function getOptions() {
  if (!cached) {
    cached = api.get("/meta/options").then((r) => r.data).catch((err) => {
      cached = null; // allow a retry after a failure
      throw err;
    });
  }
  return cached;
}

export function resetOptionsCache() {
  cached = null;
}
