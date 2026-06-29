# Tickets — UX/UI Modernization

6 tickets in 3 phases. Disjoint file ownership within each phase → safe parallel agents.
Phase-2 agents run in **isolated git worktrees**; orchestrator merges + integrates in Phase 3.
A **design-review gate** sits between Phase 1 and Phase 2 (user signs off the bold look).

```
Phase 1 (parallel ×2)        Phase 2 (parallel ×3)         Phase 3 (orchestrator)
 ┌─ T1 HTML/CSS foundation ─┐   ┌─ T3 Analysis panel ─┐
 │                          ├──►│  T4 Feedback        ├──► T6 Integrate + verify + review + commit
 └─ T2 JS seams ────────────┘   └─ T5 Shortcuts ──────┘
         │  [Phase-1 gate: app still works + user approves the look]  │
```

---

## Phase 1 — Foundation & seams (parallel ×2)

### T1 — Visual foundation, app-shell, tabbed panel, icons
**Owns:** `static/index.html`, `static/style.css` (+ creates empty `static/panel.css`,
`static/feedback.css` and links them; adds font/Lucide links to `<head>`).
**Does:** OKLCH dark palette + multi-level surface/elevation tokens + accent; Inter +
JetBrains Mono + `tabular-nums`; 4px spacing scale; motion tokens + `@media
(prefers-reduced-motion)`; **CSS Grid app-shell** (`100dvh`, header `auto` + `1fr`, right
panel independent scroll — kills dead space); restructure `<aside>` into the **tabbed
skeleton** (`#panel-tabs` + `#tab-analysis|opening|traps|repertoire`) with the existing
blocks moved into the right tabs + empty mount nodes (`#eval-bar`, `#toasts`,
`#analysis-status`); replace HTML-entity glyphs with **Lucide** icons (+ visible text/labels
kept); convert `#promo-overlay` → `<dialog id="promo-dialog">` markup; `body[data-mode]`
visibility CSS scaffolding; fix muted-label contrast; promote remaining raw-hex to tokens.
**Acceptance:** bold modern dark look; no dead space at 1440px; mobile (390px) still works;
all existing controls present + reachable; `<dialog>` markup in place; tab skeleton + mount
IDs match the spec seam contract exactly.
**Done-condition:** `pytest` green; Playwright load → screenshot desktop+mobile, **0 console
errors**, every pre-existing button still visible/clickable, FEN load still works.
**Deps:** none. Build to the spec's seam-contract IDs.

### T2 — JS seams (module extraction + injected api)
**Owns:** `static/app.js` (+ creates `static/panel.js`, `static/feedback.js`,
`static/shortcuts.js` as behavior-preserving **stubs**).
**Does:** extract the analysis-panel DOM writes (`renderAnalysis`/`renderBookMove`/
`renderOpening`) into `panel.js` `initPanel(api)` (stub = current behavior); build the
injected **`api`** (`actions` + tiny `on/emit` bus + resolved `mounts`); emit
`analysis:start/end/result` in `refreshAnalysis`; set `document.body.dataset.mode` on every
mode change + emit `mode:change`; basic **tab-switch** wiring (click `[data-tab]` → show
panel); convert `askPromotion` to drive `<dialog id="promo-dialog">` (showModal, focus,
Esc); add empty-state messages in `renderTraps` + `renderRepertoireTree`; call
`initPanel/initFeedback/initShortcuts(api)` from `init`.
**Acceptance:** app behaves **identically** to today (panel renders, all modes work, persist/
restore intact, board trampoline still reads `state.mode` at call time); stubs wired; api
exposes the full contract; **no backend/API change**.
**Done-condition:** `pytest` green (152); Playwright regression — play a move, undo/redo,
flip, load FEN, enter+exit a trap and a rep practice, promotion via `<dialog>`; **0 console
errors**; localStorage key/shape unchanged.
**Deps:** none. Build to the spec's seam-contract (mount IDs from T1, api shape from spec).

> Phase-1 gate (orchestrator + user): verify both merge cleanly and the app is unbroken;
> **user approves the bold look** before Phase 2 starts.

---

## Phase 2 — Features (parallel ×3, isolated worktrees, additive-only)

### T3 — Analysis panel: eval bar, PV, quality
**Owns:** `static/panel.js`, `static/panel.css`.
**Does:** implement the eval bar (subscribe `analysis:result`; clamp ±5, mate → full; CSS var
fill); reformat PV (move numbers, per-move `<span>` tokens, depth/score `+0.35 d20`); render
move-quality as **color + text/icon** (Lucide); style best-move; all using T1 tokens.
**Acceptance:** on each analysis, eval bar + number + quality(+icon) + numbered PV update;
quality readable without color; no color-only meaning.
**Done-condition:** Playwright — play a move (trusted mouse) → eval bar moves, PV shows
`1. e4 e5 2. Nf3…`, quality shows icon+label; 0 console errors.
**Deps:** T1 (mounts, tokens, panel.css link), T2 (panel.js stub, api bus).

### T4 — Feedback: toasts, loading, empty states
**Owns:** `static/feedback.js`, `static/feedback.css`.
**Does:** toast util (auto-dismiss, 1 at a time) fired on FEN load / engine-ready /
errors-as-banner; "Analyzing…" indicator in `#analysis-status` driven by
`analysis:start/end`; style the empty states T2 emits for filtered Traps/Repertoire.
**Acceptance:** toast appears + self-dismisses; loading shows during analysis; empty filter
shows a message, not a blank list.
**Done-condition:** Playwright — load a FEN → toast; filter traps to no-match → empty state;
slow analysis shows the indicator; 0 console errors.
**Deps:** T1 (mounts, feedback.css link, tokens), T2 (api bus, empty-state hooks).

### T5 — Keyboard shortcuts
**Owns:** `static/shortcuts.js`.
**Does:** implement `initShortcuts(api)` — Ctrl/Cmd+Z undo, Ctrl/Cmd+Y / Shift+Cmd+Z redo,
`F` flip, ←/→ step, Esc close dialog; ignore when focus is in an input/`<dialog>` text field;
no-op in modes where an action doesn't apply.
**Acceptance:** shortcuts work in play mode, don't fire while typing in the FEN box, don't
break trap/rep modes.
**Done-condition:** Playwright — `F` flips, ←/→ steps history, Ctrl+Z undoes, Esc closes the
promotion dialog; typing in FEN box doesn't trigger shortcuts; 0 console errors.
**Deps:** T2 (api.actions). Independent of T1.

---

## Phase 3 — Integration (orchestrator, serial)

### T6 — Integrate, mode-scope, verify, review, commit
**Owns:** merge of all worktrees + cross-cutting glue (small edits anywhere as needed).
**Does:** merge T3/T4/T5; finish **mode-scoping** (panel scoped per `body[data-mode]` so
trap/rep modes don't show a contradictory play-mode eval); motion/View-Transition polish on
tab + mode switches; full **Playwright** pass across all modes + mobile; independent
**review (maker ≠ checker)** via `cavecrew-reviewer`; `pytest`; reduced-motion + contrast
checks; remove debug artifacts; **commit** per policy (logical grouping: foundation, then
each feature, or one cohesive series — implemented+verified+reviewed only).
**Acceptance:** every Verify-by step in the spec passes; review clean; tests green.
**Done-condition:** full spec Verify-by green; `git` commits made (not pushed).
**Deps:** T3, T4, T5.

---

## Refuter amendments (per ticket — binding; full text in the spec)
- **T1:** preserve the exact ID list (spec §3); wrap `#board`+`#eval-bar` in `.board-wrap`
  (flex row); app-shell columns `auto minmax(280px,1fr)` (no dead space); `body[data-mode]`
  CSS hides the tab bar + play-only Analysis content in non-play modes; `<dialog
  id="promo-dialog">` markup; keep `#status` **and** add `#analysis-status`.
- **T2:** analysis render stays a **direct call** `panel.renderAnalysisPanel(a, opts)` /
  `renderBookMovePanel(data)` (pass `opts` incl. `suppressQuality`) — **not** a bus event;
  emit `toast:show` from `loadFen()` success; `init*` called **after** ground (app.js:1683);
  tab-switch handlers no-op when `body.dataset.mode !== 'play'`; align empty-state class to
  `.empty-state`; `askPromotion` Promise resolves on piece-click, **rejects on Esc → caller
  cancels move + `syncBoard()`**.
- **T3:** implement `renderAnalysisPanel(a, opts)` honouring `opts.suppressQuality` + book
  path; style `#eval-bar` (~12px, stretch) in `panel.css`.
- **T4:** subscribe to `toast:show`; **only style** the existing `.empty-state` (behaviour
  already exists in `renderTraps`).
- **T5:** Esc defers to native `<dialog>` when one is open (`dialog[open]`); ignore shortcuts
  while typing in inputs.
- **Promo verification** is gated to the **Phase-1 integration step** (needs T1's `<dialog>`
  merged), not a T2-standalone test.

## Parallelization summary
- **Phase 1:** 2 agents in parallel (T1 HTML/CSS, T2 JS) — disjoint files; both build to the
  spec seam contract. Critical path = the slower of the two.
- **Gate:** orchestrator verifies + user approves the look.
- **Phase 2:** 3 agents in parallel (T3, T4, T5) — disjoint files, additive-only, worktrees.
- **Phase 3:** orchestrator integrates + verifies + reviews + commits (serial).
- **`app.js` and `index.html`/`style.css` are each touched by exactly one agent per phase** —
  the core safety property.
