// Slice 5: saved items.
//   state.saved.items = [{ itemType: "job" | "event", itemId, label }]
//
// The only way to save a job or event in this app is through the assistant (tool save_job_or_event, after the student
// says yes). The server has no endpoint that lists saved items, so this slice remembers what the assistant saved
// during this session: it reads the assistant's answer (extraReducers) and adds an item when the save really happened.
import { createSlice } from "@reduxjs/toolkit";
import { sendAssistantMessage } from "./assistantSlice";

const savedSlice = createSlice({
  name: "saved",
  initialState: { items: [] },
  reducers: {
    savedItemsCleared: (state) => {
      state.items = [];
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(sendAssistantMessage.fulfilled, (state, action) => {
        for (const call of action.payload.tool_calls ?? []) {
          // A result starting with "Saved" means the row was written; a refusal or "already saved" does not count.
          if (call.name !== "save_job_or_event" || !String(call.result ?? "").startsWith("Saved")) continue;
          const { item_type: itemType, item_id: itemId } = call.arguments ?? {};
          if (!state.items.some((i) => i.itemType === itemType && i.itemId === itemId)) {
            state.items.push({ itemType, itemId, label: String(call.result).replace(/^Saved: /, "") });
          }
        }
      });
    // (Logging in or out resets this slice too: see rootReducer in store/index.js.)
  },
});

export const { savedItemsCleared } = savedSlice.actions;
export default savedSlice.reducer;

// Selectors
export const selectSavedItems = (state) => state.saved.items;
export const selectSavedCount = (state) => state.saved.items.length;
