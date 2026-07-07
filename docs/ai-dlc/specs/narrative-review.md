# Delta spec — narrative-review ("Game commentary")

**Goal (one line):** On-demand, cached Claude-Sonnet narrative for an analyzed game in the
Review tab — a chaptered story (both sides) plus per-ply comment cards at key moments —
generated from *already-persisted* Stockfish data only.

Contracts: `docs/ai-dlc/contracts/narrative-review.md` · Date: 2026-07-07 ·
Branch: `feat/narrative-review`

## User-visible behavior

1. Reviewing a game with `analysis_status='done'` shows a **"Generate commentary"** button.
   - No `ANTHROPIC_API_KEY` in env → button disabled with hint text ("Set ANTHROPIC_API_KEY
     to enable AI commentary").
   - Click → spinner → on success a **collapsible narrative panel** appears under the
     accuracy summary strip (collapsed to first lines + "read more"), and **moment cards**
     appear during replay when the cursor reaches a key ply (rendered in the existing
     foresight card area, visually distinct from foresight cards).
   - Cached: reopening the game shows the narrative instantly (no API call). A small
     **Regenerate** action re-runs generation and overwrites the cache.
   - API failure/timeout → toast with error; button returns to normal (retry = click again).
     Nothing persisted on failure.
2. Narrative content (single medium depth):
   - **Story**: 3 chapters (opening / middlegame / endgame — omit chapters the game never
     reached), ~300–500 words total, judging **both sides**, naming concrete move numbers.
   - **Moment cards**: 1–2 sentences each for: user mistakes/blunders, opponent
     mistakes/blunders, tide turns, critical narrow-choice positions, missed
     capitalizations, time-trouble-flagged errors.
   - **Profile tie-in**: when this game's leak categories match the user's top cross-game
     clusters, the story may reference the pattern ("third game this month…").
3. Invalidation: any action that resets `analysis_status` to `pending` (retag-color,
   per-game color change) or deletes the game also deletes the cached narrative.
   Re-analysis (`POST /api/games/{id}/analyze`) also deletes it.

## Architecture (engine owns facts; LLM narrates)

### New pure module `app/moments.py` (engine-free, network-free)
`extract_moments(plies, leaks, pos_lookup, my_color, profile_context) -> MomentsPayload`
- Inputs: `game_plies` rows, `leaks` rows, a prefetched `dict[epd -> pos_cache row]`
  (built by the caller; module itself never touches SQLite), `my_color`, optional
  profile top-cluster summaries.
- Detects, from stored data only:
  - **User mistakes/blunders**: straight from `leaks` (motif category, hung square,
    `best_san`, win-prob drop, phase).
  - **Opponent mistakes/blunders**: win-prob drop on `is_user_move=0` plies computed from
    the stored White-POV eval series via `analysis.win_prob_white`; severity via
    `analysis.leak_severity` (already pure, already the single source of truth — it is
    merely re-exported by review.py; do NOT re-derive or duplicate thresholds).
    Last-ply boundary: the eval series stores the position *before* each ply and has no
    "after" for the game's final move — same fallback as `app/review.py:383-393`
    (no next position → no computed swing; never index past the series).
  - **Tide turns**: plies where White-POV win prob crosses 0.5 with total swing ≥ 0.20
    (same last-ply boundary rule).
  - **Critical (narrow-choice) positions**: where `pos_cache.pv2_cp_white` exists and the
    gap between best and 2nd-best (converted to win-prob space) ≥ 0.15 — note pv2 has a
    score but NO move; the narrative may say "the alternatives were much worse", never
    name a second-best move. NOT "only-move" semantics: true single-legal-move positions
    have no pv2 row at all (multipv capped by legal-move count, `app/engine.py:461`) and
    are out of scope for this detector. Distinct from `review.py:_is_only_move` (100cp,
    lead-in seeding) — different purpose; don't merge, but name ours `narrow_choice` to
    avoid two things called "only-move".
  - **Missed capitalization**: opponent blunder followed by the user's next move giving
    most of the swing back.
  - **Time-trouble flag**: `clock_centis` low (< 60s) at a mistake ply, when clocks exist.
- POV discipline: `eval_cp_white`/`mate_white` are White-POV; `game_plies.win_prob` is
  MOVER-POV; `leaks.win_prob_*` are user-POV. Use `analysis.pov_score_to_white_cp` /
  `analysis.win_prob_white`; never re-derive sign rules.
- Noise guard: background evals are depth 10 — no moment is emitted for swings below the
  mistake threshold; cp deltas under 60 are never narrated as facts.
- `lead_in_ply` foresight claims require the RELATIVE guard `lead_in_ply < ply - 1`
  (exactly as `insights.py:648-658`; `lead_in_ply == ply - 1` is the display-timing
  default carrying no signal at ANY ply — an absolute `>= 2` check would wrongly flag
  nearly every leak as foreseeable).
- Cap: max 12 moments, prioritized blunders > tide turns > critical > missed chances >
  time-trouble; if the cap trims anything, the payload records what was dropped.
- Output: JSON-serializable payload — game header facts (players, ECO/opening, result,
  accuracy summary), eval-arc summary (per-phase min/max/end win prob), the moments list
  (each with ply, san, move number, side, kind, facts incl. FEN-before, best move + stored
  PV when available), and profile context. This payload is the ONLY chess content Sonnet
  ever sees.

### New module `app/narrative.py` (the only network-aware module)
- `build_prompt(payload) -> (system, user)`: pure, unit-testable. System prompt rules:
  narrate ONLY facts in the payload; concrete variations may quote the provided PV
  verbatim but never invent moves; never name a 2nd-best move; produce strict JSON
  `{chapters: [{phase, text}], moments: [{ply, text}], overall: str}`.
- `generate(payload) -> NarrativeData`: lazy `import anthropic` inside the function
  (module import stays clean — same pattern as `EngineUnavailable` lazy imports).
  Model = env `NARRATIVE_MODEL`, default `claude-sonnet-5`; `max_tokens` ≤ 2000;
  hard timeout env `NARRATIVE_TIMEOUT_S`, default 60. Parse + validate returned JSON
  (moment plies must exist in the payload); one retry on parse failure, then raise
  `NarrativeUnavailable` (new exception mirroring `EngineUnavailable` semantics).
- `is_enabled() -> bool`: `ANTHROPIC_API_KEY` present.
- Concurrency: per-game in-flight guard (module-level dict of game_id) — concurrent POSTs
  for the same game return 409. Guard entry/exit wrapped in try/finally (mirror
  `review.py:617-618`), and tests get a teardown fixture clearing the dict (same
  discipline as the manual `review._tasks` cleanup in `tests/test_review.py:153`).
  Runs as a plain awaited call inside the route (NOT inside `review.analyze_game`'s
  loop; never touches the engine lock). Does not use `review._tasks` /
  `_ANALYZE_ALL_KEY` key space at all.
- Staleness race: a re-analysis can start+finish while the Anthropic call is in flight.
  At payload-build time capture a fingerprint (analysis_status must be 'done', plies row
  count, last ply's eval/mate, leaks count); recompute immediately before
  `upsert_narrative` — on any mismatch discard the result (no cache write) and return
  409 with detail "game re-analyzed during generation — retry".
- Note: `coaching.py`'s TODO(claude-narrator) seam (per-leak foresight narration) is NOT
  implemented here — foresight cards stay template-driven. Remove/adjust that TODO comment
  only if it would now mislead (point it at `narrative.py`).

### Storage (`app/storage.py`) — schema change AUTHORIZED by this spec
- `_SCHEMA_VERSION` 2 → 3; migration in `_run_migrations` creates:
  `narratives(game_id INTEGER PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,
  model TEXT NOT NULL, narrative_json TEXT NOT NULL, created_at TEXT NOT NULL)`.
  Only successful generations are persisted (no status machine; failure = HTTP error).
- New helpers: `get_narrative(game_id)`, `upsert_narrative(...)`, `delete_narrative(game_id)`.
- Invalidation wiring: `set_my_color` and `retag_colors_by_aliases` (both already reset
  `analysis_status`) also delete the narrative row; `POST /api/games/{id}/analyze` route
  deletes it before re-analysis. Game deletion cascades via FK.
- `explanation_json` on `leaks` stays untouched (still template-narrator-owned).

### API (`app/main.py`, `app/models.py`)
- `GET /api/games/{id}/narrative` → `NarrativeStatusResponse
  {enabled: bool, narrative: NarrativeData | None}` (404 only for unknown game).
- `POST /api/games/{id}/narrative` → generates, caches, returns
  `{enabled: true, narrative: NarrativeData}`.
  Errors: 409 analysis not done / generation already in flight / re-analyzed during
  generation; 422 not enough analyzed moves; 503 `enabled=false` (no key); 502 with
  detail on API failure/timeout/parse failure.
- Route builds the payload from exactly three reusable calls — `storage.get_plies`,
  `storage.get_leaks`, `accuracy.summarize` (the `/review` route is inline, ~65 lines;
  do NOT refactor it to "share" logic) — plus profile clusters. Per-ply EPDs come
  straight from the stored `game_plies.fen_before` (first 4 FEN fields) — NO python-chess
  replay of the raw PGN (immune to the illegal-move truncation `review.py:356-365`
  tolerates). Batch pos_cache lookups via a new `storage.get_pos_cache_many(epd_keys)`
  helper that is DEPTH-AGNOSTIC: returns the deepest available row per EPD (pos_cache is
  keyed `(epd_key, depth)` and `REVIEW_BG_DEPTH` may have changed across restarts since
  the game was analyzed — filtering on the live constant would silently blank
  best-move/PV/narrow-choice data for older games). When pos_cache coverage is sparse,
  the payload records that fact so thin commentary isn't mistaken for "nothing happened".
- Degenerate games: `analysis_status='done'` is reachable with zero (or truncated)
  `game_plies` rows (`review.py:248-251, 356-365`). Route returns 422 "not enough
  analyzed moves" without an API call when plies < 4; frontend disables the button with
  that hint in the same case.
- `NarrativeData` Pydantic model: `{model, created_at, chapters: [{phase, text}],
  moments: [{ply, text}], overall}`.

### Frontend (`static/review.js`, `static/review.css`, `static/index.html`)
- review.js keeps the injected-api pattern; still never imports app.js. Extend
  `postJSON` (and `fetchJSON` if needed) to attach `{status, detail}` from the error
  response body onto the thrown Error (today they discard the JSON `detail` on non-2xx —
  `static/review.js:53-59` — but the 409/422/503/502 UX needs the human-readable detail
  in the toast). Backward-compatible: message string unchanged.
- `loadReviewData` additionally GETs `/narrative`; renders:
  - Narrative panel (`#review-narrative` host in index.html under the summary strip):
    collapsed story w/ "read more" toggle, Regenerate action when cached, Generate button
    + disabled-hint states otherwise, spinner while POST in flight.
  - Moment cards: on `review:ply`, if a narrative moment matches the cursor ply, render a
    card in the foresight host area with a distinct class (`review-moment-card`).
- CSS: tokens only (no raw hex), AA contrast, `:focus-visible` on the new controls.
- Clear narrative UI state in `openGame` (same place summary/foresight are cleared).

### Dependencies
- `requirements.txt`: add `anthropic>=0.40`. Sandbox blocks pip install — the user runs
  `pip install -r requirements.txt` in their terminal (SETUP-SANDBOX.md convention).

## Constraints (inherited)
- Pure modules stay engine-free AND network-free; full pytest passes offline with no
  Stockfish binary and no `ANTHROPIC_API_KEY` (narrative generation faked via seam).
- One Stockfish process / asyncio.Lock untouched; narrative never calls the engine.
- Server stateless except game-review SQLite (narratives table extends that exception).
- `ANTHROPIC_API_KEY` only — never Max/Pro OAuth (Anthropic ToS).
- Commit policy: implemented + verified + reviewed; Conventional Commits; feature branch
  `feat/narrative-review`; never push main/merge PRs.
- No debug artifacts.

## Out of scope
Chat/Q&A coach · streaming responses · multi-depth commentary levels · auto-generate on
import · batch "generate all" · replacing the template foresight narrator ·
non-review tabs · prompt-tuning iterations beyond one working prompt · cost dashboards.

## Verify-by (end-to-end)
1. `.venv/bin/python -m pytest -q` green, offline, no `ANTHROPIC_API_KEY` set, no binary;
   suite stays within current baseline (~35 s as of 2026-07-07 — no material regression).
   `.venv/bin/ruff check app tests` clean.
2. New unit tests: moments extractor (opponent-blunder detection incl. POV correctness,
   tide-turn crossing, only-move gap, cap/priority, depth-noise floor), prompt builder
   (facts-only payload, JSON contract), API routes with a fake generator (no-key 503 +
   `enabled:false`, not-analyzed 409, success caches, GET returns cache, retag/color-change/
   re-analyze delete cache, migration v2→v3 on an existing DB file).
3. Browser (live server, real `ANTHROPIC_API_KEY`): open analyzed game → Generate →
   story panel + moment cards appear and match real move numbers; reload → instant cached;
   Regenerate works; retag color → narrative gone; unset key + restart → button disabled
   with hint. No console errors.
