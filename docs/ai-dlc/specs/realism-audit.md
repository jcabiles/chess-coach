# Delta spec — realism trace-audit harness (M3)

**Goal (one line):** a repeatable offline measurement of how human each bot
plays — the instrument that must exist before the ladder switches to Maia,
with a committed weakened-SF baseline as the before-picture.

Roadmap: Chapter 4 slice 3 (M3). Appetite 1–2 days. Anti-contamination
contract from the roadmap (Codex fold): **two position sets — open dev set
(tuning allowed) and a SEALED, hash-pinned eval set** used only for slice
acceptance and later as Chapter-5's frozen experiment instrument, versioned.

## Data: real human games per band

- Source: ONE lichess monthly dump, **streamed** (`curl | zstdcat`, stop
  after enough matching games — never the full ~30GB). Raw stream output is
  gitignored (`data/lichess/`); a fetch script documents the exact command.
- Bands (match the roster + M4 targets): 1300–1500, 1500–1700, 1700–1900,
  1900–2100. Filter: rated blitz/rapid, both players inside the band, normal
  termination.
- From each band-game: sample mid-game positions (ply 12–60, position not in
  the app's opening book) and record `(fen, humanMoveUci, band)`. The human's
  actually-played move is the ground truth for move-match.
- **Committed artifacts** (small, public-data-derived, committable):
  `data/realism/dev-<band>.jsonl` + `data/realism/eval-<band>.jsonl`
  (~100 dev + ~50 eval positions per band), plus
  `data/realism/EVAL_SHA256` pinning the eval files. Dev/eval split is
  random-but-seeded and disjoint by GAME (never the same game in both — no
  leakage via adjacent positions).

## Harness

New `tools/realism_audit.py` (repo has no tools/ yet — verify/ holds MCP
scripts; a python CLI belongs in tools/), runnable as
`.venv/bin/python -m tools.realism_audit --set dev|eval --personas all|id,..
--engine current|sf-only [--limit N]`:

- For each position and persona, obtain the bot's move EXACTLY as the API
  would (reuse the same call path shapes: Maia branch for wired personas
  unless `--engine sf-only`, which points MAIA_WEIGHTS_DIR at an empty dir;
  persona pipeline incl. blunder/mistake gates with seed = a fixed audit
  seed). Engine access ONLY through app.bot_engine / app.maia_engine
  (roadmap no-go); the analysis engine (app.engine) is never touched.
- Metrics per persona (written to a markdown + json report):
  1. **Move-match %** vs the human move, per band-appropriate set (a persona
     is audited against ITS band's positions; single-reference-move variance
     noted in the report: ±~4pp at n=150).
  2. **Blunder frequency + mean cp-loss**: bot's chosen move scored against
     `bot_engine.candidates(fen, k=5)` best (White-POV → mover-POV), loss
     ≥300cp = blunder, 50–250 = mistake; rates compared against the
     persona's dials in the report prose.
  3. **Engine-signature flags**: mate-in-1 conversion rate (humans miss
     some; ~100% = engine tell) over positions with a mate-in-1 available
     (found via python-chess scan, engine-free); 0-cp-loss streak length
     distribution.
- Determinism: fixed audit seed per (persona, position index); reports
  reproducible run-to-run given the same binaries/nets.
- Runtime honesty: ~0.6s/position/persona (SF budget dominates) — full
  dev-set sweep across 7 personas ≈ 15–20 min; `--limit` for smoke runs.

## Baseline (committed with this slice)

`docs/analytics/realism-baseline.md`: eval-set run with `--engine sf-only`
for ALL personas (the weakened-SF before-picture M4's "+8pts" measures
against) PLUS the current state (casey on Maia) — showing the skeleton's
already-visible move-match gain. Numbers + command lines + date + eval-set
hash in the header.

## Files

1. `tools/__init__.py`, `tools/realism_audit.py` — CLI + pure helpers
   (position loading, scoring, report rendering all pure; engine calls
   isolated in one async runner).
2. `tools/fetch_lichess_sample.py` — the streaming fetch + band filter +
   dev/eval sampler (game-disjoint, seeded); writes data/realism/*.jsonl +
   EVAL_SHA256. Run once here; re-runnable by anyone.
3. `data/realism/*.jsonl` + `EVAL_SHA256` — committed. `data/lichess/` —
   gitignored raw stream cache.
4. `tests/test_realism_audit.py` — pure tests: position loader validates
   fens/band; dev/eval game-disjointness on the COMMITTED files; eval-set
   hash matches EVAL_SHA256; mover-POV loss math (reuse fixture candidates);
   mate-in-1 scanner on known positions; report renderer smoke. NO engine
   in tests.
5. `.gitignore` — `data/lichess/`.

## Review folds (dual review 2026-07-18 — both reviewers FAILED v1; binding)

1. **Statistical power (both):** n=50/band cannot detect M4's +8pp (min
   detectable difference at n=150 ≈ 16pp). New sizes: **dev 200/band, eval
   500/band** (min detectable diff ≈ 10pp at 80% power; the M4 criterion
   text stays +8pp but its pass evaluation must quote the CI — the report
   prints per-metric 95% CIs so nobody over-reads a point estimate).
   Positions are cheap; runtime is managed via an oracle cache (below).
2. **Independent loss oracle (both — circularity):** blunder/mistake scoring
   uses a DEDICATED `app.engine.StockfishEngine` instance offline at a
   FIXED strong budget (depth 14, multipv 1), NOT `bot_engine.candidates()`
   at the same weak 0.3s the bots play with. Oracle evals cached per fen —
   shared across all personas in a band — so eval-set runtime ≈ 40 min
   (measured, not asserted, in the baseline doc). The roadmap's
   "engine calls only through existing modules" is satisfied (app.engine IS
   an existing module; the harness is offline, no live-server contention).
3. **Thresholds = the codebase's (refuter):** blunder >250cp, mistake
   50–250cp — `analysis.MISTAKE_MAX` / `bot_blunder.MISTAKE_LO/HI`. No
   third scheme; cite `classify()`.
4. **Both move-match metrics (refuter — scope substitution):** primary =
   human-move match (this spec); secondary = **Maia band-net agreement %**
   (cheap diagnostic per the original M3 roadmap text) — computed for SF
   personas; printed as N/A-circular for Maia-backed personas.
5. **Shared selection function (both — drift):** the route's persona
   move-selection block is EXTRACTED into a module-level
   `async def select_persona_move(bot, persona, fen, ply, seed, recent_moves)
   -> {"uci", "engine"}` in `app/main.py`; the route calls it (behavior
   identical — 1003-test suite is the guard) and the harness imports it.
   No copy-paste pipeline. A route-parity test (fakes) pins them together.
6. **Sampling bias mitigation (both):** stream a LONG window and take every
   k-th matching game (systematic thinning) rather than the dump head;
   ≤3 positions per game (clustering); dev/eval split unit = **ECO code**
   (whole ECO codes hash to one side — opening-family leakage), enforced by
   test; dump month + snapshot id recorded in every jsonl line + report.
   Maia-training-overlap caveat documented (nets trained ≤2019; use a
   recent month → temporal separation).
7. **Engine-signature metrics redefined (Codex):** mate-in-1 conversion
   uses a SEPARATE stratified probe set (~50 positions/band WITH a mate
   available, harvested during the same stream, human's actual move kept as
   the human-conversion baseline); zero-denominator → metric reported N/A,
   never 0/0. The 0-cp-loss STREAK metric is DROPPED (samples aren't
   consecutive traces) — replaced by best-move-agreement proportion vs the
   strong oracle, with CI.
8. **Schema (both):** each jsonl line = {gameId, fen, ply, humanMoveUci,
   band, eco, timeControl, whiteElo, blackElo, dump}. Tests enforce
   ECO-disjointness + per-game caps on the COMMITTED files.
9. **Report header pins:** stockfish + lc0 versions, engine options,
   platform, loop order, cold/warm policy, wall-clock of the run.
10. **Added tests (both):** harness/route parity via fakes; sf-only mode
    provably suppresses Maia; fake-engine end-to-end report smoke; CLI
    non-zero exit on missing binaries or EVAL_SHA256 mismatch; denominator
    guards. Suite stays engine-free.
11. **Named limitation:** personas audited against their own band only;
    cross-band confusion diagnostics deferred to the ladder-switch slice.

## Out of scope

Changing any bot behavior (measurement only); M4's actual switch; Chapter-5
experiment wiring; think-time metrics; positions from the user's own games
(privacy default per B1 — public lichess data only).

## Constraints

Suite green with no binaries (harness itself needs binaries at RUNTIME, its
tests do not); pure modules stay engine-free; sealed eval set NEVER used for
tuning (only acceptance/baseline runs — the harness prints a loud warning
when `--set eval` runs); tokens/none UI; Conventional Commits.

## Verify-by

1. `.venv/bin/python -m pytest -q` green; ruff clean.
2. `python -m tools.realism_audit --set dev --personas casey --limit 20`
   completes offline and prints a per-metric table.
3. Baseline doc committed with real eval-set numbers for all personas
   (sf-only) + casey-on-Maia; eval hash matches EVAL_SHA256.
4. Committed eval/dev sets are game-disjoint (test-enforced).
