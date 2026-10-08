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
