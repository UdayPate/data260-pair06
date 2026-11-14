// "Who is logged in?", available to every component through useAuth().
//
// Lab 2: the state now lives in the Redux store (store/authSlice.js) instead of in this component. useAuth() keeps the
// same answer shape as before, so no page had to change: it reads the auth slice with selectors and its functions
// dispatch actions. The session is also kept in localStorage (store/index.js) so a page refresh doesn't log you out.
// On start-up, if a session is stored, we ask the server (GET /auth/me) whether the token is still good.
import { useCallback, useEffect, useMemo } from "react";
import { useDispatch, useSelector } from "react-redux";
import { setUnauthorizedHandler } from "../services/api";
import * as authService from "../services/authService";
import { restoreSession, selectAuth, sessionCleared, sessionStarted, userNameUpdated } from "../store/authSlice";

// The server's answer to login/signup -> what we keep.
const toSession = (reply) => ({
  token: reply.access_token,
  user: { id: reply.user_id, role: reply.role, name: reply.name },
});

// Wrap the app in this (inside the Redux <Provider>). It does the two start-up jobs; it renders nothing itself.
export function AuthProvider({ children }) {
  const dispatch = useDispatch();

  // Any 401 from the API on a normal request means the token is no longer valid.
  useEffect(() => {
    setUnauthorizedHandler(() => dispatch(sessionCleared(true)));
    return () => setUnauthorizedHandler(null);
  }, [dispatch]);

  // On start-up: is the stored token still valid?
  useEffect(() => {
    dispatch(restoreSession());
  }, [dispatch]);

  return children;
}

export function useAuth() {
  const dispatch = useDispatch();
  const { user, token, checking, sessionExpired } = useSelector(selectAuth);

  const startSession = useCallback(
    (reply) => {
      const next = toSession(reply);
      dispatch(sessionStarted(next));
      return next.user;
    },
    [dispatch]
  );

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
    dispatch(sessionCleared(false));
  }, [dispatch]);

  const updateUserName = useCallback((name) => dispatch(userNameUpdated(name)), [dispatch]);

  return useMemo(
    () => ({
      user, isAuthenticated: Boolean(token), checking, sessionExpired,
      login, signup, logout, updateUserName,
    }),
    [user, token, checking, sessionExpired, login, signup, logout, updateUserName]
  );
}
