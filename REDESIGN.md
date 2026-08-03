# Flanner — M3 Expressive redesign plan

Read from m3.material.io on 3 August 2026. `DESIGN.md` records the *baseline*
M3 pass already shipped (roles, type scale, shape scale, elevation, states,
easing tokens, breakpoints). This document is the next pass: **layout,
components and behaviour**, against M3 Expressive.

Quotes are short and attributed to the page they came from.

---

## 0. What we got wrong, and what changed under us

Two separate problems.

**Ours.** The last pass was a *token* pass. Every colour became a role and
every size became a type style, but the page kept its old bones: a hand-built
two-pane banner, a search slab with two dropdown pills, a floating glass
capsule standing in for navigation, a one-column feed at 1280px. Nothing on
the home page is actually a Material component. Retokenising a custom
component does not make it a Material component.

**Theirs.** M3 Expressive shipped in May 2025 and is *not* a coat of paint:

> "The physics system is replacing the previous system based on easing and
> duration." — Motion, *how it works*

- **Motion physics** (springs) replaces easing + duration. The old tokens are
  explicitly "a fallback".
- **14 new or updated components**, including three we need: toolbars,
  button groups, FAB menu.
- **Emphasized type styles** — a second set of 15, for hierarchy.
- **35-shape library + shape morph** — corners animate on press and selection.
- **New corner radii**: large-increased 20, extra-large-increased 32, xxl 48.
  "Fully rounded corners" is now `full`, not 50% of the component.

So the honest statement of scope: this is not a theme change. It is replacing
the home page's hero, toolbar, feed, navigation and buttons with the Material
components that exist for those jobs, and replacing our animation model.

### Availability, stated plainly

Every component page lists a status row for Web. Buttons: **Web available**
(that's `@material/web`, baseline only), **Web Expressive unavailable**. App
bars, toolbars, carousel: **Web unavailable, both**. So we keep writing the CSS
ourselves and build *to the published specs and anatomy*, naming M3 tokens.
That is the same rule as `DESIGN.md` §0, and it still holds — there is no
option to import these.

---

## 1. Motion — the physics system

Material publishes an official spring→curve conversion **for the web**:

> "Use springs when possible, otherwise use curves that mimic the springs for
> animations without interruptions or gestures." — Motion, *specs*

| Token | Curve | Duration |
|---|---|---|
| expressive fast spatial | `cubic-bezier(0.42, 1.67, 0.21, 0.90)` | 350ms |
| expressive default spatial | `cubic-bezier(0.38, 1.21, 0.22, 1.00)` | 500ms |
| expressive slow spatial | `cubic-bezier(0.39, 1.29, 0.35, 0.98)` | 650ms |
| expressive fast effects | `cubic-bezier(0.31, 0.94, 0.34, 1.00)` | 150ms |
| expressive default effects | `cubic-bezier(0.34, 0.80, 0.34, 1.00)` | 200ms |
| expressive slow effects | `cubic-bezier(0.34, 0.88, 0.34, 1.00)` | 300ms |
| standard fast spatial | `cubic-bezier(0.27, 1.06, 0.18, 1.00)` | 350ms |
| standard default spatial | same curve | 500ms |
| standard slow spatial | same curve | 750ms |
| standard fast/default/slow effects | as expressive | 150/200/300ms |

Note the y-overshoot above 1 on the spatial curves — that is the bounce, and it
is why every "spring" we ever hand-rolled and then deleted as un-M3 was
directionally right and specifically wrong.

Rules:

- **Spatial** springs animate position, size, rotation, **corner radius**.
  They overshoot. **Effects** springs animate colour and opacity, and must not.
  We currently animate opacity and transform with the same curve everywhere;
  that stops.
- Speed by element size: fast = small components (switch, button, chip),
  default = partially-covering surfaces (sheet, expanded rail), slow = full
  screen.
- Scheme: **expressive** is the default and is for "hero moments and key
  interactions"; standard is "for utilitarian products". Flanner picks
  **expressive** for the hero carousel, view switches and card presses, and
  **standard** for the timetable grid, which is a dense utility surface where
  bounce would read as jitter.

Implementation: `--md-sys-motion-spring-{scheme}-{speed}-{spatial|effects}`
plus a matching `-duration`. `--ease` is retired; the legacy easing tokens stay
in the file only as the documented fallback.

---

## 2. Home page

### 2.1 Hero → Material **carousel**, hero layout

The banner is currently one static card that swaps its contents. The component
for this exists:

> "Hero: Spotlighting very large visual items (like a movie or featured app)"
> — Carousel, *guidelines*

Adopt the **hero layout, start-aligned, snap-scrolling**:

- One large item plus a peek of the next. Research finding, quoted on the
  overview page: "A previewed or squished item strongly indicated that there
  was more content to swipe through." That is what our dots were trying and
  failing to say.
- **Items change size as they move through the carousel**, and item visuals
  get a **parallax** offset against the item frame.
- **Dynamic shape**: item corners morph while scrolling (spatial spring).
- Compact: one large + one small. Expanded and up: more large items visible.
- Small items are 40–56dp wide. Item text adapts: full title on large, title
  hidden on medium, abbreviated label on small.
- Required, because our page scrolls vertically: a **Show all** affordance —
  "carousels require an accessible way to view all the items without
  horizontally scrolling". Our heading gets the arrow icon-button variant.

The current arrows + dots go away; snap-scrolling and the peek replace them.
Keyboard and screen-reader users get the Show-all path plus arrow buttons at
non-touch pointers.

Retire the two-pane "panel left, image right" card. The text moves onto/below
the item per the hero anatomy, and the details it carries today (blurb, keyword
chips, two buttons) move to the card the carousel item links to.

### 2.2 Toolbar → search bar + filter chips + segmented button

Three fixes, all from published specs:

- **Search bar**: `surface-container-high`, and "avoid using a surface
  container high color on a surface container background… use surface
  container roles that are more than one step apart". Ours currently sits on
  the page surface with an outline. Focus opens a **search view**: full-screen
  in compact, docked with a scrim in medium and up.
- The two `All ⌄` dropdown pills become a **filter chip** row — month and
  category — with the selected check icon. Chips are the component for
  "filter content"; a pill that opens a menu is a menu button pretending.
- The view switch becomes a real **segmented button**: full corner, check icon
  on the selected segment, label-large.

### 2.3 Festival list → **feed** canonical layout, with a list at compact

> "Use a feed layout to arrange elements like cards in a configurable grid"
> — Canonical layouts

And, from Lists → *adaptive design*, the swap we should have been making all
along:

> "Information displayed in list items on mobile can change to cards on tablet
> and desktop."

So: **compact = list items** (leading media, label, supporting text, trailing
star as icon button, edge-to-edge, gaps not dividers — "Use gaps for contained
lists… Limit dividers to uncontained or complex lists"). **Medium and up =
card feed**, 2/3/4 columns by breakpoint. That replaces the current
compact-tiles / detailed-cards toggle, which was a device preference standing
in for a layout rule.

Card anatomy per spec, and the lime swoosh over the artwork goes: the category
becomes a chip in the card's content area, not a shape cut into the image.

### 2.4 App bar

Adopt the **small app bar with subtitle** (an Expressive addition), and:

> "On scroll: No drop shadow, instead a color fill creates separation from
> content" — App bars

FINLAND becomes a trailing menu button in the bar. Title = title-large,
subtitle beneath, per the flexible-bar anatomy.

### 2.5 Navigation

The glass capsule becomes the two real components, which is what the
breakpoint table already told us:

- Compact: **navigation bar**, 3–5 destinations, active indicator pill, icon
  fills when selected.
- Medium and up: **navigation rail**, collapsed by default, 3–7 items,
  top-aligned, with a **menu button** that expands it. "The active indicator
  hugs the label text in the expanded nav rail."
- The rail is the correct home for a **FAB** — "the container of the
  navigation rail is ideal for anchoring the FAB… placing the app's key action
  above navigation destinations", at elevation 0 when nested. Flanner's key
  action is *my plan*, which is currently a destination competing with three
  others.
- Selecting a destination uses the **top-level transition**, with the active
  indicator expanding from the centre of the icon.

### 2.6 Buttons

Five sizes (XS/S/M/L/XL), two shapes (round/square), five colour styles.
Concretely:

- Open planner = **filled**, Tickets = **outlined**; both size **Medium** in
  the hero, **Small** in cards. Not two identical full-width black slabs.
- **Shape morph on press** — corners go squarer while pressed, spatial spring.
  Corner values by size: square containers 12/12/16/28/28dp for XS/S/M/L/XL,
  pressed 8/8/12/16/16dp.
- Small-button padding moves 24dp → **16dp** ("no longer recommended" at 24).
- Icons 20dp, and icon and label share one colour.

This is also where the user's "buttons are black or white, only labels have
colour" rule meets the spec cleanly: filled = `primary`/`on-primary`, and our
`primary` is already the deep olive, with the lime living in
`primary-container`. No new colour enters the page.

---

## 3. Planner pages

### 3.1 **List-detail** canonical layout

The planner is a list of acts and the details of one act — that is the
canonical layout by name. Compact: list, and selecting opens a full-screen
detail. Expanded: two panes side by side, detail on the right. Today a tapped
act opens a sheet at every size, which wastes an expanded window.

### 3.2 Map becomes a pane, not a destination

Folded into the **segmented button** with Timetable and List, as approved
earlier. That drops the nav rail to three destinations plus the FAB.

### 3.3 **Docked toolbar** for the act controls

New in Expressive, and it replaces the bottom app bar:

> "The bottom app bar is no longer recommended and should be replaced with the
> docked toolbar, which functions similarly, but is shorter and has more
> flexibility." — Toolbars

Constraint to respect: "Don't show [a toolbar] at the same time as a
navigation bar." So compact keeps the navigation bar and the controls stay in
the content; medium and up gets the docked toolbar (day switch, starred
filter, download), since navigation there is the rail.

### 3.4 Act blocks and the star

- Star = **icon button, toggle**, 48×48dp target, shape morphs round↔square on
  selection.
- Selected act blocks morph corners rather than only changing colour.
- Timetable times use **tabular figures** — "Use tabular numbers to prevent
  layout shifting when values change".
- The 9px micro style stays, and stays documented (`DESIGN.md` §9).

---

## 4. Type

Adopt the **emphasized** set as a real second axis, not as an ad-hoc
`font-weight: 700`:

- Emphasized for hero titles, selected segments and destinations, filled
  buttons, unread/starred counts.
- Baseline for everything else.
- Ship **Roboto Flex** (variable) instead of the fixed-axis Roboto, so
  emphasized weights and optical sizing come from one file. Google Sans Flex is
  Google's own expressive face and is not licensed for us to self-host, so
  Roboto Flex — Material's own baseline family — is the correct choice, not a
  compromise.
- Type colour rules, now enforced: `on-surface` default, `on-surface-variant`
  as the alternative, links `primary` **and underlined**.

---

## 5. Shape

- Add the three Expressive radii: 20 / 32 / 48.
- **Shape morph** on press and on selection, driven by spatial springs, for
  buttons, chips, the star toggle, carousel items and selected act blocks.
- Deliberate tension: "using sharp shapes, thereby adding tension, creates more
  dynamic design". The feed is uniformly 12dp today. Give the carousel item and
  the FAB a distinctly different corner so the hero reads as the hero — one
  break, not a scattering.
- Abstract shapes stay **decorative only** (image crops, the mark). "Don't
  compromise clarity for the sake of visual design."

---

## 6. Hero moments — pick two, no more

> "Stick to one or two hero moments in your product; too many moments can be
> overwhelming or distracting."

1. **The carousel item opening its planner** — container transform, the item's
   image and title growing into the planner masthead.
2. **Starring an act** — shape morph plus the icon-button toggle, the one
   moment the product is *for*.

Everything else stays quiet. This is the rule that stops the redesign from
turning into an animation showcase.

---

## 7. Execution order

Each stage: build, measure at compact / medium / expanded / large, `node
--check` the script blocks, commit, verify live.

| # | Stage | Check |
|---|---|---|
| 1 | Motion physics tokens; retire `--ease`; split spatial vs effects | no transition uses an effects curve for movement, or vice versa |
| 2 | Roboto Flex + emphasized styles; type colour rules | every emphasized use is one of the four sanctioned cases |
| 3 | Shape: 3 new radii, morph on press/select | morph present on button, chip, star, carousel item |
| 4 | Home hero → carousel (hero layout, snap, parallax, peek, Show all) | one large + one small at compact; keyboard path works |
| 5 | Home toolbar → search bar + search view, filter chips, segmented button | search view full-screen at compact, docked above |
| 6 | Home feed: list at compact, card grid at medium+ | column counts by breakpoint; no device-preference toggle left |
| 7 | App bar (small + subtitle, scroll fill); nav bar / nav rail + menu + FAB | rail collapses and expands; one active indicator only |
| 8 | Buttons: 5 sizes, filled/outlined mapping, 16dp small padding, 20dp icons | no full-width black slab pairs remain |
| 9 | Planner: list-detail layout, map into the segmented button, docked toolbar | two panes at expanded; toolbar and nav bar never co-visible |
| 10 | The two hero moments; container transform card → planner | named pattern per transition; nothing else animates on entry |

Stages 1–3 are global and mechanical. 4–8 rebuild the home page. 9 rebuilds the
planners. 10 is the polish that only makes sense once the components are real.

---

## 8. What this plan does *not* do

- No ripple. Web has no ripple in the spec's own web guidance; the pressed
  state layer plus shape morph carries it.
- No dynamic/user-source colour. The brand lime stays the single source.
- Category and stage colours stay data, not theme (`DESIGN.md` §9).
- The dot-grid ground stays. It is the product's identity, it costs nothing in
  contrast, and Expressive explicitly widens the room for decorative
  non-interactive flourish.
