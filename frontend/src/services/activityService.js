// Application activity for the home-page heatmap: [{ date: "2026-09-14", count: 3 }, ...]
// Only days with at least one application are returned; the heatmap treats a missing day as 0.
import api from "./api";

export const getActivity = (days = 365) =>
  api.get("/students/me/activity", { params: { days } }).then((r) => r.data);
