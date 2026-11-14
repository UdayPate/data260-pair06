// Shared pieces for the slices that load things from the server.
//
// Every "thing we load" (the job search results, one job, my applications...) is kept in the store as a small
// QUERY object:   { data, status, error, requestId }
//   status    "idle" (never asked) | "loading" | "succeeded" | "failed"
//   requestId the id of the LATEST request. If an older request finishes after a newer one was started, its answer is
//             ignored, so a slow answer can never overwrite a newer search.
// This is exactly what the useAsync hook used to keep in the component; now it lives in the store.
import { getErrorMessage } from "../utils/errors";

export const emptyQuery = () => ({ data: null, status: "idle", error: null, requestId: null });
export const IDLE_QUERY = Object.freeze(emptyQuery());   // one shared object so useSelector does not see a "change" every render

// Adds the three reducers (pending, fulfilled, rejected) of a thunk to a slice.
// `pick(state, action)` says which query object of the slice this thunk updates.
// `alsoOnSuccess(state, action)` (optional) is extra work to do when the request succeeds. It is passed in here because
// Redux Toolkit allows only ONE reducer per action type: a slice cannot add a second case for the same "fulfilled".
export function addQueryCases(builder, thunk, pick, alsoOnSuccess) {
  builder
    .addCase(thunk.pending, (state, action) => {
      const query = pick(state, action);
      query.status = "loading";
      query.error = null;                         // the old data stays visible while the new request runs
      query.requestId = action.meta.requestId;
    })
    .addCase(thunk.fulfilled, (state, action) => {
      const query = pick(state, action);
      if (query.requestId !== action.meta.requestId) return;   // an older request: ignore it
      query.status = "succeeded";
      query.data = action.payload;
      if (alsoOnSuccess) alsoOnSuccess(state, action);
    })
    .addCase(thunk.rejected, (state, action) => {
      const query = pick(state, action);
      if (query.requestId !== action.meta.requestId) return;
      query.status = "failed";
      query.error = action.payload ?? action.error.message;
      query.data = null;
    });
}

// What a thunk's payload creator does on failure: turn the Axios error into one readable sentence.
export const failure = (error, rejectWithValue, fallback) => rejectWithValue(getErrorMessage(error, fallback));
