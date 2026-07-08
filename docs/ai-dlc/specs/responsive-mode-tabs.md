# Delta spec — responsive-mode-tabs (unify all modes)

## Goal (one line)
Make the panel tab bar visible and clickable in **every** special mode; a tab click
exits the current mode back to play and switches, popping a confirm ONLY when that
mode holds meaningful in-progress state.

## Corrected problem statement (post-refuter)
The tab bar (`#panel-tabs`) lives in `<aside class="panel">` (index.html:212-214).
- In **review** mode there is no hide rule → `.panel` + tabs stay visible, but the
  tab-click handler bails at `app.js:896` (`if body.dataset.mode !== 'play' return`)
  → tabs look clickable but are **dead**. This is the exact bug the user hit.
- In **setup / trap-watch / trap-practice / rep-practice** (`style.css:562-567`) and
  **blunder-practice** (`trainer.css:180-182`), `.panel` is `display:none` and
  `<main>` collapses to one column (`style.css:555-560`) → tabs are **not rendered
  at all**; each mode shows its own bar below the board instead.

So today only review has visible-dead tabs; the other four hide tabs entirely.
**User decision (2026-07-07): unify — un-hide the tab bar in all special modes so
tab behavior is identical everywhere**, accepting the reversal of the deliberate
"hide panel, give board full width" layout choice.

## Chosen approach
Registry Exit-Intent (ideation Approach 2) + un-hidden tab strip in all modes:

### Behavior (hub — app.js)
1. Extend `registerModeHandlers(mode, {onMove, exit})` with an optional `isDirty()`
   (no change to the function itself — it stores handlers as-is, app.js:110).
2. Add `api.hub.requestModeExit()`:
   - if `state.mode === 'play'` → return `true`;
   - `h = _modeHandlers[state.mode]`; `dirty = h && h.isDirty ? h.isDirty() : false`;
   - if `dirty` and user cancels `confirm(msg)` → return `false`;
   - else call `ensurePlay()` (app.js:686 — dispatches the registered `exit()`),
     return `true`.
   Routing through `ensurePlay()`/the registered `exit()` (NOT a raw `setMode`)
   preserves `exitTrainer`'s `flushOutcomes()` Leitner POST.
3. Register review into `_modeHandlers` where `exitReview` is defined (app.js ~767/848):
   `registerModeHandlers('review', {exit: exitReview, isDirty: () => false})`.
   Now `ensurePlay()` covers all modes uniformly. (trainer.js:293's explicit
   `exitReview()`-then-`ensurePlay()` stays harmless: `_modeHandlers['play']` is
   never registered, so the trailing `ensurePlay()` no-ops. Verified by refuter.)
4. Restructure the tab handler (app.js:893-909): replace the early `return` with —
   if `body.dataset.mode !== 'play'`: `if (!requestModeExit()) return;` then fall
   through to the existing activation code (now runs with mode === 'play'). Exit is
   synchronous through `setMode('play')`, so the fall-through re-reads play correctly;
   the captured `btn` stays valid (exits never rebuild the tab buttons — refuter-verified).

### Layout (CSS — make tabs visible in all special modes)
5. In every special mode: **keep `.panel` + `#panel-tabs` visible, hide only the
   `.tab-panel` contents, and revert the single-column collapse** so the tab strip
   sits in its normal right-column place while each mode's own bar keeps rendering
   below the board.
   - `style.css`: remove/replace the `body[data-mode=…] .panel { display:none }`
     block (setup/trap-watch/trap-practice/rep-practice) with rules that keep the
     panel + strip shown and add `body[data-mode=…] .tab-panel { display:none }`;
     drop those modes from the single-column `main` collapse (or keep 2-col only when
     the panel now shows). Same treatment for `trainer.css` (blunder-practice).
   - Preserve mobile parity (≤560px rules already exist for the mode bars).

### Indicator (fills the otherwise-empty strip; answers "no indicator")
6. Add a `#mode-indicator` element as a **sibling AFTER `#panel-tabs`** (NOT a child
   of `role="tablist"` — refuter ARIA fix), `aria-live="polite"`, permanently
   mounted. The hub sets its `textContent` on `mode:change`: a short contextual line
   in special modes (e.g. "Reviewing a saved game — pick any tab to leave") and `''`
   in play. Visibility via a class/`:empty`, node stays mounted (reliable live-region
   announcement — refuter fix). Tokens-only CSS, AA contrast.

## Dirtiness map (each module owns its predicate)
| Mode | `isDirty()` | Confirm? | Owner file |
|---|---|---|---|
| review | `() => false` | No | app.js (registration) |
| trap-watch | omit → false | No | — (cheap) |
| trap-practice | omit → false | No | — (cheap) |
| rep-practice | `() => !!(rep && rep.moves && rep.moves.length > 0)` | When a line is in progress | repertoire.js |
| blunder-practice | dirty when a drill is active AND the current puzzle is unresolved (not in `solved`/`revealed`/`summary` phase) — trainer.js exposes the predicate; MUST NOT leak drill internals to the hub | When mid-puzzle | trainer.js |
| setup | `() => true` (no dirty signal exists — conservative) | Always | setup.js |

**Confirm:** native blocking `confirm()` with a per-mode message. Custom modal is out
of scope. `flushOutcomes()` runs inside `exitTrainer` regardless of confirm outcome,
so a wrong blunder predicate only affects whether the dialog pops, never the flush.

## Correctness invariants (must hold)
- Generic exit routes through the registered `exit()` via `ensurePlay()`; never a
  hand-rolled `setMode('play')` (preserves the Leitner flush).
- Exit runs synchronously BEFORE the tab activation code, same click handler.
- New seam on `api.hub`; no feature module imports app.js.
- `setMode()` stays the only mode-flip path.
- `#mode-indicator` is a sibling of the tablist, not a child; `role=tablist` keeps
  only `role="tab"` children (roving nav / tab count intact).
- Tokens-only CSS, AA contrast, `:focus-visible` on tabs preserved.

## Out of scope
- Custom (non-native) confirm modal / toast; undo-after-exit reversibility.
- Removing the "Return to my game" buttons — they stay as explicit exit.
- Real dirty-tracking for setup beyond conservative always-confirm.
- Showing live play-mode eval/analysis content inside a special mode (panels stay
  hidden; only the strip + indicator show).
- Refactoring trainer.js:293's now-redundant review special-case.
- Any backend / DB / engine change.

## Verify-by (end-to-end — now executable; tabs visible in all modes)
- `.venv/bin/python -m pytest -q` green; `.venv/bin/ruff check app tests` clean
  (frontend-only change — sanity only).
- UI via Playwright-MCP on a live server:
  1. **Review (cheap, no confirm):** Review → open a game → click **Insights** →
     leaves review, shows Insights, no confirm, no dead click. Indicator empty in play.
  2. **Blunder (dirty, confirm + flush):** start a drill, resolve ≥1 puzzle, mid next
     puzzle click **Analysis** → confirm pops; Cancel keeps the drill; OK exits +
     switches AND the resolved outcome still flushes (POST `/api/trainer/bucket-complete`
     fired — check network).
  3. **Rep-practice (dirty when line started):** begin a prepared line, play a move,
     click a tab → confirm; from a fresh line with no move → no confirm.
  4. **Setup (always-confirm):** enter setup, click a tab → confirm appears.
  5. **Indicator + a11y:** in each special mode `#mode-indicator` shows its line and
     is visible; screenshot per mode; tab `:focus-visible` ring intact; the tablist
     still exposes exactly 6 tabs to the a11y tree (indicator not counted).
  6. **Mobile (≤560px):** tab strip reachable in a special mode; no layout breakage.
