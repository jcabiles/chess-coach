# Delta Spec — UX/UI Modernization

## Goal (one line)
Transform the front-end from a flat dev-tool look into a **bold, modern, professional**
chess app — new visual system, balanced layout, grouped/tabbed panel, an eval bar, and
the cheap-but-high-value polish — **without any backend/API change**, structured so the
work parallelizes across agents.

## Locked decisions (from interview)
- **Bold new look** (not just a refresh) — new design system; Phase-1 foundation output is
  reviewed by the user at the Phase-1 gate before features build on it.
- **New-module + foundation-first seams** parallelization (see Architecture).
- **Move list / notation history: DEFERRED** (not this session).
- **Out of scope:** light theme; deep assistive-tech a11y (screen-reader board, ARIA
  grid/treegrid, aria-live move announcements). **In scope (cheap a11y):** text-contrast
  fix, color+label/icon for move quality, keyboard shortcuts, native `<dialog>`,
  `prefers-reduced-motion`.

## In scope
- **Visual system:** OKLCH-based dark palette, multi-level surfaces/elevation, a defined
  accent, Inter (UI) + `tabular-nums`, JetBrains Mono (FEN/PV/notation), a 4px spacing
  scale, Lucide SVG icons (replace HTML-entity glyphs), motion tokens + reduced-motion.
- **Layout:** CSS Grid app-shell (`100dvh`, header `auto` + content `1fr`, right panel
  scrolls independently) → kills dead space + unbalanced columns. Mobile preserved.
- **Panel IA:** group the right `<aside>` into a **tabbed** structure
  (Analysis · Opening · Traps · Repertoire). Analysis tab is default.
- **Eval bar:** thin vertical white/black bar beside the board, driven by the existing eval
  (clamp ±5, mate → full). No API change.
- **Analysis readability:** PV reformatted with move numbers + per-move tokens + depth/score;
  move-quality shown as **color + text/icon** (never color-only); contrast fixed.
- **Feedback:** toast system; engine "Analyzing…" loading state; empty states for filtered
  Traps/Repertoire lists.
- **Promotion:** convert the custom overlay to native `<dialog>` (focus-trap, Esc, backdrop).
- **Keyboard:** Ctrl/Cmd+Z undo, Ctrl/Cmd+Y (or Shift+Z) redo, F flip, ←/→ step, Esc close.
- **Mode scoping:** in trap/rep modes the panel is scoped to the mode (fixes the live bug
  where the panel showed a contradictory play-mode eval). Done in integration.

## Out of scope (explicit)
Move list/notation history · variation tree · light/system theme · deep AT a11y · command
palette · eval graph · P3 gamut · ANY backend/`app/` change · full `app.js` module split.

## Architecture — the seam contract (interface-first)
Phase 1 establishes stable interfaces; Phase-2 agents build against them with **disjoint
file ownership** (no two agents edit one file in a phase).

**New DOM mount points (created by T1 in index.html):**
- Tab bar `#panel-tabs` with buttons `button[data-tab="analysis|opening|traps|repertoire"]`;
  tab panels `#tab-analysis`, `#tab-opening`, `#tab-traps`, `#tab-repertoire`.
- `#eval-bar` beside the board in `.board-col`.
- Promotion as `<dialog id="promo-dialog">` (replaces `#promo-overlay`).
- Toast container `#toasts`; loading slot `#analysis-status`; empty-state class `.empty-state`.
- `<head>`: Inter + JetBrains Mono font links; Lucide; `<link>`s to `panel.css`, `feedback.css`.
- CSS reflects mode via `body[data-mode="…"]` (T2 sets it).

**New JS modules (created as behavior-preserving STUBS by T2 in Phase 1; OWNED by feature
agents in Phase 2):** `static/panel.js`, `static/feedback.js`, `static/shortcuts.js`.
Each exports an init fn called by `app.js` with an injected `api`:
- `initPanel(api)` — analysis-panel render (eval/quality/best/pv/eval-bar).
- `initFeedback(api)` — toasts + loading + empty states.
- `initShortcuts(api)` — keyboard handlers.

**Injected `api` (built by T2 in app.js):**
- `api.actions` = `{ undo, redo, flip, reset, stepBack, stepForward, getState, getGround,
  closeAnyDialog }`.
- tiny bus: `api.on(evt, fn)` / internal `emit`, events: `analysis:start`, `analysis:end`,
  `mode:change`(mode), `toast:show`(message, kind?). **No `analysis:result` event** — see below.
- `api.mounts` = resolved DOM nodes (evalBar, toasts, analysisStatus, tab panels).
- **Analysis render is a DIRECT call, not a bus event** (refuter blocker 1): `panel.js` exports
  `renderAnalysisPanel(analysis, opts)` and `renderBookMovePanel(data)`; `app.js` calls these
  at the existing call sites, **passing `opts` through unchanged** (trap-practice relies on
  `opts.suppressQuality`, app.js:1283/1291; the book path stays intact). The eval bar is
  driven inside `renderAnalysisPanel` (T3 owns it). The bus carries only start/end (for the
  loading indicator), mode, and toasts.
- **init order:** `initPanel/initFeedback/initShortcuts(api)` are called from `init()` **after
  the Chessground constructor (app.js:1683)** → `api.getGround()` is safe at init time.

This removes the hotspots: **`app.js` is edited ONLY in Phase 1 (T2) and Phase 3 (me).**
Phase-2 features are additive into their own module + own CSS file.

## Refuter resolutions (binding — fold into the named ticket)
1. **(blocker) Analysis render = direct call w/ opts** — resolved above. T2 keeps the call
   sites in app.js calling `panel.renderAnalysisPanel(a, opts)` / `renderBookMovePanel(data)`;
   T3 implements those honouring `opts.suppressQuality` + the book path.
2. **(blocker) Promotion Esc-cancel contract** — `<dialog id="promo-dialog">` (T1 markup).
   `askPromotion` returns a Promise; piece click → `resolve(piece)` + `dialog.close()`;
   **Esc / cancel → reject (or resolve null) → caller cancels the pending move and calls
   `syncBoard()`** to restore the board. T2's promo Playwright check is **gated to the Phase-1
   integration step** (needs T1's dialog merged) — not a T2-standalone test.
3. **(major) ID preservation** — T1 MUST keep these IDs unchanged when moving content into
   tabs (every one is `byId()`-bound in app.js): `#eval #quality #best-move #pv #opening-name
   #repertoire-section #repertoire-tree #traps-section #traps-list #traps-name-filter
   #traps-color-filter #trap-chip #trap-chip-text #trap-chip-drill #trap-chip-dismiss
   #status`. The existing `#status` survives as-is **alongside** the new `#analysis-status`
   mount (different consumers).
4. **(major) Tab-switch must not worsen the live bug** — T1's `body[data-mode]` CSS **hides the
   tab bar** (and the play-only Analysis content) in `setup/trap-watch/trap-practice/rep`
   modes; T2's tab-switch handlers no-op when `body.dataset.mode !== 'play'`. Full per-mode
   scoping is finished in T6.
5. **(major) Eval-bar DOM** — T1 wraps `#board` + `#eval-bar` in
   `<div class="board-wrap">` (`display:flex; flex-direction:row; align-items:stretch`); T3
   styles `#eval-bar` (~`width:12px; align-self:stretch`) in `panel.css`.
6. **(major) Toast trigger** — bus event `toast:show(message, kind?)`; T2 emits it from
   `loadFen()` on success; T4's `initFeedback` subscribes and renders. No one reaches into
   app.js for toasts.
7. **(major) Grid columns (no dead space)** — app-shell content row:
   `grid-template-columns: auto minmax(280px, 1fr)` (right column fills remaining width;
   drop the old `.panel max-width:420px` cap). Makes "no dead space at 1440px" verifiable.
8. **(minor) Esc vs native dialog** — T5's Esc handler: if `document.querySelector('dialog[open]')`
   exists, **let the dialog's native cancel handle it** (don't also call `closeAnyDialog`).
9. **(minor) Empty state already exists** — `renderTraps` already emits `.traps-empty`
   (app.js:670-677). T2 just aligns the class convention to `.empty-state` (and adds the same
   to `renderRepertoireTree` if missing); **T4 only styles it** — does not introduce behaviour.

## Constraints (chess-app)
- **No backend change.** `app/analysis.py` stays pure; no `app/models.py` edits; wire-format
  field names frozen (`evalCp, mate, quality, bestMoveSan, bestMoveUci, pvSan, book,
  openingName`).
- **Invariants preserved** (see `contracts/ux-modernization.md`): stateless requests; EPD
  server-side only (client sends `{baseFen,moves}`, never an EPD); `restore()` persisted
  shape + key `chess-training:session:v1` unchanged; the `movable.events.after` trampoline
  stays one closure reading `state.mode` at call time.
- CSS: this repo is **not** tokens-only, but the rework should expand `:root` tokens and
  promote the few raw-hex literals (`#222`, `#1f3a5f`, `#10243f`, scrim).
- chessground board moves in tests need **trusted** mouse (Playwright `page.mouse`).
- No debug artifacts committed (`.playwright-mcp/`, screenshots, `console.log`).

## Verify-by (end-to-end)
1. `pytest` stays green (no backend change → 152 tests still pass).
2. Playwright browser pass: app loads; play a move (drag, trusted mouse) → eval bar + eval +
   quality(+icon) + reformatted PV update; undo/redo via keyboard; flip via `F`; tabs switch;
   enter a trap (watch+practice) and a repertoire practice → panel is **scoped** (no
   contradictory eval) → return to game restores; promotion `<dialog>` opens, traps focus,
   Esc closes; toast fires on FEN load; empty state shows on a no-match trap filter.
3. **Zero console errors**; layout balanced at 1440px (no dead space) and usable at 390px.
4. `prefers-reduced-motion` disables transitions; text contrast ≥ 4.5:1.
5. Independent review (maker ≠ checker) clean before commit.
