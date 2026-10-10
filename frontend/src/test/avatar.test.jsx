import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Avatar, { initialsOf } from "../components/Avatar";

// The HTML a given avatar produces (used to compare two avatars).
const html = (props) => render(<Avatar {...props} />).container.innerHTML;

const NAMES = ["Ada Lovelace", "Grace Hopper", "Alan Turing", "Katherine Johnson", "Linus Torvalds", "Margaret Hamilton",
  "Acme Corp", "Globex", "Initech", "Umbrella Labs", "Hooli", "Stark Industries", "Wayne Enterprises", "Cyberdyne"];

describe("Avatar: same name, same picture", () => {
  it.each(["student", "company"])("is the same every time for a %s", (kind) => {
    expect(html({ name: "Ada Lovelace", kind })).toBe(html({ name: "Ada Lovelace", kind }));
  });

  it("ignores letter case and surrounding spaces in the name", () => {
    expect(html({ name: "  ada lovelace ", kind: "student" }).replace(/aria-label="[^"]*"/, ""))
      .toBe(html({ name: "ADA LOVELACE", kind: "student" }).replace(/aria-label="[^"]*"/, ""));
  });

  it("different names give different student faces (most pairs differ)", () => {
    const faces = new Set(NAMES.map((name) => html({ name, kind: "student", decorative: true })));
    expect(faces.size).toBeGreaterThanOrEqual(NAMES.length - 1);
  });

  it("different names give different company tiles", () => {
    const tiles = new Set(NAMES.map((name) => html({ name, kind: "company", decorative: true })));
    expect(tiles.size).toBe(NAMES.length);   // the initials differ even when the colour repeats
  });
});

describe("Avatar: a real picture, with a fallback", () => {
  it("shows the real picture when a src is given", () => {
    render(<Avatar name="Ada Lovelace" src="/media/profile_pics/a.png" />);
    expect(screen.getByAltText("Ada Lovelace profile")).toHaveAttribute("src", "http://localhost:9060/media/profile_pics/a.png");
  });

  it.each(["student", "company"])("falls back to the generated %s picture when the src fails to load", (kind) => {
    const { container } = render(<Avatar name="Ada Lovelace" src="/media/broken.png" kind={kind} />);
    fireEvent.error(screen.getByAltText("Ada Lovelace profile"));
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByRole("img", { name: "Ada Lovelace (no picture)" })).toBeInTheDocument();
    expect(container.querySelector(kind === "student" ? "svg" : ".avatar-tile")).not.toBeNull();
  });

  it("tries again when it is given a new src after a failure", () => {
    const { rerender, container } = render(<Avatar name="Ada" src="/media/broken.png" />);
    fireEvent.error(container.querySelector("img"));
    expect(container.querySelector("img")).toBeNull();
    rerender(<Avatar name="Ada" src="/media/new.png" />);
    expect(container.querySelector("img")).toHaveAttribute("src", "http://localhost:9060/media/new.png");
  });

  it("uses the generated picture when there is no src at all", () => {
    const { container } = render(<Avatar name="Ada Lovelace" />);
    expect(container.querySelector("svg")).not.toBeNull();   // student is the default kind
  });
});

describe("Avatar: initials for the company tile", () => {
  it("one word gives one letter, two words give two, more words still give two", () => {
    expect(initialsOf("Globex")).toBe("G");
    expect(initialsOf("Acme Corp")).toBe("AC");
    expect(initialsOf("  stark   industries  ")).toBe("SI");
    expect(initialsOf("Bank of America")).toBe("BO");
  });

  it("shows those initials in the tile", () => {
    const { container } = render(<Avatar name="Acme Corp" kind="company" />);
    expect(container.querySelector(".avatar-tile")).toHaveTextContent(/^AC$/);
    const one = render(<Avatar name="Globex" kind="company" />);
    expect(one.container.querySelector(".avatar-tile")).toHaveTextContent(/^G$/);
  });
});

describe("Avatar: empty name, size and accessibility", () => {
  it.each(["student", "company"])("does not crash with an empty or missing name (%s) and shows a neutral tile", (kind) => {
    for (const name of ["", "   ", undefined, null]) {
      const { container, unmount } = render(<Avatar name={name} kind={kind} />);
      const tile = container.querySelector(".avatar-neutral");
      expect(tile).not.toBeNull();
      expect(tile.textContent).toBe("");
      unmount();
    }
  });

  it("uses the size for width and height", () => {
    const { container } = render(<Avatar name="Ada" size={72} />);
    expect(container.firstChild).toHaveStyle({ width: "72px", height: "72px" });
  });

  it("is hidden from screen readers when decorative, and labelled otherwise", () => {
    const hidden = render(<Avatar name="Ada Lovelace" decorative />);
    expect(hidden.container.firstChild).toHaveAttribute("aria-hidden", "true");
    expect(screen.queryByRole("img")).toBeNull();
    hidden.unmount();
    const labelled = render(<Avatar name="Ada Lovelace" kind="company" />);
    expect(screen.getByRole("img", { name: "Ada Lovelace (no picture)" })).toBeInTheDocument();
    labelled.unmount();
    const photo = render(<Avatar name="Ada Lovelace" src="/media/a.png" decorative />);
    expect(photo.container.querySelector("img")).toHaveAttribute("alt", "");
    expect(photo.container.querySelector("img")).toHaveAttribute("aria-hidden", "true");
  });
});

// ---- colours come from theme.css variables, and the company tile text is readable ----
const css = readFileSync(resolve(process.cwd(), "src/theme.css"), "utf8");
const studentTokens = css.slice(css.indexOf(':root[data-theme="student"] {')).match(/\{([^}]*)\}/)[1];
const tokenHex = (name) => studentTokens.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`))[1];
function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};
const MANY_NAMES = Array.from({ length: 200 }, (_, i) => `Company ${i} ${"abcdefghij"[i % 10]}`);
const VAR = /var\((--[a-z-]+)\)/;

describe("Avatar: colours", () => {
  it("company tiles use only palette variables, and dark text on each passes 4.5:1", () => {
    const used = new Set();
    for (const name of MANY_NAMES) {
      const { container, unmount } = render(<Avatar name={name} kind="company" />);
      used.add(container.firstChild.style.background.match(VAR)[1]);
      unmount();
    }
    expect([...used].sort()).toEqual(["--accent", "--accent-soft", "--amber", "--teal"]);   // all four are reachable
    for (const v of used) {
      expect(contrast(tokenHex("accent-ink"), tokenHex(v.slice(2))), `dark text on ${v}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("company tile: IBM Plex via the theme, no pixel font, no hard shadow", () => {
    const rule = css.match(/:root \.avatar\.avatar-tile \{([^}]*)\}/)[1];
    expect(rule).toMatch(/font-family:\s*var\(--font-body\)/);
    expect(rule).toMatch(/color:\s*var\(--accent-ink\)/);
    expect(rule).toMatch(/box-shadow:\s*none/);
    expect(rule).not.toMatch(/Press Start|font-display|font-ui/);
  });

  it("student faces: every square uses a palette variable (no hard-coded colours), crisp edges, mirrored left to right", () => {
    for (const name of NAMES) {
      const { container, unmount } = render(<Avatar name={name} />);
      const svg = container.querySelector("svg");
      expect(svg).toHaveAttribute("shape-rendering", "crispEdges");
      expect(svg).toHaveAttribute("viewBox", "0 0 8 8");
      const squares = [...svg.querySelectorAll("rect")].filter((r) => r.getAttribute("width") === "1");
      const key = (r) => `${r.getAttribute("x")},${r.getAttribute("y")}`;
      const fillOf = (r) => r.style.fill;
      const byPos = new Map(squares.map((r) => [key(r), fillOf(r)]));
      for (const r of squares) {
        expect(fillOf(r)).toMatch(VAR);
        const mirror = `${7 - Number(r.getAttribute("x"))},${r.getAttribute("y")}`;
        expect(byPos.get(mirror), `${name}: mirror of ${key(r)}`).toBe(fillOf(r));
      }
      unmount();
    }
  });

  it("the variables used all exist in theme.css", () => {
    const { container } = render(<Avatar name="Ada" />);
    const names = new Set([...container.querySelectorAll("rect")].map((r) => r.style.fill.match(VAR)[1]));
    for (const v of names) expect(studentTokens, v).toContain(`${v}:`);
  });
});
