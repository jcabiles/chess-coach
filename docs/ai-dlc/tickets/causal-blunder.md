# Tickets — B5: Causal human-like blunder model

Spec: [`../specs/causal-blunder.md`](../specs/causal-blunder.md).
Branch: `feat/causal-blunder` off up-to-date main.
Wave plan (disjoint owners): **W1:** T1 ∥ T2 → **W2:** T3 (needs T1+T2) →
**W3:** T4 (needs T3) → **W4:** T5 harness → T6 verify → T7 review → T8 close.
Refuter-only review (Codex infra-down).

## T1 — `app/bot_blunder.py` the causal gate + tests (W1) — CORE, heavy
New PURE, engine-free, seedable module:
- `plan_attention_set(recent_bot_moves, board) -> set[int]` — from/to of the last
  `PLAN_MOVES=4` own moves ∪ squares attacked by the bot's pieces on those
  to-squares.
- `opponent_threat(board) -> Threat|None` — **engine-free**: FIRST a pure mate-in-1
  scan (iterate opponent legal moves → `board.push(m); is_checkmate()`) → `type=
  'mate'`, top severity; else `motifs.detect_motifs`/`hanging_pieces` (opponent POV)
  → strongest MATERIAL threat. `Threat={squares:set[int], severity_cp:int, type,
  detail}`; `severity_cp` = material at risk (mate→`MATE_SEVERITY`; hang→piece value;
  fork→higher forked value). Order mate>queen(900)>rook(500)>minor(300)>pawn(100).
- `should_blunder(persona, phase, ply, seed, threat, plan_set) -> bool` — fires iff
  `severity_cp>=MIN_MISSABLE(200)` + off-plan (`off_plan_score = |threat.squares \
  plan_set|/|threat.squares| > persona.threatDistance`) + seeded
  `Random(hash((seed,ply))).random() < blunderRate × phase_gate × hazard(ply) ×
  severity_damp(severity_cp)`. `severity_damp = min(1, MISS_REF(~350)/severity_cp)`
  → mate/queen missed far less than a minor (kills the "misses mate-in-1 every time"
  unhumanness). Phase gate: 0 opening, full middlegame, endgame not cured. Hazard: a
  documented monotone ramp in ply (low bands first-blunder ~16, high ~30). All RNG
  from `hash((seed,ply))` — no bare random.
- `pick_survivor(candidates, board, threat) -> idx|None` — drop candidates that
  NEUTRALIZE the original threat (`opponent_threat(board after c)` absent OR
  different, where "same" = same `type` AND original target square still ∈ new
  `squares`); survivors = candidates leaving it intact; return **best survivor by
  mover-POV scoreCp, tie-broken by lowest index** (deterministic); `None` if none.
- **Owns:** `app/bot_blunder.py`, `tests/test_bot_blunder.py`
- **Done:** `pytest tests/test_bot_blunder.py -q` green — attention-set; `opponent_
  threat` surfaces planted **mate-in-1 (engine-free)**/hanging-queen/fork/back-rank
  w/ correct `severity_cp` order + pawn below MIN_MISSABLE; `should_blunder` off-plan
  + ≥MIN_MISSABLE + seeded-hit + never-opening + mate/queen damped below a minor;
  `pick_survivor` drops neutralizers (type+target rule), best-survivor tie-broken by
  index, `None` when all address it; **deterministic (same seed ⇒ same idx twice)**.
  Full `pytest -q` + `ruff` green.

## T2 — persona blunder dials + tests (W1)
`app/personas.py`: add `blunderRate` + `threatDistance` to the `Persona` dataclass
+ `_parse_persona` (elo-derived defaults so an old `data/personas.json` still
loads) + `_validate` bounds. Update `data/personas.json` with **research-calibrated**
per-band values (Casey 1350 highest blunderRate → Vera 2000 lowest). Reference
`docs/design/research/human-play-modeling/error-rates-by-rating.md` for the band
numbers.
- **Owns:** `app/personas.py`, `data/personas.json`, `tests/test_personas.py`
- **Done:** `pytest tests/test_personas.py -q` green — new dials present with
  elo-derived defaults when absent from JSON; monotone across the ladder (higher
  elo → lower blunderRate); old-JSON (no dials) still loads; `_validate` bounds.

## T3 — `app/main.py` wire the gate, gate-FIRST (W2, after T1+T2) — HOTSPOT
`BotMoveRequest` gains `recentMoves: list[str] = []`. Persona branch, **gate-first
so B4 late play is preserved:** compute `plan_attention_set` + `opponent_threat`
(pure) → if `threat and should_blunder(...)`: `candidates(k=CAND_K=5, elo)` +
`pick_survivor` → play the survivor (blunder); **else the EXISTING B4 path
UNCHANGED** (opening `weighted_choice` k=5 / post-opening best k=1). So a quiet
late-ply position keeps k=1+best. Seed the gate draw whole-game via
`hash((seed,ply))`. Legacy no-persona branch **byte-identical to B3**. Gate is
bot-move only — never touches `app.engine`.
- **Owns:** `app/main.py`, `tests/test_bot_causal_api.py` (new). **May also need a
  one-line touch to `tests/test_bot_personas_api.py::test_persona_late_ply_plays_
  best`** IF that quiet position happens to trip the gate — first confirm it stays
  green as-is (expected: no off-plan threat → k=1+best preserved); only adjust it
  (add recentMoves/seed to keep it a quiet no-blunder case) if it actually fires.
  Do NOT weaken it.
- **Done:** `pytest -q` green (incl. the B4 persona late-ply parity test) — persona
  path plays a gated blunder for a planted off-plan-threat position; a quiet late
  position stays k=1+best; **bare `{fen}` + no-persona B3-identical**; Black-bot
  mover-POV correct; recentMoves default keeps bare requests valid.

## T4 — `static/botplay.js` send recentMoves (W3, after T3)
In `requestBotMove`, add `recentMoves` to the POST body = last N plies of
`g.movesUci`. No descriptor change; nothing else.
- **Owns:** `static/botplay.js`
- **Done:** `node --check` clean; `pytest -q` green; reasoning trace: recentMoves
  sent correctly, no B2/B3/B4/B6 regression (busy/replyToken/save/persona/takeback).

## T5 — Ladder-monotonicity harness (W4)
Offline test (`tests/test_bot_blunder_ladder.py`): on a small fixed tactical suite,
a higher persona neutralizes threats a lower persona misses (stronger blunders
less) — the coherence invariant. Deterministic under fixed seeds.
- **Owns:** `tests/test_bot_blunder_ladder.py`
- **Done:** the monotonicity assertion passes; deterministic.

## T6 — Browser verification (W4)
Spec Verify-by-3: play Casey into an off-plan threat (hanging piece far wing) → bot
visibly misses it + plays its plan move; same seed replays identically; Vera
defends it; **user's eval bar/Analysis unaffected** (full strength — no leak); a
finished gated game auto-analyzes + the coach flags the bot blunder.
- **Done:** every item observed; test games cleaned from the DB.

## T7 — Dual review of the diff (W4, after T6)
Refuter (+ Codex if it recovers): survivors-logic soundness, engine-free mate
detection, determinism, severity band (no missed mate-in-1), B3/B4 parity, no
analysis leak, latency of per-candidate threat re-detection. Fold; re-verify.
- **Done:** resolved/accepted; suite green.

## T8 — Close-out (W4, after T7)
User pass/fail → mark B5 `[x]`; note B7 (clocks) the last Phase-B slice;
`pytest`/`ruff`/`node`; commit; push; PR.
- **Done:** PR open.

## Notes
- Live-reload hazard: one feature branch.
- Appetite guard (~3 days): if over, cut order — persona-temperature softmax for
  non-blunder play (best-move is fine) → the mate-in-1 pure scan (motifs-only) →
  hazard-schedule nuance (flat middlegame rate is the minimum). Never cut:
  input-side survivors logic (the causal core), determinism, B3 parity, no
  analysis leak, severity band (don't miss mate-in-1).
