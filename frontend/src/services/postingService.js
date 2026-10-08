// What a COMPANY asks the server: its job postings, the applicants, and the private resumes.
import api from "./api";

export const createJob = (payload) => api.post("/jobs", payload).then((r) => r.data);

export const updateJob = (id, changes) => api.patch(`/jobs/${id}`, changes).then((r) => r.data);

export const getMyJobs = (params) => api.get("/jobs/mine", { params }).then((r) => r.data);

export const getApplicants = (jobId, params) =>
  api.get(`/jobs/${jobId}/applications`, { params }).then((r) => r.data);

export const getApplicant = (applicationId) => api.get(`/applications/${applicationId}`).then((r) => r.data);

export const setApplicationStatus = (applicationId, status) =>
  api.patch(`/applications/${applicationId}/status`, { status }).then((r) => r.data);

// Resumes are private: the server only sends them when the request carries the login token.
// An <iframe src=...> cannot add that header, so we download the PDF with Axios (which does)
// and show it from a temporary address that exists only in this browser tab.
export const fetchResumeBlob = (applicationId) =>
  api.get(`/applications/${applicationId}/resume`, { responseType: "blob" }).then((r) => r.data);
