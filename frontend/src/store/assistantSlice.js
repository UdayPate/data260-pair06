// Slice 6: the assistant conversation.
//   state.assistant = { conversationId, messages, status, error, failedText }
//
// WHY THIS IS IN REDUX: the chat used to live in the ChatWindow component, so leaving the home page (or opening a job)
// threw the conversation away. Now the thread is in the store: the student can leave the assistant, browse, and come
// back to the same conversation. store/index.js also copies it to sessionStorage, so a page refresh keeps it too,
// and the server keeps the conversation in MongoDB under the same conversationId.
import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { sendMessage } from "../services/assistantService";
import { getErrorMessage } from "../utils/errors";

export const initialAssistantState = () => ({
  conversationId: null,
  messages: [],            // [{ role: "user" | "assistant", text, toolCalls }]
  status: "idle",          // "idle" | "sending"
  error: "",
  failedText: "",          // the message that got no answer (the "Try again" button sends it again)
  usage: null,             // token usage from the last answer: { total_tokens, context_percent, warn, context_window, ... }
});

// arg: { text, retry }   (retry = true re-sends a failed message without adding it to the thread twice)
export const sendAssistantMessage = createAsyncThunk(
  "assistant/send",
  async ({ text }, { getState, rejectWithValue }) => {
    try {
      return await sendMessage(text, getState().assistant.conversationId);
    } catch (error) {
      return rejectWithValue(getErrorMessage(error, "The assistant could not answer. Please try again."));
    }
  }
);

const assistantSlice = createSlice({
  name: "assistant",
  initialState: initialAssistantState,
  reducers: {
    // "New conversation": forget the thread (the next message starts a new conversation on the server)
    conversationReset: () => initialAssistantState(),
    // After a page refresh: put back the thread that store/index.js saved in sessionStorage
    conversationRestored: (_state, action) => ({ ...initialAssistantState(), ...action.payload }),
  },
  extraReducers: (builder) => {
    builder
      .addCase(sendAssistantMessage.pending, (state, action) => {
        state.status = "sending";
        state.error = "";
        state.failedText = "";
        if (!action.meta.arg.retry) state.messages.push({ role: "user", text: action.meta.arg.text });
      })
      .addCase(sendAssistantMessage.fulfilled, (state, action) => {
        state.status = "idle";
        state.conversationId = action.payload.conversation_id;
        state.messages.push({ role: "assistant", text: action.payload.reply, toolCalls: action.payload.tool_calls });
        // The server counts the tokens (Part 6). A command such as /memory has no usage: keep what we had.
        if (action.payload.usage) state.usage = action.payload.usage;
      })
      .addCase(sendAssistantMessage.rejected, (state, action) => {
        state.status = "idle";
        state.error = action.payload ?? action.error.message;
        state.failedText = action.meta.arg.text;
      });
  },
});

export const { conversationReset, conversationRestored } = assistantSlice.actions;
export default assistantSlice.reducer;

// Selectors
export const selectAssistant = (state) => state.assistant;
export const selectAssistantMessages = (state) => state.assistant.messages;
export const selectAssistantBusy = (state) => state.assistant.status === "sending";
export const selectAssistantUsage = (state) => state.assistant.usage;
