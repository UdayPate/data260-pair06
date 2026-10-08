// Everything the student event pages ask the server.
import api from "./api";

const repeatKeys = { indexes: null };   // ?city=A&city=B (what FastAPI expects)

export const searchEvents = (params) =>
  api.get("/events", { params, paramsSerializer: repeatKeys }).then((r) => r.data);

export const getEvent = (id) => api.get(`/events/${id}`).then((r) => r.data);

export const registerForEvent = (id) => api.post(`/events/${id}/register`).then((r) => r.data);

export const cancelRegistration = (id) => api.delete(`/events/${id}/register`);

export const getRegisteredEvents = (params) => api.get("/events/registered", { params }).then((r) => r.data);
