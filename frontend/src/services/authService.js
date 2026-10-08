import api from "./api";

const clean = (email) => email.trim().toLowerCase();

export const login = ({ email, password, role }) =>
  api.post("/auth/login", { email: clean(email), password, role }).then((r) => r.data);

export const signupStudent = ({ name, email, password, college }) =>
  api
    .post("/auth/student/signup", { name: name.trim(), email: clean(email), password, college: college.trim() })
    .then((r) => r.data);

export const signupCompany = ({ name, email, password, location }) =>
  api
    .post("/auth/company/signup", { name: name.trim(), email: clean(email), password, location: location.trim() })
    .then((r) => r.data);

export const getMe = () => api.get("/auth/me").then((r) => r.data);

export const logoutRequest = () => api.post("/auth/logout").then((r) => r.data);
