import { useEffect, useState } from "react";
import Alert from "react-bootstrap/Alert";
import { fetchResumeBlob } from "../services/postingService";
import { getErrorMessage } from "../utils/errors";
import Loading from "./Loading";

// Shows a private resume PDF inside the page, with an "open in a new tab" link.
// Reads a Blob as text (older browsers and the test environment lack blob.text()).
function readBlobText(blob) {
  if (typeof blob?.text === "function") return blob.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = reject;
    reader.readAsText(blob);
  });
}

export default function ResumePreview({ applicationId, height = 600 }) {
  const [state, setState] = useState({ url: null, error: "", loading: true });

  useEffect(() => {
    let active = true;
    let objectUrl = null;
    setState({ url: null, error: "", loading: true });
    fetchResumeBlob(applicationId)
      .then((blob) => {
        objectUrl = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
        if (active) setState({ url: objectUrl, error: "", loading: false });
      })
      .catch(async (err) => {
        // For a blob download the error body is a blob too; read the message out of it.
        let message = getErrorMessage(err);
        try {
          const body = err.response?.data;
          if (body instanceof Blob) message = JSON.parse(await readBlobText(body)).detail || message;
        } catch { /* keep the generic message */ }
        if (active) setState({ url: null, error: message, loading: false });
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);   // free the memory when the preview closes
    };
  }, [applicationId]);

  if (state.loading) return <Loading label="Loading resume…" />;
  if (state.error) return <Alert variant="danger" role="alert">{state.error}</Alert>;
  return (
    <>
      <div className="mb-2">
        <a href={state.url} target="_blank" rel="noreferrer">Open in a new tab</a>
        {" · "}
        <a href={state.url} download="resume.pdf">Download</a>
      </div>
      <iframe title="Resume" src={state.url} width="100%" height={height} style={{ border: "1px solid #d5dbe7", borderRadius: 8 }} />
    </>
  );
}
