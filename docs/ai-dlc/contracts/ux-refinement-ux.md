# UI/Design Contracts — Frontend (pre-UX/UI pass)

Scope: `static/` (10 CSS/JS modules + `index.html`). Read-only audit for: app-wide consistency sweep, Insights tab redesign, 375px mobile pass, new light theme (prefers-color-scheme + manual toggle via prefs.js).

## Tokens

All declared in `static/style.css:8-83` (`:root`). Inventory:

- **Surfaces**: `--surface-base` (14L), `--surface-panel` (18L), `--surface-raised` (22L), `--surface-overlay` (26L), `--border` (32L), `--border-subtle` (25L) — `style.css:15-25`. Every other CSS file consumes only these names (`panel.css`, `feedback.css`, `movelist.css`, `review.css`, `insights.css` — verified via grep, all `var(--surface-*)`/`var(--border*)`).
- **Legacy aliases**: `--bg: var(--surface-base)`, `--panel-bg: var(--surface-panel)` at `style.css:28-29` — grepped for consumers, **zero references anywhere** in `static/`. Dead code; safe to note but don't assume anything depends on them.
- **Text**: `--text` (94L), `--text-secondary` (74L), `--muted` (63L) — `style.css:33-37`.
- **Accent**: `--accent` (72L 231h), `--accent-dim` (30L, tinted bg), `--accent-on` (13L, text-on-accent) — `style.css:40-42`.
- **Error**: `--error` (68L 22h) — `style.css:45`.
- **Quality colors**: `--q-best/good/inaccuracy/mistake/blunder` (green→yellow→orange→red hue ramp) + `--q-book: var(--accent)` — `style.css:48-53`. Consumed by `style.css` (`.q-*` classes, `.quality`), `panel.css` (SVG icon `stroke` via inline `var(--q-*)`, `panel.js:132-161`), `movelist.css`/`movelist.js` (per-ply `q-*` class), `review.css` (badges/status), `insights.css` (highlight box uses `--accent`, not quality colors).
- **Spacing** (4px base, `--space-1..10`), **Radii** (`sm/md/lg`), **Shadows** (`sm/md/lg`, hardcoded-black-alpha oklch), **Scrim**, **Motion** (`--motion-fast`, `--motion-base`, `--ease-out`, `--ease-in-out`) — `style.css:55-83`.
- `color-scheme: dark light;` declared at `style.css:11` and mirrored in `<meta name="color-scheme" content="dark light">` at `index.html:9` — deliberately set to **both** to stop Chrome's auto-dark image inversion (comment at `index.html:6-8`); this is load-bearing for how black chess piece SVGs render and must be preserved/re-verified when a real light variant ships.
- `@media (prefers-reduced-motion: reduce)` global override at `style.css:86-91` (kills all transitions/animations) — separate, more targeted overrides also exist per-file (see Motion section below).

## Non-token colors (raw oklch literals outside `:root`)

No raw hex/rgb/hsl anywhere outside the token block or code comments (hex only appears as `/* #xxxxxx */` documentation comments next to each oklch token — not live CSS). However, several files hardcode **raw `oklch(...)` literals** instead of referencing tokens — these block clean light-theme swapping because they don't follow the palette when tokens are redefined for light:

| file:line | value | context | suggested token |
|---|---|---|---|
| `panel.css:20` | `oklch(18% 0.01 248)` | `#eval-bar::before` (black half of eval bar) | new `--eval-bar-black` — needs a dedicated pair since it must stay black/white regardless of theme (eval bar is chess-semantic, not surface-semantic) |
| `panel.css:31` | `oklch(94% 0.004 248)` | `#eval-bar::after` (white fill) | same — needs `--eval-bar-white` |
| `review.css:281` | `oklch(18% 0.05 145)` | `.review-badge-win` bg | new `--q-best-dim` (mirrors `--accent-dim` pattern) |
| `review.css:282` | `oklch(18% 0.05 22)` | `.review-badge-loss` bg | new `--q-blunder-dim` |
| `review.css:283` | `oklch(18% 0.05 85)` | `.review-badge-draw` bg | new `--q-inaccuracy-dim` |
| `review.css:346` | `oklch(25% 0.09 231)` | `.review-btn-primary:hover` bg | derivable from `--accent` via `color-mix` or new `--accent-dim-hover` |
| `review.css:351` | `oklch(32% 0.07 22)` | `.review-btn-danger` border | new `--q-blunder-border` or reuse `--error` at lower lightness |
| `review.css:356` | `oklch(18% 0.05 22)` | `.review-btn-danger:hover` bg | same family as `review.css:282` |
| `review.css:790` | `oklch(0% 0 0 / 0.35)` | `.review-toast` box-shadow | matches `--shadow-md`'s black-alpha pattern but not literally reusing it |

Note: `--shadow-sm/md/lg` and `--scrim` themselves hardcode `oklch(0% 0 0 / …)` (pure black shadows) inside the token block (`style.css:71-76`) — fine for dark, but a light theme typically wants lighter/less-opaque shadows; these tokens will need light-mode overrides even though they're "in the token file."

`color-mix(in oklch, var(--surface-raised) 35%, transparent)` at `movelist.css:76` is token-based and will re-theme automatically — no action needed, good precedent to reuse for the new theme work.

## Theming readiness

- No `@media (prefers-color-scheme: …)` query exists anywhere in the codebase (grepped — zero hits). All theming today is single dark palette baked into `:root`.
- `color-scheme: dark light` (both) is already declared (`style.css:11`, `index.html:9`) — necessary but not sufficient; it only stops browser auto-darkening, doesn't switch token values.
- **Chessground board CSS** is loaded from CDN, untouched by app CSS: `chessground.base.css`, `chessground.brown.css` (board square colors), `chessground.cburnett.css` (piece SVGs) — `index.html:23-25`. No overrides exist anywhere in `static/*.css` (grepped for `cg-`/`chessground` selectors — none). The brown board + cburnett pieces are **theme-independent** today — under a light theme the board will still render brown/cburnett by default, which is likely *desired* (boards conventionally keep their own palette) but is a decision point for the redesign, not an automatic light-mode side effect. The `#board` wrapper itself (`style.css:181-187`) is tokenized (`box-shadow`, `border`) and will re-theme fine.
- The two eval-bar raw-oklch layers (`panel.css:20,31`) are the only piece of "board-adjacent" chrome that hardcodes near-black/near-white regardless of theme — intentionally chess-semantic (black/white advantage), so these likely should stay hardcoded rather than tokenized to surface colors, but should get their own explicitly-named tokens so a reviewer doesn't mistake them for forgotten raw values.

## prefs.js seam

`static/prefs.js` — 16 lines, no DOM, no imports from `app.js` (explicit comment at line 1). API:
```js
readUiPrefs()          // → parsed object from localStorage, {} on any error
writeUiPref(key, val)  // → merges into stored object, writes back, silently no-ops on failure
```
- Storage key: `'chess-training:ui:v1'` (`prefs.js:3`) — single JSON blob, flat key/value shape.
- Current consumers:
  - `app.js:27,81,2067` — `analyzeColor` pref (`'both'|'white'|'black'`), read once at module-init time (`app.js:81`) into a `let` var, written on change (`app.js:2067`).
  - `movelist.js:10,124,134` — `moveListCollapsed` boolean, read at `initMovelist()` time to set initial collapsed state before first paint, written on toggle click.
- **A theme pref fits this seam directly**: `writeUiPref('theme', 'light'|'dark'|'system')`, read once at bootstrap to set e.g. `document.documentElement.dataset.theme`, written on manual toggle. Because `readUiPrefs()`/`writeUiPref()` are synchronous, the theme read should happen as early as possible in `<head>` (inline, before `style.css` paints) to avoid a flash-of-wrong-theme — today `app.js` is a `type="module"` script at the very bottom of `<body>` (`index.html:282`), so its `readUiPrefs()` call fires **after** first paint; a naive theme pref that waits for `app.js` will FOUC. Sharpest implementation risk for the theme toggle.

## Layout & mobile

- App shell: `body` is a 2-row CSS grid (`header` auto + `main` 1fr), `height: 100dvh; overflow: hidden` at desktop (`style.css:99-109`); becomes `height: auto; overflow: auto` under `@media (max-width: 820px)` (`style.css:1097-1101`).
- `main` grid: `grid-template-columns: auto minmax(280px, 1fr)` (board-col intrinsic + panel fills) → collapses to `1fr` single column at ≤820px (`style.css:1103-1104`).
- **Mode-driven layout collapse**: `body[data-mode="setup"|"trap-watch"|"trap-practice"|"rep-practice"]` forces `main` to single-column AND hides `.panel` entirely (`style.css:441-453`) — the right aside panel only exists in `play` and (implicitly) `review` mode. **`data-mode="review"` is conspicuously absent from this selector list** — review mode keeps the two-column grid and the panel visible (intentional, since Review/Insights need the panel), but this is easy to break by accident if a redesign "normalizes" these mode selectors.
- **Dead/orphaned class**: `document.body.classList.toggle('review-mode', on)` at `app.js:1842` — grepped across all CSS files, **zero matching `.review-mode` selector exists anywhere**. Either dead JS or an unfinished styling hook; a redesign should not assume `.review-mode` currently does anything, and should decide explicitly whether to wire it up or remove it.
- Fixed-width elements (`480px`) that only get a mobile override at `≤560px` (`style.css:1126-1136`, → `92vw`): `#board`, `.fen-row`, `.setup-bar`, `.trap-bar`, `.rep-bar`. Between 561–820px these stay literally `480px` — currently safe by margin but brittle if the redesign changes panel/board proportions. `#eval-bar` gets `min-height: 92vw` at the same breakpoint (`style.css:1135`) to stay square-ish next to the board.
- At 375px specifically: board (345px) + eval-bar (14px fixed + gap 8px) = ~367px inside a 375px viewport after `main`'s `padding: var(--space-4)` (16px) each side — **`#eval-bar` width stays a fixed `14px` at all breakpoints** (`style.css:171-172`) while the board scales to `92vw`; at very narrow viewports (< ~360px) the eval-bar+board+gap combo could exceed available width. Stress-test at exactly 375px.
- `.panel` on mobile: `min-height: 400px; max-height: none` (`style.css:1113-1117`) — sits below the board, unbounded height, whole page scrolls (`body { overflow: auto }` at ≤820px).

## Insights surface

`insights.js` (584 lines) + `insights.css` (212 lines). Structural contract, do NOT break:

- **Mount points from `index.html:261-264`**: `#tab-insights` (outer tab-panel, role=tabpanel) → `#insights-root` (`.insights-root`, rendered entirely by JS — no static HTML inside).
- **Lazy build/fetch sequencing** (`insights.js:502-582`):
  1. `initInsights(api)` (`insights.js:578`) only calls `renderEmptyState()` + `wireLazyLoad(api)` — no fetch yet.
  2. First click on the outer Insights tab (`api.mounts.tabs` click listener, gated on `document.body.dataset.mode === 'play'`, `insights.js:563-572`) → `activateInsightsTab()` → builds the Openings/Mistakes sub-tab shell once (`_shellBuilt` guard) → `loadOpenings()` fires `GET /api/insights/openings`.
  3. First click on the **Mistakes** sub-tab (`_mistakesLoaded` guard, `insights.js:540-543`) → `loadMistakes()` fires `GET /api/insights/mistakes`.
  4. Each endpoint fetched **at most once per page load** — no re-fetch/refresh trigger exists anywhere. A redesign wanting live-refresh has no existing hook — that would be new wiring, not an existing contract.
- **Sub-tab shell is built entirely in JS**, not HTML: `insights-subtabs` (`role="tablist"`), two `button[role="tab"][data-subtab]` (`insights-subtab-openings`/`-mistakes`), two `div[role="tabpanel"]` (`insights-panel-openings`/`-mistakes`) — all IDs generated at `insights.js:508-546`. They reuse the **generic** rule `[role="tabpanel"]:not(.is-active) { display: none }` at `style.css:435` (documented in `insights.css:150-154` comment) — a redesign must keep the `role="tabpanel"` + `.is-active` pattern or add equivalent CSS; removing that generic rule silently breaks Insights *and* the outer 6 tab-panels.
- **Element IDs consumed elsewhere**: none outside `insights.js` itself.
- **Deep-link seam**: `renderDeepLinkButton()` (`insights.js:108-121`) calls `_api.actions.openGameAtPly(gameId, ply)` — defined in `app.js:1981`, transitions mode to `review` and jumps the board. The **only** cross-module action Insights invokes; any redesign of card/row markup must keep this exact call signature `(gameId, ply)` and the button must remain clickable content — it's the sole navigation path from an insight to the underlying game.
- **min-sample / honesty convention** (repeated across every section, header comments `insights.js:8-23`): every metric arrives as `{value, n, sufficient}`; `renderGatedLine()`/`renderThinData()` (`insights.js:68-84`) render a muted "Not enough games yet (n=X, need Y+)" line whenever `sufficient` is false. `minSample` default is `5` in JS (`insights.js:68`) matching backend `app/insights.py`; cluster suppression threshold defaults to `4` client-side (`insights.js:322`). **A redesign must preserve this per-metric gating pattern** (not just an overall "not enough data" banner) — named product invariant ("the spec allows exactly one long-run trend, always visually secondary," `insights.css:24-26`).
- **Data-shape assumptions** baked into render functions: `data.coverage.{qualified,total}`, `data.win_rates.{families[],lines[]}` matched by `(opening, color)` pair (`insights.js:154`), `data.adherence.{avg_followed_prep_depth,lines[],games[]}`, `data.theory.{avg_book_exit_ply,avg_opening_accuracy,note,games[]}` with `book_exit_ply === 0` sentinel meaning "never entered book" (`insights.js:254-258`, intentional), `data.clusters.{items[],suppressed:{cells,leaks,gate}}`, `data.foreseeable.{rate,dominant_motif,note}`, `data.time_trouble.{baseline_rate,buckets[]}` keyed by literal bucket label `'<10s'` (`insights.js:380`), `data.capitalization.{winning_games,converted,rate,note}`. Visual redesign reordering/restyling cards is safe; changing which JS functions read which JSON keys is not.
- **`clusterDisplayName()`** (`insights.js:293-295`) strips a `" (N× so far)"` suffix that `app/coaching.py:352-353` appends server-side once count ≥ 5 — cross-file string-format coupling a redesign must not "fix" by removing (the JS strip is intentional dedup).

## States & a11y gaps

- `:focus-visible` used consistently across `style.css`, `movelist.css`, `insights.css`, `feedback.css`, most of `review.css` — **except** three controls use plain `:focus`: `.review-pgn-input:focus` (`review.css:411`), `.review-color-select:focus` (`review.css:448`), `.review-bulk-input:focus` (`review.css:734`). Normalize in the sweep.
- Two of those (`review.css:411-414`, `:734-737`) also set `outline: none` and rely solely on `border-color` change — weaker than the `outline: 2px solid var(--accent)` pattern used elsewhere; flag for AA/focus-visible invariant.
- Touch targets: default `button` is `padding: 0.45rem 0.8rem` + `font-size: 0.875rem` (`style.css:203-220`) → ~30px computed height. Smaller still: `.trap-chip-dismiss` (`style.css:702-709`), `.rep-line-practice` (`style.css:971-978`, `font-size: 0.72rem`), `.movelist-move` (`movelist.css:86-97`, `padding: 0.15rem 0.4rem`) — move-list density likely intentional; dismiss/practice buttons are candidates for enlarging on mobile.
- Empty/loading/error patterns consistent and reusable: `.empty-state` (`style.css:546-556`, owned by `style.css`, "never redefine" per `feedback.css:2` comment), toasts (`feedback.js`/`feedback.css`, `role="status" aria-live="polite"`), `#analysis-status` spinner (`feedback.css:117-167`, driven by `analysis:start`/`analysis:end`). `insights.js` reuses `.empty-state` (`insights.js:90-97`) and adds `.insights-loading`/`.insights-empty-note`/`.insights-thin-data` variants (`insights.css:18-44`).

## Motion

- Global reduced-motion kill-switch: `style.css:86-91` (`transition-duration`/`animation-duration` → 0.01ms for `*`).
- Per-file explicit reduced-motion overrides: `panel.css:37-41` (eval-bar, redundant-but-explicit), `movelist.css:50-54` (chevron, redundant), `feedback.css:156-167` (swaps spinner rotation for opacity pulse — real content-level accommodation). `review.css`'s `@keyframes review-toast-in` (`review.css:800-803`) has **no reduced-motion override** — relies on the global duration-zeroing rule; verify during sweep.
- Motion tokens used consistently for `transition:`; no ad-hoc duration literals outside keyframe animation durations (`spinner-rotate 0.75s`, `spinner-pulse 1.5s`).

## JS-coupled classnames (renaming breaks behavior)

- `app.js`: `body.setup-mode` (`app.js:619`), `body.trap-watch-mode`/`body.trap-practice-mode` (`app.js:1016-1017,1145`), `body.rep-mode` (`app.js:1595`), `body.review-mode` (`app.js:1842` — **orphaned, no CSS consumer**), `document.body.dataset.mode` (`app.js:116,1929` — drives `body[data-mode="…"]` selectors at `style.css:441-453`), `.error` toggle on `#fen-error`/`#setup-error` (`app.js:514`), `.active` on palette/tool/side buttons (`app.js:625,655-656`), `.feedback-good`/`.feedback-bad` on `#trap-feedback`/`#rep-feedback` (`app.js:1186,1281-1283,1588-1590`), `.collapsed` on `.rep-color-body`/`.rep-opening-body` (`app.js:1499,1513`), `.is-busy` on `#engine-restart-btn` (`app.js:2044,2056`), `.is-active` on `#panel-tabs button` + `.tab-panel` (`app.js:2006,2011`).
- `movelist.js`: `.collapsed` on `.movelist-block` (`movelist.js:125,132`), `.is-current` + `q-{quality}` on `.movelist-move` (`movelist.js:41-44`).
- `panel.js`: `q-{quality}` on `#quality` (`panel.js:219`), `.quality`/`.quality q-book` resets (`panel.js:209,266,299`).
- `feedback.js`: `.toast--visible`, `.toast--success`/`.toast--error` (`feedback.js:27-51,69`), `.analysis-status--active` (`feedback.js:94,101`).
- `insights.js`: `.is-active` on sub-panels (`insights.js:538-539`), `.insights-row-thin` conditionally appended based on `sufficient` (`insights.js:128,142,194,361`).

Any classname renamed during the sweep must be updated in the matching JS file(s) — CSS-only renames silently desync from JS-driven state.

## Risks for this pass (ranked)

1. **Highest** — Insights JSON-key coupling: `insights.js` render functions assume exact backend field names/shapes per section. Visual redesign safe as long as these reads aren't touched.
2. **High** — `body[data-mode]` layout collapse (`style.css:441-453`) excludes `review` mode by design; a naive "unify all non-play modes" refactor hides the panel in review mode and breaks Insights/Review visibility.
3. **High** — FOUC risk for the theme toggle: `prefs.js` reads happen post-paint today; light/dark toggle needs a pre-paint inline read.
4. **Medium** — Raw non-token `oklch()` literals (9 sites) won't repaint under a light `:root` redefinition unless converted to semantic tokens.
5. **Medium** — `body.review-mode` orphan (JS sets it, no CSS consumer) — decide: wire up vs remove.
6. **Medium** — Inconsistent focus treatment in `review.css` (3 sites) — normalize.
7. **Low-Medium** — Touch targets below target size on dense controls — conscious decision needed at 375px.
8. **Low** — `#eval-bar` fixed 14px while board scales — verify no overflow at exactly 375px.
9. **Low** — Chessground board (CDN brown + cburnett) theme-independent — product decision whether board adapts to light mode.
