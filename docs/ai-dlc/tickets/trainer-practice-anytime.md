# Tickets — Blunder Trainer practice-anytime

Spec: `docs/ai-dlc/specs/trainer-practice-anytime.md` · Contracts:
`docs/ai-dlc/contracts/trainer-practice-anytime.md`. One PR, sequential
(shared seams). Hotspots `app/main.py`, `app/models.py` single-owner.

- [x] **P1 — backend practice serve.** `assemble_session(practice=False)`
  param: practice=True serves ALL live buckets (post-hygiene) through the
  existing reserve+hardest-first+cursor-advance pipeline; due path
  byte-identical. NO request model (existing bodyless POSTs must pass
  untouched); route falls back — due serve first, practice serve iff it
  returned zero puzzles; response gains additive `practice: bool`
  (authoritative echo). Comment at the `[:SESSION_CAP]` truncation on the
  practice-mode bound. New pure tests (non-due served, schedule rows
  untouched, empty pool) + API tests (bodyless POST: practice echo on
  nothing-due fixture, due session + practice:false on due fixture,
  schedule rows unchanged after practice).
  Owned: `app/trainer.py`, `app/models.py`, `app/main.py`,
  `tests/test_trainer.py`, `tests/test_api.py`.
  **Done when:** full pytest green; existing trainer tests unmodified.

- [x] **P2 — frontend adaptive button + practice drill.** Train section:
  enabled "Practice" label + schedule-safe title when dueCount===0 (pool
  non-empty); click stays a bodyless POST (label cosmetic — server
  classifies). Drill: `drill.practice` = RESPONSE echo → title
  "(practice)" prefix, practice summary line, `flushOutcomes()` skips
  bucket-complete POSTs but keeps `refreshTrainSection()`; empty toast
  reworded to "No puzzles available right now."
  Owned: `static/trainer.js`.
  **Done when:** Playwright passes spec Verify-by 1-4 (incl. network log
  shows zero /bucket-complete calls and due-state survives practice).

- [x] **P3 — ship.** Diff review, refuter on diff, Conventional Commit,
  PR; tickets ticked.
  **Done when:** PR open with evidence; audit trail complete.

Dependencies: P1 → P2 → P3.
