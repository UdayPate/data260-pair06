import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { COMPANY, STUDENT, mockDashboard, mockMe, renderApp, storeSession } from "./helpers";

const theme = () => document.documentElement.getAttribute("data-theme");

describe("Theme follows the role", () => {
  it("uses the student theme for a logged-in student", async () => {
    storeSession(STUDENT);
    mockMe(STUDENT);
    mockDashboard("student");
    renderApp("/");
    expect(await screen.findByTestId("stat-applications")).toBeInTheDocument();
    expect(theme()).toBe("student");
  });

  it("uses the company theme for a logged-in company", async () => {
    storeSession(COMPANY);
    mockMe(COMPANY);
    mockDashboard("company");
    renderApp("/");
    expect(await screen.findByTestId("stat-jobs")).toBeInTheDocument();
    expect(theme()).toBe("company");
  });

  it.each([["/login"], ["/signup"]])("on %s the Student/Company switch picks the theme", async (route) => {
    const user = userEvent.setup();
    renderApp(route);
    expect(await screen.findByRole("radio", { name: "Student" })).toBeChecked();
    expect(theme()).toBe("student");

    await user.click(screen.getByRole("radio", { name: "Company" }));
    expect(theme()).toBe("company");

    await user.click(screen.getByRole("radio", { name: "Student" }));
    expect(theme()).toBe("student");
  });
});

describe("Pixel-art career scene", () => {
  async function renderScene() {
    storeSession(STUDENT);
    mockMe(STUDENT);
    mockDashboard("student");
    renderApp("/");
    return screen.findByTestId("career-scene");
  }
  const num = (el, name) => Number(el.getAttribute(name));
  const box = (el) => ({ x: num(el, "x"), y: num(el, "y"), w: num(el, "width"), h: num(el, "height") });
  const overlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  const parts = (scene, part) => [...scene.querySelectorAll(`rect[data-part="${part}"]`)].map(box);
  const viewBox = (scene) => scene.querySelector("svg").getAttribute("viewBox").split(" ").map(Number); // [0, 0, W, H]

  it("is on the student Home page: an inline SVG, hidden from screen readers, with no text or images", async () => {
    const scene = await renderScene();
    expect(scene).toHaveAttribute("aria-hidden", "true");
    expect(scene.textContent).toBe("");
    expect(scene.querySelectorAll("img, image")).toHaveLength(0); // drawn with SVG shapes, not pictures
    const svg = scene.querySelector("svg");
    expect(svg).toHaveAttribute("shape-rendering", "crispEdges");
    expect(svg.querySelectorAll("rect").length).toBeGreaterThan(40);
  });

  it("draws the staircase, character, coins and flag in the theme colours, with only a few lit windows", async () => {
    const scene = await renderScene();
    expect(scene.querySelectorAll("rect.px-coral")).toHaveLength(10); // 10 steps
    expect(scene.querySelectorAll('rect[data-part="tread"].px-salmon')).toHaveLength(10); // a highlight on each tread
    expect(parts(scene, "coin").length).toBeGreaterThanOrEqual(3);
    expect(scene.querySelectorAll('rect[data-part="window"]').length).toBeLessThanOrEqual(12); // quiet skyline
    expect(scene.querySelectorAll('rect[data-part="window"]').length).toBeGreaterThan(0);
    expect(scene.querySelectorAll("rect.px-tower").length).toBeGreaterThan(10);
  });

  it("the whole flag, pole and cloth, is inside the drawing and clear of the top edge", async () => {
    const scene = await renderScene();
    const [, , W, H] = viewBox(scene);
    const flag = parts(scene, "flag");
    expect(flag).toHaveLength(2); // pole + cloth
    const top = Math.min(...flag.map((r) => r.y));
    expect(top).toBeGreaterThan(0); // the regression this test guards: the pole used to touch y = 0
    expect(top).toBeGreaterThanOrEqual(8); // at least 8 pixels of free space above the flag
    for (const r of flag) {
      expect(r.x).toBeGreaterThan(0);
      expect(r.x + r.w).toBeLessThan(W);
      expect(r.y + r.h).toBeLessThan(H);
    }
  });

  it("nothing in the front layer touches the edge of the drawing", async () => {
    const scene = await renderScene();
    const [, , W, H] = viewBox(scene);
    const front = [...scene.querySelectorAll('g[data-layer="front"] rect')].map(box);
    expect(front.length).toBeGreaterThan(20);
    for (const r of front) {
      expect(r.x).toBeGreaterThan(0);
      expect(r.y).toBeGreaterThan(0);
      expect(r.x + r.w).toBeLessThan(W);
      expect(r.y + r.h).toBeLessThan(H); // the stairs stand on a floor above the bottom edge
    }
  });

  it("the stairs run from 15% to 85% of the width, in evenly spaced steps", async () => {
    const scene = await renderScene();
    const [, , W] = viewBox(scene);
    const steps = parts(scene, "step").sort((a, b) => a.x - b.x);
    expect(steps).toHaveLength(10);
    expect(steps[0].x / W).toBeCloseTo(0.15, 2);
    expect((steps[9].x + steps[9].w) / W).toBeCloseTo(0.85, 2);
    const widths = new Set(steps.map((s) => s.w));
    const gaps = new Set(steps.slice(1).map((s, i) => s.x - (steps[i].x + steps[i].w)));
    const rises = new Set(steps.slice(1).map((s, i) => steps[i].y - s.y));
    expect(widths.size).toBe(1); // every step is as wide as the others
    expect([...gaps]).toEqual([0]); // and they touch: no uneven gaps
    expect(rises.size).toBe(1); // every step rises by the same amount
    expect([...rises][0]).toBeGreaterThan(0); // rising to the right
  });

  it("the character is about two thirds of the way up, the coins are above steps, the flag is on the top step", async () => {
    const scene = await renderScene();
    const [, , , H] = viewBox(scene);
    const steps = parts(scene, "step").sort((a, b) => a.x - b.x);
    const floor = steps[0].y + steps[0].h; // y of the ground the stairs stand on
    const topY = steps[9].y;
    const stepAt = (x) => steps.find((s) => x >= s.x && x < s.x + s.w);

    const character = parts(scene, "character");
    const feet = Math.max(...character.map((r) => r.y + r.h));
    const left = Math.min(...character.map((r) => r.x));
    expect(feet).toBe(stepAt(left).y); // standing on a tread
    const progress = (floor - feet) / (floor - topY); // 0 = bottom, 1 = top
    expect(progress).toBeGreaterThan(0.6);
    expect(progress).toBeLessThan(0.75);

    for (const coin of parts(scene, "coin")) {
      const step = stepAt(coin.x);
      expect(step, "a coin is over a step").toBeTruthy();
      expect(coin.y + coin.h).toBeLessThan(step.y); // floating above the tread, not inside it
    }

    const flag = parts(scene, "flag");
    const pole = flag.find((r) => r.w === 1);
    expect(pole.y + pole.h).toBe(topY); // the pole stands on the top step
    expect(pole.x).toBeGreaterThanOrEqual(steps[9].x);
    expect(pole.x).toBeLessThan(steps[9].x + steps[9].w);
    expect(H).toBeGreaterThan(topY);
  });

  it("no building or window is drawn on top of the stairs, character, coins or flag", async () => {
    const scene = await renderScene();
    const all = [...scene.querySelectorAll("rect")];
    const frontStart = all.findIndex((el) => el.closest("g")?.dataset.layer === "front");
    const lastBack = all.map((el) => el.closest("g")?.dataset.layer).lastIndexOf("back");
    expect(lastBack).toBeLessThan(frontStart); // the skyline comes first in the drawing order, so the front covers it

    const front = [...scene.querySelectorAll('g[data-layer="front"] rect')].map(box);
    for (const w of parts(scene, "window")) {
      for (const f of front) expect(overlap(w, f), `window at ${w.x},${w.y} overlaps ${JSON.stringify(f)}`).toBe(false);
    }
  });

  it("keeps at least 16px of free space above the flag at every page width, phones included", async () => {
    const scene = await renderScene();
    const [, , W, H] = viewBox(scene);
    const flagTop = Math.min(...parts(scene, "flag").map((r) => r.y));
    // the box proportions and minimum height come straight from theme.css
    const rule = css.slice(css.indexOf(':root[data-theme="student"] .career-scene {'));
    const [ratioW, ratioH] = rule.match(/aspect-ratio:\s*(\d+)\s*\/\s*(\d+)/).slice(1).map(Number);
    const minHeight = Number(rule.match(/min-height:\s*(\d+)px/)[1]);
    expect([ratioW, ratioH]).toEqual([W, H]); // the box has the drawing's proportions, so nothing is cropped
    const border = 2;
    for (const pageWidth of [296, 320, 351, 414, 516, 696, 936, 1110, 1296]) {
      const innerWidth = pageWidth - 2 * border;
      const boxHeight = Math.max(minHeight, (pageWidth * ratioH) / ratioW);
      const innerHeight = boxHeight - 2 * border;
      const scale = Math.min(innerWidth / W, innerHeight / H); // the drawing is fitted inside the box ("meet")
      const freeAboveFlag = innerHeight - H * scale + flagTop * scale; // from the inside of the top border to the pole
      expect(freeAboveFlag, `page width ${pageWidth}px`).toBeGreaterThanOrEqual(16);
      expect(H * scale, "the art is fully inside the box").toBeLessThanOrEqual(innerHeight + 0.001);
    }
  });

  it("is not on the company Home page", async () => {
    storeSession(COMPANY);
    mockMe(COMPANY);
    mockDashboard("company");
    renderApp("/");
    expect(await screen.findByTestId("stat-jobs")).toBeInTheDocument();
    expect(screen.queryByTestId("career-scene")).not.toBeInTheDocument();
  });
});

// ---- The stylesheet itself: tokens and WCAG AA contrast (4.5:1 for normal text) ----
const css = readFileSync(resolve(process.cwd(), "src/theme.css"), "utf8") // vitest runs from the frontend folder;
const block = (selector) => css.slice(css.indexOf(selector)).match(/\{([^}]*)\}/)[1];
const studentTokens = block(':root[data-theme="student"] {');
const companyTokens = block(':root[data-theme="company"] {');
const token = (name) => studentTokens.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`))[1];

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

describe("theme.css", () => {
  it("uses the specified palette", () => {
    expect(token("bg")).toBe("#001008");
    expect(token("panel")).toBe("#081810");
    expect(token("panel-raised")).toBe("#0c1f17");
    expect(token("text")).toBe("#f8f8f8");
    expect(token("muted")).toBe("#c8d0d0");
    expect(token("accent")).toBe("#f86048");
    expect(token("accent-soft")).toBe("#f8a8a0");
    expect(token("teal")).toBe("#2fb58d");
    expect(token("amber")).toBe("#f8c860");
    expect(token("hairline")).toBe("#1f3a2e");
  });

  it("company theme: no pixel font, 6px corners, 1px borders, no hard shadow", () => {
    expect(companyTokens).toMatch(/--font-ui:\s*var\(--font-body\)/);
    expect(companyTokens).toMatch(/--font-title:\s*var\(--font-body\)/);
    expect(companyTokens).toMatch(/--radius:\s*6px/);
    expect(companyTokens).toMatch(/--border-w:\s*1px/);
    expect(companyTokens).toMatch(/--shadow:\s*0 1px 2px/);
    expect(companyTokens).toMatch(/--shadow-btn:\s*none/);
    expect(studentTokens).toMatch(/--radius:\s*0;/);
    expect(studentTokens).toMatch(/--border-w:\s*2px/);
    expect(studentTokens).toMatch(/--shadow:\s*4px 4px 0/);
  });

  it("text and status colours meet WCAG AA contrast (4.5:1)", () => {
    const pairs = [
      ["text on page", token("text"), token("bg")],
      ["text on panel", token("text"), token("panel")],
      ["text on raised panel", token("text"), token("panel-raised")],
      ["muted text on page", token("muted"), token("bg")],
      ["muted text on panel", token("muted"), token("panel")],
      ["muted text on raised panel", token("muted"), token("panel-raised")],
      ["coral text on panel (company active nav)", token("accent"), token("panel")],
      ["coral text on page", token("accent"), token("bg")],
      ["link on panel", token("accent-soft"), token("panel")],
      ["dark text on coral button", token("accent-ink"), token("accent")],
      ["dark text on salmon button hover", token("accent-ink"), token("accent-soft")],
      ["dark text on amber (Pending)", token("accent-ink"), token("amber")],
      ["dark text on teal (Reviewed)", token("accent-ink"), token("teal")],
      ["dark text on coral-red (Declined)", token("accent-ink"), token("danger")],
      ["coral-red error text on panel", token("danger"), token("panel")],
    ];
    for (const [name, fg, bg] of pairs) {
      expect(contrast(fg, bg), `${name}: ${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
    }
    // form field borders need 3:1 against the page (non-text contrast)
    expect(contrast(token("field-border"), token("bg"))).toBeGreaterThanOrEqual(3);
  });

  it("has no leftover horizon, mountain or perspective-grid styles", () => {
    expect(css).not.toMatch(/horizon|perspective|mountain/i);
  });

  it("the only animation is the coin glint, and it is switched off for reduced motion", () => {
    expect(css.match(/@keyframes\s+[\w-]+/g)).toEqual(["@keyframes pixel-glint"]);
    const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce) { .pixel-glint"));
    expect(reduced).toMatch(/\.pixel-glint\s*\{\s*animation:\s*none/);
  });

  it("keeps keyboard focus visible and honours reduced motion", () => {
    expect(css).toMatch(/:focus-visible[^{]*\{[^}]*outline:\s*3px solid var\(--focus\)/);
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
  });
});

// ---- Home page follow-up: heatmap colours and width, stat cards ----
const indexCss = readFileSync(resolve(process.cwd(), "src/index.css"), "utf8");

describe("Heatmap colours and width", () => {
  it("uses the dark-to-neon-green ramp", () => {
    expect(token("heat-0")).toBe("#10261c");
    expect(token("heat-1")).toBe("#0e5a33");
    expect(token("heat-2")).toBe("#14a055");
    expect(token("heat-3")).toBe("#39ff88");
    for (const n of [0, 1, 2, 3]) expect(css).toMatch(new RegExp(`\\.heat-${n}\\s*\\{\\s*background:\\s*var\\(--heat-${n}\\)`));
  });

  it("the 53 week columns share the card width, with square squares and a minimum size", () => {
    expect(indexCss).toMatch(/--cell-min:\s*11px/);
    expect(indexCss).toMatch(/--cols:\s*53/);
    expect(indexCss).toMatch(/grid-template-columns:\s*var\(--label-w\) repeat\(var\(--cols\), minmax\(var\(--cell-min\), 1fr\)\)/);
    expect(indexCss).toMatch(/aspect-ratio:\s*1 \/ 1/);
    expect(indexCss).toMatch(/\.heatmap\s*\{[^}]*min-width:[^}]*var\(--cell-min\)/); // narrower than this, the card scrolls
    expect(indexCss).toMatch(/\.heatmap\s*\{[^}]*max-width:/);                          // and a cap for very wide screens
    expect(indexCss).toMatch(/\.heatmap-scroll\s*\{[^}]*overflow-x:\s*auto/);
  });
});

describe("Stat cards", () => {
  it("share the row evenly (equal-width columns, no fixed 4-of-12 width)", async () => {
    storeSession(STUDENT);
    mockMe(STUDENT);
    mockDashboard("student");
    renderApp("/");
    const first = (await screen.findByTestId("stat-applications")).parentElement;
    const second = screen.getByTestId("stat-events").parentElement;
    expect(first.parentElement).toBe(second.parentElement); // the same row
    for (const col of [first, second]) {
      expect(col).toHaveClass("col-md");
      expect(col.className).not.toMatch(/col-md-\d/);
    }
  });

  it("take their colours from the palette: no leftover Bootstrap blue", () => {
    expect(indexCss).not.toMatch(/\.stat-(blue|green|orange)\s*\{[^}]*--accent:/); // this used to override the theme with #4263eb
    expect(css).toMatch(/\.stat-blue\s*\{\s*--accent-color:\s*var\(--accent\)/);  // coral
    expect(css).toMatch(/\.stat-green\s*\{\s*--accent-color:\s*var\(--teal\)/);
    expect(css).toMatch(/\.stat-orange\s*\{\s*--accent-color:\s*var\(--amber\)/);
  });
});

// ---- Stage 2: the remaining pages ----
const cssNoComments = css.replace(/\/\*[\s\S]*?\*\//g, "");
const placeholderColor = css.match(/\.form-control::placeholder\s*\{\s*color:\s*(#[0-9a-fA-F]{6})/)[1];

describe("Stage 2: styling of the other pages", () => {
  it("the pixel font is only reachable through the nav / button / badge / title tokens", () => {
    expect(cssNoComments.match(/var\(--font-display\)/g)).toHaveLength(2); // --font-ui and --font-title, nothing else
    expect(cssNoComments).toMatch(/--font-ui:\s*var\(--font-display\)/);
    expect(cssNoComments).toMatch(/--font-title:\s*var\(--font-display\)/);
    expect(cssNoComments.match(/font-family:\s*var\(--font-(ui|title)\)/g).length).toBeGreaterThan(5); // used for buttons, nav, badges, tabs, h1
    expect(cssNoComments).not.toMatch(/font-family:[^;]*Press Start/); // only named once, in the token
  });

  it("leaves no light-theme colours behind (no white or near-white backgrounds)", () => {
    expect(cssNoComments).not.toMatch(/#fff(fff)?\b/i);
    expect(cssNoComments).not.toMatch(/:\s*white\b(?!-)/i); // the colour keyword (white-space and .px-white are not colours)
    expect(cssNoComments).not.toMatch(/background(-color)?:\s*#(f[0-9a-f]){3}\b/i);
  });

  it("styles tags, category badges, alerts, tabs, the resume modal, checkboxes and selects from the tokens", () => {
    expect(css).toMatch(/\.badge\.bg-light\s*\{[^}]*background-color:\s*var\(--panel-raised\)\s*!important/);
    expect(css).toMatch(/:root\[data-theme="company"\] \.badge\.bg-primary\s*\{[^}]*background-color:\s*var\(--panel-raised\)/); // company: not coral
    expect(css).toMatch(/--alert-color:\s*var\(--alert-default\)/);
    expect(css).toMatch(/\.alert-secondary\s*\{\s*--alert-color:\s*var\(--grey-outline\)/);
    expect(css).toMatch(/\.nav-pills \.nav-link, \.nav-tabs \.nav-link\s*\{/);
    expect(css).toMatch(/:root\[data-theme="company"\] \.nav-pills \.nav-link\.active\s*\{[^}]*box-shadow:\s*inset 0 -2px 0 var\(--accent\)/);
    expect(css).toMatch(/\.modal\s*\{[^}]*--bs-modal-bg:\s*var\(--panel\)/);
    expect(css).toMatch(/\.modal-content\s*\{\s*box-shadow:\s*var\(--shadow\)/);
    expect(css).toMatch(/:root\[data-theme="company"\] \.form-check-input:checked\s*\{[^}]*var\(--grey-outline\)/);
    expect(css).toMatch(/\.form-select option\s*\{[^}]*background:\s*var\(--field-bg\)/);
  });

  it("a spinner inside a button keeps the button's text colour (coral on coral would be invisible)", () => {
    expect(css).toMatch(/\.btn \.spinner-border\s*\{\s*color:\s*currentColor/);
  });

  it("company theme has no pixel font, coral or hard shadow in the new rules", () => {
    const stage2 = css.slice(css.indexOf("/* ===== 12."));
    const company = stage2.split("\n").filter((l) => l.includes('data-theme="company"')).join("\n");
    expect(company).not.toMatch(/font-display|Press Start|--shadow-btn:\s*[0-9]/);
    expect(company).not.toMatch(/background(-color)?:\s*var\(--accent\)/); // coral fills only on the primary button (set elsewhere)
  });

  it("form fields, tags and placeholders meet contrast on their backgrounds", () => {
    const fieldBg = token("field-bg");
    expect(contrast(token("text"), fieldBg)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token("muted"), fieldBg)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(placeholderColor, fieldBg)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token("accent-soft"), token("panel-raised"))).toBeGreaterThanOrEqual(4.5); // links and alert links
    expect(contrast(token("danger"), token("panel-raised"))).toBeGreaterThanOrEqual(4.5);       // error text and Declined text on raised panels
    expect(contrast(token("accent"), token("panel-raised"))).toBeGreaterThanOrEqual(4.5);       // coral active tab text (company)
    expect(contrast(token("grey-outline"), token("panel"))).toBeGreaterThanOrEqual(3);          // tag and outline-button borders (non-text)
    expect(contrast(token("grey-outline"), token("panel-raised"))).toBeGreaterThanOrEqual(3);
  });
});
