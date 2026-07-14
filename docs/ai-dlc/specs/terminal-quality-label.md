# Delta spec — terminal-position quality label (checkmate / draw)

**Goal:** A move that ends the game gets a terminal-state quality label
(`checkmate` or `draw`) instead of being mis-classified — today a mating move
shows as a red **Blunder** by the winner.

## Root cause

In `/api/move` (`app/main.py`) the mover's move is pushed, then the *after*
position is analyzed and fed to `analysis.classify`. When the move ends the game
(`fen_after` is terminal / no legal reply), the engine's eval of that position is
degenerate; `classify` sees a huge cpLoss and buckets the winner's move as
`blunder`. The **review** path already avoids this (`app/review.py:473-474`
checks `is_checkmate()` first) — the bug is confined to the live `/api/move` path.

## Approach

Detect the game-over state in `/api/move` right after `board.push(move)` /
`fen_after`, **before** the book fast-path and the `req.analyze` opt-out, and
**before** touching the engine (a terminal position has nothing to analyze):

- `board.is_checkmate()` → quality `"checkmate"`
- any other `board.is_game_over()` (stalemate, insufficient material, 75-move,
  fivefold) → quality `"draw"`

Return a `MoveResponse(legal=True, fen=fen_after, lastMoveSan=..., analysis=...)`
whose `Analysis` is built **directly** (no engine call): a decisive
White-POV eval for checkmate (winner-signed, via the existing `MATE_CP` / mate
convention) or `0` for a draw; `bestMoveSan`/`pvSan`/retro = `None` (game over —
nothing to suggest). This makes the endpoint return correctly even with **no
Stockfish binary** for terminal moves.

## Display decisions (confirmed with user)

- **Checkmate** badge reuses the green **Best** color (`--q-best`) with its own
  label text "Checkmate" and a distinct icon (flag/crown).
- **Draw** badge is **neutral** — reuse the calm azure `--q-book` color, label
  "Draw", neutral icon (equals/handshake). No new color token added.
- Label text renders via `textContent = a.quality` (CSS capitalizes), so no
  text-mapping change is needed — only the icon map + a color class.

## Files / interfaces to touch

- `app/models.py` — extend `Quality` Literal with `"checkmate"`, `"draw"`
  (comment: terminal-state labels set by the API, **not** `classify` buckets).
- `app/main.py` — `/api/move`: game-over branch that emits the terminal label +
  synthetic `Analysis`, before book / analyze-opt-out / engine.
- `static/panel.js` — add `checkmate` + `draw` entries to `QUALITY_ICONS`.
- `static/style.css` — add `.q-checkmate { color: var(--q-best); }` and
  `.q-draw { color: var(--q-book); }` beside the existing `.q-*` rules (~line 685).
- `tests/test_api.py` — a mating-move case (→ `checkmate`) and a stalemate case
  (→ `draw`); both must pass **without** a Stockfish binary.

## Out of scope

- The **review** / profiler path (already correct) — no change.
- `analysis.classify` / `bucket` / `cp_loss` — untouched; terminal labels are set
  outside the cpLoss pipeline, never returned by `classify`.
- No new color token; no eval-bar / PV redesign; no persistence change
  (`state.moveQuality` stays transient).
- Opening/traps/repertoire trainers (do not surface these labels).

## Constraints (from profile)

- Pure modules stay engine-free; the new tests must pass with no Stockfish
  binary (guaranteed — terminal moves skip the engine).
- Reuse `pov_score_to_white_cp` / the `MATE_CP` mate convention; don't re-derive
  the White-POV sign rule.
- Warm-TT invariant untouched (we skip the engine on terminal moves; no `game=`).
- Frontend: tokens-only CSS (no raw hex), AA contrast, no import from `app.js`.

## Verify-by (end-to-end)

1. `.venv/bin/python -m pytest -q tests/test_api.py` — new checkmate → `"checkmate"`
   and stalemate → `"draw"` cases pass; full suite green with no engine.
2. `.venv/bin/ruff check app tests` clean.
3. Live UI (Playwright/manual): play a Scholar's-mate finish — the mating move's
   badge reads **"Checkmate"** in green, not a red "Blunder"; a stalemate finish
   reads a neutral **"Draw"**.

## Risk table (self-review — maker≠checker delegated only if requested)

- `Quality` Literal is not exhaustively matched anywhere that would break on new
  members (frontend `QUALITY_ICONS` is already a superset incl. `book`; insights/
  profile aggregate stored review leaks, which never carry these labels). ✅
- Terminal check placed before book + analyze-opt-out so an opponent's mating
  move is labeled even when the client skipped analysis (analyze-my-color). ✅
- `mate`-in-0 display: synthesize a decisive eval rather than emitting `M0`. ⚠️
  ticket T2 nails the exact eval encoding.
