# Flanner

Plannable timetables for Helsinki festivals — **<https://uenian33.github.io/flanner/>**

Each page carries its own markup, styles and data; the type, the libraries and
the pictures are files the whole site shares. It keeps working with no signal —
the worker holds the pages and everything they name — and it is installable to a
home screen, where it opens without browser chrome.

| Page | |
|---|---|
| `/` | Festival list, highlights, search and filters |
| `/kallio/` | Kallio Block Party 2026 — 98 acts, 9 stages |
| `/flow/` | Flow Festival 2026 — 156 sets, 10 stages, 3 days |
| `/about/` `/terms/` `/privacy/` | About, terms, EU data policy |

## Building

Everything under `scripts/` generates the pages; never edit the built HTML.

```bash
python3 scripts/build_planner.py   # kallio/index.html, flow/index.html
python3 scripts/build_home.py      # index.html
python3 scripts/build_info.py   # about, terms, privacy
python3 scripts/build_og.py     # social cards
cd scripts && python3 build_pwa.py   # icons, manifest, service worker
python3 scripts/build_seo.py    # robots.txt, sitemap.xml, IndexNow key — run last
```

`python3 tools/theme_parity.py` checks the browser's colour engine against the
build's, tone for tone and token for token. Run it after touching either.

`build_seo.py --submit` additionally pushes the six URLs to IndexNow (Bing,
Yandex, Seznam, Naver). Google has no equivalent ping and picks changes up by
crawling, or immediately if the URL is submitted in Search Console. To verify
ownership there, paste the token into `GOOGLE_VERIFY` in `scripts/seo.py` and
rebuild — every page then carries the meta tag.

Shared pieces are single files the home and info pages include — `_nav.css`,
`_footer.html`, `_settings.html`, `_pagefx.html`, `_offline.html` — so the bar,
footer and settings card cannot drift between them.

The home page's navigation is the planners' navigation at every width: a 96px
rail from 600 up, and below that the same four-cell bar, whose last cell opens
the rail as a 280px drawer — the mark and the name at its head, the same three
destinations, a hairline, then the utilities as labelled rows. It is one
element throughout, so the destinations and the utilities in the panel are the
buttons from the bar with the handlers they already had. Below 600 the bar is
the planner's bar measured off it rather than described a second time: 16px of
air under it, `min(94vw, 430px)` wide, 64 tall on the extra-large corner with
6 of padding, the card tone at 88% behind `blur(14px) saturate(1.4)`, a
hairline of outline-variant at 60%, and a 54×30 indicator on a 16px corner
behind the icon of the cell you are on. It states the same two heights, 64 and
48, and minimises the same way — the label's box collapses and the icon takes
the middle. The planner's is the same capsule less 72px, which is where its
back button stands; this page is where back goes, so that width is a fourth
destination instead.

And it is the one page on the site with no colour of its own. Every planner is
themed from its festival's own hue, so a list of them cannot be: a shell in
some third colour would be advertising a hue that belongs to nothing on it,
and each planner's would arrive as a clash rather than as the festival's. So
`build_home.py` asks `m3color` for Material's **monochrome** variant — the
scheme variant that sets all five palettes to chroma 0 and re-tones the
accents, primary to the ends of the ramp and its container in to 25/85, whose
numbers are the `isMonochrome()` branches of material-color-utilities. What
colour is left on the page belongs to the festivals: their photographs,
their wordmarks and their drawn covers, and nothing else. The mark goes with it — `--mark-ink` is
primary here, which is tone 0 on paper and tone 100 in the dark, where the
planners keep the brand's green because there the mark is the one thing on
the page that is not the festival's.

Two things followed from taking the hue out. The card was five tonal palettes,
one per category, written as light-only hexes — so a pale pink card burned a
hole in the dark page. It is one theme now and every value in it is a role, so
it follows the theme and stands in step with the chrome around it; the
category is still on the chip in words and still drawn as its own motif behind
it, which is what was carrying the meaning alongside the colour. And the
calendar's five category colours are one tonal bar with a filled one for what
is in your plan, so the legend that keyed those five is down to the sentence
that explains that — five identical grey swatches would be a key to nothing.

The cover a card draws when a festival has no photograph is the third of those
three, and it is the festival's own colour rather than the page's. A festival
with a planner of ours takes the colour that planner is themed from — the
`accent` in `festivals.json`, Flow's `#fff203` and Kallio's `#b6fc46` — so the
card and the page it opens are one colour and the tap between them is not a
change of subject. A festival we have not built a planner for has no colour of
its own to borrow, so it takes its category's, the one already on the chip in
the corner: art, music, film, culture, others, from `categories.json`.

Only the hue travels, which is the rule the planners follow too. The ramp keeps
the five tones it already resolves to as a grey — the page mixes its own ink
into its own paper at 8, 16, 24 and 70 per cent — and takes its chroma from the
planner's own artwork roles, so the two drawings are the same drawing in two
hues. Nothing moves a lightness: the motif holds 7.9:1 on its ground in the
light theme and 9.1:1 in the dark, which is what the grey held. And the ramp
never claims more chroma than the source colour has, so `others` — a grey by
definition — stays the exact grey it was. `schema.artwork_css` generates it,
one rule per category and one per themed festival, keyed off the `data-cat` and
`data-id` the card already carries.

**The five category colours are a setting, not a derivation.** They live in
`data/categories.json` and nothing else on the site decides them:

| | | |
|---|---|---|
| Art | `#ff9ec4` | pink |
| Music | `#FFD8E8` | pale pink |
| Film | `#b69df8` | purple |
| Culture | `#ffc861` | amber |
| Others | `#d9d9d9` | grey, and grey on purpose |

Film is purple rather than the blue it was: it lands on Material's own
baseline purple once toned — a scheme sourced from it puts primary within a
hair of `#6750a4` — and it is set at the tone the other four are set at, so
the family keeps one lightness and one chroma range and only the hue changes
between them. Editing one of these five re-themes every drawn cover, calendar
bar and highlight for every festival in that category; nothing needs touching
in a stylesheet.

The same five values feed three things: the cover's ramp, the highlight's
scheme, and the calendar bar. A festival's own `accent` overrides all three
where it has a planner.

Three controls on this page are the planner's rather than this page's, and
they are copied value for value rather than approximated. The masthead's
search is the planner's search button — no border, a 5.5% resting wash, an 8%
inset flood on hover, 20px glyph in a 44px disc — and the masthead draws no
rule under itself, because a planner's bar does not either: what separates it
from the page is that the page runs under it. The highlight's three actions
are `.fest .actions`: three equal shares of the row, 48dp on a 16px corner
that opens to 28 under a pointer, label-medium at 600 beside an 18px glyph, on
the white step above the card, with the plan button filling in the festival's
tint and taking half a share more of the row once it is pressed. And starring
throws the planner's own blast — two rings, then waves of streaks, sparks and
stars — in the festival's colours, read off the card rather than written down.

A favourite is a star on this site, so a card in the list carries one: the
page's own grey until it is starred, the festival's own colour once it is.
The highlight keeps the heart, because the card it is a copy of does.

The two planners are one design, held in `scripts/planner.artifact.html`
exactly as it was exported: a template with `{{ }}` bindings, the component
that feeds them, and the runtime that compiles the one against the other.
Nothing in it is edited by hand — `build_planner.py` unpacks it and substitutes
each festival's stages, sets, days and facts, and every substitution is
anchored to a string in the design and fails the build if that string moves.
Re-exporting the design and dropping the new file in place is the whole update
procedure.

Besides the line-up, the build makes these changes to the design, each one
anchored the same way and commented where it is made:

| | |
|---|---|
| Nothing the phone can mistake for a link | A stage is called Main Stage and a set runs 21:00–22:00; iOS reads both as things to link, wraps them in an anchor of its own and paints them blue — which is what a real phone showed of the map's stage list. Three answers: the row and the name state their colour rather than inheriting one, the page asks for no detection at all with `format-detection`, and where an anchor is injected anyway `a[x-apple-data-detectors]` takes the colour of the text it replaced. |
| One colour per stage | The design colours a set by what kind of act it is, which is three colours for ten stages. Each stage takes a tonal palette of its own instead, generated by `m3color`, stated for both themes as `--st<n>-*` variables so the grid follows the theme. |
| A travelling indicator | M3 draws one indicator for a navigation list and moves it. The pill is measured off the current destination — drawer row, rail pill or bar pill — and slides on the emphasised spring; it also follows the page, so reaching the programme moves it to Programme and unfolding the cards brings it back to Info. |
| One day at a time | The design draws a single sample day. The programme, the filter counts, the stage counts and every heading are scoped to the day on screen. |
| A real forecast | Fetched from Open-Meteo for the festival's own coordinates — the mean of its stages — for the hours it is open, three apart; the card and the temperature in the bar stay away until it answers. The design's caption called its sample numbers illustrative and they were, so it said `Alppila · illustrative` over real ones for a while. It says which kind they are now: a festival still to come is a `forecast`, one that has been is `recorded`, since Open-Meteo answers for a past date too and what it sends back is what happened. The sentence above them follows the same tense. |
| The name in the cell | A cell says who is playing, and every other thing in it was taking room from that. The genres are gone — the act's card and every row of the list carry them. The star has moved to the bottom-right corner, out of the line the name starts on, and the name is clamped to the whole lines that fit above it. On a phone the cell keeps 2px from its lane instead of 10 and 7px of inset instead of 9, and its bar stays compact for the whole of the programme rather than resizing under the thumb on every scroll. |
| The artist card | Pressing a set opens the act's own card: the name over the artwork, the organiser's introduction, the act's Spotify, YouTube, SoundCloud and Instagram pages, its tags and the two actions. The card is the exported design's own stylesheet and markup, rule for rule — `CARD_CSS` in `build_planner.py` is its `<style>` block from the strand themes to the end of the adaptive rules, and nothing sets a property it already sets. Five departures, each commented where it is made: its reduced-motion rule is scoped to `.ac` rather than to every element on the page; its light-theme colour names are emitted under `:root:not([data-theme="dark"])`, because the planner's own scheme declares them only for the dark theme; the hero is as tall as what stands in it rather than 16/10, since the artwork is generated and there is no photograph to frame; on a phone the body is a column rather than a grid of auto rows, which shared the card's spare height out between the blocks; and the stage pill hugs its label instead of stretching across the hero. It grows out of the cell along an arc and shrinks back down the same one; a drag from anywhere throws it home. |
| The list row, at a phone's size | The design draws a row for a screen with room in it: a 96×72 picture, a 17px name — the size of the festival's own name in the bar above it, and heavier — and two more sizes under that. On a phone it is M3's list item instead: a 56dp square image rounded to 16, the type label gone, and the three lines taking the type scale's own steps, Title Small over Body Small, which puts the act's name a step below the bar's title rather than level with it. The artwork takes the stage's palette, the one the cell and the card's hero take — in the deep tones the hero is drawn in when the act is in your plan, and in the quiet tint the Lineup wears when it is not, so a list of eighty acts is a light column with the plan standing out of it rather than eighty full-chroma squares among which the plan is lost. Above 640px the row is the design's own. |
| One star, one state | The card's star and its `Add to plan` are the same state and always were, but the flood that fills the star was written for a `.ac__tool` this card does not have — so a starred act kept an outline star and its fill was clipped to nothing for good. It floods now, in the colour the plan button is filled with, and the sparks come out of the star whichever of the two was pressed: a blast out of the wide button says nothing, out of the star it says the star has changed. |
| What you starred goes where it is kept | Pressing the star turned a cell dark and put a number up somewhere else on the screen, with nothing between them the eye could follow — so the cell goes: a copy leaves the grid on the card's own arc, stretches along the line of travel, necks down across it and is drawn through the button that counts your picks, which answers with a beat of its own. A row in the list sent nothing, and for a reason: it is the width of the screen, and a thing that wide drawn through a 40px button is a curtain closing rather than an act being put somewhere. So a row sends its picture, and only its picture: already the act, already square, already the shape of the thing it is going into, and the one part of a row that can be made small without anything in it being squeezed — a squeezed word is the one thing that reads as a trick. It takes the same eased arc at the same eased speed and keeps its proportions the whole way: one scale for both axes, no stretch, no neck, no corner morph. Those belong to the minimise a cell makes, and a minimise is for a thing whose shape is arbitrary; warp a picture and it reads as the picture being wrong rather than as the picture being put away. The grid's cell still makes it. Only starring flies; unstarring does not, and neither does anything under reduced motion. |
| My plan, as a filter | The third destination narrows the list to what you starred rather than opening a page of its own: same list, same three controls over it, one more clause in the one predicate the list and the calendar both ask. So Time, Type and the three shapes the list takes all keep working inside it, and a page of its own would have had to grow each of them again and then drift from them. The heading says which list it is — `All Festivals` or `My Plans` — the empty line says which of the two nothing-founds this is, and the highlight steps out, being a rail of what is coming up rather than of what you chose. Reaching either of the other two destinations leaves it, because they are places on the page and this is a state of it; and while it is on, the observer that names the section you are reading holds off, since the list is the same element either way and scrolling it would send the mark back to Festivals. |
| A language, not a place | The masthead's control chose a place from a list of two, on a site that only covers one country, and nothing on the page read the answer. It picks the language instead — the same three a planner's own picker offers, so the site has one set rather than one per page — and the choice is kept on the device and put on the document, where the browser's translate offer and a screen reader's voice both read it. What it changes on the page today is the category names, the one pair of labels the data carries twice; the sheet says so rather than leaving a reader to find out by picking one and watching nothing happen. The rail's Language button, which said `English only for now` and did nothing, opens the same picker. The trigger shows the code and the list shows the names: the bar sets that label in uppercase with wide tracking, where `SVENSKA` takes half the row from the search beside it. |
| Keeping the plan | A plan lives on the device, so the page that keeps one offers to be on the device too — a tonal band above the plan, in the plan view only, where the offer is about the thing you are looking at. There is no one way to ask: Chromium fires `beforeinstallprompt`, which can be held and replayed from a press, and that is the only path where the button installs anything. Every browser on iOS is WebKit whatever its name, and Firefox on Android has no such event either, so there the button explains, with the steps that browser actually needs rather than a line about the browser menu. Nothing is offered inside an already installed window, or once the offer has been answered either way — asking again every visit is what makes these hated. It sits one step of the surface ramp above the cards it stands over, `-high` against their `-low`, so it separates by a shade rather than by weight: on secondary-container, four steps down, it was a slab, and the eye went to the block instead of the words. |
| A press that only closes | Any selector on this page closes when something outside it is pressed, and that press does nothing else. It is caught on the way down rather than on the way up: closing used to happen while the press bubbled, so it reached whatever was under it too — reaching past the language list to shut it landed on a festival and opened that festival's planner. |
| The bar takes the name of what you are reading | Once a section's heading has gone under the masthead, the bar carries that section's name, and gives it back when the heading comes out again — the rule a planner's bar follows with the festival's name, on the same fade-through. Both headings are in one ordered list, and the last one that has passed under the bar is the one the bar says, so scrolling out of the highlight and into the festivals hands the name over rather than clearing it: `Highlights`, then `All Festivals` — or `My Plans`, since the bar says whatever the heading says. Read on scroll rather than watched with an observer, because the answer is which of several is lowest past the line: one ordered pass over two rects says that directly, where two observers each know only their own and have to be reconciled. A heading in a section that is not on the page does not count, which is what keeps `Highlights` out of the bar while the plan is showing. It followed `at-cards` before — on as soon as the list owns the middle of the screen — which put the words in the bar while the heading was still in plain sight under it. |
| Three whole lines, or none | The About card shows three lines and folds the rest behind `Read more`. The window was `calc(3 * 1.45em)` on a box that inherited the card's 15px while the paragraph is set at 13 — 65.25px over an 18.85px line, which is three lines and 46% of a fourth, sliced through the middle of its letters. The size is restated on the box so the `em` it counts in is the line it is counting. What decides whether there is a `Read more` at all already measured the paragraph's own leading; this is the box catching up with it. |
| The same throw on the list page | Starring a festival here does what starring an act does in a planner: a copy leaves the page on the card system's arc, stretches along the line of travel, necks across it and is drawn through **My plan**, whose icon answers out and back on the emphasised curve and whose count arrives a beat later. The list's cards only: the highlight is one card filling most of the screen, and a copy of it flying is the page itself leaving rather than a festival being put away. What travels is the card's picture, tile or row alike, at its own proportions the whole way — one scale for both axes, no stretch and no neck. The count is M3's badge, in `error` — the one role the monochrome variant keeps, semantic colours being exempt by construction, so the page gets a highlight colour without getting a hue that belongs to no festival on it. The throw is the phone's alone: above the bar's width the plan lives in the rail down the side of the page, and a copy crossing a wide page to a column that never left view is travel for its own sake — the count going up says it. The test is which cell is showing rather than a width written down twice. The count itself follows that cell either way: the shell's dock below the rail's width and the rail's own above it, put back whenever the dock repaints. Written only when it changes — setting the text replaces a node, which is a change on the row being watched for exactly that repaint, and a badge that rewrote itself every time hung the page. |
| One scroll, and one grip | The sheet is the scroller rather than the block under its picture, so the picture goes up with the words instead of standing over them, and because the sheet is as tall as what is in it up to the height there is, a card with more to say opens taller and a short one never scrolls at all. Nothing behind it moves while it is up. The row of actions rides at the foot of that scroll, 14px clear of the edge. And the gesture is M3's rule for a sheet with something scrollable in it: the handle and the header move the sheet, the content scrolls itself — the player is a cross-origin frame with its own track list, a finger on it belongs to it, so the picture above it is the sheet's grip and a drag that starts there always moves the sheet, wherever it is scrolled to. Anywhere else the old rule holds: a drag from the top of the content dismisses, one from the middle of it scrolls. |
| A bottom sheet on a phone | Below 640px the card is M3's modal bottom sheet rather than a page: it rises from the bottom edge on the emphasised decelerate, stands on that edge with a 28px top corner and its drag handle, and is as tall as its own content — a card with a player fills the screen, one with a name and two tags is half of it. It never covers the whole screen, so the timetable stays in view, and the page behind steps back — scaled and rounded — while it is up. Dragging it down moves it with the finger and only from the top of its content, so an introduction can still be scrolled; far enough or fast enough and it carries on out of the screen, otherwise it springs back. Above 640px nothing changes: the card still grows out of the cell that was pressed and is still thrown away in any direction. |
| The card rises once | A callback ref is read by identity, so a fresh arrow in the render's own bindings is a new ref on every render: React took the card off the old one and put it on the new one each time, and since the ref is where the card is played in, the card played in each time — four rises on opening, and another for every render after. The ref is the setter itself, one function for the life of the component, and which card has been played in is forgotten when no card is open rather than when the element goes. Nothing in that ref touches state: React calls a ref while it is still committing, and a `setState` from inside one throws and stops the component rendering. What a card needs set is set where a card is asked for — `openCard`, which every way in now goes through: the cell, the row, the Lineup and the key that stands in for any of them. |
| A dark hero, in the stage's colour | The artwork is ours, so it takes the stage's hue at the tones the design drew it in — and it takes the dark scheme's tones under both themes. A 46% wash sits over it and the name on top is white: tinting a light picture down to carry white text left a grey with no colour in it. |
| A player, where there is something to play | Spotify embeds an artist, an album or a track from its own URL, so those play in the card — its own card, at its own height, with no cover, name or play button of ours standing over it saying the same three things again. Spotify draws that card two ways from the one URL, and a phone opens the short one: the act, its Follow and its play button, with a chevron under it that turns as the card grows to the full height and the track list arrives. YouTube embeds a video, and every YouTube link in this data is a channel, so those stay links. The embed is there when the card opens, which is why `frame-src` names the two hosts: opening an act now asks Spotify for it. Neither embed starts playing by itself. |
| Its own place | The design's three sample cities become the festival's own; the language picker keeps its job and names the festival's days in each of its three languages. |
| The festival, at a phone's size | Below 640px the festival's own card is a second design of ours, `festival-mobile.html`, carried over rule for rule: the artwork with the notch cut into the page, the meta list, the genre rail, the plan button beside its two square actions, and an About card that opens on `Read more` and states three facts under a rule. The design's headline is not in it: the bar names the festival at the top of every view, and a page states its name once. Nor is its Set times chip, which the bar's own Schedule destination is. What is left of the status row is the live chip, on the days it is true. The facts are set at the size the Lineup sets an act's name in, one size for the two things on the page that name something. `FEST_CSS` is that file's stylesheet with every selector scoped to `.fest`; its type scale moves onto that element because the planner's root declares one of its own, and the colour roles it names at the root are the planner's roles already, so they are simply used — the artwork's five arrive with the strand class the card system puts on the element. The design's three facts are the admission; ours are the line-up: stages, length, acts. Where the design generates strand artwork the page shows the festival's own photograph, the one the home page's card carries, and the festival says what it is the way an act does: the artist card's hero, rule for rule — the flat 46% wash rather than a gradient, so the line keeps its contrast wherever the picture is light; the date and hours over the name in the strand's tint; and the place as the pill that goes to the map. Nothing under the picture repeats them, which is what the list of facts there used to be. The picture, the chips and the actions are one card, at the card system's own proportions — a 12px inset around a 20px picture inside a 28px corner — so the block stands with the About card under it rather than as three loose things, and the two links step up a tone to the surface above the card, since the same colour on both read as one shape. The strand is a filled chip at the head of the genre row rather than a notch cut into the corner, four chips in all — a fifth only ever showed as a sliver at the edge — and they are set at the size of the button labels beside them. The page has two sizes under its headings and no more: 13 for a sentence or a fact — the About copy, the facts under its rule, the forecast's own line — and 12 for a label, which is what a chip, a button and a set time are. And the About card's `Read more` is there only when there is something folded away: the introduction is measured against three lines of its own leading rather than against the box, because the box is what opens and measuring it during the 340ms it takes answers for a height it is halfway through leaving, and what it costs to get in is a fact in the About card with the others. Under the actions is the Lineup, a row you scroll: an act is its artwork in its stage's tones, its name and when it plays, a starred one wears a ring and a tick, and pressing one opens that act's card — the same card the timetable opens. Who is in it is the festival's own headliners first, in the order the record names them, then the act that closes each stage they have not already spoken for. `See all` goes to the programme. It is laid out on the three edges the forecast card already keeps: a card on 12, a surface inside it on 24 — the picture, the chips, the actions, the forecast's hourly rows — and a word on 36. So the Lineup's heading and the first face in its row line up with About's heading, its copy, the facts under its rule and the forecast's own sentence, and the trailing `See all` ends where that copy ends. Above 640px nothing changes and the wide card is the one that renders. |
| The festival's own hue | The design is drawn in one green, and that green is the card system's rather than any festival's. A planner is one festival, so it is drawn in the colour that festival publishes: `accent` in `festivals.json` — Flow's `#fff203`, which is the `--brand-primary` in Flow's own stylesheet. What turns is the hue and only the hue. Every token keeps the lightness and the chroma the design gave it, so no contrast pair moves: the page changes colour without changing tone. And only what is already in the seed's hue turns — the warm heart, the pink plan sheet and the amber and violet strands are deliberate second colours, and a rotation that swept them up would flatten the scheme into one hue. The stage wheel starts at the festival's hue too, so its main stage is the festival's colour and the other nine are the golden angle away from it. The values are read out of the design rather than restated: 39 of the light tokens are declared in the card's own block, 26 exist nowhere but as the fallback beside each use, and the dark ones are declared once by the design — a re-theme that missed the 26 would turn the dark page and leave the light one green. |
| One hue, on the whole page | The forecast had a colour of its own — a pink, picked against the green — and dynamic colour would put a role like that at tertiary, hue + 60. It goes to the festival's own hue instead: one hue for the whole page reads as one page, where a forecast sixty degrees off the festival it belongs to read as something borrowed from another app. It keeps its own tones, so it is still a surface of its own rather than the About card again, and the temperature in the bar follows because it is drawn from the same six. The amber a plan is starred in goes the same way and for the same reason: a page carrying its festival's colour plus two others is a page of three colours, and neither of these was saying anything the festival's own hue could not. The names stay `--pink-*` and `--heart-*`, which every use site says. |
| The picture, in the festival's colour | A photograph arrives in the colours its photographer found and a poster in the colours it was printed in, and neither is the app's — Kallio's key art alone carries a lime wordmark, orange flames and a blue coat. So the picture is taken to luminance and the festival's own hue is blended back over it: `color` takes hue and chroma from the layer above and lightness from the picture below, which is a duotone in the colour the rest of the page is drawn in. The picture keeps its shapes and gives up its palette, and the wash over it is 52% rather than 46. The two layers isolate, so nothing under the hero blends with them. |
| A face is a surface | In the Lineup an act is a face in a row of faces, and M3 makes that a surface — a surface-variant ground with an on-surface-variant mark — rather than a picture. The hero's artwork tones are drawn to be read through a 46% wash; a row of them at 72px and eight across is eight full-chroma discs shouting over the names under them. Three more stage roles hold the hue and drop the chroma to a tint: the ground a step off the card it sits on, the mark at a middle tone, measured at 3.6:1 against it in the light theme and 4.4 in the dark. |
| Two names in the bar | While the festival's own card is on screen the bar has nothing to add — the card says the name at four times the size — so it carries the site's instead, and takes the festival's when that card goes under it. Both names are in the bar, stacked in one grid cell so it keeps its width and its ellipsis, and they change places on M3's fade through: the one leaving falls out over 180ms on the accelerate, the one arriving rises 6px into place over 280 on the emphasised decelerate. It reverses the moment the card's bottom clears the bar again, and above the phone's breakpoint — or on any view but Info — the festival's name simply stays. The name with `Your` in front of it, which the bar takes when the plan is the only thing showing, is a third in the same cell and crosses the same way: it used to appear and vanish with the word. |
| The plan, as a picture | With the picks filter on, the page is showing one thing — what you starred — so the pill that carries the temperature carries the way to send it instead: the same pill, in the same place, saying what it does now. It draws the plan on a canvas and hands it to the share sheet, or saves it where there is no sheet. One layout: the schedule, as stage columns against the clock, with the site's own map under it. A column is headed by the pin the map drops for that stage — the same number in the same disc — so the two halves name a stage the same way and the plan can be read against the ground. The map is fitted to the box the stages occupy rather than to the basemap sheet: containing the whole sheet letterboxes a portrait map into a landscape panel, covering it crops the pins at the edges away, and a pin is the whole reason the map is there. The stages of the plan wear their pin in the stage's own dark container; the rest of the site is a light dot, there so the plan reads against the whole ground rather than against a map with holes in it. It draws the still basemap, which is same-origin — a live tile would taint the canvas and make the export throw online where it passed offline. Both carry the mark, `Flanner`, `Your Festival Planner`, the festival's name, its dates and its city, and a footer that says where it came from and that set times move. Every colour is read off the page's live custom properties, so a poster is in the festival's own hue and in the theme the reader has on, and everything in it is drawn — no map tile, no photograph, nothing that could taint the canvas and make the export throw online where it passed offline. It is all synchronous: iOS spends the tap's activation on the first `await`, and a share without activation is a `NotAllowedError`, so the PNG is made with `toDataURL` and turned into a blob by hand rather than fetched back — which `connect-src` would refuse anyway. A grid is one day's shape, so on a three-day festival it draws the day on screen and names it; the list carries the whole plan. |
| A quieter filter card | Its foot carried a count and two buttons about the plan; the card keeps `Clear all`, at the top right. |

## Going between pages

A planner used to be one file with everything inside it, which is a good answer
to "does it work in a field" and a bad one to "what does it cost to open". It
cost a megabyte, and base64 does not compress: a photograph inlined into a
document is 33% larger than the file it came from and gzip cannot win any of
that back. The reader paid it on every page, and paid it again on the second
planner, because two documents cannot share a byte.

So the pages carry what is theirs and name what is not.

| | |
|---|---|
| The libraries | React, ReactDOM, Leaflet and the runtime are 351 KB and both planners had the same 351 KB. They are four files under `assets/js/` now, named by a hash of their contents, so the second planner is free and a re-export ships a new name rather than a stale file. `Artifact.lib_tags` writes them; the tags stay classic and in order, because the runtime needs React in the document before it compiles. |
| The type | Every page inlined its own cut of the font. Subsetting was written to make that cheap and it stopped paying on the pages that matter: a planner sets every artist's name, so its cut of Inter came to 83 KB against the full file's 84. The four faces are shared files, preloaded, fetched once for the site. `fontsub.inline` is still there for the artifact, which really is one file. |
| The maps | 573 KB of basemap sat in front of the first paint for a view most readers never open — and when there is a signal the probe in `initMap` throws both stills away for live tiles a moment later. They are fetched when the map is first shown. |
| The photographs | The home page inlined every festival's picture, including two it never draws, and a data URI cannot be lazy. They are files, so `loading="lazy"` means something; the planner's hero is the same file as the card that linked to it, so arriving from the list costs nothing. |
| Assets are not revalidated | The worker treats a document as something that can be corrected — cache first, refresh behind the reader — and an asset as something that cannot. The cache name hashes every page *and* every file under `assets/`, so a changed basemap arrives with a new store rather than being asked about on every page view. |

That is the weight. The rest is the wait.

| | |
|---|---|
| Nothing delays the navigation | The page-transition layer used to hold every navigation for 190ms so its own fade could finish, covering a gap the browser does not leave. It does not preventDefault at all now. The departure is the browser's; the only frames the file owns are the arrival and the wait. |
| Fetched before it is asked for | Speculation rules prerender a destination on hover, or on the press itself on a touch screen. Where they are not understood, `pointerenter` and `touchstart` warm the worker's cache, which takes the network out of the navigation even though the parse remains. Neither runs under `saveData` or on a 2g connection. |
| The transition | M3's fade-through between documents: the old page leaves over 90ms on the accelerate, the new one arrives over 210 on the decelerate and settles up from 92%, overlapping, so no frame is empty. Where cross-document transitions are not implemented the arrival is a CSS animation on `body` — it has to be CSS, because a class added by a tag at the end of the body arrives after the first paint and turns a fade in into a flash. |
| The bar carries across | The bottom bar is the same component on the list and on a planner, so both name it `navbar` and the browser morphs one into the other instead of fading a page over it — M3's container transform. The right edges are in the same place, so what the morph shows is the left edge travelling in by the width of the back button, which surfaces in the room it leaves. Named on one side only this would be worse than a cross-fade, so `_nav.css` and `NAV_VT_CSS` in `build_planner.py` are two halves of one thing. Below 600 only: above it the list's element is a rail down the side, and flying a column into a pill is not continuity. |
| The wait, when there is one | If the page has not arrived in 110ms, the reader is shown the shape of the one they asked for — the header, the card, the rail, the bar, in the real geometry — sweeping on a 1.6s pass. Three shapes for the three kinds of page. It is armed *behind* the navigation, so a destination that was prerendered or cached never shows it. The map and the home page's cards use the same tone and the same sweep while their pictures load, and both stop themselves: `:has()` matches only while nothing has painted. |

Everything above respects `prefers-reduced-motion`, which here means the shapes
hold still and the navigation goes back to the browser's own cut.

## The scheme, in the browser

Every planner is the same design in a different hue, and the turning used to
happen only in Python: `theme_recipe` reads every tone the design chose,
`render_recipe` re-emits them at the festival's hue, and the answer is baked
into that festival's page. It still is — the first paint is themed, never a
green flash — but the same arithmetic now ships to the browser as well, so a
planner can be handed an accent it was never built for and draw itself.

| | |
|---|---|
| One recipe, two renderers | `theme_recipe` returns the design's tokens with the hue taken out of them: a lightness and a chroma waiting for an angle, or the literal value where the scheme leaves a colour alone. The page's stylesheet and the browser's are rendered from that same object, so they cannot drift into disagreeing about a festival. |
| Only the hue moves | Every token keeps the lightness and chroma the design gave it, so every contrast pair the design was drawn against still holds. That is what makes it safe to theme a festival nobody has audited by hand. 22 of the 63 tokens are the same for every festival: below chroma 3 there is no hue to turn — `--card` measures 2.65, `--wash` 0.00 — and the amber and violet strands are second colours on purpose. |
| Proved, not trusted | Two implementations of the same maths drift silently, and the drift is a colour nobody chose. `tools/theme_parity.py` holds `scripts/_theme.js` against `scripts/m3color.py`: 8,280 tones across the whole space, then every token of the whole scheme at every festival's accent, at 10 stages and at 17. Any disagreement fails; the Python wins. Run it before pushing a colour change. |
| One file for the site | The engine and the recipe are hue-independent, so they are written once as `assets/js/theme-<hash>.js` and shared. That it really is festival-independent is checked rather than assumed — the second planner to ask for it is compared against the first, and a difference fails the build. |
| What a page carries | `<html data-festival data-accent data-stages>`. That is the whole interface: the engine reads those three and writes the scheme, including the per-stage palettes. Re-theming a live page measures 3.4ms. |

`FlannerTheme.apply(accent, stages)` re-themes the document at any time, which
is what a planner rendered from a dataset rather than from a build will use.

## Scrolling the map view

The phone map view spends the opening stretch of a drag collapsing the map
instead of scrolling the list — "the map keeps its width, loses height down to a
floor, and re-frames every pin". The effect is the design's and it stays. How it
was driven cost a frame every time, and cost the gesture as well.

| | |
|---|---|
| The collapse is not a render | Each touchmove in the band called `setState`. The planner is one React component with no memo boundary between the root and the leaves, so a state change reconciles all 539 nodes to write four attributes: a median 10.6ms per event on a desktop core, 5.5 to 23.4 at the edges, against a 16.7ms frame — and four to six times that on a mid-range phone. It does not read as a freeze; it reads as the map landing in four or five steps instead of following the thumb. The height is a number on one node, so `setMapScroll` writes it to that node. React is told once, on `touchend`. Measured after: a median of 0.2ms per event, nothing over frame budget. |
| The drag no longer dies at the floor | The design says a drag is spent on the map "until it reaches its floor; only then does the list itself start to move". It never did. The first touchmove calls `preventDefault`, and a browser told no at the start of a gesture will not begin scrolling later in that same gesture — so the map collapsed, the list stayed put, and it took a second swipe to move it. The rest of that drag is handed to the list by hand now: one drag collapses the map by 73px *and* scrolls the list 160px, which is what the comment always claimed. |
| Leaflet waits for the finger | `invalidateSize` was called per event and `fitBounds` re-framed every pin under the thumb, fighting the drag. The resize is coalesced into a frame with `pan:false`; the re-framing happens once, when the finger lifts. |
| A real scroll is left alone | Once the committed `mapScroll` is at the floor the list is a plain scroller, and a drag on it returns without `preventDefault` — so the browser scrolls it on the compositor with its own momentum. The hand-scrolling above applies only where the browser would not scroll anyway: a clipped box, or a gesture the collapse already took. |
| One viewport change, one answer | Four sources watch the viewport, and a phone fires all of them for one event, because scrolling is one of the ways a viewport changes there — the address bar slides away mid-scroll. Each arrival cost a `setState`, a header measure, a Leaflet resize and a nav-pill measure that reads layout back. A size is answered once now, by whichever source says it first, compared against the last size acted on rather than against state, which is a commit behind. Twenty redundant events do no work at all. It is not deferred to a frame: coalescing is worth having, a layout that is wrong for a frame is not. |

Left alone deliberately: the two `position:fixed` glass elements over the
bottom of the scroller do re-blur every scrolled frame, and that is a real cost
— but it is the M3 surface this bar is drawn on, and the gesture work above is
the part that was measurable in whole frames.

A pin and its row are the same stage, so pressing either opens the same panel —
the address, and the two ways of leaving with it. The pin used to say only which
stage it was, in a popup, and stop there; finding that stage again in the list
and pressing it a second time was left to the reader. It opens rather than
toggles, which is where it parts company with the row: a press on a pin also
opens Leaflet's popup, every time, and a pin that closed the panel on the second
press would be answering one press two ways. The row is brought into view as it
opens, because on a phone it is usually below the map being pressed, and an
expansion off the bottom of the screen is one nobody sees.

## Data

| File | Holds |
|---|---|
| `data/festivals.json` | one record per festival, plus the site's own details |
| `data/categories.json` | the category list: id, labels (en/fi), colour, ink |
| `data/acts.json`, `basemap.json`, `artwork.json` | per-planner timetable, map and artwork |

`scripts/schema.py` is the contract for those first two, and every builder loads
them through it (`schema.load()`, `schema.festival(id)`) rather than parsing the
JSON itself. It does two things:

**Derives what can be derived.** `month`, the display date range (`dates`) and
`stats.days` are all functions of `start` and `end`, so they are computed at
build time. Editing a date cannot leave a stale label behind.

**Fails the build on bad data**, listing every problem at once — a missing
field, a category that is not in `categories.json`, an end before a start, a
non-https link, a ticketed festival with no ticket URL. Check the data on its
own with:

```bash
python3 scripts/schema.py
```

Adding a category means adding an entry to `categories.json`: its colour reaches
the CSS as `--cat-<id>` (generated by `schema.category_css`), its label reaches
the filter chips, and cards pick both up through `data-cat`.

## What the pages remember

Three settings — theme, card view, place — held by the `Store` module in
`scripts/home.html`. No identifiers, no analytics, nothing that leaves the
device. Each field declares its allowed values and its default, so a stale or
hand-edited value fails the check and the default takes over. Keys are
namespaced and versioned (`flanner1.theme`), written to both a first-party
cookie and local storage because neither survives every situation alone, and the
older `fp-*` keys are still read so existing devices keep their settings.

Timetables are transcribed from each organiser's published schedule. Unofficial,
not affiliated with any festival.
