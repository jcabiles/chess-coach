# Contracts — Blunder Trainer practice-anytime

Area: `app/trainer.py` session assembly, `POST /api/trainer/session/start`
route (`app/main.py`, `app/models.py`), `static/trainer.js` Train section +
drill. Mapped directly by the main session (scheduler read in full this
session, `app/trainer.py:242-359`).

## Contracts a practice mode must respect

1. **Due-ness is computed, not stored** (`is_due`, trainer.py:77): a bucket
   is due when `today - last_reviewed >= INTERVAL_DAYS[box]`; never-reviewed
   is always due. The ONLY writer of `last_reviewed` is
   `complete_bucket_review` (trainer.py:335-358), invoked solely by
   `POST /api/trainer/bucket-complete`, which the CLIENT calls from
   `flushOutcomes()` (trainer.js). ⇒ a practice session that must not touch
   the schedule has to (a) never call bucket-complete and (b) never add a
   server-side stamp path.
2. **Cursor advance is schedule-neutral.** `assemble_session` step 5
   persists `cursor_key` via `upsert_trainer_box` but passes through the
   EXISTING `box` + `last_reviewed` unchanged (trainer.py:314-319) — so a
   practice serve advancing rotation does NOT affect due-ness. Reuse this
   exact write; do not invent a second upsert shape.
3. **Serve is mutating; preview is not.** GET /api/trainer/session
   (preview_due_buckets) must stay cursor-neutral; POST /session/start
   burns rotation — frontend calls it exactly once per Start click
   (trainer.js startSession). Practice must flow through the SAME
   start-once discipline.
4. **Session shape**: `{"buckets": [...], "puzzles": [...]}`; puzzles carry
   `key/bucket/game_id/ply/fen_before/color/severity/best_uci/best_san/
   win_prob_drop/threat_uci/hung_square`. Frontend drill consumes this
   verbatim; `bucket` field drives outcome grouping. A practice response
   must keep the shape (additive flag only) — `models.py` response schema
   change is additive.
5. **min-sample / next_box** (trainer.py:90-106): box transitions happen
   only in `complete_bucket_review`. Practice skipping the flush entirely
   never reaches this code — no guard changes needed.
6. **Box hygiene** (`_reset_empty_boxes`) runs on both preview and serve;
   practice serve must keep running it (idempotent).
7. **Frontend**: `startSession()` disables the Start button during flight
   and re-enables on empty/error; `drill` object owns session state;
   `flushOutcomes()` is called from BOTH endSession and exitTrainer
   (guarded by `drill.flushed`) — a practice flag must suppress the
   bucket-complete POSTs in BOTH paths (keep the final
   `refreshTrainSection()`).
8. **Stats**: `/api/trainer/check` records every real attempt in
   `trainer_attempts` regardless of session kind — practice attempts land
   in stats by design (user-approved).
9. **Tests**: `tests/test_trainer.py` pure suite (no Stockfish);
   `tests/test_api.py` trainer cases use ScriptedEngine +
   `app.dependency_overrides[get_engine]`. New behavior needs cases in
   both; suite must stay engine-free.

## Integration points

- `app/trainer.py` — `assemble_session` grows a practice path (all live
  buckets instead of due-only).
- `app/models.py` — session-start RESPONSE additive field only (adding a
  request body model would 422 the existing bodyless POSTs unless the
  route param defaults a whole model instance — avoided by having none).
- `app/main.py` — route classifies at serve time: due serve first,
  practice fallback iff zero puzzles; response echo is authoritative.
- `static/trainer.js` — adaptive Start button, practice flag on drill,
  flush suppression, practice labeling.
- NOT touched: storage.py schema, /check, /bucket-complete,
  preview_due_buckets semantics.
