// Slice 2: jobs and companies.
//   state.jobs.search     the job search results  (one query object, see store/query.js)
//   state.jobs.byId[id]   one job's detail page   (a query object per job id)
//   state.jobs.companies  every company we have seen in a job result, by id (company cards, no second request)
import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { getJob, searchJobs } from "../services/jobService";
import { addQueryCases, emptyQuery, failure, IDLE_QUERY } from "./query";

export const fetchJobs = createAsyncThunk("jobs/fetchJobs", async (params, { rejectWithValue }) => {
  try {
    return await searchJobs(params);
  } catch (error) {
    return failure(error, rejectWithValue);
  }
});

export const fetchJob = createAsyncThunk("jobs/fetchJob", async (id, { rejectWithValue }) => {
  try {
    return await getJob(id);
  } catch (error) {
    return failure(error, rejectWithValue);
  }
});

const jobsSlice = createSlice({
  name: "jobs",
  initialState: { search: emptyQuery(), byId: {}, companies: {} },
  reducers: {},
  extraReducers: (builder) => {
    // Besides the results themselves, remember the companies that came with the jobs.
    addQueryCases(builder, fetchJobs, (state) => state.search, (state, action) => {
      for (const job of action.payload.items ?? []) {
        if (job.company?.id) state.companies[job.company.id] = job.company;
      }
    });
    addQueryCases(builder, fetchJob, (state, action) => (state.byId[action.meta.arg] ??= emptyQuery()), (state, action) => {
      const company = action.payload.company;
      if (company?.id) state.companies[company.id] = company;
    });
  },
});

export default jobsSlice.reducer;

// Selectors
export const selectJobSearch = (state) => state.jobs.search;
export const selectJobQuery = (id) => (state) => state.jobs.byId[id] ?? IDLE_QUERY;
export const selectCompanyById = (id) => (state) => state.jobs.companies[id] ?? null;
export const selectCompanies = (state) => state.jobs.companies;
