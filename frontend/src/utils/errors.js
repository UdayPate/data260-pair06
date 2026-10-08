// Turns whatever went wrong into a sentence a person can read.
// The backend answers errors in two shapes:
//   { "detail": "Invalid email or password" }                      (a plain message)
//   { "detail": [ { "loc": ["body","password"], "msg": "..." } ] }  (validation: one entry per bad field)

const HIDDEN_LOCATIONS = new Set(["body", "query", "path"]);

function cleanMessage(msg = "") {
  return String(msg).replace(/^Value error,\s*/i, "");
}

export function getErrorMessage(error, fallback = "Something went wrong. Please try again.") {
  const response = error?.response;

  if (!response) {
    if (error?.code === "ECONNABORTED") {
      return "The server took too long to respond. Please try again.";
    }
    if (error?.message === "Network Error" || error?.request) {
      return "Cannot reach the server. Is the backend running on port 9060?";
    }
    return fallback;
  }

  const detail = response.data?.detail;
  if (typeof detail === "string" && detail) return detail;

  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.filter((p) => !HIDDEN_LOCATIONS.has(p)).join(".") : "";
        const message = cleanMessage(item.msg);
        return field ? `${field}: ${message}` : message;
      })
      .join("; ");
  }

  if (response.status >= 500) return "The server had a problem. Please try again in a moment.";
  return fallback;
}
