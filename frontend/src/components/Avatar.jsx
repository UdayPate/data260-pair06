import { mediaUrl } from "../utils/format";

// A round profile picture, or the person's initials when there is no picture.
export default function Avatar({ name = "", url, size = 72 }) {
  const src = mediaUrl(url);
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
  const box = { width: size, height: size, fontSize: size * 0.38 };
  return src ? (
    <img src={src} alt={`${name} profile`} className="avatar" style={{ ...box, objectFit: "cover" }} />
  ) : (
    <div className="avatar avatar-initials" style={box} aria-label={`${name} (no picture)`}>{initials || "?"}</div>
  );
}
