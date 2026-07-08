# Contracts Report: AI Narrative Commentary for Review Tab

*(contract-mapper output, 2026-07-07 — read-only scan; drives `specs/narrative-review.md`)*

## 1. Persisted per-ply analysis data (SQLite schema)

All schema in `app/storage.py:44-141`.

**`games`** (`app/storage.py:51-68`): one row per imported PGN. Notable columns: `my_color` (nullable — `'white'`/`'black'`/`NULL`), `analysis_status` (`'pending'|'analyzing'|'done'|'failed'`, CHECK-constrained), `opening`/`eco`/`result`/`date`, `content_hash` (dedup key), `ply_count`.

**`pos_cache`** (`app/storage.py:70-82`): keyed `(epd_key, depth)` — transposition cache, not game-scoped.
- `eval_cp_white` INTEGER — **White-POV** centipawns, NULL when mate.
- `mate_white` INTEGER — **White-POV** mate-in-N, NULL when not mate.
- `best_uci`/`best_san` — engine's best move.
- `pv_san_json` — JSON array of SAN strings for the **best line only** (written from `results[0].pv_san` in `app/review.py:172-173`; depth = however many plies Stockfish returned in that PV, not a fixed count).
- `pv2_cp_white` — 2nd-best line's score, White-POV cp (mate lines mapped to large cp via `pov_score_to_white_cp`, `app/review.py:184-186`). This is the **only** multipv-2 signal retained; no `pv2_san`/2nd-best move UCI/SAN stored anywhere.

**`game_plies`** (`app/storage.py:84-96`): PK `(game_id, ply)`. Columns actually written (`app/storage.py:415-448`, `app/review.py:540-554`): `san`, `uci`, `fen_before`, `eval_cp_white` (White-POV), `mate_white` (White-POV), `win_prob` (**mover-POV**, not White-POV — `app/review.py:332-334`; `insights.py:725-736` flips it back), `is_user_move` (0/1), `clock_centis`.
- **Important gap**: `game_plies` does NOT store `best_uci`/`best_san`/PV/pv2 — those live only in `pos_cache`, joined by `(epd_key, depth)` which is never persisted on the ply row. To get "best move at ply N" you must replay to compute the EPD and hit `pos_cache`, or use `leaks.best_uci`/`best_san` (only present for classified user mistakes/blunders).

**`leaks`** (`app/storage.py:98-118`): one row per classified user mistake/blunder (never opponent moves, never inaccuracies — filtered at `app/review.py:399-400`). Columns: `severity` (`'mistake'|'blunder'`), `category` (motif-derived: `hanging`/`fork`/`knight_fork`/`pin`/`skewer`/`discovered`/`back_rank`/`mate`/`missed_threat`), `motif_json`, `phase` (`opening|middlegame|endgame`), `win_prob_before/after/drop` (user-POV 0..1), `hung_square`, `threat_uci`, `threat_motif`, `best_uci`/`best_san`, `lead_in_ply` (display-timing default `ply - 1`, indistinguishable from genuine 1-ply signal — `insights.py:648-667` guards with `>= 2`), `tags_json`, `explanation_json` (**always NULL today** — placeholder, `app/storage.py:117,175`).

**Mate encoding**: `mate_white` non-NULL ⇔ `eval_cp_white` NULL (mutually exclusive by construction, `app/review.py:160-169`). Narrative code reading `eval_cp_white` must NULL-guard and fall back to `mate_white`, as `analysis.win_prob_white` does (`app/analysis.py:192-213`).

**Schema version**: `_SCHEMA_VERSION = 2` (`app/storage.py:38`) — new table/column requires bump + migration branch in `_run_migrations` (`app/storage.py:182-201`).

## 2. Review pipeline outputs

`analyze_game()` (`app/review.py:222-561`) per ply:
1. `pos_cache` lookup by `(epd, BACKGROUND_DEPTH)`; miss → `engine.analyze_multi(fen, depth, multipv=2)` (`app/review.py:313`) — **depth = `BACKGROUND_DEPTH`, default 10** (`app/review.py:85`, env `REVIEW_BG_DEPTH`), much shallower than interactive `DEFAULT_DEPTH=18`. Depth-10 evals are materially noisier than the interactive analysis panel's depth-18.
2. Pass 2 (`app/review.py:378-536`) computes `win_prob_before/after/drop` purely from stored data — no fresh engine calls except the null-move threat probe.
3. **Null-move threat probe**: pushes null move at leak position, re-analyzes at same depth for opponent's best reply (`app/review.py:456-464`), runs `motifs.detect_motifs`/`hanging_pieces` to derive `category`/`threat_motif`/`hung_square`/`motif_json`/`tags_json`.
4. Bulk-writes `game_plies` + `leaks`, sets `analysis_status='done'`.

**Everything an LLM narrator would read is fully computed and persisted by `analysis_status='done'`** — no additional engine calls needed for narrative generation.

`app/accuracy.py::summarize(plies, my_color)` (`app/accuracy.py:123-223`) is **pure and on-demand** — computed at request time in `GET /api/games/{id}/review` (`app/main.py:889-891`), never persisted. Returns `{white_accuracy, black_accuracy, white_elo, black_elo, white_moves, black_moves, my_color}` (Lichess win%-drop formula; Elo heuristic explicitly uncalibrated).

## 3. Existing narrative/coaching layers (candidate LLM inputs)

**`app/coaching.py`** — THE existing seam for this exact feature.
- `TemplateNarrator.narrate_leak(leak)` → `{"threat", "hanging", "plan", "summary"}` (`app/coaching.py:139-300`), keyed off `category`/`threat_motif`/`hung_square`/`best_san`/`win_prob_drop`/`phase`.
- `get_narrator()` factory (`app/coaching.py:494-511`) already reads `COACH_NARRATOR` env var; `'claude'` currently returns `TemplateNarrator` with an explicit **TODO block** (`app/coaching.py:16-22, 501-508`): "TODO(claude-narrator): when COACH_NARRATOR='claude', instantiate ClaudeNarrator instead… should use ANTHROPIC_API_KEY (not OAuth/Max)… Do NOT add an `anthropic` import to this module until that work is ready." Implement this seam, don't invent a parallel one.
- Surfaced via `GET /api/games/{id}/review` → `NarratedLeak.narration` (`app/models.py:341-343`) → `review.js::renderForesightCard` (`static/review.js:729-756`).
- `name_cluster(category, stats)` (`app/coaching.py:306-354`) feeds profile/insights cluster names.

**`app/profile.py`** — cross-game aggregator over `leaks`/`games` WHERE `my_color IS NOT NULL AND analysis_status='done'` (`app/profile.py:43-49`). Output: `top_leaks`, `by_phase`, `by_opening`, `by_color`, `hope_chess_rate`, `trend`. Surfaced at `GET /api/profile`.

**`app/motifs.py`** — pure tactical detector. Motifs: `hanging`, `fork`, `knight_fork`, `pin`, `skewer`, `discovered`, `back_rank` (`app/motifs.py:239-571`), each `{type, by, targets, detail}`. This closed set (plus `mate`/`missed_threat` synthesized in review.py) is the vocabulary the narrator speaks in.

**`app/insights.py`** — pure read-models: openings/mistakes/endgame insights (`app/insights.py:534-951`). Cross-game aggregates (win rates, adherence, clusters, time-trouble, capitalization, endgame accuracy) — candidate *context*, but cross-game, not per-game scoped.

**`app/endgame.py`** — pure material-signature classifier + stable-suffix finder (`app/endgame.py:87-208`); feeds insights endgame slice only.

## 4. Review API surface

Routes (`app/main.py`): `GET /api/games` (656), `POST /api/games/import` (587), `PATCH /api/games/{id}` (757), `POST /api/games/{id}/analyze` (783), `GET /api/games/{id}/status` (812), `GET /api/games/{id}` → `GameDetail` (710), `GET /api/games/{id}/review` → `ReviewResponse` (827-893) — **where per-game narrative already attaches** (`narration` on each `NarratedLeak`), `DELETE /api/games/{id}` (896), `GET /api/profile` (913), `GET /api/insights/*` (946, 977, 1028).

**Response shapes** (`app/models.py`): `GameDetail` (255-311), `NarratedLeak` (324-343), `GameAccuracySummary` (346-355), `ReviewResponse` (358-368).

**Natural attachment points**:
- **Minimal-diff**: real `ClaudeNarrator` behind `coaching.get_narrator()`'s `'claude'` branch — `NarratedLeak.narration` already carries free-form dict text to UI, zero schema change, reuses `GET /api/games/{id}/review`.
- **New-route**: `GET /api/games/{id}/narrative` (or field on `ReviewResponse`) for game-level summary — needs new Pydantic model and likely persistence/caching (LLM calls aren't free/instant like the template narrator).

## 5. Frontend seams

`static/review.js` (injected-`api` module, never imports `app.js` — `static/review.js:1-8`).
- `openGame(gameId)` (516-560): fetch `GameDetail` → `loadReviewData` if done, else `awaitAnalysisThenLoad` poll.
- `loadReviewData(gameId)` (605-615): fetches `ReviewResponse` into `_reviewData`, triggers `renderForesight(cursor)` + `renderGameSummary(summary)`.
- `renderForesight(ply)` (671-699) + `renderForesightCard(leak, kind)` (701-768): renders `narration.{threat,hanging,plan,summary}` per leak, keyed to replay cursor via `review:ply` event (940-943).
- New narrative panel mounts as: (a) another bucket in `renderForesightCard` if per-leak, or (b) new host element (e.g. `#review-narrative`) populated per `loadReviewData` if whole-game.
- `fetchJSON`/`postJSON` helpers (47-61) = HTTP pattern to reuse.

## 6. External-call precedent

**No outbound network calls exist anywhere today.** `requirements.txt` has no `anthropic`/`requests`/runtime `httpx` (`httpx>=0.27` is `# test-only` for TestClient). Stockfish is a local subprocess.

Env-var precedent for `ANTHROPIC_API_KEY` (all `os.environ.get`, resolved at call time, safe fallback): `STOCKFISH_PATH` (`app/engine.py:94`), `GAMES_DB` (`app/storage.py:219`), `CHESS_SKIP_ENGINE_AUTOSTART` (`app/main.py:107,245`), `COACH_NARRATOR` (`app/coaching.py:501`) — **the switch this feature flips to `'claude'`**, `REVIEW_BG_DEPTH`, `CHESS_USERNAME`, data-file overrides.

**Flag**: Anthropic API = app's **first-ever outbound dependency** (today fully offline/air-gapped). No existing retry/backoff/rate-limit pattern; nearest analog is `app/engine.py`'s soft/hard timeout pattern (`ENGINE_SOFT_TIME_S`/`ENGINE_HARD_TIMEOUT_S`, `app/engine.py:64,69`) and `EngineUnavailable`/`'failed'` degradation UX — imitate, don't invent.

## 7. Invisible contracts / risks

- **Pure-module invariant**: analysis, motifs, pgn, coaching, profile, accuracy, insights, endgame stay engine-free AND network-free — pytest passes with no binary and no API key. `coaching.py` docstring: no eager `anthropic` import. `ClaudeNarrator` behind the `COACH_NARRATOR=claude` branch with lazy import preserves the offline guarantee; default `template` path never touches network in tests.
- **White-POV vs mover-POV mixing**: `game_plies.eval_cp_white`/`mate_white` White-POV; `game_plies.win_prob` **mover-POV** (opposite conventions, same table — `insights.py:725-736`). Prompt-builder must apply correct POV per column; reuse `analysis.pov_score_to_white_cp`/`classify`/`win_prob_white`.
- **`lead_in_ply` ambiguity**: default `ply - 1` (`app/review.py:410`) — apply `insights.py:648-667`'s `>= 2` guard or the narrative overclaims foresight on every leak.
- **`explanation_json` always NULL** — plausible persistence target for cached LLM output, but docstring implies template-narrator ownership; spec must explicitly authorize any reuse/schema change.
- **Background-task singleton** (`app/review.py:99-103, 569-742`): `_tasks` keyed by `game_id`, sentinel `_ANALYZE_ALL_KEY=-1`. New narrative job must not collide with key space or `analysis_status` semantics — narrative needs its **own status field**; `set_my_color`/`retag_colors_by_aliases` (`app/storage.py:524-548, 551-601`) reset `analysis_status='pending'` and must also invalidate any narrative cache, or lifecycles silently desync (stale AI commentary on re-tagged games).
- **Engine lock adjacent**: LLM call = second independent async I/O source with higher latency than a depth-10 ply. Must NOT run inside `analyze_game`'s per-ply loop (would multiply worst-case interactive `/api/move` latency); run as independent async task/queue.
- **Stateless-server exception**: narrative cache extends the existing game-review SQLite exception, not a new one — but audit every invalidation path (`set_my_color`, retag, delete cascade).
- **Import-safety convention**: `storage.init()` never raises; main.py wraps storage in try/except and degrades. New Anthropic client follows `EngineUnavailable`-style import-safe graceful degradation, not uncaught exceptions in handlers.
- **Test-suite cost/determinism**: pytest offline + fast (~19s). LLM path excluded from default run (default `COACH_NARRATOR=template` + scripted fake seam analogous to `ScriptedEngine`).

## Risks for this feature (summary)

1. First outbound dependency — needs timeout/degradation UX modeled on `EngineUnavailable`.
2. POV mixing (White-POV cp vs mover-POV win_prob) in any prompt-builder.
3. Narrative cache invalidation on retag/color-change/delete must track `analysis_status` resets.
4. Depth-10 eval noise — swing thresholds must be conservative.
5. Best-move/PV only in `pos_cache` (EPD replay needed) or on leaks rows; pv2 has score but no move.
6. Pure-module/pytest offline invariant — lazy `anthropic` import, fake narrator seam for tests.
7. `lead_in_ply >= 2` guard to avoid foresight overclaim.
8. LLM job stays out of Stockfish pipeline critical path.
