import { useEffect, useState } from "react";
import { mediaUrl } from "../utils/format";

// A profile picture. If there is no real picture (or it fails to load) we draw one from the name:
//   student -> a small pixel-art face,   company -> a rounded tile with the initials.
// The same name always gives the same picture, because everything is picked by a hash of the name.
// All colours are CSS variables from theme.css, so the pictures follow the theme.

// Hash = a number computed from text. This one is FNV-1a (a tiny, well-known 32-bit hash).
export function hashName(name) {
  let h = 2166136261;
  for (const ch of String(name).trim().toLowerCase()) {
    h ^= ch.codePointAt(0);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h;
}

// Up to two letters: first letters of the first two words ("Ada Lovelace" -> "AL", "Acme" -> "A").
export function initialsOf(name) {
  return String(name)
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => Array.from(w)[0].toUpperCase())
    .join("");
}

// ---- student face -------------------------------------------------------------------------------
// The face is 8 x 8 squares. We only store the LEFT 4 columns of each row; the right half is the mirror image.
// Letters: . = background, h = hair, s = skin, t = shirt.
const HEADS = [
  ["..hh", ".hhh", ".hss", ".sss", ".sss", "..ss", ".ttt", "tttt"],   // short hair
  ["hhhh", "hhhh", "hhss", "hhss", "hsss", "..ss", ".ttt", "tttt"],   // big hair
  ["....", ".hhh", ".hhh", ".sss", ".sss", "..ss", ".ttt", "tttt"],   // fringe
  ["..hh", "..hh", ".hhh", ".sss", ".sss", "..ss", ".ttt", "tttt"],   // cap
];

// Eyes and mouth go on top of the head: [row, column] in the LEFT half (the mirror adds the other side).
const EYES = [[3, 3], [3, 2], [4, 2]];
const MOUTHS = [
  [[5, 2], [5, 3]],   // wide
  [[5, 3]],           // small
  [[4, 3], [5, 3]],   // tall
];

// Colour choices (all palette variables). Skin and hair must differ, and the shirt differs from both.
const SKINS = ["--accent-soft", "--amber", "--teal"];
const HAIRS = ["--accent", "--panel-raised", "--amber", "--teal"];
const SHIRTS = ["--accent", "--teal", "--amber", "--accent-soft"];

function faceCells(name) {
  const h = hashName(name);
  const head = HEADS[h % HEADS.length];
  const eye = EYES[(h >>> 3) % EYES.length];
  const mouth = MOUTHS[(h >>> 6) % MOUTHS.length];
  const skin = SKINS[(h >>> 9) % SKINS.length];
  let hair = HAIRS[(h >>> 12) % HAIRS.length];
  if (hair === skin) hair = "--panel-raised";
  let shirt = SHIRTS[(h >>> 15) % SHIRTS.length];
  if (shirt === skin || shirt === hair) shirt = SHIRTS.find((c) => c !== skin && c !== hair);
  const colour = { h: hair, s: skin, t: shirt, e: "--bg", m: "--bg" };

  const grid = head.map((row) => row.split(""));
  grid[eye[0]][eye[1]] = "e";
  for (const [r, c] of mouth) grid[r][c] = "m";
  // mirror: column c on the left <-> column 7 - c on the right
  const cells = [];
  grid.forEach((row, y) => {
    row.slice(0, 4).forEach((letter, x) => {
      if (letter === ".") return;
      cells.push({ x, y, colour: colour[letter] });
      cells.push({ x: 7 - x, y, colour: colour[letter] });
    });
  });
  return cells;
}

// ---- company tile -------------------------------------------------------------------------------
const TILES = ["--accent", "--accent-soft", "--teal", "--amber"];   // all take dark text (--accent-ink)

export default function Avatar({ name: rawName, src, size = 40, kind = "student", decorative = false }) {
  const name = rawName == null ? "" : String(rawName);   // null / undefined count as "no name"
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);   // a new picture gets a fresh chance to load

  const url = mediaUrl(src);
  const box = { width: size, height: size };

  if (url && !failed) {
    return (
      <img
        src={url}
        alt={decorative ? "" : `${name} profile`}
        aria-hidden={decorative ? "true" : undefined}
        className="avatar"
        style={{ ...box, objectFit: "cover" }}
        onError={() => setFailed(true)}
      />
    );
  }

  // Decorative: hidden from screen readers (the name is already on the page). Otherwise: an image with a label.
  const a11y = decorative ? { "aria-hidden": "true" } : { role: "img", "aria-label": `${name} (no picture)` };
  const empty = !String(name).trim();

  if (empty) {
    return <span className="avatar avatar-tile avatar-neutral" style={box} data-kind={kind} {...a11y} />;
  }

  if (kind === "company") {
    const tile = TILES[hashName(name) % TILES.length];
    return (
      <span
        className="avatar avatar-tile"
        style={{ ...box, background: `var(${tile})`, fontSize: size * 0.4 }}
        data-kind="company"
        {...a11y}
      >
        {initialsOf(name)}
      </span>
    );
  }

  return (
    <span className="avatar avatar-face" style={box} data-kind="student" {...a11y}>
      <svg viewBox="0 0 8 8" width="100%" height="100%" shapeRendering="crispEdges" focusable="false" aria-hidden="true">
        <rect width="8" height="8" style={{ fill: "var(--bg)" }} />
        {faceCells(name).map((c) => (
          <rect key={`${c.x}-${c.y}`} x={c.x} y={c.y} width="1" height="1" style={{ fill: `var(${c.colour})` }} />
        ))}
      </svg>
    </span>
  );
}
