# Contracts — Blunders-only: hide best move + PV

Area: Analysis panel render filter (play / bot-play paths).

## Invisible contracts touched

1. **`analysisOpts(a)` is the ONLY place the blunders-only filter is decided**
   (`static/app.js:923-928`). Computed at render time from the *current* `analysisMode`,
   never a flag stored on the analysis object. Returns `{}` (show everything) for
   `full`/`off`, for blunders, and for `checkmate`/`draw` quality (game-enders stay
   visible). Otherwise returns the suppress flags. → Add `suppressBest` here, same gate.

2. **`renderAnalysisPanel(a, opts)` is shared** (`static/panel.js:282`) by three callers:
   - play/bot-play via `renderAnalysis` → passes `analysisOpts(a)` (filter applies)
   - review replay via `hub.renderAnalysis` → passes `{}` (NO filter)
   - trap practice → passes `{suppressQuality, suppressRetro}` only
   New `suppressBest` must default falsy so review + trap are unaffected. Only the
   play-path (`analysisOpts`) sets it. Mirrors how `suppressQuality`/`suppressRetro`
   already work.

3. **Best move + PV DOM** (`static/panel.js:309-333`): `#best-move` gets
   `a.bestMoveSan || '—'`; `#pv` gets tokenized PV or `'—'`. Suppress = force both to
   `'—'` (the existing empty-state), not hide the rows — keeps layout stable, matches
   the `'—'` convention already used for quality/eval empty states.

4. **Toggle re-render** (`static/app.js:1546-1565`): flipping Full↔Blunders in
   play/bot-play bumps `analysisToken` and calls `refreshAnalysis()`, which re-renders
   through `analysisOpts`. So the panel catches up on toggle with no extra wiring —
   the fix in `analysisOpts` covers both "new move" and "toggle" cases.

5. **Eval bar + eval number stay** (`panel.js:283-288`) — chosen scope. `suppressBest`
   must NOT touch `setEvalBar`/`#eval`.

## Integration points / non-regression

- `renderBookMovePanel` / `renderSkippedPanel` are separate functions — book moves have
  no best/PV, skipped already gates retro carry-over (`app.js:951`). No change needed.
- `checkmate`/`draw` early-return in `analysisOpts` (line 926) preserved → game-ending
  moves still show best line.
