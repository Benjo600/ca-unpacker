---
name: CA Unpacker App Shell
description: A keyboard-first graphite workbench for unpacking CA client file dumps locally.
colors:
  bg: "#0b0d0f"
  panel: "#111417"
  panel-2: "#171b1f"
  elevated: "#1c2126"
  hairline: "rgba(255, 255, 255, 0.08)"
  hairline-strong: "rgba(255, 255, 255, 0.14)"
  text: "#eceef1"
  text-2: "#98a2ad"
  text-3: "#7c8794"
  accent: "#4c7dff"
  accent-hover: "#6b93ff"
  accent-ink: "#0b0d0f"
  accent-wash: "rgba(76, 125, 255, 0.14)"
  ok: "#3fb950"
  ok-wash: "rgba(63, 185, 80, 0.14)"
  warn: "#e0a33e"
  warn-wash: "rgba(224, 163, 62, 0.14)"
  bad: "#f85149"
  bad-wash: "rgba(248, 81, 73, 0.14)"
  focus: "#4c7dff"
  paper: "#e9ebed"
  paper-ink: "#22262b"
  paper-rule: "rgba(34, 38, 43, 0.16)"
  paper-hi: "rgba(224, 163, 62, 0.24)"
  paper-debit: "#8a2b22"
  paper-tie: "#8a5a12"
typography:
  display:
    fontFamily: "Archivo, Segoe UI, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.015em"
  headline:
    fontFamily: "Archivo, Segoe UI, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Archivo, Segoe UI, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "Archivo, Segoe UI, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "Archivo, Segoe UI, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1.4
  figure:
    fontFamily: "Spline Sans Mono, ui-monospace, Consolas, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.4
    fontFeature: "\"tnum\" 1"
  mono:
    fontFamily: "Spline Sans Mono, ui-monospace, Consolas, monospace"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  xs: "2px"
  sm: "3px"
  md: "4px"
  lg: "5px"
  xl: "6px"
spacing:
  micro: "2px"
  tight: "6px"
  control: "8px"
  gutter: "12px"
  panel: "14px"
  section: "18px"
  row: "28px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.xl}"
    padding: "0 11px"
    height: "28px"
    typography: "{typography.title}"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
    textColor: "{colors.accent-ink}"
  button-default:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.text}"
    rounded: "{rounded.xl}"
    padding: "0 11px"
    height: "28px"
    typography: "{typography.title}"
  button-default-hover:
    backgroundColor: "{colors.panel-2}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text-2}"
    rounded: "{rounded.xl}"
    padding: "0 11px"
    height: "28px"
    typography: "{typography.title}"
  input-search:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.text}"
    rounded: "{rounded.xl}"
    padding: "0 9px"
    height: "28px"
    typography: "{typography.body}"
  tab-active:
    textColor: "{colors.text}"
    padding: "0 10px"
    height: "30px"
    typography: "{typography.title}"
  tab-inactive:
    textColor: "{colors.text-2}"
    padding: "0 10px"
    height: "30px"
    typography: "{typography.title}"
  chip-tag:
    backgroundColor: "{colors.panel-2}"
    textColor: "{colors.text-2}"
    rounded: "{rounded.md}"
    padding: "0 6px"
    height: "18px"
    typography: "{typography.label}"
  card:
    backgroundColor: "{colors.panel}"
    rounded: "{rounded.xl}"
    padding: "9px 12px"
  rail-item:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    padding: "7px 12px 7px 10px"
    typography: "{typography.body}"
  rail-item-active:
    backgroundColor: "{colors.panel-2}"
    textColor: "{colors.text}"
  checkbox:
    backgroundColor: "{colors.bg}"
    rounded: "{rounded.md}"
    size: "15px"
  checkbox-checked:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
  command-palette:
    backgroundColor: "{colors.elevated}"
    rounded: "{rounded.xl}"
    width: "min(560px, 92vw)"
  kbd:
    backgroundColor: "{colors.panel-2}"
    textColor: "{colors.text-3}"
    rounded: "{rounded.md}"
    padding: "1px 5px"
    typography: "{typography.mono}"
---

# Design System: CA Unpacker App Shell

## Overview

**Creative North Star: "The Practice Desk"**

The Practice Desk is the surface a CA actually works at during filing week: a graphite workbench, not a dashboard and not a costume. The client's folder is the primary object, held in a persistent left rail; the work surface in the middle is where files classify, parse, and reconcile; the right side is a source inspector that keeps every parsed figure one keystroke from the document it came from. The interface is dense on purpose — 42px table rows, an 11–13px type scale, hairlines instead of gaps — because the person using it is scanning hundreds of figures per period and cannot afford decoration. Density here means many figures per screen, not cramped ones: the rows are tall enough to read comfortably and the scan is carried by alignment and hairlines, not by tight leading.

The world is dark-first: a near-black ground, three closely-stepped panel grays, and 8% white hairlines do the structural work. Color is strictly functional. One cobalt signal marks action and selection; amber is attention only; green and red are state only. Nothing else is colored. Documents are the single exception — source previews and the output sheet sit on a neutral paper ground with dark ink, so a document never reads as application chrome and is never confused with it.

The shell runs on an airy rhythm rather than a cramped one: a 48px top bar, 42px table rows, 34px controls, and 16–22px panel padding. Nothing is tight enough to make a figure hard to read; where space was given up it was returned as hairline structure, not as smaller type. This shell was built code-led: there are no comps, plates, or rasters. Every icon is an authored inline SVG on a 24px viewBox with a 1.5px stroke, every background is a CSS color, and the only binary assets are four self-hosted woff2 font files. It deliberately refuses the two nearest defaults named in its direction contract: the KPI-card SaaS dashboard and the physical-world costume (printout spools, film rails, record almirahs).

**Key Characteristics:**
- Dark-first graphite ground (#0b0d0f) with a parallel light theme; both are first-class.
- One cobalt action signal (#4c7dff / #2a5bd7 in light), used sparsely.
- Amber attention (#e0a33e) reserved for ITC mismatch, held items, and the tie-out marker.
- Neutral paper document ground (#e9ebed) for all source and output previews.
- Archivo for UI, Spline Sans Mono for every figure and identifier; both self-hosted woff2.
- Square and hairline form language with a hard 6px radius ceiling; no glass, no gradients.
- Keyboard-first: Ctrl K command palette, `T` tie-out, visible focus rings.

## Colors

A functional graphite palette: three near-black panel steps for structure, one cobalt signal for interaction, and a semantic trio (green/amber/red) for state. The frontmatter above records the **dark-first canonical set**; the light theme is the parallel set listed below and carried in full in the sidecar (`extensions.themeOverrides.light`).

### Primary
- **Action Cobalt** (#4c7dff / dark, #2a5bd7 / light): the single interactive signal. Primary buttons, selected table rows, active tab underline, the running state mark, focus rings, checkbox fills, and progress fills. It never carries meaning (a value is never "cobalt means good").
- **Cobalt Wash** (`rgba(76,125,255,0.14)`): the selected-row and pressed-toggle fill. Selection is a wash, not a border.

### Secondary
- **Attention Amber** (#e0a33e / dark, #9a6700 / light): ITC mismatch, held files, "to review" counts, the tie-out highlight on paper. This is the only warm color in the world and it means "a human must look".
- **State Green** (#3fb950 / dark, #1a7f37 / light): parsed, matched, ready.
- **State Red** (#f85149 / dark, #cf222e / light): parse failure, blocked.

### Neutral
- **Ground Graphite** (#0b0d0f): the app background and the body of the work surface.
- **Panel** (#111417): the top bar, client rail, inspector, cards, and status bar — the chrome that frames the work.
- **Panel Raised** (#171b1f): table headers, row hover, segmented-control selection, the `.kbd` chip.
- **Elevated** (#1c2126): genuinely floating layers only — the command palette box.
- **Hairline** (`rgba(255,255,255,0.08)`) and **Hairline Strong** (`rgba(255,255,255,0.14)`): all borders and dividers. Structure is drawn with 1px lines, not fills.
- **Ink** (#eceef1): primary text.
- **Ink Secondary** (#98a2ad): supporting text, meta, values-as-prose.
- **Ink Tertiary** (#7c8794): labels, placeholders, timestamps, hints.
- **Paper** (#e9ebed) with **Paper Ink** (#22262b): the document ground. Source previews and the export sheet. In light theme paper drops to #f6f7f8 so it still separates from panel white.
- **Paper Debit** (#8a2b22): the one red allowed on paper — debit amounts in the output sheet.
- **Paper Tie** (#8a5a12): the tie-out chip's ink on paper.

### Named Rules
**The One Signal Rule.** Cobalt is the only interactive color and appears on well under 10% of any screen. If something is cobalt, it can be clicked or it is selected; nothing else may be cobalt.

**The Amber Means Attention Rule.** Amber is reserved for ITC mismatch, held/attention states, and the tie-out marker. It is never used for decoration, branding, or a secondary accent.

**The Document Ground Rule.** Any surface that represents a source document or an export sits on the paper ground with paper ink and paper rules. Document previews never adopt panel chrome.

**The Two-Theme Parity Rule.** Every token has a dark and a light value. A new color is not added to the system until it has both; the light theme is not an afterthought filter.

## Typography

**Display Font:** Archivo (with Segoe UI, system-ui, sans-serif fallback)
**Body Font:** Archivo (same stack)
**Label/Mono Font:** Spline Sans Mono (with ui-monospace, Consolas, monospace fallback)

**Character:** A single grotesque for all UI copy and a single monospace for all data. Archivo is tight and modern at small sizes (negative tracking on the name and title); Spline Sans Mono gives financial figures an honest, ledger-like column alignment. The pairing is deliberately narrow — two families, no display face, no serif.

Both families are **self-hosted** as woff2 in `apps/ui/fonts/` (downloaded from the Google Fonts API, no CDN at runtime): `archivo-latin.woff2` + `archivo-latin-ext.woff2` and `splinemono-latin.woff2` + `splinemono-latin-ext.woff2`. Each is declared with `font-weight: 400 600` and `font-display: swap`, and the Latin-Ext files carry the rupee and extended punctuation the Indian data needs.

### Hierarchy
- **Display** (600, 17px, 1.2, -0.015em): the work-surface title — the client name. One per screen.
- **Headline** (600, 13px, 1.3, -0.01em): brand name, selected source filename, inspector file.
- **Title** (600, 12px, 1.4): card titles, rail title; at 500 weight it also sets buttons, tabs, and segmented controls.
- **Body** (400, 13px, 1.45): the app base size — table cells, prose, inputs.
- **Label** (500, 11px, 1.4): status, counts, meta, footer, card notes, hints. The most common size in the shell.
- **Figure** (400–500, 13–14px, tabular): amounts, row counts, confidence, differences. Always tabular.
- **Mono** (400, 11px, 1.5): GSTINs, invoice numbers, checksums, source line text, keyboard chips.

### Named Rules
**The Figures Are Mono Rule.** Every monetary amount, GSTIN, invoice number, checksum, row count, confidence score, and line number is set in Spline Sans Mono with tabular numerals (`font-variant-numeric: tabular-nums`, `font-feature-settings: "tnum" 1`). Proportional figures are never used for data.

**The Two-Family Rule.** The system has exactly two typefaces. No third face, no system display substitute, no serif headline, no glyph icon font — icons are authored SVG.

**The Small-Size Rule.** The shell runs at 13px body with an 11px label floor. Type does not go below 11px, and density is bought with spacing and hairlines rather than smaller text.

## Layout

A three-column workbench inside a fixed 48px top bar and 32px status bar:

- **Body grid:** `48px minmax(0, 1fr) 32px` rows, overflow hidden — the app never scrolls as a whole; only the three columns scroll internally.
- **Columns:** `288px minmax(0, 1fr) 400px` — client rail, work surface, source inspector. All three are `min-height: 0` flex/grid children so their inner scrollers behave.
- **Vertical rhythm:** sections are separated by `gutter` (14–18px) to `section` (18–22px); controls sit at `control` (34px) height with 8–10px gaps; panel padding is 16px, and `work-head`/`tabs`/`work-scroll` use 22px horizontally.
- **Table:** `table-layout: fixed`, sticky headers, 42px row height, 10px cell padding, right-aligned mono columns for figures (`Rows`, `Confidence`, `2B value`, `Books value`, `Difference`). Column widths are pinned as percentages and must total 100 across the header row; the `Rows`, `Period`, and `Confidence` columns are sized so their widest values and headers never truncate.
- **Rail rows:** 11px vertical padding, a 9px state square, name over meta on the left and a two-line figures/state pair on the right. Left and right cells are block-level flex/grid children so long names ellipsize instead of overlapping the right column.
- **Responsive:** at ≤1360px the rail tightens to 250px and the inspector to 362px (the inspector is held at 362px so the tied source line and its chip never collide, and the work surface is held wide enough that all figures and headers still fit); at ≤1120px the inspector leaves the grid and becomes a fixed overlay (`top: 48px; bottom: 32px`) toggled by the top-bar panel button; at ≤860px the rail narrows to 236px, the command field hides, the four stage cells wrap to two rows, and 4-up definition strips collapse to two; at ≤640px the rail hides and the body is a single column.
- **Status bar pruning:** groups carry semantic classes (`g-files`, `g-rows`, `g-held`, `g-sample`, `g-engine`, `g-packs`, `g-cmd`) that the breakpoints hide in order of expendability — engine + command hint at ≤1120px, packs at ≤860px, held-count at ≤640px. The "Sample data — synthetic" disclosure is never pruned; it is a trust statement, not a metric.

The spacing scale is 2 / 6 / 8 / 10 / 12 / 14 / 16 / 18 / 20 / 22 / 28 / 32px. It is deliberately airier than a typical desktop-tool scale — the shell buys legibility with taller rows and roomier padding, and pays for structure with hairline separators rather than tight gaps.

### Named Rules
**The 34px Control Rule.** Buttons and inline controls sit at 34px tall (32px for the top-bar command field and icon buttons, 28px for pills and the avatar, 26px for segmented buttons), tabs are 40px, table rows are 42px, and the command-palette field is 52px. Control height is a system constant, not a per-view choice — a control is never squeezed to fit content.

**The Internal-Scroll Rule.** The page itself never scrolls. The rail, work surface, and inspector each own their scroll, so the top bar, tabs, and status bar never leave the viewport.

## Elevation & Depth

This is a flat, hairline-separated system. Depth is carried almost entirely by tonal stepping (bg → panel → panel-2 → elevated) and 1px borders, not by shadow. There is no glass, no blur, no gradient, and no neumorphism. Two shadows exist, and only two.

### Shadow Vocabulary
- **Ambient Low** (`0 1px 2px rgba(0,0,0,0.4)`) — the selected segment in the client-filter segmented control. A whisper of lift on one raised control.
- **Floating** (`0 12px 32px -8px rgba(0,0,0,0.6)`) — only genuinely floating layers: the command palette box and the inspector when it becomes an overlay below 1120px.

In light theme both shadows swap to ink-tinted equivalents (see sidecar): `0 1px 2px rgba(15,23,42,0.08)` and `0 12px 32px -8px rgba(15,23,42,0.18)`.

### Named Rules
**The Flat-By-Default Rule.** Surfaces are flat at rest. A shadow appears only when an element genuinely floats above the page (a dialog, an overlay panel) or is the single selected control in a group.

**The Hairline-Not-Fill Rule.** Structure between regions is a 1px border at 8% white (14% for controls that need to read as bounded). Never a filled divider band, never a rule you can see at a glance.

## Shapes

Square and squared-off. The **6px radius ceiling** is absolute: cards, buttons, inputs, tabs' swimlane, stages, table wrappers, the command palette, and the paper previews all top out at 6px. Inside that ceiling the system steps down: 5px for the brand mark, 4px for tags, segmented buttons, checkboxes, and `kbd` chips, 3px for focus outlines, source lines, and the tie-out marker, 2px for client state marks and the thin stage/quota bars. Fully circular geometry is used only for the 6px status dot (`.sdot`).

Borders are hairlines, never heavy. Icons are authored inline SVG symbols on a 24×24 viewBox rendered at 12–16px with `stroke: currentColor`, `stroke-width: 1.5`, round caps and joins — outlined, never filled (except the check glyph inside a checked checkbox, which strokes at 2.5 for legibility).

### Named Rules
**The 6px Ceiling Rule.** No corner radius exceeds 6px anywhere in the shell. When in doubt, go squarer.

**The Squared-State Rule.** State marks in the client rail are 9px squares (2px radius); state dots in tables are 7px circles. Status glyphs are outlined SVG at a 1.5px stroke, never filled or emoji.

## Components

### Buttons
- **Shape:** 28px tall, 6px radius, 11px horizontal padding, 7px icon gap, 12px/500 label.
- **Default:** panel background, hairline-strong border, primary ink. Hover lifts to panel-raised.
- **Primary:** cobalt fill with cobalt-ink text (near-black on dark, white on light), no border; hover steps to the lighter cobalt (#6b93ff dark / #2450c2 light).
- **Ghost:** transparent, secondary ink; hover fills panel-raised and returns to primary ink. Used for "Add folder" and the tie-out toggle.
- **Icon Button:** 28×28, transparent border; hover fills panel-raised; when `aria-pressed="true"` it takes the cobalt wash and cobalt ink (theme toggle, inspector toggle).
- **Focus:** all buttons take the global `:focus-visible` treatment — a 2px cobalt outline at 1px offset with a 3px radius.

### Chips, Tags & Pills
- **Tag:** 18px tall, 4px radius, 11px/500, 6px horizontal padding. Neutral tags use panel-raised fill with a hairline-strong border; semantic tags drop the border and use the matching wash fill with the semantic ink (`.ok`, `.warn`, `.bad`, `.acc`).
- **Keyboard chip (`kbd`):** 11px mono, panel-raised fill, hairline border, 4px radius, 1px/5px padding. Used in the command field, status bar, palette footer, and the `T` tie-out hint.
- **Pill:** 24px tall, 6px radius, hairline border, 11px secondary text. The "Local only" pill carries the green lock icon — the only place a status color sits in the top bar.
- **State indicator (`.state`):** 6px dot plus 11px label; dot color follows the semantic token (`ok`/`run`/`warn`/`bad`), and the running dot pulses (1.6s ease-in-out, opacity 1 → 0.35).

### Cards / Containers
- **Corner Style:** 6px.
- **Background:** panel (#111417) on the graphite ground.
- **Border:** 1px hairline on all sides; `overflow: hidden` so header rules sit flush to the radius.
- **Internal Padding:** header 9px/12px, body 12px; hairline rule under the header.
- **Variants:** the definition strip (`.defs`) is a vertical hairline-divided key/value list; `.defs-4` is the same idea in four columns, collapsing to two at ≤860px and one at ≤640px. The `.stages` strip is a single bordered container split into four hairline-separated cells.

### Inputs / Fields
- **Search (`.rail-search`)**, **command field (`.cmd`)**, and **palette input** share a shape: graphite background, 1px hairline border, 6px radius, 11–13px text. `.rail-search` is 28px and takes a cobalt border on `:focus-within`; `.cmd` is 26px and darkens its border on hover.
- **Checkbox:** 15×15, 4px radius, hairline-strong border on graphite; checked fills cobalt with a cobalt-ink check glyph. Built as a `role="checkbox"` span, keyboard-reachable, not a native input.
- **Focus:** text fields suppress their own outline in favour of the border swap / `:focus-within`; everything else uses the global focus-visible ring.

### Navigation
- **Top bar:** 40px, panel background, 1px bottom hairline. Brand mark (22px, 5px radius, inverted) + name, a breadcrumb (firm › client › period) whose current segment is primary ink and period is mono, a flexible command field, then the local-only pill, theme toggle, inspector toggle, and a 2-letter avatar.
- **Tabs:** 30px, hairline bottom border on the strip; the selected tab is primary ink with a cobalt 2px underline inset 8px from each edge; counts ride beside the label in tertiary mono.
- **Client rail:** 264px panel column. A header row (title + active count), a 28px filter field, a segmented All/Attention/Ready control, then dense client rows. Each row is a 12px state mark, a two-line name + mono GSTIN/period block, and a right-aligned file count + state label. Hover fills panel-raised; the current row takes panel-raised plus top and bottom hairlines (`aria-current`).
- **Command palette:** hidden overlay; dim backdrop `rgba(0,0,0,0.45)`, an elevated box at `min(560px, 92vw)` with the floating shadow, a 44px input row, a 320px result list, and a keyboard-hint footer. Items highlight with the cobalt wash; favourites are commands, then clients.

### Signature Components

**The Tie-Out Inspector.** The source inspector (380px) shows the selected file's raw source on the paper ground, rendered as numbered monospace lines. When tie-out is on, the line that produced the currently selected figure is highlighted in amber paper-hi, given extra right padding for a chip, and annotated with a `TIE-OUT` marker that animates in (opacity + 8px slide, 240ms on the shared ease). The matched line is scrolled to the vertical centre of the inspector. Below the source, a definition strip prints the matched line number, parsed value, active rule, and checksum. The inspector footer always states the local guarantee: "Read locally · no upload" and "Original unchanged on disk". This is the interaction the whole shell is built around — figure → keystroke (`T`) → source line.

**The Stage Strip.** Four cells (Intake, Parse, Reconcile, Export) in one bordered container. Each cell carries a 2px track with a fill that scales from the left on the shared ease (200ms). Fill color is semantic: green when done, amber at a partial `--fill` when held, cobalt while running, red on failure. The label row pairs a 12px/500 stage name with a mono value ("8 files", "7,412 rows", "3 open", "Not started").

**The Client Rail State Marks.** An 8px 2px-radius square leads every client row and encodes processing state by color alone (grey idle, green ready, cobalt running, amber held, red failed) — a single visual vocabulary reused by the table dots and tags.

### Browser-Surface Theming
The shell themes the parts of the WebView2 surface that CSS usually leaves default:
- **Color scheme:** `color-scheme: dark` / `light` is set per theme so native controls, scrollbars, and form chrome follow.
- **Selection:** `::selection` uses the cobalt wash with primary ink.
- **Caret:** `caret-color` is cobalt in every input and button.
- **Scrollbars:** thin, `scrollbar-color: hairline-strong transparent`; the WebKit path is a 10px track with a 6px-radius thumb drawn via a 3px transparent border and `background-clip: content-box`, brightening to tertiary ink on hover.
- **Focus ring:** one global `:focus-visible` rule — 2px cobalt outline, 1px offset, 3px radius.
- **Numerals:** tabular, feature-driven, on every figure.
- **Reduced motion:** `prefers-reduced-motion: reduce` collapses all animation and transition durations to 0.001ms.

## Do's and Don'ts

### Do:
- **Do** keep every figure, identifier, checksum, and count in Spline Sans Mono with tabular numerals.
- **Do** separate regions with 1px hairlines (8% white / 14% strong in dark) and tonal steps, and keep every surface flat at rest.
- **Do** cap all radii at 6px and buy density with 28px rows, 6–8px control gaps, and 11–13px type.
- **Do** put any source or export preview on the neutral paper ground (#e9ebed ink #22262b) so it reads as a document.
- **Do** reserve cobalt for action/selection, amber for attention, green/red for state — and give every color both a dark and a light value.
- **Do** route every control through the shared `:focus-visible` cobalt ring and keep Ctrl K and `T` as live keyboard paths.

### Don't:
- **Don't** introduce a third typeface, a serif display face, a glyph icon font, or a filled icon — icons are authored SVG at a 1.5px stroke.
- **Don't** add glass, blur, gradients, neumorphism, or any shadow beyond the two recorded tokens; depth is tonal.
- **Don't** use rounded-full cards, pill buttons, or radii above 6px, and don't lift cards on hover — hover is a panel-raised fill, not a shadow.
- **Don't** let cobalt carry meaning or amber decorate; the One Signal Rule and the Amber Means Attention Rule are absolute.
- **Don't** style a document preview with panel chrome, and don't use the app palette inside a paper surface.
- **Don't** let the page itself scroll — the rail, work surface, and inspector each own their scroll.

## Auth Surface

`apps/ui/auth.html` — a single self-contained file (inline CSS and JS) that gates the practice desk. It inherits this world rather than starting a second one: same palette, same two typefaces, same 6px radius ceiling, same hairline grammar. Its only binary assets are the four shared woff2 files.

### Screens and states
- **Boot** — a full-bleed overlay on the ground: 52px mark, wordmark, sub-line, a 260px progress rule, and a leader-dot log in Spline Sans Mono that prints one line every 240ms. Each line lands with its `ok` right-aligned in green; the final `Ready` line sits at 600 weight and the rule turns green on completion. It auto-runs on load, any key/click/`Esc` skips it, and "Replay boot" runs it again.
- **Sign in** — 17px heading, lede, work email and password fields, "Keep me signed in", "Forgot password?", a full-width primary action, and a footer link to sign-up.
- **Sign up** — firm name, work email, password with strength meter, confirm password, a local-licence checkbox, the primary action, and a footer link back.
- **Confirmations** — "Workspace ready" (carries the link into `shell.html`) and "Account created" (returns to sign-in with the email prefilled). Both are an inline check beside a 17px heading; there is no icon tile above the heading.

### Components
- **Auth field** — a 38px control: inset ground, `hairline-strong` border, leading 15px authored SVG icon, 13px input, optional reveal toggle. Focus is a cobalt border plus a 3px cobalt-wash ring; invalid is the same in red.
- **Strength meter** — three 3px segments plus a text label (Weak / Fair / Strong), driven by `data-level` 0–3 and stepping neutral → red → amber → green.
- **Inline alert** — 1px red border on a red wash, a 16px alert icon, a bold problem line, and a plain recovery line. The success variant swaps to green and the check icon.
- **Fact readout** — a bordered 11px definition list in the auth rail: label left, mono value right, hairline rows. It is the same information voice as the shell's status bar.
- **Boot log** — an ordered list of mono rows: label left, dotted leader (`border-bottom: 1px dotted`), state right.

### Named Rules
**The 38px Auth Field Rule.** The auth surface relaxes the 28px row to a 38px control and pays for it with a deliberately looser vertical rhythm. Auth is a low-frequency gate, not the dense work surface; the 28px Row Rule still governs everything behind it.

**The One Auth Moment Rule.** The boot sequence is this surface's single authored moment — per-line reveal, progress fill, and one exit transition. Everything after it is quiet by design: no entrance choreography on sign-in or sign-up, no motion on state changes beyond focus, invalid, and busy.

**The Shared Theme Rule.** Both themes ship on the auth surface, and the choice persists under the same `caunpacker-theme` key as the shell, so the gate and the desk never disagree about theme.

### Layout
Split at ≥861px — a `minmax(320px, 400px)` facts rail plus a flexible pane, with a 392px card centred by `margin: auto` (which keeps the top reachable when the card is taller than the pane). At ≤860px it becomes one normal scrolling document: body rows `auto 28px`, the facts panel full width, the card top-aligned, the status bar sticky, and the optional status groups pruned.

### Intentional behaviour
The boot sequence re-runs on every load of this page; there is no per-session suppression, which is the requested behaviour. It is skippable in one keystroke and fully suppressed under `prefers-reduced-motion`.

## Open Items

Known issues carried by the build at the time of documentation — recorded as defects, not canonized as rules:

- **Tie animation replays on inspector re-render.** Every inspector re-render rebuilds the source lines, so the tie-out sweep and chip animations (`tie-sweep`, `tie-chip`) fire again on unrelated updates (file selection, client switch, tie toggle) rather than only when the tied line changes.
- **The longest intake filename and two reconcile supplier names ellipsize.** At the ≤1360px column set, `Purchase_Register_Aug2026.xlsx`, `Ganesh Packaging`, and `Sunrise Chemicals` clip by 8–13px. Figures, identifiers, and status labels never clip; these are the only truncated cells, and they are names rather than data.
