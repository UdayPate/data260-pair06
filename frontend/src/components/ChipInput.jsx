import { useId, useState } from "react";
import Form from "react-bootstrap/Form";

// A list of short words shown as removable "chips", with a box to add more.
// Press Enter or comma to add. `suggestions` pop up as the user types (they may also type their own).
export default function ChipInput({ label, values, onChange, suggestions = [], placeholder, max = 30 }) {
  const [text, setText] = useState("");
  const listId = useId();
  const inputId = useId();

  function add(raw) {
    const word = raw.trim().replace(/\s+/g, " ");
    if (!word) return;
    const exists = values.some((v) => v.toLowerCase() === word.toLowerCase());
    if (!exists && values.length < max) onChange([...values, word]);
    setText("");
  }

  return (
    <div className="mb-3">
      <Form.Label htmlFor={inputId}>{label}</Form.Label>
      <div className="d-flex flex-wrap gap-2 mb-2">
        {values.map((v) => (
          <span className="chip" key={v}>
            {v}
            <button type="button" aria-label={`Remove ${v}`} onClick={() => onChange(values.filter((x) => x !== v))}>×</button>
          </span>
        ))}
      </div>
      <div className="d-flex gap-2">
        <Form.Control
          id={inputId}
          list={listId}
          value={text}
          placeholder={placeholder}
          maxLength={100}
          onChange={(e) => {
            const v = e.target.value;
            if (v.endsWith(",")) add(v.slice(0, -1));
            else setText(v);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();       // Enter adds a chip; it must not submit the whole form
              add(text);
            }
          }}
        />
        <button type="button" className="btn btn-outline-primary" onClick={() => add(text)}>Add</button>
      </div>
      <datalist id={listId}>{suggestions.map((s) => <option key={s} value={s} />)}</datalist>
      {values.length >= max && <div className="form-text">You can add up to {max}.</div>}
    </div>
  );
}
