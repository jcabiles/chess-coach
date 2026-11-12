# Agent tickets

Small, fully specified tickets that Codex, Gemini or Claude may pick up without the ai-org
build process. The procedure is in `AGENTS.md`, "Working an agent ticket". Claude or the project
owner adds tickets here; only a reviewer checks a box, after the fix is reviewed and merged.

Each ticket names its id (used for the branch `ticket/<id>`), the bug or task, how to confirm it
(a command or a test that fails today), and where it came from. Every bug below was reproduced
against the code on 2026-11-12, and every fix starts with a test that fails before the change.

- [ ] **pilot-1 · Book cache ignores config edits** — `app/book.py` `load()` builds its cache
      signature from the config path and the passed-in lines only, so editing `data/book.json`
      and calling `load()` again with the same arguments returns the stale index · done when:
      rewriting the config file between two `load()` calls changes the result (for example, an
      added `extraLines` entry is in the book), and an unchanged file still hits the cache.
- [ ] **pilot-2 · Move numbers glued to SAN moves skip the line** — `app/book.py`
      `_epds_for_san_movetext()` strips only separate move numbers (`1. e4`), so `1.e4 e5` or
      `1...e5` fails to parse and the whole extra line is dropped · done when: `"1.e4 e5 2.Nf3"`
      yields 3 positions, `"1. e4 1... e5"` yields 2, and an illegal move still yields `[]`.
- [ ] **pilot-3 · A trap with a list `id`, list `color` or non-text `name` aborts the traps load**
      — `app/traps.py` `_validate_trap()` checks only that fields exist, so the `in` test on
      `color`, the dictionary insert on `id` or the name sort raises `TypeError` and no trap
      loads · done when: each malformed trap is dropped with a warning and the rest load.
- [ ] **pilot-4 · Duplicate trap ids leave the indexes disagreeing** — `app/traps.py` `load()`
      overwrites `traps_by_id` on a repeated `id` but keeps both summaries and both start-position
      entries (20 summaries for 19 traps) · done when: a repeated `id` is dropped with a warning
      and `traps_by_id`, the summaries and the start-position index agree.
- [ ] **pilot-5 · `available()` raises on `None` moves** — `app/traps.py` `available()` promises
      "Never raises" but iterates `uci_moves` outside its `try`, so `None` raises `TypeError` ·
      done when: `None` or another non-iterable returns `[]`.
- [ ] **pilot-6 · An absurd stored bot rating overflows the Elo update** — `app/rating.py`
      `build_rating()` accepts any integer `personaElo`, and `elo_update()` raises
      `OverflowError` for values such as 10,000,000 · done when: a game whose `personaElo` is
      outside 100–4000 counts toward `gamesSkipped` and the rating still computes.
