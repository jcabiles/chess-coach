# Research — Insights / Analytics Dashboard

Pre-build research for a game-analytics dashboard. Four parallel passes: (A) do
respected players/coaches think game analytics help, (B) what existing products do,
(C) feasibility of the candidate features against this codebase. Sources listed per
section. This record justifies the design decisions in
`docs/ai-dlc/specs/insights-dashboard.md`.

## A — Does game analytics help improvement? (expert / coach opinion)

**Verdict: skeptical-but-conditionally-useful.** No respected coach or canonical
improvement resource treats analytics dashboards as a *driver* of improvement. The
defensible claim is narrow: aggregate stats are a **diagnostic/triage tool** — good for
pointing at *which* phase/theme to work on — while the actual work (deep game analysis,
tactics, calculation, stronger opposition) is unchanged.

**For (conditional):**
- FM Nate Solon (data scientist / coach): the highest-signal thing to study is *patterns
  of mistakes* — "many mistakes result from the same thought-process error." Aggregation
  across games is what surfaces those patterns.
- Reviewer consensus: useful mainly for **plateaued intermediates (~1000–1800)** who
  can't easily self-diagnose their systematic leak.

**Against:**
- The improvement canon simply omits it. Ben Johnson's *Perpetual Chess Improvement* four
  pillars (play, analyze, calculate/pattern-train, coach/peers) and Solon's "5 reasons
  you're not improving" don't mention stats at all. That absence is the strongest signal.
- Dan Heisman: passive engine consumption teaches nothing — a number gives the "what,"
  never the "why."
- **ACPL / single accuracy % are weak metrics:** context-blind, gameable, and a Goodhart
  trap (optimizing accuracy rewards avoiding complexity → real strength flatlines).
- Rating/metric obsession is a recognized progress-killer.

**Design implications (drove the spec):** build a **triage router, not a report card** —
every insight links to a concrete action; de-emphasize/omit a headline accuracy/Elo
number; lean into what only aggregation gives (recurring-mistake clustering, weakest
phase, results-by-opening, time-trouble); frame as periodic review, not a live per-game
scoreboard; be honest about thin data.

Sources: Nate Solon (chess.com Coach-of-the-Month; Zwischenzug), Ben Johnson *Perpetual
Chess Improvement*, Dan Heisman (danheisman.com), MyChessPlan (ACPL vs accuracy), chess.com
ACPL blog, Lichess Insights forum threads, checkmatex Aimchess review, ChessMood/GM
Gabuzyan on rating obsession. (Con case is better-sourced than the pro case.)

## B — Existing product landscape

- **Chess.com Insights** (Diamond-only): games/openings/tactics/moves/calendar/geography;
  accuracy by move/color/phase, opening performance, tactic found-vs-missed. Gripes:
  paywall, time-control silos, Insights vs Game-Review accuracy mismatch, secret formula.
- **Lichess Insights** (free): pivot-table metric×dimension×filter; ACPL, opportunism,
  luck, open accuracy formula (harmonic mean). Gripe: "you must know what to ask."
- **Aimchess** (freemium): 6 scored categories — openings, tactics, endgames, **advantage
  capitalization**, **resourcefulness**, **time management** — + "train on your own
  mistakes." Praised for correcting self-misdiagnosis; criticized as biased/paywalled/
  cloud-dependent, "diagnostic not cure."
- **DecodeChess**: per-position LLM-style explainer (Threats/Plans/Tactics). Boundary — we
  are deterministic, don't compete here.
- **Chessable/ChessMonitor/OpeningTree**: adjacent (study SR, opponent scouting, opening
  trees). Not cross-game weakness profiling from your own games.

**Valued (actionable):** cross-game weakness ranking that corrects self-misdiagnosis;
phase-specific weakness; **time-trouble tied to blunders** (most-cited single metric);
recurring-mistake/personal-mistake-database (everyone recommends, no product automates);
opening results by line; train-on-your-own-mistakes; opportunism/luck.

**Vanity (ignored):** geography maps, time-of-day, single blended accuracy %, estimated
Elo per game, peer "similar players," glamour move labels.

**Gaps a local deterministic single-user app can uniquely fill:** true recurring-mistake
profiling across full history; pre-blunder foresight as a first-class metric;
time-trouble→blunder done right; honest/transparent metrics (no secret score); no paywall/
privacy-tradeoff/time-control silos; guided weakness surfacing (push top weaknesses vs.
Lichess's build-your-own pivot).

Sources: official Chess.com Insights help + ChessGoals breakdown, Lichess Insights blog +
accuracy page + forum critiques, Aimchess reviews (checkmatex, Chessily, Medium),
DecodeChess review + Chrome-store reviews, ChessMonitor/OpeningTree/Chessable pages,
ChessChatter "measure improvement without rating," ChessWorld "personal mistake database."

## C — Feasibility against this codebase

All candidate features are computable **deterministically** (python-chess + Stockfish +
SQLite, no LLM). The review pipeline already writes most of the needed data.

**Baseline the pipeline already produces** (`app/review.py::analyze_game` → `game_plies`,
`leaks`; `app/profile.py::build_profile`): per-ply White-POV eval / win_prob / is_user_move
/ **clock_centis**; user-color leaks classified by win-prob drop with category, phase,
hung_square, threat_uci/motif, best_uci, **lead_in_ply**, tags_json; cross-game aggregates
by category/phase/opening/color + hope-chess rate + weekly trend.

Feature-by-feature (effort S/M/L):

- **Win% by opening — S.** All fields already tagged (`games.eco/opening/result/my_color`,
  120/120 games). Pure SQL. Catch: small samples → ECO-family aggregation + min-sample gate.
- **Opening adherence — S–M (honest form).** No offline "respected" definition exists.
  Reuse `app/repertoire.py` tree (single prepared move per your-turn node) for **repertoire
  adherence**; `app/book.py::is_in_book` (book.py:208) + `openings.identify` for named-theory
  **book-exit**; opening-phase accuracy for soundness. True "respected by masters" needs the
  Lichess masters API (not downloadable, network-gated) — opt-in only. "In book" = named,
  not endorsed — don't oversell.
- **Recurring-mistake clustering — M.** `coaching.name_cluster` already emits "Missing
  knight forks in the middlegame (14× so far)." Needs a multi-dim GROUP BY over `leaks` +
  a ranked panel. Capped by `motifs.py` taxonomy (generic `missed_threat` bucket dominates).
- **Foreseeable-rate — S–M.** `lead_in_ply < ply` fraction + mode of `threat_motif`. Pure
  aggregation over `leaks`. Narrow definition (only-move seed, 3-ply lookback) — frame honestly.
- **Time-trouble → blunder — S.** *Confirmed clocks survive:* `pgn.py` parses `%clk` →
  `clock_centis`, `storage.py` persists it end-to-end. "<10s remaining → blunder-rate" = a JOIN.
- **Conversion / resourcefulness — S–M.** Scan stored eval curves (`win_prob` + `games.result`)
  for sustained winning/losing stretches → converted/held. No engine calls.
- **Endgame by material type — S (+ M for tablebases).** Material-signature classification
  trivial (`board.pieces`, bishop square color); endgame accuracy/conversion by type from
  stored evals. Optional **Syzygy 5-man WDL** (378 MB) gives deterministic "threw a
  theoretical win/draw" but only engages ≤7 pieces and is network/disk-gated (user runtime only).
- **Spaced repetition on own blunders — M–L.** Puzzle content free (blunder FEN + best move
  stored); needs schema v2 + scheduler (recommend **SM-2**) + a new interactive puzzle UI.
  The only feature needing real new infrastructure.

**Two cross-cutting limits:** background evals are **depth-10** (noisier thresholds); all
insights gated on `my_color` tagged + `analysis_status='done'`.

**Frontend map (feasibility of the surface):** vanilla ES modules, no build step; single
`static/index.html` SPA; `app.js` orchestrates + injects an `api` into feature modules.
Adding a tab = button (`index.html:161-167`) + panel div (~`:251`) + a module + **two**
hardcoded tab-array edits (`app.js:2005`, `review.js:515`) + a CSS link. `/api/profile`
already returns openings/mistakes/phases/trend. Deep-linking an insight to a position is
trivial: `loadFen` (`app.js:573-611`) or `openGame(id)` (`review.js:489`) + `goto(ply)`
(`app.js:539`). No URL router (only needed for shareable links). No committed FE tests —
verify via Playwright-MCP.
