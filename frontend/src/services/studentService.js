// The student directory (what you see depends on whether you are a company or a student;
// the server decides, so these functions are the same for both).
import api from "./api";

export const searchStudents = (params) =>
  api.get("/students", { params, paramsSerializer: { indexes: null } }).then((r) => r.data);

export const getStudent = (id) => api.get(`/students/${id}`).then((r) => r.data);
