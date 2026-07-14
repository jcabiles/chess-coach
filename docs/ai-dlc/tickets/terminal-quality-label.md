# Tickets — terminal-quality-label

Small stack; implement in order. T1→T2 are backend (same author, T2 depends on
T1's type). T3/T4 are frontend and can go in parallel with each other after T2.
T5 verifies. Single-agent implementation recommended (tickets are tiny).

## T1 — Extend the `Quality` type
- **File (owner):** `app/models.py`
- **Do:** Add `"checkmate"` and `"draw"` to the `Quality` Literal. Add a one-line
  comment noting these are terminal-state labels set by the API, not `classify`
  cpLoss buckets.
- **Done:** `Quality` includes both members; `pytest -q` still green.

## T2 — Terminal-state branch in `/api/move`
- **File (owner):** `app/main.py`  *(hotspot — single owner)*
- **Depends on:** T1
- **Do:** After `board.push(move)` / `fen_after`, before the book fast-path and
  the `req.analyze` opt-out, add: if `board.is_game_over()`, set quality =
  `"checkmate" if board.is_checkmate() else "draw"` and return
  `MoveResponse(legal=True, fen=fen_after, lastMoveSan=..., analysis=<synthetic>)`.
  Build the `Analysis` directly (no engine): checkmate → decisive winner-signed
  White-POV eval (reuse `MATE_CP`/mate convention, `mate` set so the panel shows
  a decisive result, not "M0"); draw → `evalCp=0`, `evalWhitePov=0`;
  `bestMoveSan`/`bestMoveUci`/`pvSan`/retro all `None`.
- **Done:** `POST /api/move` with a mating move returns `legal=True`,
  `analysis.quality == "checkmate"`; with a stalemating move returns
  `"draw"`; **no engine call** on that path.

## T3 — Quality icons for the new labels
- **File (owner):** `static/panel.js`
- **Depends on:** T1 (label names)
- **Do:** Add `checkmate` (flag/crown glyph, `var(--q-best)`) and `draw`
  (equals/handshake glyph, `var(--q-book)`) to `QUALITY_ICONS`. No label-text map
  change (text comes from `a.quality`).
- **Done:** Rendering an analysis with `quality:"checkmate"` shows the green
  crowned badge; `quality:"draw"` shows the neutral badge; no console error.

## T4 — Color classes for the new labels
- **File (owner):** `static/style.css`
- **Do:** Add `.q-checkmate { color: var(--q-best); }` and
  `.q-draw { color: var(--q-book); }` beside the existing `.q-*` rules (~line 685).
- **Done:** Grep shows both rules; badge text picks up the color via
  `q-${quality}` class.

## T5 — Tests + verify
- **File (owner):** `tests/test_api.py`
- **Depends on:** T2
- **Do:** Add a checkmate-move case (mate-in-1 FEN → play the mate → assert
  `quality == "checkmate"`, `legal == True`, `analysis` not `None`) and a
  stalemate case (→ `"draw"`). Both must pass with **no Stockfish binary**.
- **Done-condition:** `.venv/bin/python -m pytest -q` green;
  `.venv/bin/ruff check app tests` clean.
