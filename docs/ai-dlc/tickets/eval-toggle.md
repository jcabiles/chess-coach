# Tickets — Evaluation on/off toggle

Spec: `docs/ai-dlc/specs/eval-toggle.md`. Contracts: `docs/ai-dlc/contracts/eval-toggle.md`.

**Shared contract (all tickets agree):**
- Button id `#eval-toggle`, `type="button"`, canonical mapping **`aria-pressed="true"` = eval ON**
  (matches `evalEnabled` default `true`). Label reflects state ("Evaluation: On" / "Evaluation: Off").
- `evalEnabled` is a **session-only** `app.js` module var (default `true`) — NOT persisted, NOT in
  `chess-training:ui:v1`. Independent of `analyzeColor`.
- **Freeze, not blank:** eval-off never calls `renderSkipped()`; it skips render so the panel's
  last DOM stays. Only the analyze-color skip (enabled, wrong color) still calls `renderSkipped()`.
- **Toggle-off must `analysisToken++`** to drop any in-flight `refreshAnalysis` response.
- No backend / models / `/api/move` / DB / schema change — frontend-only.

**Orchestration:** T1 (markup/CSS) and T2 (app.js logic) touch disjoint files but T2's wiring
targets `#eval-toggle`, so implement T1 first (or together), then T2. Single agent is fine — only
one hotspot (`app.js`). T3 verify last. `app.js` is a single-owner hotspot: one owner (T2).

| # | Ticket | Owned files | Done-condition | Deps |
|---|--------|-------------|----------------|------|
| T1 | Add `<button id="eval-toggle" type="button" aria-pressed="true">Evaluation: On</button>` in `#tab-analysis` near `.analyze-color-row`; style it tokens-only: `[aria-pressed="true"]` active vs `[aria-pressed="false"]` muted/paused, `:focus-visible` ring, AA contrast both states. No JS. | `static/index.html`, `static/style.css` | Button renders in Analysis tab; no new raw hex; focus ring visible. | — |
| T2 | `app.js` logic: add `let evalEnabled = true`; prepend `if (!evalEnabled) return false;` to `shouldAnalyzeMove` + `shouldAnalyzeCursor`; `refreshAnalysis` freeze branch (`!evalEnabled` → `setStatus(''); emit('analysis:end'); return;`, **no** `renderSkipped()`, after the coalesce guard); `onUserMove` — gate `setStatus('Analyzing…')` on `evalEnabled`, and render branch `else if (evalEnabled) renderSkipped()`; wire `#eval-toggle` click → flip `evalEnabled`, update label + `aria-pressed`, **on-enable** `refreshAnalysis()`, **on-disable** `analysisToken++`. | `static/app.js` | `evalEnabled=true` = today byte-for-byte; off → 0 engine calls on play + nav, panel frozen (not "—"), no "Analyzing…" flash; toggle-off mid-flight doesn't render stale; re-enable analyzes current pos; color filter still works. | T1 |
| T3 | Verify end-to-end: browser (Playwright-MCP on live server) walks spec Verify-by 1–7 incl. the mid-flight race (#4) and reload-resets-on (#6); run `pytest -q` + `ruff check` (expect unchanged green — no backend touched). | — | See spec Verify-by; 0 console errors. | T1, T2 |

## Notes
- No new automated test: the change is pure frontend with no JS test harness in-repo; `pytest`/`ruff`
  are run only to confirm no regression (they cover no new surface here). Verification is browser-led.
- Watch the live-reload hazard ([[live-reload-branch-hazard]]): the user may have `uvicorn --reload`
  running — coordinate branch/checkout so their server isn't yanked onto an unpushed branch.

## Result — shipped
Branch `feat/eval-toggle`, stacked on `fix/analysis-render-race` (PR #44) for its `analysisToken++`
machinery. `pytest` 719 passed (no backend touched); ruff not installed locally but 0 `.py` files
changed. Browser-verified (Playwright-MCP, live server) against Verify-by 1–7:
- Default On (aria-pressed=true), moves evaluate, start eval renders. ✓
- Off → `/api/move {analyze:false}`, panel FROZEN at last eval (+1.50, not blanked), no "Analyzing…"
  flash, button "Evaluation: Off" aria-pressed=false. ✓
- Nav while off → 0 `/api/analyze`, frozen. ✓
- **Race (#4):** toggle off mid-navigation → the in-flight response (prior position's +1.50) was
  DROPPED, panel did not repaint — `analysisToken++` on toggle-off works. ✓
- Toggle on → re-analyzes current position (new `/api/move` fires). ✓
- Reload while off → back to On; `chess-training:ui:v1` has no eval flag (session-only). ✓
- `:focus-visible` accent ring; 0 console errors. ✓

### Verification note — a suspected nav bug that turned out to be a FALSE ALARM
During verification I briefly suspected keyboard navigation dropped a valid eval to "—" on non-book
positions. I instrumented the base branch (temp logging of myToken/token/cursor/book in
`refreshAnalysis`) and DISPROVED it: every nav is a single refreshAnalysis and every response
renders (book plies correctly show "—"; rapid bursts coalesce to the final position). The confusion
came from a flaky a-pawn board-drag that kept landing on BOOK positions — which legitimately show no
eval. No bug on `fix/analysis-render-race`; nothing to fix there.
