# Spec — Opening Book Fast-Path

**Goal (one line):** When a move follows a curated opening book, return an instant
"Book Move" result with **no Stockfish call**; the moment a move leaves book, fall
back to today's full analysis.

Status: inception (plan gate). No feature code until approved.

---

## Why

`POST /api/move` runs **two** depth-18 Stockfish analyses per move (before + after)
to label move quality. In the opening the user always plays a fixed, pre-agreed
repertoire, so that engine work is wasted and makes opening play feel slow. A book
lookup is a ~1 ms dictionary hit; we use it to skip the engine while in book.

---

## Decisions (locked via interview 2026-06-27)

1. **Book source** = the **common variations of the user's repertoire openings,
   derived from the already-downloaded lichess DB** in `data/openings/` (no new
   download) **UNION** all trap mainlines. Scope = every lichess line whose first move
   is **1.e4** (White repertoire + all Black defenses to e4, incl. the whole Sicilian)
   or **1.d4** (Black's Indian + White's d4 systems incl. the London). `data/book.json`
   is a small **repertoire config** — which first moves count, a traps toggle, optional
   `extraLines` — **not** a hand-typed move list (hand-authoring opening theory from
   memory is how wrong lines creep in; the DB is authoritative). Flank first moves
   (1.c4 / 1.Nf3 / …) are left off-book for now (one-line config change to add).
   **UX trade the user accepted:** with all common variations in book, a *theoretical*
   move that isn't the user's usual choice still shows "Book Move" rather than a quality
   label. Narrowing to hand-picked lines is possible later via `book.json`.
2. **In-book display** = a **"Book Move"** badge only. No eval number, no best move,
   no PV while in book (nothing ran).
3. **Transition** = **stateless, per-position**. Each move is judged on its own
   position via EPD; undo back into the opening re-enters fast mode; a transposition
   into a known line is treated as book. No per-game latch / no server session state.
4. **Scope** = the play-mode move path only. `/api/load` (FEN paste) and the trap
   watch/practice modes keep today's exact behavior.

---

## Mechanism

At startup build a **set of known repertoire positions** `book_epds: set[str]` —
the EPD of every position reached along an in-scope lichess line (first move ∈ config)
and along every trap mainline (lead-in + mainline). EPDs use the same
`chess.Board(...).epd()` convention as `openings.py` / `traps.py`; **computed
server-side only — the client never sends or computes them**. A set (not an
edge map) is enough and is naturally transposition-safe: we ask whether the position
a move *reaches* is known theory.

Per move, **before** any engine call (move already legality-checked):
push the move on `chess.Board(fen)` → is the resulting `board.epd()` in `book_epds`?
- **yes** → return instantly `{legal: true, fen: after, lastMoveSan, analysis: null, book: true}`. No engine call.
- **no** → existing path (two analyses, real quality, eval, PV); `book: false`.

(Reaching a known position by a non-mainline move order is therefore treated as book —
intended: it's still a known theoretical position. A line's deepest named position is
the natural depth limit; the next move falls through to Stockfish.)

The server is stateless and cannot tell *play* from *trap-practice* (both call
`/api/move`). So the fast path is **opt-in per request**: `MoveRequest.useBook`
(default **false**). Only the play-mode callers set it true; every other caller
(trap-practice lazy eval, future callers) is unaffected by default.

---

## Files / interfaces to touch

- **NEW `app/book.py`** — module singleton mirroring `openings.py`:
  - `load(config_path=None, lines=(), trap_ucis=()) -> BookIndex` — read `book.json`
    config (`firstMoves`, `includeTraps`, `extraLines`); from `lines` (all lichess
    UCI move-lists, supplied by the caller) keep those whose first UCI ∈ `firstMoves`;
    replay each + the trap lines + any `extraLines` to collect every reached EPD into
    `book_epds: set[str]`. Import-safe + graceful (missing config ⇒ empty set ⇒ never
    marks book).
  - `init(config_path=None, lines=(), trap_ucis=())` — startup wrapper.
  - `is_book_move(fen: str, uci: str) -> bool` — pure: push `uci` on `chess.Board(fen)`,
    return `board.epd() in book_epds`; `False` on bad FEN / illegal move / empty set.
  - `BookIndex.empty` property.
  - **No engine import. No network.**
- **NEW `data/book.json`** — small **repertoire config** (not a move list):
  `{ "firstMoves": ["e2e4","d2d4"], "includeTraps": true, "extraLines": [] }`.
  `extraLines` (optional) = hand-added lines as `{ "name", "moves": "<SAN/UCI>" }` for
  anything not in the DB; empty for now. Editing `firstMoves` broadens/narrows scope.
- **`app/openings.py`** — add `iter_lines() -> list[list[str]]`: the UCI move-list of
  every parsed lichess line, so `book` can build its set without re-parsing the TSVs
  (openings owns TSV parsing — one file = one owner). `load()` retains these lists on
  the index (a small `lines` field); read-only accessor, no behavior change to
  `identify()`/name detection.
- **`app/traps.py`** — add `iter_mainline_ucis() -> list[list[str]]`: each variation's
  mainline as a **full UCI line from the standard start**, so `book` can fold trap
  lines in without re-parsing `traps.json` (one file = one owner: traps owns its data).
  **CRITICAL:** a trap's `mainLine` begins *after* its `leadInSan` prefix (e.g.
  `ruy-lopez-trap` has `leadInSan=["e4","e5","Nf3"]` and `mainLine[0].uci="b8c6"`).
  Replaying `b8c6` from `chess.Board()` raises `IllegalMoveError`. So
  `iter_mainline_ucis()` MUST convert `leadInSan` → UCI and **prepend** it to each
  variation's mainline UCIs (→ `["e2e4","e7e5","g1f3","b8c6",...]`). It must also be
  **exception-safe**: skip any malformed variation and never raise (return `[]` on
  total failure) so it cannot crash startup (see lifespan below).
- **`app/models.py`**:
  - `MoveRequest`: add `useBook: bool = False`.
  - `MoveResponse`: add `book: bool = False`. When `book` is true, `analysis` is
    `None` and `lastMoveSan` / `fen` are set as usual. (`Analysis` is left unchanged —
    no eval fields go nullable.)
  - **Known test impact:** `tests/test_api.py::test_move_illegal` asserts the response
    body equals the exact 4-key dict `{legal, fen, lastMoveSan, analysis}`. Adding
    `book` makes it a 5-key body, so that assertion must be updated to include
    `"book": False` (owned by TB8, not TB4).
- **`app/main.py`**:
  - Lifespan: `book.init(str(BOOK_FILE), lines=openings.iter_lines(), trap_ucis=traps.iter_mainline_ucis())`
    **after** `openings.init(...)` and `traps.init(...)` (book needs both loaded first). The lifespan
    currently leaves `openings.init` / `traps.init` un-try/except'd; this call adds a
    nested `traps.iter_mainline_ucis()` whose failure would crash startup — and the
    API tests run the **real lifespan** via `TestClient`, so a crash takes the *whole*
    suite down. Guard it: `iter_mainline_ucis()` is exception-safe (above) **and** the
    `book.init(...)` call is wrapped so any failure logs a warning and leaves an empty
    index (degrade, never crash).
  - `/api/move`: if `req.useBook` and `book.is_book_move(req.fen, req.move)` **and the
    move is legal**, return the book response without calling the engine. Otherwise
    today's path unchanged. (Legality is still checked first so an illegal "book" move
    can't slip through.)
- **`static/app.js`**:
  - `onUserMove` (`:268`) and `refreshAnalysis`'s `cursor>0` branch (`:234`) — the two
    play-mode `/api/move` callers — send `useBook: true` and route the response through
    a shared renderer that checks `data.book` **FIRST**: `data.book` → "Book Move" badge
    (clear eval/best/PV); else `renderAnalysis(data.analysis)` as today. **Regression
    risk:** `refreshAnalysis`'s existing `renderAnalysis(data.legal ? data.analysis : null)`
    ternary would render a blank `—` on undo-into-book unless the `data.book` branch is
    taken before it. (undo/redo/reset/persist-reload all funnel through `refreshAnalysis`,
    so this one fix covers all navigation.)
  - `refreshAnalysis`'s `cursor===0` branch (`/api/analyze` on `baseFen`) unchanged.
  - Trap-practice's `/api/move` call (`:1251`) and all `/api/analyze` calls unchanged
    (no `useBook`).
- **`static/style.css`** — a `.q-book` badge style (calm/accent, distinct from the
  five quality colors).

---

## Out of scope

- Authoring the *entire* repertoire in one go — book content is data and can grow;
  TB1 seeds an initial set with the user.
- Showing book evals, PV, or "next book move" hints while in book.
- Any client-side EPD computation (stays server-side).
- Changes to `/api/load`, `/api/analyze`, trap watch/practice behavior, engine config,
  or search depth.
- A per-game "latch" or any server-side session state.

---

## Constraints

- **Stateless per request** — book check is a pure position+move lookup; no session.
- **EPD server-side only** — client never computes/sends EPDs (matches openings/traps).
- **Engine untouched** — `engine.py` unchanged; the book path has **zero** engine
  dependency (so booked opening play works even if Stockfish is absent).
- **Graceful degrade** — missing/empty `data/book.json` and no trap lines ⇒ index
  empty ⇒ `useBook` requests simply behave like today (full analysis).
- **Backward-safe defaults** — `useBook` defaults false; `book` defaults false; every
  existing *caller* keeps its current runtime behavior. (One existing *test* must
  change: `test_move_illegal`'s exact-dict assertion gains `"book": False` — see TB8.)

---

## Verify-by (what `/verify-change` checks)

- **Unit `tests/test_book.py`** — index built from a fixture: `is_book_move` true for
  in-book continuations, false off-book; a transposition (different move order to the
  same EPD) is recognized; empty/missing file ⇒ all false.
- **API `tests/test_book_api.py`** — `book.is_book_move` is a **module-level** call in
  `/api/move` (not dependency-injected like the engine), and `TestClient` runs the real
  lifespan that loads the shipped `data/book.json`. So the test must install a known
  index itself: call `book.load(<fixture>)` (or monkeypatch `app.main.book`) before the
  request and reset after — mirroring how the traps tests call `traps.load(...)`. Then,
  with a fake engine that **raises if called**, `/api/move` with `useBook:true` on a
  fixture book move returns `{book:true, analysis:null}` and the engine is **never**
  invoked (the raise proves the skip *only because* the fixture actually contains the
  move). Off-book with `useBook:true` → normal analysis. `useBook:false` (default) →
  always full analysis (proves trap-practice stays correct).
- **Data `tests/test_book_data.py`** — `data/book.json` is valid config; any
  `extraLines` replay legally; a known repertoire continuation is recognized
  (e.g. Italian `e4 e5 Nf3 Nc6 Bc4`, a Najdorf position, a KID position, and a trap
  continuation like `e4 e5 Nf3 → b8c6` are all in `book_epds`); an offbeat move
  (e.g. `1.a4`) is **not** (no engine needed).
- **Browser/manual** — play a booked line → instant "Book Move" badges, no eval;
  deviate one move → eval + quality reappear; **undo** back into book → badge returns.
- Full suite stays green (the existing ~95 `def test_` functions, minus the one
  intentional `test_move_illegal` edit; use `pytest --collect-only -q` for the exact
  baseline rather than a guessed number).
