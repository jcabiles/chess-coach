# Contracts — opening-book seeding vs. trap mainlines

Area: `app/book.py`, `app/traps.py`, `app/main.py` book wiring, `/api/move` fast-path.

## Invisible contracts (must not break)

1. **Book fast-path skips the engine.** `/api/move` (main.py:497) returns
   `book:true`, `analysis:null` when `book.is_book_move(fen_before, uci)` — no
   eval, no quality label. This is intentional latency optimization for *known
   theory*. Contract: only moves that DON'T need eval feedback belong in the book.
   **The bug:** trap mainlines deliberately contain the victim's "??" moves, which
   very much need feedback → they must NOT be booked.

2. **Book membership = reached position (EPD), transposition-safe.**
   `is_book_move` pushes the move and tests `board.epd() in book_epds`. A position
   is booked if ANY seeded line reaches it. So removing a position from the trap
   contribution only un-books it if no *other* seeded source (opening DB, repertoire)
   also reaches it. Junk trap positions (post-Nxe5??) are not reachable by sound
   theory, so dropping them from the trap seed does un-book them.

3. **`book.load` seeds every ply's EPD of each supplied line** via
   `_epds_for_uci_line`. It has NO per-ply side info — it cannot itself skip the
   victim plies. Side tags (`mainLine[i]["side"] == "victim"|"trapper"`) live in
   `traps.json` / `app.traps`. So the victim filter must be computed in `traps.py`
   (where the tags are) and handed to `book` as positions, not derived in `book`.

4. **`main.py:164` shares the `trap_ucis` slot for two sources:**
   `traps.iter_mainline_ucis()` + `repertoire.iter_lines()`. Repertoire lines are
   the user's sound prep and MUST stay fully seeded. Any change must keep repertoire
   seeding intact while filtering only the trap contribution.

5. **`iter_mainline_ucis()` has other callers' expectations.** It returns full
   legal-from-start UCI lines. `mainline_ucis_for()` (repertoire trap-leaf refs) and
   trap-practice rely on the FULL mainline including victim moves — do NOT change
   `iter_mainline_ucis()` semantics. Add a NEW function for the book-filtered set.

6. **Startup must never crash** (runs in app lifespan). Trap iteration is
   exception-safe per-trap; the new function must preserve that (skip malformed
   traps, never raise).

7. **Pure/engine-free invariant.** `book.py` and `traps.py` stay import-safe with
   no Stockfish binary; the full pytest suite runs engine-free. New code must not
   import the engine.

## Integration points / consumers
- `/api/move` book fast-path (only live-play consumer that hides quality).
- Game-review pipeline (`review.py`) does NOT use the book fast-path — it evals
  every ply, so it already flags these blunders. Bug is scoped to live play.
- `trap-practice` mode + repertoire trap-leaf refs consume `iter_mainline_ucis` /
  `mainline_ucis_for` — unaffected if we add a new function instead of editing them.
