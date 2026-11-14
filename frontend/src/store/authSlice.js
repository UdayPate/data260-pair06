// Slice 1: authentication and session.  state.auth = { token, user, checking, sessionExpired }
//
//   user     { id, role, name } of the person logged in, or null
//   checking true while we ask the server "is the stored token still good?" at start-up
// The session is also written to localStorage by store/index.js, so a page refresh does not log you out.
import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { readStoredSession } from "../services/api";
import * as authService from "../services/authService";

export function initialAuthState() {
  const stored = readStoredSession();
  return { token: stored?.token ?? null, user: stored?.user ?? null, checking: Boolean(stored), sessionExpired: false };
}

// Start-up check: GET /auth/me. Only a 401 means the token is no longer valid; if the server is just unreachable the
// session is kept and the screens show their own "cannot reach the server" message.
export const restoreSession = createAsyncThunk(
  "auth/restoreSession",
  async (_arg, { rejectWithValue }) => {
    try {
      const me = await authService.getMe();
      return { id: me.id, role: me.role, name: me.name };
    } catch (error) {
      return rejectWithValue({ unauthorized: error.response?.status === 401 });
    }
  },
  { condition: (_arg, { getState }) => Boolean(getState().auth.token) }   // nobody logged in: nothing to check
);

const authSlice = createSlice({
  name: "auth",
  initialState: initialAuthState,
  reducers: {
    // payload: { token, user }  (after a successful login or signup)
    sessionStarted(state, action) {
      state.token = action.payload.token;
      state.user = action.payload.user;
      state.checking = false;
      state.sessionExpired = false;
    },
    // payload: true when the server said the token expired (shows "your session expired" on the login page)
    sessionCleared(state, action) {
      state.token = null;
      state.user = null;
      state.checking = false;
      state.sessionExpired = Boolean(action.payload);
    },
    // After the profile is saved the name may have changed; keep the top bar in step.
    userNameUpdated(state, action) {
      if (state.user) state.user.name = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(restoreSession.fulfilled, (state, action) => {
        state.user = action.payload;
        state.checking = false;
      })
      .addCase(restoreSession.rejected, (state, action) => {
        state.checking = false;
        if (action.payload?.unauthorized) {
          state.token = null;
          state.user = null;
          state.sessionExpired = true;
        }
      });
  },
});

export const { sessionStarted, sessionCleared, userNameUpdated } = authSlice.actions;
export default authSlice.reducer;

// Selectors: the only way components read this slice.
export const selectAuth = (state) => state.auth;
export const selectUser = (state) => state.auth.user;
export const selectIsAuthenticated = (state) => Boolean(state.auth.token);
