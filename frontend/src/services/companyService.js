// What a COMPANY asks the server about itself and its events.
import api from "./api";

export const getMyCompany = () => api.get("/companies/me").then((r) => r.data);

export const updateMyCompany = (changes) => api.patch("/companies/me", changes).then((r) => r.data);

export function uploadCompanyLogo(file) {
  const form = new FormData();
  form.append("file", file);
  return api.post("/companies/me/profile-picture", form).then((r) => r.data);
}

export const createEvent = (payload) => api.post("/events", payload).then((r) => r.data);

export const updateEvent = (id, changes) => api.patch(`/events/${id}`, changes).then((r) => r.data);

export const getMyEvents = (params) => api.get("/events/mine", { params }).then((r) => r.data);

export const getEventRegistrations = (id, params) =>
  api.get(`/events/${id}/registrations`, { params }).then((r) => r.data);
