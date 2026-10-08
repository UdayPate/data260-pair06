// Everything the student job pages ask the server.
import api from "./api";

// FastAPI wants repeated keys:  ?city=San Jose&city=Sunnyvale
// Axios' default would send  ?city[]=San Jose  which FastAPI ignores, so we change it.
const repeatKeys = { indexes: null };

export function searchJobs(params) {
  return api.get("/jobs", { params, paramsSerializer: repeatKeys }).then((r) => r.data);
}

export function getJob(id) {
  return api.get(`/jobs/${id}`).then((r) => r.data);
}

// The resume goes up as a multipart form, field name "resume".
export function applyToJob(id, file) {
  const form = new FormData();
  form.append("resume", file);
  return api.post(`/jobs/${id}/apply`, form).then((r) => r.data);
}

export function getMyApplications(params) {
  return api.get("/applications/mine", { params }).then((r) => r.data);
}
