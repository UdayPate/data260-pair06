import { useEffect, useRef, useState } from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Card from "react-bootstrap/Card";
import Form from "react-bootstrap/Form";
import { sendMessage } from "../services/assistantService";
import { getErrorMessage } from "../utils/errors";

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

// The chat box on the student's home page. It talks to the assistant only through
// services/assistantService.js, so whoever builds the real assistant changes nothing here.
export default function ChatWindow() {
  const [messages, setMessages] = useState([]);       // [{ role: "user" | "assistant", text, toolCalls }]
  const [conversationId, setConversationId] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [failedText, setFailedText] = useState("");   // the message that did not get an answer
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages, busy]);

  async function send(message, { retry = false } = {}) {
    const clean = message.trim();
    if (!clean || busy) return;
    setBusy(true);
    setError("");
    setFailedText("");
    if (!retry) setMessages((m) => [...m, { role: "user", text: clean }]);
    setText("");
    try {
      const reply = await sendMessage(clean, conversationId);
      setConversationId(reply.conversation_id);
      setMessages((m) => [...m, { role: "assistant", text: reply.reply, toolCalls: reply.tool_calls }]);
    } catch (err) {
      setError(getErrorMessage(err, "The assistant could not answer. Please try again."));
      setFailedText(clean);
    } finally {
      setBusy(false);
    }
  }

  function newConversation() {
    setMessages([]);
    setConversationId(null);
    setError("");
    setFailedText("");
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
