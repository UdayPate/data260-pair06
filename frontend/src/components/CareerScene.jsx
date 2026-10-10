// Decorative pixel-art banner at the top of the student Home page. It is only a drawing:
// inline SVG on a coarse grid (1 SVG unit = 1 "pixel"), no text, no images, hidden from
// screen readers. Colours come from the theme tokens through the .px-* classes in theme.css.
//
// Back layer  : a quiet night skyline of office towers with a few lit windows.
// Front layer : a coral staircase going up to the right (from 15% to 85% of the width), a little
//               character with a briefcase about two thirds of the way up, coins above some
//               steps and a flag on the top step.
//
// The SVG keeps its proportions (see .career-scene in theme.css), so the whole scene, flag
// included, scales with the page width. The art has 9 pixels of free space above the flag.

export const W = 300; // size of the drawing in pixels
export const H = 39;
export const GROUND = H - 2; // the stairs and towers stand on this line; a 2-pixel floor lies below it

// --- Back layer: towers as [x, width, height] over a 264-pixel-wide stretch ---
const SKYLINE_WIDTH = 264;
const TOWERS = [
  [0, 14, 14], [14, 10, 19], [24, 16, 11], [40, 12, 22], [52, 18, 15], [70, 10, 20], [80, 16, 12],
  [96, 14, 23], [110, 12, 16], [122, 18, 13], [140, 10, 21], [150, 16, 15], [166, 12, 24], [178, 18, 12],
  [196, 10, 19], [206, 16, 14], [222, 12, 22], [234, 16, 13], [250, 14, 18],
];
const ANTENNAS = [[45, 22], [101, 23], [171, 24], [227, 22]]; // [x, tower height]: a thin mast on four towers
// The stretch is centred in the drawing and repeated on both sides, so the skyline also fills
// the space beside the drawing when the page is wider than the drawing's proportions.
const SKYLINE_X = (W - SKYLINE_WIDTH) / 2;
const SKYLINE_COPIES = [SKYLINE_X - SKYLINE_WIDTH, SKYLINE_X, SKYLINE_X + SKYLINE_WIDTH];
// Lit windows [x, y, colour], each inside a tower. (y was measured from a ground at 30; the ground is now at 37.)
const LIT_WINDOWS = [
  [18, 20, "teal"], [43, 12, "teal"], [46, 17, "amber"], [100, 10, "amber"], [104, 16, "teal"],
  [143, 15, "teal"], [169, 8, "teal"], [173, 15, "amber"], [199, 18, "teal"], [225, 12, "amber"],
].map(([x, y, c]) => [x + SKYLINE_X, y + (GROUND - 30), c]);
// A few more on the right-hand towers, which the staircase does not cover
const EXTRA_WINDOWS = [[257, 27, "teal"], [262, 31, "amber"], [272, 24, "amber"]];

// --- Front layer: the staircase, evenly spaced, from 15% to 85% of the width ---
const STEPS = 10;
const STEP_X0 = Math.round(W * 0.15); // 45
const STEP_WIDTH = Math.round((W * 0.85 - STEP_X0) / STEPS); // 21
const STEP_RISE = 2; // every step is 2 pixels higher than the one before
const stepX = (i) => STEP_X0 + STEP_WIDTH * i;
const stepTop = (i) => GROUND - STEP_RISE * (i + 1); // y of the top of step i (0 = lowest)
const TOP = STEPS - 1;

const CHARACTER_STEP = 6; // 7th of 10 steps: about two thirds of the way up
const CHARACTER_X = stepX(CHARACTER_STEP) + 8;
const CHARACTER_Y = stepTop(CHARACTER_STEP) - 8; // the character is 8 pixels tall
const COIN_STEPS = [1, 3, 4, 7, 8]; // a coin floats above each of these steps
const GLINT_STEP = 4; // this coin glints
const coinPos = (i) => [stepX(i) + 9, stepTop(i) - 4]; // 2x2 coin, one empty pixel row above the tread
const FLAG_X = stepX(TOP) + 14; // the pole stands on the top step
const FLAG_BOTTOM = stepTop(TOP);

// Keep lit windows out of the way of the front layer: not hidden behind a step, not within 4
// pixels above a tread, and not next to the character.
function stairTopAt(x) {
  const i = Math.floor((x - STEP_X0) / STEP_WIDTH);
  return i >= 0 && i < STEPS ? stepTop(i) : GROUND;
}
const nearCharacter = (x, y) => x >= CHARACTER_X - 4 && x <= CHARACTER_X + 9 && y >= CHARACTER_Y - 4;
const visibleWindows = [...LIT_WINDOWS, ...EXTRA_WINDOWS].filter(
  ([x, y]) => y + 1 + 4 <= stairTopAt(x) && y + 1 + 4 <= stairTopAt(x + 1) && !nearCharacter(x, y)
);

// A rectangle on the pixel grid in one of the theme colours; `part` labels it (used by the tests)
const Px = ({ x, y, w = 1, h = 1, c, part }) => (
  <rect x={x} y={y} width={w} height={h} className={`px-${c}`} data-part={part} />
);

export default function CareerScene() {
  const [coinX, coinY] = coinPos(GLINT_STEP);

  return (
    <div className="career-scene" aria-hidden="true" data-testid="career-scene">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMax meet"
        shapeRendering="crispEdges"
        focusable="false"
      >
        {/* back layer: skyline and floor (drawn first, so everything in front covers it) */}
        <g data-layer="back">
          {SKYLINE_COPIES.flatMap((offset) => [
            ...TOWERS.map(([x, w, h]) => (
              <Px key={`t${offset}-${x}`} x={x + offset} y={GROUND - h} w={w} h={h} c="tower" part="tower" />
            )),
            ...ANTENNAS.map(([x, h]) => (
              <Px key={`a${offset}-${x}`} x={x + offset} y={GROUND - h - 3} h={3} c="tower" part="tower" />
            )),
          ])}
          <Px x={SKYLINE_X - 2 * SKYLINE_WIDTH} y={GROUND} w={5 * SKYLINE_WIDTH} h={H - GROUND} c="tower" part="floor" />
          {visibleWindows.map(([x, y, c]) => <Px key={`w${x}-${y}`} x={x} y={y} w={2} c={c} part="window" />)}
        </g>

        {/* front layer */}
        <g data-layer="front">
          {/* stairs: coral, with a salmon highlight on each tread */}
          {Array.from({ length: STEPS }, (_, i) => (
            <g key={`s${i}`}>
              <Px x={stepX(i)} y={stepTop(i)} w={STEP_WIDTH} h={GROUND - stepTop(i)} c="coral" part="step" />
              <Px x={stepX(i)} y={stepTop(i)} w={STEP_WIDTH} c="salmon" part="tread" />
            </g>
          ))}

          {/* coins (2x2 amber), and one tiny white glint that flashes now and then */}
          {COIN_STEPS.map((i) => {
            const [x, y] = coinPos(i);
            return <Px key={`c${i}`} x={x} y={y} w={2} h={2} c="amber" part="coin" />;
          })}
          <rect className="pixel-glint px-white" x={coinX} y={coinY} width={1} height={1} data-part="glint" />

          {/* the character: hair, face, teal suit, hand holding an amber briefcase, legs */}
          <Px x={CHARACTER_X} y={CHARACTER_Y} w={3} c="muted" part="character" />
          <Px x={CHARACTER_X} y={CHARACTER_Y + 1} w={3} c="salmon" part="character" />
          <Px x={CHARACTER_X} y={CHARACTER_Y + 2} w={3} h={3} c="teal" part="character" />
          <Px x={CHARACTER_X + 3} y={CHARACTER_Y + 2} c="teal" part="character" />
          <Px x={CHARACTER_X + 3} y={CHARACTER_Y + 3} c="salmon" part="character" />
          <Px x={CHARACTER_X + 3} y={CHARACTER_Y + 4} w={2} h={2} c="amber" part="character" />
          <Px x={CHARACTER_X} y={CHARACTER_Y + 5} h={3} c="muted" part="character" />
          <Px x={CHARACTER_X + 2} y={CHARACTER_Y + 5} h={3} c="muted" part="character" />

          {/* the flag on the top step: a salmon pole and an amber flag */}
          <Px x={FLAG_X} y={FLAG_BOTTOM - 8} h={8} c="salmon" part="flag" />
          <Px x={FLAG_X + 1} y={FLAG_BOTTOM - 8} w={6} h={3} c="amber" part="flag" />
        </g>
      </svg>
    </div>
  );
}
