// Slice 4: events and registrations.
//   state.events.search        the event search results (query object)
//   state.events.byId[id]      one event's detail page (query object per event)
//   state.events.registered    the student's registered events (query object)
//   state.events.registrations [eventId] -> { status, action, error } while registering or cancelling
import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import {
  cancelRegistration, getEvent, getRegisteredEvents, registerForEvent, searchEvents,
} from "../services/eventService";
import { addQueryCases, emptyQuery, failure, IDLE_QUERY } from "./query";

const query = (name, call) =>
  createAsyncThunk(`events/${name}`, async (arg, { rejectWithValue }) => {
    try {
      return await call(arg);
    } catch (error) {
      return failure(error, rejectWithValue);
    }
  });

export const fetchEvents = query("fetchEvents", searchEvents);
export const fetchEvent = query("fetchEvent", getEvent);
export const fetchRegisteredEvents = query("fetchRegistered", getRegisteredEvents);
export const registerEvent = query("register", registerForEvent);          // arg: the event id
export const cancelEventRegistration = query("cancel", async (id) => {      // the DELETE answers 204 with no body
  await cancelRegistration(id);
  return { id };
});

const eventsSlice = createSlice({
  name: "events",
  initialState: { search: emptyQuery(), byId: {}, registered: emptyQuery(), registrations: {} },
  reducers: {},
  extraReducers: (builder) => {
    addQueryCases(builder, fetchEvents, (state) => state.search);
    addQueryCases(builder, fetchEvent, (state, action) => (state.byId[action.meta.arg] ??= emptyQuery()));
    addQueryCases(builder, fetchRegisteredEvents, (state) => state.registered);
    for (const [thunk, action] of [[registerEvent, "register"], [cancelEventRegistration, "cancel"]]) {
      builder
        .addCase(thunk.pending, (state, a) => {
          state.registrations[a.meta.arg] = { status: "working", action, error: "" };
        })
        .addCase(thunk.fulfilled, (state, a) => {
          state.registrations[a.meta.arg] = { status: "done", action, error: "" };
        })
        .addCase(thunk.rejected, (state, a) => {
          state.registrations[a.meta.arg] = { status: "failed", action, error: a.payload ?? a.error.message };
        });
    }
  },
});

export default eventsSlice.reducer;

// Selectors
const NO_REGISTRATION = Object.freeze({ status: "idle", action: null, error: "" });
export const selectEventSearch = (state) => state.events.search;
export const selectEventQuery = (id) => (state) => state.events.byId[id] ?? IDLE_QUERY;
export const selectRegisteredEvents = (state) => state.events.registered;
export const selectRegistration = (id) => (state) => state.events.registrations[id] ?? NO_REGISTRATION;
