# Contracts — Repertoire Trainer (tree + jump + practice)

Read-only map of the existing contracts this feature must not break, gathered for
the inception of `repertoire-trainer`. Sources: `app/main.py`, `app/models.py`,
`app/traps.py`, `app/openings.py`, `app/book.py`, `static/app.js`, `static/index.html`.

## Invisible contracts (must hold)

1. **Stateless per request.** The server never holds game state; the client owns
   `{baseFen, moves[], cursor}` (`static/app.js:42`). "Jump to a position" is purely a
   client state change — set those three fields. No new server session.
2. **Position identity is server-side only.** EPDs are produced exclusively by
   `chess.Board(...).epd()` in `openings.py` / `traps.py` / `book.py`; the client never
   computes or sends EPDs (it sends `baseFen` + UCI `moves`, server derives identity).
   → A repertoire **move tree** that the client walks by *move sequence* (not by EPD)
   stays inside this contract: it replays legal UCIs, it never computes identity.
3. **`Analysis` is the single shared shape** returned identically by `/api/move`,
   `/api/analyze`, `/api/load` (`models.py` docstring). Adding an **optional** field
   (default `None`) is backward-safe; making an existing field nullable is not.
4. **Data modules degrade gracefully.** `openings`/`traps`/`book` each load at lifespan
   start, reset to empty on any error, and never raise into startup (`traps.load`
   resets-then-populates; `book.init` is wrapped in try/except in `main.py:75`). A new
   data module must follow the same import-safe, reset-first, never-raise pattern.
5. **Engine is optional + serialized.** One Stockfish process behind an `asyncio.Lock`;
   import-safe when absent (`EngineUnavailable`). Engine routes return 503 when it's
   missing; non-engine routes still work. Any new engine use must tolerate absence.
6. **Frontend FSM.** `state.mode ∈ {'play','setup','trap-watch','trap-practice'}`
   (`app.js:43`). Each non-play mode: snapshots the play game, swaps a body CSS class +
   a dedicated bar, and is **transient — never persisted** (`persist()` early-returns for
   setup/trap modes, `app.js:72`). Input is gated by mode at the top of `onUserMove`
   (`app.js:251`). A new `'rep-practice'` mode must follow this exact shape.
7. **`/api/move` book fast-path is opt-in.** `useBook` defaults false; only play-mode
   callers set it. Book = a set of repertoire EPDs built at startup from lichess lines
   (scoped by `book.json`) + `traps.iter_mainline_ucis()` (`main.py:75`). New repertoire
   lines should fold into that set so a jumped position shows the "Book Move" badge.
8. **Route ordering.** Literal API paths must be registered before parameterized ones
   (`/api/traps/check` before `/api/traps/{trap_id}`, `main.py:267`). The static mount is
   last so `/api/*` wins (`main.py:308`). A new `/api/repertoire` is a fixed path — safe.
9. **CSS = existing tokens / component classes.** Bars (`#setup-bar`, `#trap-bar`) and
   panel sections (`#traps-section`) are the established patterns to mirror; reuse them.

## Integration points

- **Lifespan** (`main.py:58`): add `repertoire.init(...)` after `openings.init` /
  `traps.init`; fold `repertoire.iter_lines()` into the `book.init(...)` extra lines
  (alongside `traps.iter_mainline_ucis()`). Keep it inside the existing guard so a
  malformed line can never crash startup.
- **`_build_analysis`** (`main.py:101`): the engine PV is already UCI-native
  (`result.pv: list[chess.Move]`); SAN is derived for the response. Exposing the best
  move in UCI (for the practice engine auto-opponent) is a one-line addition here.
- **Trap-practice machinery** (`app.js` ~`:786`–`:880`): `enterTrap` snapshots the play
  game; `applyTrapModeUI` toggles body classes + controls; the drill auto-plays scripted
  victim moves and offers take-back / reveal / show-refutation (`#trap-reveal`,
  `index.html:107`). This is the template for the repertoire practice loop (auto-opponent
  + deviation take-back/reveal).
- **Jump primitive**: `loadFen()` (`app.js:422`) already sets `baseFen`/`moves`/`cursor`
  and re-renders. A full-history jump is the same assignment with `baseFen=START`,
  `moves=<line UCIs>`, `cursor=moves.length`, then `syncBoard()` + `refreshAnalysis()`.
- **Opening name on jump**: `/api/opening` (`identify(baseFen, moves)`) and the book
  badge both work off `baseFen`+`moves`, so a full-history jump auto-names the opening
  with no extra work.

## Hotspots (flag at "go")

- `static/app.js` (1391 lines) — single owner; this feature adds the most code here
  (tree render + jump + the practice FSM). Largest review surface.
- `app/main.py` — lifespan + routes; touched by every feature. Keep the change additive.

## Risks this feature introduces (for the refuter to probe)

- **Engine auto-opponent is genuinely new**: today nothing auto-plays a move for the
  opponent; the user moves both sides. The practice end-of-prep handoff requires the app
  to play the engine's move — new control flow + a UCI best-move on `Analysis`.
- **"Your-turn single prepared move" invariant** across independently-authored lines —
  two lines could disagree on your move at a shared position (authoring conflict).
- **Move-order-specific tree** — no transposition merging; reaching a prepared position
  by a different order won't be recognized in practice (accepted, out of scope).
