---
name: visual-builder
description: Analyzes images, art, wireframes, screenshots and UI mockups to produce high-fidelity, visually accurate builds in HTML/Tailwind, React, SVG, CSS or 3D/Three.js. Use this skill whenever the user uploads or points to an image (.png, .jpg, .jpeg, .webp, .gif, .svg, a Figma/Dribbble export or a screenshot) and wants it turned into code, or says things like "build this design", "make it look like this", "replicate this mockup", "convert this artwork to code", "clone this UI" or "match this screenshot", even if they don't mention an exact framework.
---

# Visual-to-Code Precision Protocol

Turning a picture into code fails in predictable ways: colours get eyeballed, spacing falls back to
framework defaults, and the result drifts into a generic look (purple buttons, 16px padding
everywhere). This protocol prevents that by measuring first, fixing the measurements as tokens,
building against those tokens, and then checking the rendered result against the reference.

Work through the phases in order. Don't write the final implementation until Phases 1 and 2 are done:
the audit and tokens are what keep the build honest.

## Phase 1: Visual extraction and audit

Look at the image carefully, and measure rather than guess wherever the file is available:

```bash
python scripts/extract_palette.py reference.png            # size, dominant colours as hex
python scripts/extract_palette.py reference.png --at 120,48 --at 300,210   # exact pixels
```

Document:

1. **Layout architecture.** Containers and hierarchy; which regions are Flexbox (one axis) versus
   Grid (two axes); fixed versus fluid areas; how it should reflow on narrower screens.
2. **Design tokens.**
   - **Colour:** background, surfaces, primary/secondary accents, text (primary, muted), borders,
     gradient stops, as hex/RGB values taken from the image.
   - **Typography:** likely font family (or closest web-safe/Google match), weights, sizes,
     line-heights, letter-spacing. Measure cap height or x-height in pixels to estimate sizes.
   - **Spacing and shape:** paddings, gaps, margins, border radii. Look for the base unit
     (4px or 8px grids are common) and express the rest as multiples of it.
3. **Visual art and assets.** Shadows (offset, blur, colour), glassmorphism/blur, overlays,
   borders, icon sets, illustrations or vector shapes that need custom SVG/CSS reconstruction.

Write the audit out briefly (a short table or list) before moving on. It's the contract the rest
of the build is checked against.

## Phase 2: Design system and token setup

Turn the audit into tokens in the target stack, e.g. a Tailwind `theme.extend`, CSS custom
properties on `:root`, or a theme object for styled-components. Name tokens by role (`--surface`,
`--accent`, `--radius-card`) rather than by value, so later corrections happen in one place.

## Phase 3: Component reconstruction

- **Structure first.** Semantic, accessible HTML/JSX: landmarks, headings in order, real buttons
  and links, alt text, labelled form controls.
- **Styling second.** Apply the tokens: colours, type scale, spacing, radii, effects.
- **Accuracy rules.**
  - No fallback defaults: no stock component-library look and no browser-default paddings.
    Every visible value should trace back to a token or a measurement.
  - Use exact measurements, or proportional scaling when the reference is at a different size.
  - For artwork, logos or vector shapes, use inline SVG (paths, gradients, masks) or canvas so the
    geometry lines up. Reserve Three.js/WebGL for references that are actually 3D.
  - If a detail can't be determined from the image (hidden states, off-screen content), choose
    something consistent with the tokens and say what you assumed.

## Phase 4: Self-verification audit

Render the result at the reference's size and compare it with the image. Don't judge from the
source code alone:

```bash
python scripts/compare_render.py reference.png index.html --out compare/
# -> compare/render.png, compare/side_by_side.png, compare/diff.png and a mismatch score
```

(If no headless browser is available, take a screenshot another way and pass it with `--render`.)

Check against the reference:

- [ ] Are all visual elements present, in the correct hierarchy and order?
- [ ] Do colours, gradients and shadows closely match (sample them in the render too)?
- [ ] Are spacing and alignment proportional to the reference (the diff image makes offsets obvious)?
- [ ] Are text styles, weights and line heights accurate?

If there are discrepancies, correct them and re-render. Usually one or two passes are enough.
Finish by telling the user what matches and what remains approximate (for example a substituted
font or an illustration simplified to SVG).
