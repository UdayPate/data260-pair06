// The chat with the AI assistant. One endpoint: POST /assistant/chat.
//   send:    { message, conversation_id }      (conversation_id is null for a new conversation)
//   receive: { reply, conversation_id, tool_calls: [ { name, arguments, result } ] }
import api from "./api";

// A local model can take a while to think, so this request waits much longer than the usual 15 s.
const CHAT_TIMEOUT_MS = 120000;

export function sendMessage(message, conversationId) {
  return api
    .post("/assistant/chat", { message, conversation_id: conversationId ?? null }, { timeout: CHAT_TIMEOUT_MS })
    .then((r) => r.data);
}
