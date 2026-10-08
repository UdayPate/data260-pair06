import { useState } from "react";
import Alert from "react-bootstrap/Alert";
import Form from "react-bootstrap/Form";
import { uploadProfilePicture } from "../services/profileService";
import { getErrorMessage } from "../utils/errors";
import { checkImageFile } from "../utils/format";
import Avatar from "./Avatar";

// Shows the current picture and uploads a new one as soon as a file is chosen.
// `upload` is the function that sends the file (students and companies use different addresses).
export default function PictureUploader({ name, url, onUploaded, upload = uploadProfilePicture, label = "Profile picture" }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function choose(e) {
    const file = e.target.files[0];
    if (!file) return;
    const problem = checkImageFile(file);
    if (problem) return setError(problem);
    setBusy(true);
    setError("");
    try {
      const result = await upload(file);
      onUploaded(result.profile_pic_url);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="d-flex align-items-center gap-3 mb-4">
      <Avatar name={name} url={url} size={88} />
      <div>
        <Form.Group controlId="picture">
          <Form.Label>{label}</Form.Label>
          <Form.Control type="file" accept="image/png,image/jpeg,image/webp" onChange={choose} disabled={busy} />
          <Form.Text>{busy ? "Uploading…" : "PNG, JPEG or WebP, up to 2 MB."}</Form.Text>
        </Form.Group>
        {error && <Alert variant="danger" role="alert" className="mt-2 mb-0">{error}</Alert>}
      </div>
    </div>
  );
}
