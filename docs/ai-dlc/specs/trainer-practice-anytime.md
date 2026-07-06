# Spec — Blunder Trainer practice-anytime

**Goal (one line):** let the user start a Blunder Drill session any time —
when nothing is due, the Start button becomes "Practice" and serves puzzles
from all buckets with **zero impact on the Leitner schedule**.

Contracts: `docs/ai-dlc/contracts/trainer-practice-anytime.md`. Follow-up to
the Blunder Trainer epic. User decisions: zero schedule impact; one adaptive
button.

## Backend

1. `trainer.assemble_session(today=None, practice=False)`:
   - `practice=False` — behavior byte-identical to today (due buckets only).
   - `practice=True` — candidate set is **all live-pool buckets** (after box
     hygiene), not just due ones; same deterministic motif order, same
     reserve-1-slot-per-bucket + prefix-constrained hardest-first fill, same
     SESSION_CAP/PER_BUCKET_CAP, same cursor advance (contract #2: the
     cursor upsert passes box/last_reviewed through unchanged — schedule
     neutral).
2. `POST /api/trainer/session/start`: **request body unchanged** (still
   none — the existing tests POST with no body and must pass untouched;
   refuter MED: adding an optional Pydantic body silently 422s bodyless
   POSTs unless the param defaults a whole model instance — avoided
   entirely by not adding one). The ROUTE decides at serve time:
   `data = assemble_session()`; if `data["puzzles"]` is empty →
   `data = assemble_session(practice=True)` (double hygiene run is
   idempotent; the first call served nothing so no cursors moved).
   Response gains additive `practice: bool = False` — True iff the
   fallback fired. This echo is AUTHORITATIVE: it reflects actual
   due-state at serve time, killing the stale-render race (refuter MED:
   a tab left open overnight could otherwise request "practice" for a
   now-due bucket and silently suppress its real review flush).
3. `complete_bucket_review` and `/api/trainer/bucket-complete`: UNCHANGED.
   Practice never reaches them (client suppresses the flush — see frontend;
   single-user local app, no server-side enforcement needed).
4. `/api/trainer/check` UNCHANGED — practice attempts are recorded in
   trainer_attempts / stats by design.

## Frontend (`static/trainer.js`)

5. Train section: Start button disabled ONLY when the pool is empty or the
   preview fetch failed. When `dueCount > 0` → label "Start training",
   behavior unchanged. When `dueCount === 0` → label "Practice", title
   "Extra practice — doesn't affect your review schedule". The click sends
   the same bodyless POST either way — the label is cosmetic; the SERVER
   decides review vs practice at serve time (see item 2), so a stale
   label can never mis-classify a session.
6. Drill: `drill.practice` = the RESPONSE's `practice` echo (never a
   client-derived guess). Title prefix
   "Blunder Drill (practice) — 1/N · Fork". Summary line for practice:
   "Practice complete — {solved}/{total} solved. Your review schedule is
   unchanged."
7. `flushOutcomes()`: when `drill.practice`, skip ALL
   `/api/trainer/bucket-complete` POSTs (both endSession and exitTrainer
   paths share this function; the `drill.flushed` guard stays) but still
   call `refreshTrainSection()`.
8. Empty-session toast: reword the generic "Nothing due right now." to
   "No puzzles available right now." — with server-side classification the
   empty case now covers both an empty pool and a nothing-due default, and
   "due" is wrong for a Practice-labeled click (refuter LOW).
9. Everything else in the drill (check flow, retry, reveal, Correct! pause,
   Return restore, transient persistence) is shared code — unchanged.

## Known bound (documented, accepted)

Practice serves at most SESSION_CAP (10) buckets per session via the
existing `[:SESSION_CAP]` truncation, in deterministic motif order
(refuter LOW). The live motif vocabulary is 9 values (mate, hanging, fork,
knight_fork, pin, skewer, discovered, back_rank, missed_threat), so today
nothing is unreachable; P1 adds a comment at the truncation site noting
the practice-mode implication if the vocabulary ever grows past the cap.

## Out of scope

Bucket picker, practicing while reviews are due (due days keep the normal
button), server-side rejection of bucket-complete for practice sessions,
box promotion from practice, stats UI changes.

## Constraints

- Pure module stays pure: `trainer.py` gets no new imports; suite stays
  engine-free (ScriptedEngine for the API case).
- No DB schema change.
- Additive-only API change (existing clients/tests unaffected).
- Frontend: injected-api discipline; tokens-only CSS if any style is
  touched (label swap needs none).

## Verify-by

`.venv/bin/python -m pytest -q` green with NEW cases:
- pure: practice serve returns non-due buckets; cursor advances; box +
  last_reviewed rows unchanged after a practice serve; practice with zero
  live pool → empty lists; due session (practice=False) byte-identical to
  before (existing tests untouched).
- API: bodyless POST /session/start (exactly like the existing tests) on
  a nothing-due fixture returns puzzles + `practice: true`; on a due
  fixture returns the due session + `practice: false`; schedule rows
  (box, last_reviewed) unchanged after the practice serve.

Playwright on live :8001 (today's state is nothing-due — ideal fixture):
1. Train section shows "Practice" enabled with the schedule-safe hint.
2. Start → drill runs with "(practice)" in the title; solve one (Correct!
   pause from PR #31 still works), Return.
3. After exit: Train section still shows all buckets NOT due (no
   last_reviewed change today→today, box levels unchanged) — the schedule
   was not consumed.
4. No console errors; no /bucket-complete request fired (network log).
