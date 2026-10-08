import { API_URL } from "../config";

// Small helpers that turn data into readable text.
export function formatDate(value) {
  if (!value) return "";
  // "2026-11-30" has no time zone; build it from its parts so it never shifts by a day.
  const [datePart] = String(value).split("T");
  const [y, m, d] = datePart.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export const CATEGORY_LABELS = {
  full_time: "Full-time",
  part_time: "Part-time",
  on_campus: "On-campus",
  internship: "Internship",
};

export const categoryLabel = (c) => CATEGORY_LABELS[c] ?? c;

export const MAX_RESUME_BYTES = 5 * 1024 * 1024;

// Returns an error sentence, or "" when the file is fine to upload.
export function checkResumeFile(file) {
  if (!file) return "Choose your resume (a PDF file).";
  if (!/\.pdf$/i.test(file.name)) return "The resume must be a PDF file.";
  if (file.size === 0) return "That file is empty.";
  if (file.size > MAX_RESUME_BYTES) return "The resume must be 5 MB or smaller.";
  return "";
}

export function formatDateTime(value) {
  if (!value) return "";
  const d = new Date(value);          // event times are plain local times (no time zone)
  return d.toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric",
                                      hour: "numeric", minute: "2-digit" });
}

// "Mar 2024 – Present" style range for an experience entry.
export function formatRange(start, end) {
  const fmt = (v) => {
    const [y, m] = String(v).split("-").map(Number);
    return new Date(y, (m || 1) - 1, 1).toLocaleDateString("en-US", { month: "short", year: "numeric" });
  };
  if (!start && !end) return "";
  return `${start ? fmt(start) : "?"} – ${end ? fmt(end) : "Present"}`;
}

// Picture addresses from the server look like "/media/profile_pics/x.png" (no host).
// The browser must ask the API server for them, not the React dev server.
export const mediaUrl = (path) => (path ? (/^https?:/i.test(path) ? path : `${API_URL}${path}`) : null);

export const MAX_IMAGE_BYTES = 2 * 1024 * 1024;

export function checkImageFile(file) {
  if (!file) return "Choose a picture.";
  if (!/\.(png|jpe?g|webp)$/i.test(file.name)) return "The picture must be a PNG, JPEG or WebP image.";
  if (file.size === 0) return "That file is empty.";
  if (file.size > MAX_IMAGE_BYTES) return "The picture must be 2 MB or smaller.";
  return "";
}
