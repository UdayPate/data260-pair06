// Slice 3: applications.
//   state.applications.mine         the student's own applications (one query object)
//   state.applications.submissions  [jobId] -> { status, error } for an application being sent:
//        "sending"  the request is on its way
//        "received" the server answered 202 Accepted: the application is QUEUED, a Kafka worker saves it a moment later
//        "saved"    the job now has my_application (the worker finished)
//        "failed"   the server said no (a closed job, a bad file, already applied...)
//
// The 202 matters: POST /jobs/{id}/apply does not return the application, so "received" is NOT "saved".
// The job page keeps asking for the job until it shows my_application, and this slice then flips the status to "saved".
import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { applyToJob, getMyApplications } from "../services/jobService";
import { fetchJob } from "./jobsSlice";
import { addQueryCases, emptyQuery, failure } from "./query";

export const fetchMyApplications = createAsyncThunk("applications/fetchMine", async (params, { rejectWithValue }) => {
  try {
    return await getMyApplications(params);
  } catch (error) {
    return failure(error, rejectWithValue);
  }
});

// arg: { jobId, file }
export const submitApplication = createAsyncThunk("applications/submit", async ({ jobId, file }, { rejectWithValue }) => {
  try {
    await applyToJob(jobId, file);   // 202 Accepted
    return { jobId };
  } catch (error) {
    return failure(error, rejectWithValue);
  }
});

const applicationsSlice = createSlice({
  name: "applications",
  initialState: { mine: emptyQuery(), submissions: {} },
  reducers: {},
  extraReducers: (builder) => {
    addQueryCases(builder, fetchMyApplications, (state) => state.mine);
    builder
      .addCase(submitApplication.pending, (state, action) => {
        state.submissions[action.meta.arg.jobId] = { status: "sending", error: "" };
      })
      .addCase(submitApplication.fulfilled, (state, action) => {
        state.submissions[action.payload.jobId] = { status: "received", error: "" };
      })
      .addCase(submitApplication.rejected, (state, action) => {
        state.submissions[action.meta.arg.jobId] = { status: "failed", error: action.payload ?? action.error.message };
      })
      // The worker has saved the application once the job comes back with my_application.
      .addCase(fetchJob.fulfilled, (state, action) => {
        if (action.payload.my_application) state.submissions[action.payload.id] = { status: "saved", error: "" };
      });
  },
});

export default applicationsSlice.reducer;

// Selectors
const NO_SUBMISSION = Object.freeze({ status: "idle", error: "" });
export const selectMyApplications = (state) => state.applications.mine;
export const selectSubmission = (jobId) => (state) => state.applications.submissions[jobId] ?? NO_SUBMISSION;
