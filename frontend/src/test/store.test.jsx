// The Redux store (src/store): actions, reducers, selectors, and the two behaviours the assignment names:
//   * the applications slice handles the 202 of POST /jobs/{id}/apply
//   * the student can leave the assistant and come back without losing the conversation thread
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { STORAGE_KEY } from "../services/api";
import { fetchMyApplications, selectSubmission, submitApplication } from "../store/applicationsSlice";
import { conversationReset, selectAssistant, selectAssistantUsage, sendAssistantMessage } from "../store/assistantSlice";
import { restoreSession, selectIsAuthenticated, selectUser, sessionCleared, sessionStarted } from "../store/authSlice";
import { fetchEvent, registerEvent, selectEventQuery, selectRegistration } from "../store/eventsSlice";
import { makeStore } from "../store";
import { fetchJob, fetchJobs, selectCompanyById, selectJobQuery, selectJobSearch } from "../store/jobsSlice";
import { selectSavedItems } from "../store/savedSlice";
import { STUDENT, mock, mockDashboard, mockMe, renderApp, storeSession } from "./helpers";

const chatReply = (reply, id = "conv-1", tool_calls = []) => [200, { reply, conversation_id: id, tool_calls }];
const pdf = new File(["%PDF-1.4"], "cv.pdf", { type: "application/pdf" });

// ---------------------------------------------------------------- slice 1: authentication
describe("auth slice", () => {
  it("starts logged out and logs in and out through actions", () => {
    const store = makeStore();
    expect(selectIsAuthenticated(store.getState())).toBe(false);
    store.dispatch(sessionStarted({ token: "t1", user: STUDENT }));
    expect(selectUser(store.getState())).toEqual(STUDENT);
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY))).toEqual({ token: "t1", user: STUDENT });   // survives a refresh
    store.dispatch(sessionCleared(false));
    expect(selectUser(store.getState())).toBeNull();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("a stored session is picked up at start-up and checked with GET /auth/me", async () => {
    storeSession(STUDENT);
    mockMe({ ...STUDENT, name: "Ada Renamed" });
    const store = makeStore();
    expect(store.getState().auth.checking).toBe(true);
    await store.dispatch(restoreSession());
    expect(store.getState().auth).toMatchObject({ checking: false, user: { name: "Ada Renamed" } });
  });

  it("a 401 on the start-up check clears the session and says it expired", async () => {
    storeSession(STUDENT);
    mock.onGet("/auth/me").reply(401, { detail: "expired" });
    const store = makeStore();
    await store.dispatch(restoreSession());
    expect(store.getState().auth).toMatchObject({ token: null, user: null, sessionExpired: true, checking: false });
  });

  it("an unreachable server keeps the session (only a 401 ends it)", async () => {
    storeSession(STUDENT);
    mock.onGet("/auth/me").networkError();
    const store = makeStore();
    await store.dispatch(restoreSession());
    expect(selectUser(store.getState())).toEqual(STUDENT);
  });

  it("logging out wipes the other slices too", async () => {
    const store = makeStore();
    store.dispatch(sessionStarted({ token: "t1", user: STUDENT }));
    mock.onPost("/assistant/chat").reply(...chatReply("hi"));
    await store.dispatch(sendAssistantMessage({ text: "hello" }));
    expect(selectAssistant(store.getState()).messages).toHaveLength(2);
    store.dispatch(sessionCleared(false));
    expect(selectAssistant(store.getState()).messages).toEqual([]);
  });
});

// ---------------------------------------------------------------- slice 2: jobs and companies
describe("jobs slice", () => {
  const page = (items) => ({ items, total: items.length, page: 1, page_size: 10, total_pages: 1 });

  it("keeps the search results and the companies that came with them", async () => {
    const store = makeStore();
    expect(selectJobSearch(store.getState()).status).toBe("idle");
    mock.onGet("/jobs").reply(200, page([{ id: 1, title: "Data Intern", company: { id: 9, name: "Acme" } }]));
    const done = store.dispatch(fetchJobs({ q: "data" }));
    expect(selectJobSearch(store.getState()).status).toBe("loading");
    await done;
    expect(selectJobSearch(store.getState())).toMatchObject({ status: "succeeded", data: { total: 1 } });
    expect(selectCompanyById(9)(store.getState())).toEqual({ id: 9, name: "Acme" });
  });

  it("a failed request keeps a readable message, not an Axios error", async () => {
    const store = makeStore();
    mock.onGet("/jobs/7").reply(404, { detail: "Job not found" });
    await store.dispatch(fetchJob("7"));
    expect(selectJobQuery("7")(store.getState())).toMatchObject({ status: "failed", error: "Job not found", data: null });
  });

  it("an older, slower answer never overwrites a newer one", async () => {
    const store = makeStore();
    let calls = 0;
    mock.onGet("/jobs").reply(() => {
      calls += 1;
      const mine = calls;
      return new Promise((resolve) => setTimeout(() => resolve([200, page([{ id: mine, title: `search ${mine}` }])]), mine === 1 ? 60 : 0));
    });
    await Promise.all([store.dispatch(fetchJobs({ q: "first" })), store.dispatch(fetchJobs({ q: "second" }))]);
    expect(selectJobSearch(store.getState()).data.items[0].title).toBe("search 2");   // the first one finished last and was ignored
  });
});

// ---------------------------------------------------------------- slice 3: applications and the 202
describe("applications slice", () => {
  it("handles the 202: 'received' is not 'saved', and the job coming back with my_application is", async () => {
    const store = makeStore();
    expect(selectSubmission(5)(store.getState()).status).toBe("idle");
    mock.onPost("/jobs/5/apply").reply(202, { status: "received" });
    const sending = store.dispatch(submitApplication({ jobId: 5, file: pdf }));
    expect(selectSubmission(5)(store.getState()).status).toBe("sending");
    await sending;
    expect(selectSubmission(5)(store.getState()).status).toBe("received");     // queued, NOT in the database yet

    mock.onGet("/jobs/5").replyOnce(200, { id: 5, title: "x", company: { id: 1, name: "A" }, my_application: null });
    await store.dispatch(fetchJob(5));
    expect(selectSubmission(5)(store.getState()).status).toBe("received");     // the worker has not finished: still waiting

    mock.onGet("/jobs/5").replyOnce(200, { id: 5, title: "x", company: { id: 1, name: "A" }, my_application: { status: "Pending" } });
    await store.dispatch(fetchJob(5));
    expect(selectSubmission(5)(store.getState()).status).toBe("saved");        // the worker wrote it
  });

  it("a refusal is kept as a readable message", async () => {
    const store = makeStore();
    mock.onPost("/jobs/6/apply").reply(409, { detail: "You already applied to this job" });
    await store.dispatch(submitApplication({ jobId: 6, file: pdf }));
    expect(selectSubmission(6)(store.getState())).toEqual({ status: "failed", error: "You already applied to this job" });
  });

  it("loads my applications into the store", async () => {
    const store = makeStore();
    mock.onGet("/applications/mine").reply(200, { items: [{ id: 1 }], total: 1, page: 1, page_size: 10, total_pages: 1 });
    await store.dispatch(fetchMyApplications({ page: 1 }));
    expect(store.getState().applications.mine.data.items).toEqual([{ id: 1 }]);
  });
});

// ---------------------------------------------------------------- slice 4: events and registrations
describe("events slice", () => {
  it("registers and remembers the state of that registration", async () => {
    const store = makeStore();
    mock.onGet("/events/3").reply(200, { id: 3, name: "Fair", registered: false, company: { id: 1, name: "A" } });
    await store.dispatch(fetchEvent("3"));
    expect(selectEventQuery("3")(store.getState()).data.name).toBe("Fair");
    mock.onPost("/events/3/register").reply(201, { id: 3 });
    const registering = store.dispatch(registerEvent("3"));
    expect(selectRegistration("3")(store.getState())).toMatchObject({ status: "working", action: "register" });
    await registering;
    expect(selectRegistration("3")(store.getState()).status).toBe("done");
  });

  it("a refused registration is kept as a readable message", async () => {
    const store = makeStore();
    mock.onPost("/events/4/register").reply(403, { detail: "This event is not open to your major" });
    await store.dispatch(registerEvent("4"));
    expect(selectRegistration("4")(store.getState())).toMatchObject({ status: "failed", error: "This event is not open to your major" });
  });
});

// ---------------------------------------------------------------- slice 5: saved items
describe("saved slice", () => {
  const saved = { name: "save_job_or_event", arguments: { item_type: "job", item_id: 12 }, result: "Saved: the job 12 (Data Intern) is now in the student's saved list." };

  it("remembers an item only when the assistant really saved it, once", async () => {
    const store = makeStore();
    mock.onPost("/assistant/chat").replyOnce(...chatReply("Saved.", "c1", [saved]));
    await store.dispatch(sendAssistantMessage({ text: "save job 12" }));
    mock.onPost("/assistant/chat").replyOnce(...chatReply("Saved again?", "c1", [saved]));
    await store.dispatch(sendAssistantMessage({ text: "save it again" }));
    expect(selectSavedItems(store.getState())).toEqual([
      { itemType: "job", itemId: 12, label: "the job 12 (Data Intern) is now in the student's saved list." }]);

    mock.onPost("/assistant/chat").replyOnce(...chatReply("No.", "c1", [{ ...saved, arguments: { item_type: "job", item_id: 99 },
      result: "CANCELLED: the student declined, so nothing was saved." }]));
    await store.dispatch(sendAssistantMessage({ text: "save job 99" }));
    expect(selectSavedItems(store.getState())).toHaveLength(1);       // a declined save is not remembered
  });
});

// ---------------------------------------------------------------- slice 6: the assistant conversation
describe("assistant slice", () => {
  it("builds the thread from actions: user message, then the answer, and keeps the conversation id", async () => {
    const store = makeStore();
    mock.onPost("/assistant/chat").replyOnce(...chatReply("Hello!", "conv-7"));
    const sending = store.dispatch(sendAssistantMessage({ text: "hi" }));
    expect(selectAssistant(store.getState())).toMatchObject({ status: "sending", messages: [{ role: "user", text: "hi" }] });
    await sending;
    expect(selectAssistant(store.getState())).toMatchObject({
      status: "idle", conversationId: "conv-7", messages: [{ role: "user" }, { role: "assistant", text: "Hello!" }] });
    mock.onPost("/assistant/chat").replyOnce(...chatReply("Again!", "conv-7"));
    await store.dispatch(sendAssistantMessage({ text: "more" }));
    expect(JSON.parse(mock.history.post.at(-1).data).conversation_id).toBe("conv-7");     // the same conversation continues
  });

  it("a failure keeps the thread, shows an error, and a retry does not add the user's message twice", async () => {
    const store = makeStore();
    mock.onPost("/assistant/chat").replyOnce(500, { detail: "model down" });
    await store.dispatch(sendAssistantMessage({ text: "hi" }));
    expect(selectAssistant(store.getState())).toMatchObject({ error: "model down", failedText: "hi", messages: [{ text: "hi" }] });
    mock.onPost("/assistant/chat").replyOnce(...chatReply("Back!"));
    await store.dispatch(sendAssistantMessage({ text: "hi", retry: true }));
    expect(selectAssistant(store.getState()).messages.map((m) => m.text)).toEqual(["hi", "Back!"]);
    expect(selectAssistant(store.getState()).error).toBe("");
  });

  it("'New conversation' empties the thread", async () => {
    const store = makeStore();
    mock.onPost("/assistant/chat").reply(...chatReply("x"));
    await store.dispatch(sendAssistantMessage({ text: "hi" }));
    store.dispatch(conversationReset());
    expect(selectAssistant(store.getState())).toMatchObject({ conversationId: null, messages: [] });
  });

  it("the thread survives a page refresh (sessionStorage) but not for another person", async () => {
    storeSession(STUDENT);
    const before = makeStore();
    mock.onPost("/assistant/chat").reply(...chatReply("I am here", "conv-9"));
    await before.dispatch(sendAssistantMessage({ text: "remember me" }));

    const after = makeStore();                                          // a "refresh": a new store, same browser tab
    expect(selectAssistant(after.getState())).toMatchObject({ conversationId: "conv-9", messages: [{ text: "remember me" }, { text: "I am here" }] });

    localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: "other", user: { id: 2, role: "student", name: "Bob" } }));
    expect(selectAssistant(makeStore().getState()).messages).toEqual([]);     // Bob must not see Ada's chat
  });
});

// ---------------------------------------------------------------- leave the assistant and come back
describe("leaving the assistant and coming back", () => {
  it("the same store keeps the thread when the home page is closed and opened again", async () => {
    const user = userEvent.setup();
    storeSession(STUDENT);
    mockMe(STUDENT);
    mockDashboard("student");
    mock.onPost("/assistant/chat").reply(...chatReply("Here are two internships.", "conv-3"));
    const store = makeStore();

    const first = renderApp("/", store);
    await user.type(await screen.findByLabelText("Message to the assistant"), "find internships{Enter}");
    expect(await screen.findByText("Here are two internships.")).toBeInTheDocument();
    first.unmount();                                                    // leave: the whole home page is gone

    mock.onGet("/students/me/activity").reply(200, []);
    renderApp("/", store);                                              // come back
    expect(await screen.findByText("Here are two internships.")).toBeInTheDocument();
    expect(screen.getByTestId("chat-user")).toHaveTextContent("find internships");
    await user.type(screen.getByLabelText("Message to the assistant"), "and another{Enter}");
    await screen.findAllByTestId("chat-assistant");
    expect(JSON.parse(mock.history.post.at(-1).data).conversation_id).toBe("conv-3");   // it is still the same conversation
  });
});

// ---------------------------------------------------------------- token usage in the assistant slice and the chat window
const usageInfo = (percent, extra = {}) => ({
  model_calls: 2, prompt_tokens: 9000, completion_tokens: 300, total_tokens: 9300, context_tokens: Math.round((percent / 100) * 8192),
  context_window: 8192, context_percent: percent, context_estimated: false, warn: percent > 70, compact_recommended: percent >= 85,
  compactions: 0, ...extra,
});
const chatWithUsage = (reply, usage, id = "conv-u") => [200, { reply, conversation_id: id, tool_calls: [], trace_id: "t-1", usage }];

describe("token usage", () => {
  it("the slice keeps the usage of the last answer, and a command without usage does not erase it", async () => {
    const store = makeStore();
    mock.onPost("/assistant/chat").replyOnce(...chatWithUsage("hi", usageInfo(40)));
    await store.dispatch(sendAssistantMessage({ text: "hello" }));
    expect(selectAssistantUsage(store.getState())).toMatchObject({ context_percent: 40, warn: false });
    mock.onPost("/assistant/chat").replyOnce(200, { reply: "no notes yet", conversation_id: "conv-u", tool_calls: [], usage: null });
    await store.dispatch(sendAssistantMessage({ text: "/memory" }));
    expect(selectAssistantUsage(store.getState()).context_percent).toBe(40);
    store.dispatch(conversationReset());
    expect(selectAssistantUsage(store.getState())).toBeNull();
  });

  it("the chat window shows the tokens and the context percent, with no warning at 70 percent or below", async () => {
    const user = userEvent.setup();
    storeSession(STUDENT);
    mockMe(STUDENT);
    mockDashboard("student");
    mock.onPost("/assistant/chat").reply(...chatWithUsage("hello", usageInfo(60)));
    renderApp("/");
    await user.type(await screen.findByLabelText("Message to the assistant"), "hi{Enter}");
    const line = await screen.findByTestId("token-usage");
    expect(line).toHaveTextContent("Tokens used: 9,300");
    expect(line).toHaveTextContent("60% full");
    expect(screen.queryByTestId("context-warning")).not.toBeInTheDocument();
  });

  it("warns above 70 percent, and the Compact button sends /compact and shows the smaller usage", async () => {
    const user = userEvent.setup();
    storeSession(STUDENT);
    mockMe(STUDENT);
    mockDashboard("student");
    mock.onPost("/assistant/chat").replyOnce(...chatWithUsage("long answer", usageInfo(78)));
    renderApp("/");
    await user.type(await screen.findByLabelText("Message to the assistant"), "hi{Enter}");
    const warning = await screen.findByTestId("context-warning");
    expect(warning).toHaveTextContent("78%");

    mock.onPost("/assistant/chat").replyOnce(...chatWithUsage("Compacted: 14 messages became 2.", usageInfo(21, { compactions: 1, context_estimated: true })));
    await user.click(within(warning).getByRole("button", { name: "Compact" }));
    expect(await screen.findByText(/Compacted: 14 messages became 2/)).toBeInTheDocument();
    expect(JSON.parse(mock.history.post.at(-1).data).message).toBe("/compact");
    expect(await screen.findByTestId("token-usage")).toHaveTextContent("about 21% full");        // an estimate until the next answer
    expect(screen.queryByTestId("context-warning")).not.toBeInTheDocument();
  });
});
