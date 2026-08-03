# Flanner — Material 3 redesign plan

Every visual decision in this project defers to **Material 3**
(<https://m3.material.io/foundations>). This document is the plan for getting
there and the record of what M3 actually says, so a later change can be checked
against the source rather than against memory.

Values below were read from m3.material.io on 3 August 2026. Where a page is
quoted, the quote is short and attributed.

---

## 0. What "follow M3" means for this project

M3 ships components for Android, Flutter and Compose. **There is no official
Material web component set for M3** — the shape page says plainly: *"Web is not
currently available"* for the shape library. So "follow M3" here means:

1. Adopt the **foundations** verbatim — colour roles, type scale, shape scale,
   elevation, state layers, motion tokens, breakpoints, accessibility minimums.
   These are platform-neutral and we can implement them exactly.
2. Rebuild our components to the **published component specs** (what a card,
   a chip, a filled button, a navigation rail is made of), since we must write
   the CSS ourselves anyway.
3. Record every deliberate departure in §9 with its reason. An undocumented
   departure is a bug.

---

## 1. Colour — 26 roles, six groups

Source: [Color roles](https://m3.material.io/styles/color/roles).

> "There are 26 standard color roles organized into six groups: primary,
> secondary, tertiary, error, surface, and outline."

Rules that bind us:

- **Roles, not colours.** Components map to roles; the palette is generated,
  not hand-picked. *"Color roles are like the 'numbers' in a paint-by-number
  canvas."*
- **Pairs are contracts.** *"These color pairs provide an accessible minimum
  3:1 contrast."* `on-x` goes on `x`, never anywhere else.
- **Container roles are fills.** *"They should not be used for text or icons."*
- Improper layering *"may break contrast necessary for visual accessibility"*.

### Work

1. Choose one **source colour** and generate the tonal palettes (primary,
   secondary, tertiary, neutral, neutral-variant, error) at tones
   0/10/20/30/40/50/60/70/80/90/95/99/100.
   Candidate source: the brand lime `#C9F24D`. Its tonal ramp gives a dark
   `primary` in light mode (tone 40) — which is what the current black buttons
   already approximate, so the identity survives.
2. Emit both schemes as tokens: `--md-sys-color-<role>` for light and dark.
   Full set: primary, on-primary, primary-container, on-primary-container;
   the same four each for secondary and tertiary and error; surface,
   on-surface, surface-variant, on-surface-variant, surface-container-lowest /
   low / base / high / highest, inverse-surface, inverse-on-surface,
   inverse-primary, outline, outline-variant, scrim, shadow.
3. Delete our ad-hoc `--bg/--bg2/--panel/--panel2/--tx/--tx2/--tx3/--line/
   --line2`; map every use site onto a role.
4. Verify every pair we actually use at ≥3:1, and body text at ≥4.5:1.

Festival stage hues and category colours are **data**, not theme (§9).

---

## 2. Typography — one scale, 15 + 15 styles

Source: [Type scale tokens](https://m3.material.io/styles/typography/type-scale-tokens).

> "Material 3 has one type scale containing two sets of type styles: 15
> baseline and 15 emphasized… The scale is a range of contrasting styles…
> No single product will use all the styles."

Baseline scale (size / line-height / tracking / weight):

| Style | L | M | S |
|---|---|---|---|
| Display | 57/64/-0.25/400 | 45/52/0/400 | 36/44/0/400 |
| Headline | 32/40/0/400 | 28/36/0/400 | 24/32/0/400 |
| Title | 22/28/0/400 | 16/24/+0.15/500 | 14/20/+0.1/500 |
| Body | 16/24/+0.5/400 | 14/20/+0.25/400 | 12/16/+0.4/400 |
| Label | 14/20/+0.1/500 | 12/16/+0.5/500 | 11/16/+0.5/500 |

Emphasized styles are the same sizes at heavier weight, *"best applied to bold,
selection, and other areas of emphasis"* — use for primary-action buttons,
selected items, badges.

### Work

1. Replace our nine invented roles with the M3 names, as tokens
   `--md-sys-typescale-<style>-<size>-{size,line-height,tracking,weight}`.
2. Pick the subset we use: display-small, headline-medium/small,
   title-large/medium/small, body-large/medium/small, label-large/medium/small.
3. Re-map every element (§7 tables).
4. This **undoes the 80% global scale** — M3 body-medium is 14px, close to our
   current 14.4px, but headings become larger and tracking becomes real values
   instead of `normal`.

---

## 3. Shape — corner radius scale

Source: [Shape](https://m3.material.io/styles/shape/shape-scale-tokens).

Scale: none 0 · extra-small 4 · small 8 · medium 12 · large 16 ·
extra-large 28 · full (pill). The expressive update adds large-increased 20,
extra-large-increased 32 and extra-extra-large 48.

Assignments follow the component specs: cards → medium (12), chips → small (8),
FAB → large (16), dialogs and bottom sheets → extra-large (28), buttons and
the search bar → full.

Our four-radius set (`--r-pill/--r-card 36/--r-panel 18/--r-box 10`) is replaced
by the seven M3 steps.

---

## 4. Elevation and surfaces

M3 has six levels, 0–5 (0, 1, 3, 6, 8, 12 dp). In M3 a raised surface is
expressed with **surface-container roles**, not with a heavier shadow — the
tonal step does the work. Plan: shadows only where M3 uses them (menus,
dialogs, FAB, snackbar); everything else changes surface role.

---

## 5. States — one layer, fixed opacities

Source: [States](https://m3.material.io/foundations/interaction/states/state-layers).

> "A state layer is a semi-transparent covering… The state layer is an overlay
> with a fixed opacity for each state and uses the same color as the content."
> "The size of state layers is 40dp while the interactive target size is 48dp."

Opacities: hover 8%, focus 10%, pressed 10%, dragged 16%.
Layer colour = the element's **content** colour, not an arbitrary grey.

Our hovers currently invert to black or wash 10% of `--tx`; both are replaced by
a real state layer.

---

## 6. Motion

Source: [Easing and duration](https://m3.material.io/styles/motion/easing-and-duration/tokens-specs).

- Standard easing, CSS: `cubic-bezier(0.2, 0, 0, 1)` — *"used for simple,
  small, or utility-focused transitions."*
- Emphasized easing is the expressive default; CSS has no single-curve
  equivalent, and the spec says *"N/A (Use Standard as a fallback)"*.
- Durations: short1–4 = 50/100/150/200 ms; medium1–4 = 250/300/350/400 ms;
  long1–4 = 450/500/550/600 ms.

Our single `--ease: cubic-bezier(.16,1,.3,1)` and hand-picked 140–550 ms
durations are replaced by these tokens.

---

## 7. Layout — five breakpoints

Source: [Breakpoints](https://m3.material.io/foundations/layout/applying-layout/window-size-classes).

| Breakpoint | Width | Panes |
|---|---|---|
| Compact | <600 | 1 |
| Medium | 600–839 | 1–2 |
| Expanded | 840–1199 | 2 |
| Large | 1200–1599 | 2–3 |
| Extra-large | ≥1600 | 2–3 |

> "Layouts typically transition from a single pane to two or three panes as
> window size increases."

Navigation follows the same table: **navigation bar** in compact, **navigation
rail** from medium up. That is already roughly what we do — our breakpoints
(620 / 820 / 900) move to 600 / 840 / 1200.

---

## 8. Component mapping

| Ours today | M3 component | Notes |
|---|---|---|
| masthead | Top app bar (small) | 64dp, title = title-large |
| phone nav bar | Navigation bar | 80dp, 3–5 destinations, active indicator pill |
| desktop rail | Navigation rail | 80dp wide, icons + label-medium |
| festival card | Card (elevated / filled) | corner medium 12, not 36 |
| highlight banner | Card, hero carousel item | image + supporting text |
| page dots | Carousel page indicator | keep; already M3-shaped |
| date pill, category chip | Assist / suggestion chip | 32dp, corner small 8 |
| filter chips in sheets | Filter chip | with selected check icon |
| Open planner / Tickets | Filled / outlined button | 40dp, full corner, label-large |
| toolbar triggers | Filter chip or Menu button | |
| search field | Search bar → search view | 56dp, corner full |
| filter sheets | Menu (desktop) / Bottom sheet (compact) | |
| month picker dialog | Dialog | corner extra-large 28 |
| settings card | Bottom sheet / Dialog | |
| toast | Snackbar | 48dp min, corner extra-small |
| timetable grid | (no M3 equivalent) | custom; obeys tokens |
| star toggle | Icon button (toggle) | 48dp target |
| Timetable/List switch | Segmented button | corner full, check on selected |

---

## 9. Deliberate departures

1. ~~Typeface.~~ Resolved: the pages ship **Roboto Flex**, which the type
   scale page nominates by name as the replacement for Roboto, subset per page
   to the characters that page sets. Roboto and then Arial remain only as the
   fallback stack.
2. **Emphasized weights are derived, not copied.** The published emphasized
   token table renders inside an interactive widget that does not expose its
   values as text, so the five weights in `_tokens.css` are one step up the
   standard 400/500/700 ladder rather than the exact tokens. The rule the page
   states in prose is followed — higher weight, applied consistently across the
   set — and adjusting axes is explicitly sanctioned once the typeface is
   swapped, which shipping Roboto Flex does. Replace with the real values if
   they ever become readable.
3. **Category and stage colours.** These encode data (what kind of festival,
   which stage), not theme. They stay outside the role system and are checked
   for contrast against their own `on` colours.
4. **Dot-grid ground.** Not an M3 pattern. It is the product's identity and
   costs nothing in contrast; it fades out past the highlight.
5. **No ripple.** M3's pressed state is a ripple on Android. On the web we use
   the pressed state layer only.

---

## 10. Execution order

Each stage ends with a build, a measured check at compact/expanded/large, and
a commit. Nothing merges on "it looks right".

| Stage | Work | Check |
|---|---|---|
| 1 | Colour: generate palettes, emit 26 roles ×2 schemes, remap every use site | every used pair ≥3:1, body ≥4.5:1 |
| 2 | Type: M3 scale tokens, re-map every element | no element off-scale |
| 3 | Shape + elevation: 7 radii, surface-container levels | no ad-hoc radius or shadow left |
| 4 | States + motion: state layers, M3 easing and durations | hover/focus/pressed present on every control |
| 5 | Breakpoints: 600/840/1200/1600, rail vs bar | layouts at each breakpoint |
| 6 | Components, home page (§8) | 48dp targets, roles correct |
| 7 | Components, planner pages | as above, plus grid legibility |
| 8 | Info pages, settings, footer | as above |
| 9 | Motion patterns: lateral, top-level, container transform | each transition names its pattern |

Stages 1–5 are mechanical and touch every page; 6–8 are per-page.
