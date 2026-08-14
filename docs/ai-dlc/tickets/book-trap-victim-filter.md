# Tickets — Stop the opening book from swallowing trap blunders

Spec: `docs/ai-dlc/specs/book-trap-victim-filter.md`
Approach: build book from all sources, then subtract a victim-EPD blocklist.

Do sequentially (T1 → T2 → T3 → T4 → T5). Single owner per file; no parallelism needed
(tiny change, shared files T1/T4 = traps.py & main.py).

---

### T1 — `traps.iter_victim_epds()`
Add a new pure function to `app/traps.py`: for each loaded trap variation, replay
`leadInSan` (SAN→UCI) then `mainLine` ucis, collecting `board.epd()` after each ply
whose step `side == "victim"`. Missing `side` key → NOT victim. Exception-safe per-trap
(skip malformed, never raise). Do NOT touch `iter_mainline_ucis()` / `mainline_ucis_for()`.
- **Owns:** `app/traps.py`
- **Done:** `python -c "from app import traps; traps.load(); print(len(traps.iter_victim_epds()))"`
  prints a non-zero count; no exception on load.
- **Accept:** returns a set/list of EPD strings; Blackburne Shilling's 4 victim EPDs are
  members; a trap-free load returns empty.

### T2 — `book.load` blocklist subtraction + cache-sig
Add `blocklist_epds: Iterable[str] = ()` to `book.load()` and `book.init()`. After
building `book_epds` from all sources, `book_epds -= set(blocklist_epds)` (LAST step).
Fold `blocklist_epds` into the `sig` tuple (book.py:141) so a changed blocklist rebuilds.
- **Owns:** `app/book.py`
- **Depends:** none (param plumbing; independent of T1)
- **Done:** `pytest tests/test_book.py -q` green.
- **Accept:** subtraction removes blocked EPDs; two loads with same lines/trap_ucis but
  different `blocklist_epds` produce different `book_epds` (cache-sig honored).

### T3 — unit tests (engine-free)
Add tests asserting post-fix book membership:
(a) Blackburne Shilling victim plies (`Nxe5`/`Nxf7`/`Rf1`/`Be2`) → `is_book_move` False;
    lead-in + `Qg5` (trapper) → True.
(b) **Fried Liver** victim plies (`Nxd5`/`Kxf7`/`Ke6`) → False (transposition-escape:
    guards the high finding — this position is also in the opening DB).
(c) cache-sig: two `book.load()` with differing `blocklist_epds` → different sets.
- **Owns:** `tests/test_book.py` (and/or `tests/test_traps.py`)
- **Depends:** T1, T2
- **Done + accept:** `.venv/bin/python -m pytest -q` green; the three assertions pass;
  removing the subtraction line makes (a) and (b) fail (test has teeth).

### T4 — wire blocklist into startup
In `app/main.py` book init (~161-164), keep the existing `trap_ucis` seeding and ADD
`blocklist_epds=traps.iter_victim_epds()`.
- **Owns:** `app/main.py`  ⚠ hotspot — single owner
- **Depends:** T1, T2
- **Done:** app imports; `/api/move` route test below passes.
- **Accept (route test, engine present):** TestClient POST `/api/move` for `7.Be2`
  (trap position, `{useBook:true, analyze:true}`) → `book == false` and
  `analysis.quality == "blunder"`. Add as a route test.

### T5 — audit retired-wiring test + full regression
Audit `tests/test_book_data.py::test_trap_continuation_recognized` (refuter low finding):
it builds a book from `iter_mainline_ucis()` and asserts a trap's last ply is in book
(passes by coincidence). Update it to build via the blocklist wiring OR add an assertion
that a victim ply is NOT in book. Then run full regression.
- **Owns:** `tests/test_book_data.py`
- **Depends:** T1–T4
- **Done:** `.venv/bin/python -m pytest -q` fully green; `.venv/bin/ruff check app tests`
  clean.
- **Accept:** repertoire continuation still `is_book_move` True; trap-practice unaffected;
  manual Playwright check (spec verify-by #5) shows victim moves labeled, not "Book".

---

**Out of scope (do not touch):** opening-DB/repertoire full seeding, `iter_mainline_ucis`
/ `mainline_ucis_for` semantics, `classify`/eval math, traps.json data, DB schema. The
pre-existing `repertoire.load()` "could not resolve a legal line" warnings for 4
trap-leaf refs are a SEPARATE issue — note only, not this ticket.
