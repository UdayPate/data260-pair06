import { useEffect, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Card from "react-bootstrap/Card";
import Form from "react-bootstrap/Form";
import { conversationReset, selectAssistant, sendAssistantMessage } from "../store/assistantSlice";
import { selectSavedItems } from "../store/savedSlice";

const SUGGESTIONS = [
  "Find internships in my preferred cities",
  "Which upcoming events fit my major?",
  "Show jobs that match my skills",
];
const MAX_LENGTH = 2000;

// What the assistant did, shown under its answer so the student can see (and trust) the work.
function ToolCalls({ calls }) {
  if (!calls?.length) return null;
  return (
    <details className="chat-tools">
      <summary>Tools used ({calls.length})</summary>
      <ul className="mb-0">
        {calls.map((c, i) => (
          <li key={i}>
            <code>{c.name}</code>
            {c.arguments && Object.keys(c.arguments).length > 0 && <code className="ms-2">{JSON.stringify(c.arguments)}</code>}
          </li>
        ))}
      </ul>
    </details>
  );
}

// The chat box on the student's home page. The conversation lives in the Redux assistant slice (store/assistantSlice.js),
// NOT in this component: leaving the home page and coming back shows the same thread. Only the text being typed is local.
export default function ChatWindow() {
  const dispatch = useDispatch();
  const { messages, status, error, failedText, usage } = useSelector(selectAssistant);
  const saved = useSelector(selectSavedItems);       // what the assistant saved during this session
  const busy = status === "sending";
  const [text, setText] = useState("");
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages, busy]);

  function send(message, { retry = false } = {}) {
    const clean = message.trim();
    if (!clean || busy) return;
    setText("");
    dispatch(sendAssistantMessage({ text: clean, retry }));   // the slice adds the message, calls the server, adds the answer
  }

  function newConversation() {
    dispatch(conversationReset());
    setText("");
  }

  return (
    <Card className="chat-card" data-testid="assistant-card">
      <Card.Body>
        <div className="d-flex justify-content-between align-items-start mb-2">
          <div>
            <Card.Title as="h2" className="h5 mb-0">AI Assistant</Card.Title>
            <div className="text-muted small">Ask for jobs and events that fit you.</div>
          </div>
          {messages.length > 0 && (
            <Button variant="outline-secondary" size="sm" onClick={newConversation} disabled={busy}>New conversation</Button>
          )}
        </div>

        <div className="chat-log" role="log" aria-live="polite" aria-label="Conversation">
          {messages.length === 0 && !busy && (
            <div className="chat-empty">
              <p className="text-muted mb-2">Try asking:</p>
              <div className="d-flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <Button key={s} variant="outline-primary" size="sm" onClick={() => send(s)}>{s}</Button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`chat-row chat-${m.role}`}>
              <div className="chat-bubble" data-testid={`chat-${m.role}`}>
                {/* plain text only: the assistant's words are never inserted as HTML */}
                <div style={{ whiteSpace: "pre-wrap" }}>{m.text}</div>
                {m.role === "assistant" && <ToolCalls calls={m.toolCalls} />}
              </div>
            </div>
          ))}
          {busy && (
            <div className="chat-row chat-assistant">
              <div className="chat-bubble text-muted" role="status">Assistant is thinking…</div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        {usage && (
          <div className="small text-muted mt-2" data-testid="token-usage">
            Tokens used: {usage.total_tokens.toLocaleString()} · Context window:{" "}
            {usage.context_estimated ? "about " : ""}{usage.context_percent}% full
            ({usage.context_tokens.toLocaleString()} of {usage.context_window.toLocaleString()} tokens)
          </div>
        )}
        {usage?.warn && (
          <Alert variant="warning" className="d-flex justify-content-between align-items-center mt-2 mb-0" data-testid="context-warning">
            <span>
              This conversation uses {usage.context_percent}% of the model&apos;s memory. Compact it to keep a summary and free space
              (it also happens automatically at 85%).
            </span>
            <Button size="sm" variant="outline-warning" disabled={busy} onClick={() => send("/compact")}>Compact</Button>
          </Alert>
        )}

        {saved.length > 0 && (
          <div className="small text-muted mt-2" data-testid="saved-items">
            Saved by the assistant: {saved.map((s) => `${s.itemType} ${s.itemId}`).join(", ")}
          </div>
        )}

        {error && (
          <Alert variant="danger" className="d-flex justify-content-between align-items-center mt-3 mb-0" role="alert">
            <span>{error}</span>
            {failedText && <Button size="sm" variant="outline-danger" onClick={() => send(failedText, { retry: true })}>Try again</Button>}
          </Alert>
        )}

        <Form className="d-flex gap-2 mt-3" onSubmit={(e) => { e.preventDefault(); send(text); }}>
          <Form.Control
            as="textarea" rows={1} aria-label="Message to the assistant" placeholder="Type your message…"
            value={text} maxLength={MAX_LENGTH} disabled={busy}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {     // Enter sends, Shift+Enter makes a new line
                e.preventDefault();
                send(text);
              }
            }}
          />
          <Button type="submit" disabled={busy || !text.trim()}>Send</Button>
        </Form>
      </Card.Body>
    </Card>
  );
}
