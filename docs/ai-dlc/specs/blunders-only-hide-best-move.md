# Spec — Blunders-only: hide best move + PV for non-blunders

## Goal
In Analysis "Blunders only" mode, a move that is **not** a blunder must not reveal the
engine's best move or principal variation. Today `#best-move` + `#pv` still render.
Suppress both (show `'—'`); keep the eval bar + eval number visible. Blunders (and
checkmate/draw game-enders) continue to show everything.

## Behavior (blunders mode, non-blunder move)
| Element        | Before | After |
|----------------|--------|-------|
| Eval bar       | shown  | shown |
| Eval number    | shown  | shown |
| Quality label  | `—` (already) | `—` |
| Best move      | **shown** | **`—`** |
| PV             | **shown** | **`—`** |
| Retro block    | hidden (already) | hidden |

Blunder / checkmate / draw → unchanged (full panel). `full` and `off` modes → unchanged.
Review replay + trap practice → unchanged.

## Files / interfaces to touch
- `static/panel.js` — `renderAnalysisPanel`: honor a new `opts.suppressBest`; when set,
  force `#best-move` and `#pv` text to `'—'` (skip the normal bestMoveSan/PV paint).
  Must not affect eval bar/number, and must default falsy.
- `static/app.js` — `analysisOpts(a)`: for the non-blunder blunders-mode branch, add
  `suppressBest: true` to the returned flags (alongside `suppressQuality`,
  `suppressRetro`). No other branch changes.

## Out of scope
- Eval bar / eval number suppression (explicitly kept).
- Review-replay and trap-practice panels (they never pass `suppressBest`).
- `off` mode freeze behavior, movelist quality dots, book/skipped panels.
- Any server / Pydantic / engine change — frontend-only.

## Constraints (from profile)
- Frontend modules receive injected `api`; `panel.js` must not import from `app.js`.
  `suppressBest` is threaded as an opt, matching existing `suppressQuality`/`suppressRetro`
  — no new coupling.
- Tokens-only CSS, AA contrast, `:focus-visible` — N/A (no new markup/CSS; reuses `'—'`).
- No debug artifacts.

## Verify-by (end-to-end)
1. `.venv/bin/python -m pytest -q` — full suite green (pure/API unaffected; no engine).
2. Live server + Playwright-MCP (play mode):
   - Play a quiet non-blunder move → set mode to **Blunders only** → assert `#best-move`
     and `#pv` read `'—'`, while `#eval` + eval bar still show a value.
   - Play/reach a **blunder** in Blunders-only → assert `#best-move` + `#pv` populated.
   - Switch to **Full** → assert best move + PV reappear for the non-blunder.
3. Review-replay tab: open a game, step a move → best move + PV still shown (filter not
   inherited).
