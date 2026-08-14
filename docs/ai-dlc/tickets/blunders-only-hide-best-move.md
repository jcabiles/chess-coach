# Tickets — Blunders-only: hide best move + PV

Single-owner files flagged (hotspots). T1→T2 sequential (T2 sets the flag T1 consumes);
T3 verifies. Small enough for one agent, one commit.

## T1 — panel.js: honor `opts.suppressBest`
- **Owns:** `static/panel.js` (hotspot — single owner)
- **Do:** In `renderAnalysisPanel`, when `opts.suppressBest` is truthy, set `#best-move`
  and `#pv` textContent to `'—'` instead of the bestMoveSan / tokenized-PV paint. Leave
  eval bar, eval number, quality, and the retro/second block logic untouched.
- **Acceptance:** Calling `renderAnalysisPanel(a, {suppressBest:true})` with a real
  analysis object shows `'—'` for best move + PV but a real eval; `{}` shows them normally.
- **Done-condition:** `.venv/bin/python -m pytest -q` green (no regressions).

## T2 — app.js: set `suppressBest` in `analysisOpts`
- **Owns:** `static/app.js` (hotspot — single owner)
- **Do:** In `analysisOpts(a)`, the non-blunder blunders-mode return
  (`{ suppressQuality:true, suppressRetro:true }`) gains `suppressBest: true`. Do not
  touch the `checkmate`/`draw`/`{}` branches.
- **Acceptance:** In blunders mode, non-blunder → opts include `suppressBest:true`;
  blunder/checkmate/draw → `{}`; full/off → `{}`.
- **Done-condition:** `.venv/bin/python -m pytest -q` green.
- **Depends on:** T1.

## T3 — Verify end-to-end (Playwright-MCP)
- **Owns:** no source files (manual/browser check).
- **Do:** Run the Spec "Verify-by" steps 2–3 on a live server: non-blunder in Blunders-only
  hides best move + PV (eval stays); blunder shows them; Full re-shows; review replay
  unaffected.
- **Done-condition:** All four assertions observed in-browser; no console errors.
- **Depends on:** T2.
