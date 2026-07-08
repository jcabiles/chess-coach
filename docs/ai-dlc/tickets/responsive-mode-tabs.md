# Tickets — responsive-mode-tabs (unify all modes)

Spec: `docs/ai-dlc/specs/responsive-mode-tabs.md`. Contracts:
`docs/ai-dlc/contracts/responsive-mode-tabs.md`. One-file-one-owner enforced —
each hotspot file has exactly one owning ticket.

## DAG
```
T1(index.html) ─┐
T3(css)        ─┼─► T2(app.js seam) ─► T4(module isDirty) ─► T5(verify)
                │        ▲                     
                └────────┘  (T2 null-guards indicator; T1/T3 make tabs visible)
```
T1 + T3 are independent of each other and of T2's logic, but T5 (verify) needs all.
Realistic order: **T1, T3 → T2 → T4 → T5.** T2 works without T4 (degrades to
no-confirm); T4 turns on the confirms.

---

### T1 — Add mode-indicator markup (owns: static/index.html)
Add `<div id="mode-indicator" aria-live="polite"></div>` as a **sibling immediately
AFTER** `#panel-tabs` (index.html:214-221), OUTSIDE `role="tablist"`. Empty by default.
- **Done:** element present, not a child of the tablist; `#panel-tabs` still contains
  exactly the 6 `role="tab"` buttons.
- **AC:** a11y tree still reports 6 tabs; no new tab counted.

### T2 — Hub exit seam + tab handler (owns: static/app.js)
- Add `requestModeExit()` (per spec §Behavior 2); expose on `api.hub`.
- Register review: `registerModeHandlers('review', {exit: exitReview, isDirty: () => false})`
  near `exitReview` (app.js ~767/848).
- Restructure tab handler (app.js:893-909): replace `if (…!== 'play') return;` with
  `if (…!== 'play') { if (!requestModeExit()) return; }` then existing activation.
- On `mode:change`, set `#mode-indicator` textContent (contextual line per special
  mode, `''` in play). Null-guard the element.
- **Done:** in review, clicking a non-review tab exits review + switches (no confirm);
  `pytest`/`ruff` unaffected; no import of feature modules.
- **AC (runnable):** `.venv/bin/ruff check app tests` clean; manual/Playwright: review
  tab-away works; indicator text set on mode change.
- **Depends:** T1 (indicator id) — soft (null-guarded).

### T3 — Un-hide tabs in special modes (owns: static/style.css, static/trainer.css)
- Replace the `body[data-mode=…] .panel { display:none }` block (style.css:562-567)
  and the blunder rule (trainer.css:180-182) with rules that keep `.panel` +
  `#panel-tabs` visible but `hide` the `.tab-panel` contents; revert the
  single-column `main` collapse (style.css:555-560) for these modes so the strip
  shows. Add tokens-only styles for `#mode-indicator` (visible only when non-empty;
  AA contrast). Preserve ≤560px mobile parity.
- **Done:** in setup/traps/rep/blunder, the tab strip renders; play-mode analysis
  content does NOT show; board still usable.
- **AC (runnable):** Playwright screenshots per mode show the strip; no raw hex added
  (tokens-only); AA contrast on indicator.
- **Depends:** none (independent of T2).

### T4 — Per-module isDirty predicates (owns: static/setup.js, static/repertoire.js, static/trainer.js)
- `setup.js:229`: add `isDirty: () => true` to its registration.
- `repertoire.js:416`: add `isDirty: () => !!(rep && rep.moves && rep.moves.length > 0)`.
- `trainer.js:612`: add `isDirty: () => <drill active AND current puzzle unresolved>`,
  predicate defined inside trainer.js from its own `drill` state (no hub leak).
- trap-watch/trap-practice: leave unregistered-dirty (cheap → no confirm).
- **Done:** confirm pops only for setup (always), rep with a move played, blunder
  mid-puzzle; never for review/traps/fresh-rep.
- **AC (runnable):** Playwright per spec Verify steps 2-4; blunder OK-exit still fires
  `/api/trainer/bucket-complete`.
- **Depends:** T2 (consumes `isDirty` via `requestModeExit`).

### T5 — Verify (owns: no source files; evidence only)
Run the spec's full Verify-by: `pytest -q`, `ruff`, and Playwright steps 1-6
(review no-confirm, blunder confirm+flush, rep conditional, setup always-confirm,
indicator+a11y 6-tabs, mobile ≤560px). Capture evidence; no debug artifacts left.
- **Depends:** T2, T3, T4 (and T1).

## Parallelization
- T1 and T3 can run in parallel (disjoint files, no logic dependency).
- T2 after T1. T4 after T2. T5 last.
- Hotspots each single-owned: index.html→T1, app.js→T2, style.css/trainer.css→T3,
  feature modules→T4. No file double-owned.
