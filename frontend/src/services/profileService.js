// The logged-in student's OWN profile and preferences (always /students/me/...).
import api from "./api";

export const getMyProfile = () => api.get("/students/me").then((r) => r.data);

export const updateMyProfile = (changes) => api.patch("/students/me", changes).then((r) => r.data);

export function uploadProfilePicture(file) {
  const form = new FormData();
  form.append("file", file);                    // the server's field is called "file"
  return api.post("/students/me/profile-picture", form).then((r) => r.data);
}

export const getMyPreferences = () => api.get("/students/me/preferences").then((r) => r.data);

export const savePreferences = (prefs) => api.put("/students/me/preferences", prefs).then((r) => r.data);

export const clearPreferences = () => api.delete("/students/me/preferences");
