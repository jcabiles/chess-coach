# Tickets — movelist relocation (spec: specs/movelist-relocation.md)

**Bottom line:** 4 sequential tickets, one owner each, no parallelization (T2/T3
depend on T1's markup; T4 verifies everything). Small feature — a single implementer
agent or inline work covers all four. Updated after the dual review (ledger/
movelist-relocation.md): height-chain, bot-play gate, responsive width, and
CSS-scoping requirements folded in.

## T1 — Move the markup + desktop column layout

Move `.movelist-block` from `.panel-eval-card` into `.action-col` and build the
height/width chain the review demanded.

- Files owned: `static/index.html`, `static/style.css` (action-col + main grid only).
- Acceptance: block renders under "Set up position" as a card; `.action-col` gets
  `align-self:stretch` (desktop) + `min-height:0` down the chain so `#move-list`
  (`flex:1; overflow-y:auto`) actually fills and scrolls — no clipping by
  `main{overflow:hidden}`; column ~220px normally, responsive (clamp) when the bot
  rail is open at 1281–1440px so the board stays usable; tokens-only CSS; all new
  rules scoped under `.action-col .movelist-block` (shared `.movelist-toggle`/
  `.movelist-chevron` selectors byte-identical).
- Done-condition (runnable): Playwright — `.action-col .movelist-block` exists,
  `#tab-analysis .movelist-block` does not; with 40+ plies the list's scrollHeight >
  clientHeight and the column bottom is not clipped; rail-open at 1350px leaves no
  board clipping.

## T2 — Scroll containment fix + bot-play render gate (depends T1)

In `static/movelist.js`: replace `scrollIntoView` with `#move-list`-scoped scrolling
via `getBoundingClientRect()` deltas (or add `#move-list{position:relative}` and use
offset math), and add `'bot-play'` to the render-mode gate at `movelist.js:78`.

- Files owned: `static/movelist.js`.
- Acceptance: after each of 16+ trusted-mouse moves, `#tab-analysis.scrollTop === 0`
  and `window.scrollY === 0`; current cell's rect within `#move-list` rect; clicking
  an early move scrolls only the box. Bot game: list updates live; clicking a cell is
  a no-op (app.js `goto()` gate untouched — do not widen it).
- Done-condition: Playwright assertion loop (Verify-by §2) + bot-play check (§7) pass.

## T3 — Mode gating + mobile fallback + collapsed sizing (depends T1)

Hide the block in setup/trap-watch/trap-practice/rep-practice/blunder-practice via the
mode-class mechanism (`style.css:945-951` pattern); ≤820px stacking; collapsed flex.

- Files owned: `static/style.css` (mode gating + media query), `static/movelist.css`.
- Acceptance: the five special modes show no moves list and no stale table; return to
  play restores it; ≤820px the block gets `flex-basis:100%` so it always lands on its
  own line under the button row, capped ~12rem, internal scroll, ≥24px hit targets;
  `.movelist-block.collapsed { flex:0 0 auto }` — header-only footprint, verified on
  fresh collapse AND persisted-collapsed reload. Cross-tab visibility (list shown on
  all tabs in play mode) is intended — no tab wiring added.
- Done-condition: Playwright — setup mode → block hidden; 800px width → block on its
  own line, `overflow-y:auto`, capped; collapsed reload → header-only.

## T4 — End-to-end verification + regression pass (depends T2, T3)

Run the spec's full Verify-by list (§1–§10) and the pytest suite; fix nothing new —
file follow-ups instead.

- Files owned: none (read-only + test run).
- Acceptance: `.venv/bin/python -m pytest -q` green (baseline 1022 passed);
  Verify-by §1–§10 all pass, including review-mode auto-follow, bot-play live list,
  rail-open board width, cross-tab visibility, and the shared-disclosure regression
  check.
- Done-condition: the Verify-by checklist recorded pass/fail in the PR description.

## Notes

- Hotspots touched: `static/index.html`, `static/style.css` (profile hotspots) —
  single-owner per ticket; no two tickets edit the same file concurrently.
- No backend surface; no DB schema; no new dependencies.
