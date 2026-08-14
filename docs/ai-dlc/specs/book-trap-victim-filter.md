# Spec — Stop the opening book from swallowing trap blunders

## Goal (one line)
In live play, moves that lose to a trap (the trap's **victim**-side moves) must fall
through to the engine and get a quality label, instead of being silently treated as
"book" theory.

## Problem (verified)
App startup seeds the opening book from trap mainlines
(`book.init(trap_ucis=traps.iter_mainline_ucis() + repertoire.iter_lines())`,
main.py:161-164). Trap mainlines are the *full* line including the victim's blunders
(e.g. Blackburne Shilling `4.Nxe5?? … 7.Be2` before `7…Nf3#`). Every position along
the mainline is added to the book, so `/api/move`'s book fast-path (main.py:497)
returns `book:true` with no engine call and **no quality label** for those blunders.
Reproduced: all 13 plies of the reported game → `book:true`; `7.Be2` (walks into
mate-in-1) returned `quality:null`. Systemic: **all 19 traps**, **60 victim-side
plies** seeded into the book.

## Approach (chosen: "drop victim moves from book") — BLOCKLIST SUBTRACTION
The victim's blunder positions must be un-booked **regardless of which source seeded
them**. A naive "skip victim plies in the trap seed" is INSUFFICIENT (refuter high
finding): several trap-blunder positions are *also* reached by sound opening-DB /
repertoire lines (e.g. Fried Liver's `Nxd5`, Damiano, Stafford, Noah's Ark, Mortimer —
verified 10 victim EPDs across 5 traps collide with the non-trap book). Skipping them
in the trap seed would leave them booked by the opening DB → fix silently no-ops there.

So: build the book from **all** sources as today (opening DB + repertoire + trap
mainlines), then **subtract a blocklist** = the set of EPDs reached by any
**victim**-side trap move. Result: trapper's winning moves + lead-in stay "book"; every
victim blunder position is removed no matter who seeded it → falls through to the engine
→ real `Blunder` label.

Semantics (playback item): subtract only positions reached by a `side == "victim"` ply.
Trapper + lead-in positions are untouched (matches the chosen option: "trapper's winning
moves … stay book"). Edge case: if a victim EPD coincides with a trapper/lead-in EPD
elsewhere, subtraction still un-books it — acceptable, because that position is
objectively bad and an engine eval of the move into it is correct (no false blunders:
`classify` compares before/after). Confirm at Gate 1.

## Files / interfaces to touch
- **`app/traps.py`** — add a NEW function `iter_victim_epds() -> set[str]` (or list):
  replay each variation (`leadInSan` SAN→UCI prefix, then `mainLine` ucis) and collect
  `board.epd()` after each ply whose step `side == "victim"`. A missing `side` key →
  treat as NOT victim (don't block). Exception-safe per-trap (skip malformed, never
  raise), mirroring `iter_mainline_ucis()`. Do NOT modify `iter_mainline_ucis()` /
  `mainline_ucis_for()` (trap-practice + repertoire trap-leaf refs depend on the full
  line).
- **`app/book.py`** — add a `blocklist_epds: Iterable[str] = ()` param to
  `load()`/`init()`. After building `book_epds` from all sources, do
  `book_epds -= set(blocklist_epds)` (subtract LAST). **Fold `blocklist_epds` into the
  cache signature `sig`** (book.py:141) so a changed blocklist rebuilds — otherwise a
  reload with same lines/trap_ucis but different blocklist returns a stale index
  (refuter med finding).
- **`app/main.py`** (book wiring, ~161-164) — keep the existing
  `trap_ucis=traps.iter_mainline_ucis() + repertoire.iter_lines()` seeding; ADD
  `blocklist_epds=traps.iter_victim_epds()`.

## Out of scope
- Opening-DB (lichess TSV) lines and repertoire lines stay fully booked — their data
  is curated-sound (no deliberate "??" moves), so they don't currently swallow
  blunders. Not touched. (Same *mechanism*; only trap data triggers it today.)
- `trap-practice` mode, `iter_mainline_ucis()`, `mainline_ucis_for()` behavior —
  unchanged.
- Game-review pipeline — already evals every ply (doesn't use the book fast-path).
- No change to `classify` / eval math (verified correct: engine labels `Be2` a
  blunder at every preset once it actually runs).
- No traps.json data edits; no DB schema change.

## Constraints (from profile invariants)
- `book.py`/`traps.py` stay engine-free + import-safe with no Stockfish; full pytest
  suite runs with no binary.
- Reuse existing side tags in `traps.json`; do not re-derive.
- Startup wiring must never raise (runs in app lifespan).
- Auth: none (local single-user).

## Verify-by (end-to-end)
1. **Unit (engine-free):** with traps loaded + book built as at startup (INCLUDING the
   blocklist), `book.is_book_move(fen_before, uci)` is **False** for every victim-side
   ply and **True** for lead-in + trapper replies. Must cover BOTH:
   (a) Blackburne Shilling (`Nxe5`/`Nxf7`/`Rf1`/`Be2` → False), AND
   (b) a **transposition-escape trap** whose victim EPD is also in the opening DB —
   e.g. Fried Liver `Nxd5` / Kxf7 / Ke6 → False (this is the case the naive approach
   missed; guards the high finding). Add to `tests/test_book.py` / `tests/test_traps.py`.
- Command: `.venv/bin/python -m pytest -q`
2. **Route (TestClient, engine present):** POST `/api/move` for `7.Be2` from the trap
   position with `{useBook:true, analyze:true}` returns `book:false` and
   `analysis.quality == "blunder"` (currently `book:true`, `quality:null`).
3. **Cache-sig test (engine-free):** two `book.load()` calls with identical
   `lines`/`trap_ucis` but different `blocklist_epds` must yield different `book_epds`
   (guards the med finding — proves blocklist is in `sig`).
4. **Regression:** full `pytest` green; `ruff check app tests` clean; repertoire lines
   still book (`is_book_move` True for a known repertoire continuation); trap-practice
   unaffected (`iter_mainline_ucis` unchanged). **Audit `tests/test_book_data.py::
   test_trap_continuation_recognized`** (refuter low finding): it builds a book from
   `iter_mainline_ucis()` mirroring the OLD wiring and asserts a trap's last ply is in
   book (passes by coincidence — Fried Liver ends on a trapper ply). Either update it to
   build via the new blocklist wiring, or add an assertion that a victim ply is NOT in
   book, so it stops giving false confidence.
5. **Manual (live server, Playwright-MCP):** play the 13-move line in free play; the
   victim moves show `Blunder`/`Mistake` labels instead of a `Book` tag.

## Refuter findings (folded in)
- **HIGH — naive skip no-ops on transposition-escape traps** (10 victim EPDs / 5 traps
  also in the opening-DB book: fried-liver, damiano, stafford, noahs-ark, mortimer).
  → RESOLVED by switching to blocklist subtraction (un-books regardless of source).
  Verify-by #1(b) adds a Fried-Liver test so this can't regress.
- **MED — blocklist must be in `book.load` cache signature** or a reload returns a stale
  index. → Spec now requires folding `blocklist_epds` into `sig`; verify-by #3 tests it.
- **LOW — `test_book_data.py::test_trap_continuation_recognized` exercises retired
  wiring** and passes by data coincidence. → Verify-by #4 requires auditing/updating it.
- Informational (accepted): no current trap has a victim-free or victim-ending mainline;
  missing `side` key must default to NOT-victim (spec states this). Terminal/checkmate
  branch (main.py ~464) runs before the book check, so a game-ending victim move is a
  non-issue (`Nf3#` is trapper-side anyway).
