# Delta spec — relocate moves list to the action column + fix auto-scroll

**Bottom line:** move the Moves list from the right Analysis panel into the middle
action column (under the board buttons) as a tall card, and replace the
`scrollIntoView` call with scrolling scoped to the list box itself, so playing a move
never scrolls the panel or page again. Chosen from 4 mockups (option B) on 2026-08-13.

## Goal (one line)

Moves list lives in the action column with a tall internal scroller; the
follow-the-current-move behavior scrolls only `#move-list`, never an ancestor.

## Behavior

1. **Placement (desktop, >820px):** `.movelist-block` moves from `.panel-eval-card`
   (`static/index.html:293-296`) into `.action-col` (`static/index.html:222-229`),
   below the "Set up position" button. Styled as a card (tokens only); list fills the
   remaining column height (no 18rem cap) and scrolls internally.
   - **Height chain (review finding #1):** `.action-col` currently has
     `align-self:start` (`style.css:383-393`) so a `flex:1` child has NO height
     source and `main{overflow:hidden}` would clip overflow (moves unreachable).
     Required: `align-self:stretch` on `.action-col` (desktop only) + `min-height:0`
     on `.action-col`, `.movelist-block`, and `#move-list`, with
     `flex:1; overflow-y:auto` on `#move-list`. The ≤820px rule restores auto
     height before applying the mobile cap.
   - **Column width (review finding #4):** ~220px normally, but responsive when the
     bot rail is open — at 1281–1440px the grid also carries a fixed 300px rail
     track; the column must shrink (e.g. `clamp()`/container-responsive width) so
     the board keeps a usable width. Acceptance case at 1281–1440px rail-open.
   - **Collapsed state (review finding #7):** `.movelist-block.collapsed` is
     `flex: 0 0 auto` — only the header row occupies space; verified for both a
     fresh collapse and a persisted-collapsed reload.
   - **CSS scoping (review finding #8):** every new rule is scoped under
     `.action-col .movelist-block`; the shared `.movelist-toggle` /
     `.movelist-chevron` selectors (also used by the Play-vs-Bot and
     analysis-settings disclosures) stay byte-identical.
2. **Scroll fix (review finding #5):** in `static/movelist.js` render(), replace
   `active.scrollIntoView({block:'nearest'})` with scrolling scoped to `#move-list`
   only, computed via `getBoundingClientRect()` deltas between the current cell and
   the list box (NOT `offsetTop` — no positioned ancestor exists), or add
   `#move-list{position:relative}` first. No ancestor may move.
3. **Mobile (≤820px, review finding #6):** the action column folds into a
   `flex-wrap` row; the Moves card gets `flex-basis:100%` so it always starts its
   own line below the button row, capped ~12rem, internal scroll. CSS-only
   fallback — one DOM location.
4. **Modes (review findings #2, #3):**
   - Renders and auto-follows in `play`, `review`, AND `bot-play` (add `bot-play`
     to the `movelist.js:78` mode gate — today the list silently freezes during
     bot games; this fixes that). Click-to-jump in bot-play is a safe no-op via
     app.js `goto()`'s existing play/review gate — do not widen that gate.
   - Hidden (mode-class mechanism, `style.css:945-951` pattern) in
     setup/trap-watch/trap-practice/rep-practice/blunder-practice; no stale table
     may linger after leaving a rendering mode.
   - **Cross-tab visibility (documented decision):** while mode is `play`, the
     list is visible on ALL tabs (Opening/Traps/Repertoire/Insights), exactly like
     the Undo/Redo/Flip/Reset buttons beside it — the action column is not
     tab-scoped and no tab-hook wiring is added. This is an intended behavior
     change from today (list previously hid with the Analysis tab panel).
5. **Unchanged:** collapse chevron + `moveListCollapsed` pref, click-to-jump,
   `.q-*` quality tints, `.is-current` ring, blunders-only filter, `#move-list` /
   `#movelist-toggle` IDs, injected-`api` pattern (no imports from app.js).

## Files / interfaces to touch

- `static/index.html` — move the `.movelist-block` markup.
- `static/movelist.css` — card styling, height/flex rules, mobile fallback.
- `static/style.css` — `.action-col` width/flex, ≤820px fold adjustments,
  mode-visibility gating for the block.
- `static/movelist.js` — scroll-containment fix only.

## Out of scope

No changes to the eval card, Play-vs-Bot section, analysis-mode settings, review
coaching column, backend, or any Python file. No renames of IDs or events. No new
dependencies.

## Constraints (from profile)

- Frontend modules receive an injected `api`; never import from app.js.
- Tokens-only CSS (no raw hex), AA contrast, `:focus-visible` on interactive controls,
  ≥24px hit targets ≤820px.
- Pure-module invariants untouched (no backend surface); full pytest suite must still
  pass with no Stockfish binary.
- Commit policy: implemented + verified (browser) + reviewed; Conventional Commits;
  feature branch only.

## Verify-by (end-to-end)

1. `.venv/bin/python -m pytest -q` passes (no backend change; regression guard).
2. Playwright on the live server: reset, play 16+ moves via trusted mouse;
   assert after each move that `#tab-analysis.scrollTop === 0` and
   `window.scrollY === 0` (the old bug), and that the current-move cell is visible
   inside `#move-list` (its bounding box within the list's box).
3. Click an early move → board jumps, list scrolls only internally; collapse chevron
   hides list and survives reload; blunders-only mode still filters dots.
4. Resize to ≤820px: Moves card sits on its own line under the button row, capped
   height, internal scroll; hit targets ≥24px.
5. Enter setup mode and a trap drill: no moves list visible; return to play: list back.
6. Open a Review game: list renders in the action column and replay navigation
   auto-follows without any panel scroll.
7. Bot-play: start a bot game, play 4+ moves — list updates live; clicking a move
   cell does nothing (no cursor jump, no board change).
8. Open the bot rail at 1281–1440px viewport: board stays usable (no clipping of
   h-file or Load button); Moves column shrinks responsively.
9. Browse Opening/Traps/Repertoire/Insights tabs in play mode: list stays visible
   beside the board and current (intended cross-tab behavior).
10. Collapse the list, reload: only the Moves header occupies column space (no blank
    flex gap); Play-vs-Bot and analysis-settings disclosures render identically to
    main (shared-class regression check).
