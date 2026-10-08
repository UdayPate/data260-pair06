// The links shown in the navigation bar for each kind of user.
// Later steps add entries here when a new page is built.
export const NAV_LINKS = {
  student: [
    { to: "/", label: "Home", end: true },
    { to: "/jobs", label: "Jobs" },
    { to: "/applications", label: "My applications" },
    { to: "/events", label: "Events", end: true },
    { to: "/events/registered", label: "My events" },
    { to: "/students", label: "Students" },
  ],
  company: [{ to: "/", label: "Home", end: true }],
};
