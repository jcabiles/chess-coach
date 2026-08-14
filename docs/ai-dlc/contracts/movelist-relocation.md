# Contracts — moves list relocation (mapped inline, 2026-08-13)

**Bottom line:** the moves list is a self-contained module wired by element IDs and an
injected `api`; relocating its mount point in the DOM is safe as long as the IDs, the
event subscriptions, and the prefs seam survive. The one behavioral landmine is the
`scrollIntoView` call, which scrolls every scrollable ancestor — that is the bug being
fixed, and its replacement must scroll only `#move-list`.

## Root cause (verified live via Playwright, 2026-08-13)

- `static/movelist.js:127` — `active.scrollIntoView({ block: 'nearest' })` runs on every
  render (every move).
- The page body is `overflow: hidden`; the actual scroller is `#tab-analysis` (the right
  Analysis panel). `scrollIntoView` scrolls **all** scrollable ancestors, so each move
  drags the panel to its bottom, pushing the eval card out of view. This is the
  "auto-scrolls to the bottom of the page" the user reported.

## Invisible contracts

1. **IDs are the wiring.** `#move-list`, `#movelist-toggle`, `.movelist-block` are read
   by `movelist.js` (`byId`). Moving the block in `index.html` is fine; renaming anything
   is not.
2. **Injected api, no imports.** `movelist.js` receives `api` at init and never imports
   from `app.js` (profile invariant). Relocation must not add imports.
3. **Render triggers:** `position:change` and `analysis-mode:change` bus events. The
   module re-renders the whole table each time — any scroll position on `#move-list`
   must be re-applied after `innerHTML` replacement (already true today; keep it true).
4. **Mode gating:** render early-returns unless `state.mode` is `play` or `review`
   (`movelist.js:78`). The block also lives inside `#tab-analysis`, which panel.js
   shows/hides by tab. Moving the block OUT of the tab panel changes visibility
   semantics: it will be visible on every tab unless explicitly gated. The action
   column (`.action-col`) is visible in all tabs/modes; several board-col bars
   (setup/trap/rep/trainer) take over the board area in special modes while the module
   renders nothing (early return) — a stale table could linger. Relocation must define
   who hides the block in non-play/review modes (CSS mode classes or the module itself).
5. **Prefs seam:** `moveListCollapsed` via `prefs.js` `readUiPrefs`/`writeUiPref`;
   applied before first paint; chevron `aria-expanded` kept in sync.
6. **Quality classes:** `.q-*` text tints, `.is-current` ring (accent inset shadow),
   blunders-only filter (`BLUNDERS_MODE_VISIBLE`). Pure CSS/class contracts — survive
   relocation as long as `movelist.css` still applies.
7. **Layout grid:** `main` is `auto | minmax(0,582px) | auto | minmax(280px,300px)`
   (+300px bot rail when open). The action column is the intrinsic (`auto`) 3rd track —
   widening it steals width from nothing at desktop sizes, but on narrow viewports the
   board's `100cqw` width-guard will shrink the board. At ≤820px the action column folds
   into a horizontal row under the board (media query at `style.css` ~2296).
8. **Accessibility:** tokens-only CSS (no raw hex), AA contrast, `:focus-visible` on all
   interactive controls, ≥24px hit targets at ≤820px (movelist.css already provides).
9. **Review mode:** `review.js` drives the same board/state; the list renders in review
   replays. `#analysis-review-col` occupies panel width in review mode — removing the
   moves list from the panel actually frees panel space there.

## Integration points

- `static/index.html:293-296` — current mount (inside `.panel-eval-card` in
  `#tab-analysis`).
- `static/index.html:222-229` — `.action-col`, the target mount.
- `static/movelist.css` — all list styling incl. 18rem cap + mobile hit-boxes.
- `static/style.css` — `.action-col` styling, `main` grid, ≤820px fold media query,
  mode-gating classes on `body`/`main` (check which class hides action-col children in
  special modes, if any).
- `static/app.js` — calls `initMovelist(api)`; no changes expected.
- `tests/` — frontend has no JS unit tests; verification is Playwright + pytest
  (pytest unaffected: no backend surface touched).
