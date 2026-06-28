# Tickets — Opening Book Fast-Path

Spec: `docs/ai-dlc/specs/opening-book-fastpath.md`. Slug: `opening-book-fastpath`.
≤8 tickets. "Owned files" = the only files that ticket may edit (one file = one owner).

---

### TB1 — Repertoire config  ·  owns `data/book.json`
A small config (not a move list): `{ "firstMoves": ["e2e4","d2d4"], "includeTraps":
true, "extraLines": [] }`. Decision: book = lichess lines starting 1.e4 or 1.d4
(≈3,245 lines) + traps. `extraLines` empty for now.
**Done:** `data/book.json` is valid JSON with those three keys.
**Dep:** none.

### TB2 — `app/book.py` loader + lookup  ·  owns `app/book.py`
Build `book_epds: set[str]` from the config: filter injected `lines` (all lichess UCI
move-lists) by `firstMoves`, replay each + `trap_ucis` (+ any `extraLines`) collecting
every reached EPD. Expose `load(config_path, lines, trap_ucis)`, `init`,
`is_book_move(fen, uci)` (push move → `board.epd() in book_epds`), `BookIndex.empty`.
Import-safe; graceful when data absent. No engine/network import.
**Done:** `python -c "import app.book"` ok; with real data, `is_book_move` true for an
Italian/Najdorf/KID continuation + a trap continuation, false for `1.a4`; empty ⇒ false.
**Dep:** TB1 (config), TB3b (lines), TB3 (trap lines).

### TB3b — Openings line accessor  ·  owns `app/openings.py`
Add `iter_lines() -> list[list[str]]` returning each parsed lichess line's UCI
move-list; `load()` retains these on the index (small `lines` field). Read-only; no
change to `identify()` / name detection.
**Done:** returns ≈3,733 UCI lists against real data; existing openings tests pass.
**Dep:** none. **Parallel with** TB1, TB3, TB4, TB7.

### TB3 — Trap mainline accessor  ·  owns `app/traps.py`
Add `iter_mainline_ucis() -> list[list[str]]` returning each variation's mainline as
a **full UCI line from the standard start** (so `book` folds in trap lines without
re-parsing `traps.json`). **Must prepend `leadInSan`-as-UCI** to each variation's
mainline UCIs — a trap's `mainLine[0]` (e.g. `b8c6`) is illegal from `chess.Board()`
without the lead-in (`e4 e5 Nf3`). **Must be exception-safe**: skip malformed
variations, never raise, return `[]` on total failure (it runs in the lifespan).
**Done:** for `ruy-lopez-trap`, output starts `["e2e4","e7e5","g1f3","b8c6",...]` and
replays legally from the start position; a deliberately broken variation is skipped,
not raised.
**Dep:** none. **Parallel with** TB2, TB4, TB7.

### TB4 — Model fields  ·  owns `app/models.py`
`MoveRequest.useBook: bool = False`; `MoveResponse.book: bool = False`. `Analysis`
unchanged.
**Done:** models import; defaults false; existing `/api/move` tests still pass.
**Dep:** none. **Parallel with** TB2, TB3, TB7.

### TB5 — API wiring  ·  owns `app/main.py`
Lifespan: `book.init(BOOK_FILE, lines=openings.iter_lines(), trap_ucis=traps.iter_mainline_ucis())`
after `openings.init` + `traps.init`, **wrapped so any failure logs a warning and leaves an empty index**
(TestClient runs the real lifespan — a crash here would down the whole suite).
`/api/move`: when `useBook` + legal + `book.is_book_move` ⇒ return
`{legal:true, fen:after, lastMoveSan, analysis:null, book:true}` **without** an engine
call; else unchanged.
**Done:** book move skips engine (fake-engine-raises test); off-book unchanged;
startup survives a malformed trap/book line.
**Dep:** TB2, TB3, TB4.

### TB6 — Frontend book rendering  ·  owns `static/app.js`
`onUserMove` + `refreshAnalysis` (cursor>0 branch) send `useBook:true` and route the
response through a shared renderer: `data.book` ⇒ "Book Move" badge + clear
eval/best/PV; else `renderAnalysis`. `cursor===0` / `/api/analyze` / trap-practice
calls unchanged.
**Done:** booked line shows instant badges; deviation restores eval; undo back into
book restores badge (browser-verified).
**Dep:** TB4 (shape), TB5 (live behavior).

### TB7 — Book badge styling  ·  owns `static/style.css`
`.q-book` badge — calm/accent color, distinct from the five quality colors.
**Done:** badge legible in the quality slot; tokens-only; AA contrast.
**Dep:** none (parallel); visually confirmed alongside TB6.

### TB8 — Tests (maker ≠ checker)  ·  owns `tests/test_book.py`, `tests/test_book_api.py`, `tests/test_book_data.py`, **edits `tests/test_api.py`**
Unit (index/lookup/transposition/empty), API (engine-skipped via fake engine;
off-book + `useBook:false` paths; **install a fixture index via `book.load(<fixture>)`
or monkeypatch `app.main.book` and reset after** — `is_book_move` is a module call, not
DI, and TestClient loads the real data), data (every `book.json` line + a known trap
continuation replay/are recognized). Also **update `tests/test_api.py::test_move_illegal`**
to expect `"book": False` in the exact-dict assertion (the only required existing-test
edit). Written by an agent **other** than TB2/TB5's author.
**Done:** `pytest` green; the fake-engine API test fails if the engine is called on a
fixture book move; a trap continuation (e.g. after `e4 e5 Nf3` → `b8c6`) is recognized.
**Dep:** TB2, TB5 (overlaps TB6).

---

## Parallelization

- **Phase 1 (parallel):** TB1 ‖ TB3 ‖ TB4 ‖ TB7 — disjoint files.
- **Phase 2:** TB2 (after TB1 format).
- **Phase 3:** TB5 (after TB2, TB3, TB4) — hotspot `app/main.py`.
- **Phase 4:** TB6 (after TB5) — hotspot `static/app.js`.
- **Phase 5:** TB8 (after TB5; overlaps TB6).

Most of the chain is sequential through `main.py → app.js` (same as prior features).
Real parallelism is Phase 1 only.

## Suggested model assignment (lock at "go")

- **Opus** — TB2 (EPD/index correctness), TB5 (engine-skip wiring), TB8 (verification).
- **Sonnet** — TB1 (data, then user-verified), TB3, TB4, TB6, TB7 (pattern-following).
