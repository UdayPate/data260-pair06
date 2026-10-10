import { useEffect } from "react";

// Sets the colour theme: <html data-theme="student"> or <html data-theme="company">.
// theme.css reads that attribute. Pass a falsy value to leave the current theme alone.
// Used by App (from the logged-in role) and by the sign-in / sign-up pages (from the Student/Company switch).
export function useTheme(theme) {
  useEffect(() => {
    if (theme) document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);
}
