// The Redux store: one place that holds the state the pages share.
//
//   auth          who is logged in
//   jobs          job search, job details, companies
//   applications  my applications, and applications being sent (the 202)
//   events        event search, details, my registrations
//   saved         jobs and events the assistant saved
//   assistant     the conversation with the assistant
//
// Redux DevTools (the browser extension) shows every action and the state after it: the store is named "Handshake p06".
import { combineReducers, configureStore } from "@reduxjs/toolkit";
import { STORAGE_KEY } from "../services/api";
import applications from "./applicationsSlice";
import assistant, { conversationRestored, initialAssistantState } from "./assistantSlice";
import auth, { sessionCleared, sessionStarted } from "./authSlice";
import events from "./eventsSlice";
import jobs from "./jobsSlice";
import saved from "./savedSlice";

const appReducer = combineReducers({ auth, jobs, applications, events, saved, assistant });

// Logging in or out wipes everything that belongs to the previous person (their jobs list, their chat...).
const rootReducer = (state, action) => {
  if (sessionCleared.match(action) || sessionStarted.match(action)) {
    const { auth: current } = state ?? {};
    state = current ? { auth: current } : undefined;   // keep auth (its own reducer handles the action), reset the rest
  }
  return appReducer(state, action);
};

// ---- keeping the session and the conversation across a page refresh ----
const assistantKey = (userId) => `p06_assistant_${userId}`;

function readAssistant(userId) {
  try {
    const stored = JSON.parse(sessionStorage.getItem(assistantKey(userId)));
    return stored && Array.isArray(stored.messages) ? { ...initialAssistantState(), ...stored } : undefined;
  } catch {
    return undefined;   // private window, blocked storage or damaged text: just start a new conversation
  }
}

function persist(store) {
  let last = store.getState();
  store.subscribe(() => {
    const now = store.getState();
    try {
      if (now.auth.token !== last.auth.token || now.auth.user !== last.auth.user) {
        if (now.auth.token) localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: now.auth.token, user: now.auth.user }));
        else localStorage.removeItem(STORAGE_KEY);
      }
      if (last.auth.user && !now.auth.user) sessionStorage.removeItem(assistantKey(last.auth.user.id));
      if (now.auth.user && now.assistant !== last.assistant) {
        const { conversationId, messages } = now.assistant;
        sessionStorage.setItem(assistantKey(now.auth.user.id), JSON.stringify({ conversationId, messages }));
      }
    } catch {
      // storage is optional: the app works without it
    }
    last = now;
  });
}

export function makeStore() {
  const store = configureStore({
    reducer: rootReducer,
    devTools: { name: "Handshake p06" },
    middleware: (getDefault) =>
      getDefault({ serializableCheck: { ignoredActionPaths: ["meta.arg"] } }),   // meta.arg holds the resume File
  });
  // Bring back this person's conversation after a refresh.
  const user = store.getState().auth.user;
  const stored = user ? readAssistant(user.id) : undefined;
  if (stored) store.dispatch(conversationRestored(stored));
  persist(store);
  return store;
}

const store = makeStore();
export default store;
