// The ONE Axios instance every service uses.
//  - adds "Authorization: Bearer <token>" to every request when someone is logged in
//  - when the server says "401 not authenticated" (expired or invalid token) it tells
//    the app to sign the user out
import axios from "axios";
import { API_URL } from "../config";

export const STORAGE_KEY = "handshake_auth";

const api = axios.create({ baseURL: API_URL, timeout: 15000 });

let unauthorizedHandler = null;
export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

export function readStoredSession() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return parsed && parsed.token && parsed.user ? parsed : null;
  } catch {
    return null;
  }
}

api.interceptors.request.use((config) => {
  const session = readStoredSession();
  if (session) config.headers.Authorization = `Bearer ${session.token}`;
  return config;
});

// A 401 from the login or signup forms just means "wrong password", not "session expired".
const isCredentialRequest = (url = "") => url.startsWith("/auth/login") || url.includes("/signup");

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const url = error.config?.url ?? "";
    if (error.response?.status === 401 && !isCredentialRequest(url) && unauthorizedHandler) {
      unauthorizedHandler();
    }
    return Promise.reject(error);
  }
);

export default api;
