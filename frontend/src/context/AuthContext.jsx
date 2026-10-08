// "Who is logged in?", available to every component through useAuth().
//
// The session ({ token, user: { id, role, name } }) is kept in localStorage so a page
// refresh doesn't log you out. On start-up, if a session is stored, we ask the server
// (GET /auth/me) whether the token is still good before showing any protected screen.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import * as authService from "../services/authService";
import { STORAGE_KEY, readStoredSession, setUnauthorizedHandler } from "../services/api";

const AuthContext = createContext(null);

function saveSession(session) {
  if (session) localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  else localStorage.removeItem(STORAGE_KEY);
}

// The server's answer to login/signup -> what we keep.
const toSession = (reply) => ({
  token: reply.access_token,
  user: { id: reply.user_id, role: reply.role, name: reply.name },
});

export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => readStoredSession());
  const [checking, setChecking] = useState(() => Boolean(readStoredSession()));
  const [sessionExpired, setSessionExpired] = useState(false);

  const clearSession = useCallback((expired = false) => {
    saveSession(null);
    setSession(null);
    setSessionExpired(expired);
  }, []);

  // Any 401 from the API on a normal request means the token is no longer valid.
  useEffect(() => {
    setUnauthorizedHandler(() => clearSession(true));
    return () => setUnauthorizedHandler(null);
  }, [clearSession]);

  // On start-up: is the stored token still valid?
  useEffect(() => {
    const stored = readStoredSession();
    if (!stored) return undefined;
    let active = true;
    authService
      .getMe()
      .then((me) => {
        if (!active) return;
        const refreshed = { token: stored.token, user: { id: me.id, role: me.role, name: me.name } };
        saveSession(refreshed);
        setSession(refreshed);
      })
      .catch((error) => {
        // Only a 401 means "this token is no longer valid". If the server is just unreachable
        // we keep the session, and the screens show their own "cannot reach the server" message.
        if (active && error.response?.status === 401) clearSession(true);
      })
      .finally(() => active && setChecking(false));
    return () => {
      active = false;
    };
  }, [clearSession]);

  const startSession = useCallback((reply) => {
    const next = toSession(reply);
    saveSession(next);
    setSession(next);
    setSessionExpired(false);
    return next.user;
  }, []);

  const login = useCallback(async (credentials) => startSession(await authService.login(credentials)), [startSession]);

  const signup = useCallback(
    async (role, form) =>
      startSession(await (role === "company" ? authService.signupCompany(form) : authService.signupStudent(form))),
    [startSession]
  );

  const logout = useCallback(async () => {
    try {
      await authService.logoutRequest();
    } catch {
      // Even if the server can't be reached we still sign out on this device.
    }
    clearSession(false);
  }, [clearSession]);

  const value = useMemo(
    () => ({ user: session?.user ?? null, isAuthenticated: Boolean(session), checking, sessionExpired, login, signup, logout }),
    [session, checking, sessionExpired, login, signup, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
