# Delta spec — B5: Causal human-like blunder + style model (signature plan-fixation)

**Goal (one line):** make the persona bots fail **causally and input-side** — the
bot pursues its own plan and misses the opponent's threat *because its attention
was elsewhere*, never via an output-side dice roll — by gating threat-responding
moves out of the engine's candidate set so the bot plays its best *remaining*
(plan) move; research-calibrated per persona; deterministic per seed.

Slice: **B5** of [`../roadmap/training-and-portfolio.md`](../roadmap/training-and-portfolio.md)
Chapter 3 (N3 · P2 — the core "realistic bots" requirement). Depends on B4
(shipped — the persona ladder). Contracts:
[`../contracts/causal-blunder.md`](../contracts/causal-blunder.md). Gate 1 confirmed
2026-07-17: **signature plan-fixation (mechanism A) + low-band drop; defer C
(calculation decay)** · **research-calibrated blunder rates** · **internal only**
(existing game-review coach narrates from analysis; no new surfacing) ·
**refuter-only review** (Codex infra-down).

## The model (input-side, never random)

Every induced blunder must answer the **anti-randomness triple** — (1) what the
bot was attending to (its plan), (2) what it therefore didn't see (the threat),
(3) why that miss is plausible at this rating. If any answer is "the dice said
so", the design has regressed to random weakening. This triple is computed for
each blunder and available internally (for tests + future coach narration).

### NEW `app/bot_blunder.py` (pure, engine-free, seedable)
- **`plan_attention_set(recent_bot_moves, board) -> set[int]`** — the squares the
  bot is "attending to": the from/to squares of its last `PLAN_MOVES` (=4) own
  moves, ∪ the squares currently attacked by the bot's pieces standing on those
  to-squares (its active pieces' influence). Cheap python-chess board
  introspection. Empty early (few own moves) → the gate can't fire yet (fine —
  matches "survive the opening").
- **`opponent_threat(board) -> Threat | None`** (pure, ENGINE-FREE):
  - **Mate-in-1 scan (engine-free — refuter HIGH):** on the null-move board (or
    directly, since it's the opponent to move), iterate the opponent's legal moves
    and test `board.push(m); is_checkmate()`. If any mates → the strongest threat
    is `type='mate'` (top severity). This is pure python-chess (~30 pushes) — NOT
    the engine null-probe `review.py` uses. (Deeper mate threats are not detected
    engine-free and are simply not "missable" in v1 — safe: the bot plays normally.)
  - Else run `motifs.detect_motifs` / `hanging_pieces` from the opponent's POV and
    take the **strongest material threat**. `Threat = {squares: set[int], severity_cp:
    int, type, detail}` where `squares` = the threat's key squares (target + the
    threatened piece's square; for a fork, the forked squares) and **`severity_cp` =
    the material at risk in centipawns** (mate → a large sentinel `MATE_SEVERITY`;
    hanging piece → its `PIECE_VALUES`; fork → the value of the more valuable forked
    piece; from `motifs` `type`+`see`/`PIECE_VALUES`). Ordering: mate > queen(900) >
    rook(500) > minor(300) > pawn(100). No win-prob, no engine eval.
- **`should_blunder(persona, phase, ply, seed, threat, plan_set) -> bool`** — the
  mechanism-A gate. Returns true iff:
  - a `threat` exists with **`severity_cp >= MIN_MISSABLE` (=200cp)** — trivial
    (pawn) threats don't count as a "blunder to miss", AND
  - the threat is **off-plan**: `off_plan_score(threat.squares, plan_set) >
    persona.threatDistance`, where **`off_plan_score = |threat.squares \ plan_set|
    / |threat.squares|`** ∈ [0,1] (fraction of the threat's key squares OUTSIDE the
    bot's attention). Lower elo → lower `threatDistance` → misses threats even
    partly on-plan; higher elo → only fully-off-plan threats. `plan_set` empty
    (opening / no recentMoves) → `off_plan_score = 1.0` but the phase gate below
    still suppresses opening blunders, AND
  - a **seeded** draw `rng < fire_prob` where `rng = Random(hash((seed, ply)))
    .random()` and `fire_prob = persona.blunderRate × phase_gate(phase) ×
    hazard(ply) × severity_damp(severity_cp)`:
    - `phase_gate`: **0 in the opening** (`ply < OPENING_PLIES`); 1.0 middlegame;
      endgame NOT reduced (endgame blunders stay per research).
    - `hazard(ply)`: a rising schedule — ~0 before a band-dependent first-blunder
      ply (low bands ~move 16, high ~move 30), rising after. Keep it a simple
      documented monotone function of `ply` (e.g. clamped ramp), tunable.
    - **`severity_damp`**: **bigger threats are missed LESS often** (a 1350 rarely
      misses a mate/queen, more often a minor) — e.g. `min(1, MISS_REF /
      severity_cp)` with `MISS_REF ~350cp`, so a mate/queen is heavily damped, a
      knight is near-full. This is what stops the "misses mate-in-1 every time"
      unhumanness the pure severity gate would otherwise cause (refuter HIGH).
  All RNG derives from `hash((seed, ply))` — never bare `random`.
- **`pick_survivor(candidates, board, threat) -> idx | None`** (pure) — among the
  engine's candidates, drop those that **NEUTRALIZE the original threat**: for each
  `c`, `c` neutralizes iff `opponent_threat(board after c)` is absent OR is a
  DIFFERENT threat, where **"same threat" = same `type` AND the original target
  square still ∈ the new threat's `squares`** (so capturing/blocking/defending/
  moving the piece all count as neutralizing; a candidate that fixes X but hangs a
  new piece Y is ALSO treated as neutralizing X — the bot "reacted"). Survivors =
  candidates that leave the original threat intact (the bot ignored it). Return the
  **best survivor by mover-POV scoreCp, tie-broken by lowest candidate index**
  (stable → deterministic). If no survivors (every candidate addresses it) → return
  `None` (no forced blunder). `None` threat → `None`.
- **Route flow (see Server): compute the gate FIRST, raise k ONLY to blunder** —
  the route calls `opponent_threat` + `should_blunder` (both pure, cheap) BEFORE
  choosing the candidate budget. Only when the gate fires does it request the wider
  `candidates(k=CAND_K, elo)` and call `pick_survivor`; otherwise it takes the
  UNCHANGED B4 path (opening softmax k=5 / post-opening best k=1). This preserves
  B4's late-play behavior for the common no-blunder case and confines the cost +
  the k increase to induced-blunder moves. `reason = {attending: plan_set, missed:
  threat, why: severity+off_plan}` is assembled when a blunder is played (internal).
- **Low-band drop (mechanism B)** is folded into A: when the opponent's LAST move
  created the threat and the persona is the ladder floor, `off_plan_score` +
  `blunderRate` already produce the one-move-miss. (Our ladder is 1350–2000, all
  above the <1200 hope-chess band, so B is a mild edge case here; noted for when
  sub-1200 personas are added.)

### `app/personas.py` + `data/personas.json` — new dials (graceful defaults)
Add to the `Persona` dataclass + `_parse_persona` (default from `elo` so an old
`data/personas.json` still loads — mirror the temperature-from-style fallback):
- **`blunderRate`** (float ∈ [0,1], base middlegame fire probability,
  **research-calibrated per band** from `error-rates-by-rating`): Casey 1350
  highest → Vera 2000 lowest. Default formula, monotone decreasing in elo, e.g.
  `clamp(0.9 - (elo-1300)/1000, 0.03, 0.9)` (Casey≈0.85, Morgan≈0.65, Alex≈0.40,
  Vera≈0.20 — T1/T2 tune to the research band table).
- **`threatDistance`** (float ∈ [0,1], the `off_plan_score` threshold a threat must
  exceed to be missed; lower elo → lower threshold → misses more): default e.g.
  `clamp((elo-1200)/1200, 0.15, 0.85)` (Casey≈0.13→floor 0.15, Vera≈0.67).
`_validate` bounds both to [0,1]; sync committed `data/personas.json`. New fields
auto-flow into `/api/bot/status` (additive, safe).

### `app/main.py` — wire the gate into the persona path ONLY
- `BotMoveRequest` gains **`recentMoves: list[str] = []`** (last N bot-relevant
  UCI plies; default empty → bare `{fen}` still B3-valid).
- **Persona branch, gate-FIRST (preserves B4 late play):**
  1. `plan = bot_blunder.plan_attention_set(recentMoves, board)`;
     `threat = bot_blunder.opponent_threat(board)` (both pure, cheap).
  2. `if threat and bot_blunder.should_blunder(persona, phase, ply, seed, threat,
     plan)`: request `candidates(fen, k=CAND_K=5, elo=persona.elo)`, `idx =
     bot_blunder.pick_survivor(cands, board, threat)`. If `idx is not None` → play
     `cands[idx]` (the causal blunder; assemble `reason`).
  3. **Else (no threat / gate didn't fire / no survivors) → the EXISTING B4 path
     UNCHANGED:** opening (`ply<OPENING_PLIES`) `candidates(k=SAMPLE_K=5, elo)` +
     `weighted_choice`; post-opening `candidates(k=1, elo)` best. So a quiet
     position at late ply still uses **k=1 + best move** exactly as B4 — the
     `test_persona_late_ply_plays_best` (k==1, plays-best) assertion holds whenever
     no blunder is induced. **Test-update note (refuter HIGH):** that B4 test uses a
     quiet position + a seed; verify it does NOT trigger the gate (no off-plan
     threat) → it stays green as-is; if it happens to fire, add a `recentMoves`/
     seed to the test so it exercises the intended quiet no-blunder path. Only
     `tests/test_bot_personas_api.py` may need this touch — flag it, don't silently
     change semantics.
- **Selection is seeded across the WHOLE game** — the gate's `should_blunder` draw
  uses `hash((seed, ply))` at every ply (B4's opening `weighted_choice` seed is
  unchanged). `reason` is internal (not in the v1 response).
- **Legacy no-persona branch stays byte-identical to B3** (k=1, idx 0, no gate).
- **CRITICAL:** the gate lives ONLY here. The eval shown to the user
  (`refreshAnalysis` via the shared `app.engine`) must NEVER route through the
  gated path — bot weakness ≠ the user's analysis.

### `static/botplay.js` — send recent moves
In `requestBotMove`, add `recentMoves` to the POST body = the last N plies of
`g.movesUci` (the client already owns full history; additive, no descriptor
change). Nothing else changes.

## Out of scope
- **Mechanism C — calculation decay / defensive-resource blindness in deep lines**
  (Gate 1 defer — needs engine-internal lookahead manipulation, impractical with
  SimpleEngine) · Maia move-source (not installed; the gate is Maia-free) ·
  **move-matching validation vs a lichess corpus** (heavy infra — B5 validates via
  determinism + ladder-monotonicity + the anti-randomness triple instead) ·
  surfacing "why" to the user / new coach narration (internal only — the existing
  review pipeline already auto-analyzes + narrates bot blunders) · sub-1200
  personas · clocks/time-pressure spike (mechanism D — needs B7) · any DB schema
  change · gating the analysis/eval path.

## Constraints (profile)
- **Deterministic/seedable** — all B5 RNG from `hash((seed, ply))`; same
  seed+persona+moves ⇒ identical game. **Server stateless** — plan context rides
  the request (`recentMoves`). **Engine isolation** — the gate runs over the
  isolated `BotEngine` candidates; never touches `app.engine`; no `note_interactive`.
  **Pure modules** — `bot_blunder.py` engine-free/no-I/O, like `motifs.py`; do not
  add engine/I/O to `motifs`/`analysis`. **No DB schema change.**
- **Bot weakness ≠ user analysis** (the load-bearing invariant): gate only
  `/api/bot/move`'s persona selection.
- **Legacy `{fen}` = B3 byte-identical.** Feature branch + PR; commit only
  implemented+verified+reviewed.

## Verify-by
1. `pytest -q` + `ruff check app tests` green. **`bot_blunder.py` unit tests**
   (pure, NO engine): `plan_attention_set` from known recent moves; `opponent_threat`
   surfaces a planted **mate-in-1 (engine-free scan)**, hanging queen, fork, and
   back-rank with correct `severity_cp` ordering (mate>queen>rook>minor); a pawn-only
   threat is below `MIN_MISSABLE`; `should_blunder` fires ONLY when off-plan
   (`off_plan_score>threatDistance`) + `severity_cp>=MIN_MISSABLE` + seeded draw hits,
   NEVER in the opening (phase gate), and a mate/queen is missed far less often than a
   minor (`severity_damp`); `pick_survivor` drops threat-neutralizing candidates
   (same-type+target rule) and returns the best surviving PLAN move tie-broken by
   index, `None` when every candidate addresses it; **deterministic** (same seed ⇒
   same idx, twice). `personas` dials load with elo-derived defaults from an old JSON
   (monotone across the ladder). `/api/bot/move`: a planted off-plan-threat position
   plays the gated blunder; a **quiet late-ply position stays k=1 + best (B4-parity)**;
   **bare `{fen}` + no-persona stay B3-identical**. Mover-POV correct for a Black bot.
2. **Ladder-monotonicity harness** (offline, fake/real engine): on a small fixed
   tactical suite, a higher persona neutralizes threats a lower persona misses
   (stronger bot blunders less) — a cheap coherence invariant.
3. Browser (Playwright/manual, real engine): play a persona (e.g. Casey) into a
   position where you set up an off-plan threat (e.g. a hanging piece on the far
   wing) → the bot **visibly misses it and plays its plan move**, and the SAME
   position replays identically under the same seed; a stronger persona (Vera)
   defends it. Confirm the **user's eval bar / Analysis is unaffected** (full
   strength — the gate didn't leak). A finished gated game auto-analyzes and the
   existing coach flags the bot's blunder.
