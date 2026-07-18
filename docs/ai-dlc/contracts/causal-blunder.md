# Contracts — B5: Causal human-like blunder + style model

Read-only scan (contract-mapper, 2026-07-17). Evidence `file:line`.

## Move-selection interception (the seam)
- `POST /api/bot/move` (`main.py:637-733`): 3 branches → one `cands[idx]` play
  block (`main.py:730-733`). Legacy no-persona = `candidates(fen,k=1)` idx 0
  (**B3 byte-identical — B5 must gate ONLY the persona path**). Persona opening
  (`ply<OPENING_PLIES=8`) = `candidates(k=5,elo)` + `weighted_choice`. Persona
  post-opening = `candidates(k=1,elo)` idx 0.
- `bot_engine.candidates(fen,k,elo)` (`bot_engine.py:369-421`) returns best-first
  `[{uci,san,scoreCp}]` (White-POV; mate=±MATE_CP=100000). `k>1` is the documented
  persona-consumption seam. **B5 intercepts where `idx` is computed** (gate + pick
  best surviving candidate).
- **Post-opening k is 1 today → B5 must raise k** to get a candidate SET to
  re-rank. Larger k at the fixed `BOT_MOVETIME_S=0.3` spreads MultiPV thinner →
  noisier scoreCp (tension: enough candidates vs score accuracy).

## Input-side gate WITHOUT Maia — the pattern already exists
- `review.py:461-499` already does it: take the position where it's the
  OPPONENT's turn (null-move/"pass" board), call `motifs.detect_motifs(null_board)`
  to enumerate what the opponent threatens + `motifs.hanging_pieces(after, my_color)`
  for what hangs; a null-move engine probe finds the single strongest threat +
  `is_checkmate()`. **B5 mirrors this** to identify "the threat to miss", then
  drops threat-responding moves from `candidates()` so the persona plays its best
  remaining (plan) move.
- `app/motifs.py` is **pure, engine-free, synchronous, python-chess-only** — safe
  in-request, no lock/await. `detect_motifs(board,move) -> [{type,by,targets,detail}]`
  (type ∈ hanging/fork/knight_fork/pin/skewer/discovered/back_rank, side-to-move
  POV); `hanging_pieces(board,color) -> [{square,piece,see}]`; `see(board,move) ->
  cp` (SEE severity, no x-ray). Severity order: mate > hanging queen > fork >
  minor, from `type` + `PIECE_VALUES`/`see`. Needs a `chess.Board` — already parsed
  at `main.py:653`, no extra parse.

## Win-prob / severity axis
- `analysis.py` pure. `win_prob_from_cp(cp)` (Lichess `1/(1+exp(-0.00368208cp))`,
  mover-POV) = the Regan-Haworth curve input + severity sizing (target WP drop
  0.20–0.35). `pov_score_to_white_cp`, `cp_loss`, `classify`, `game_phase` all
  available. **Mover-POV flip already in the endpoint** (`main.py:697-702`).
- **Two MATE_CP constants:** `analysis.MATE_CP=10000` vs `bot_engine.MATE_CP=100000`
  (`candidates` scoreCp uses the latter). Harmless in win-prob (saturates) but
  don't mix axes when sizing severity.

## Persona dials (loader-touching)
- `Persona` frozen dataclass (`personas.py:39-51`): id/name/elo/style/description/
  temperature. New B5 dials (blunder rate, threat-blindness, plan-persistence,
  style bias) require: dataclass fields + `_parse_persona` reads WITH graceful
  defaults (mirror the temperature-from-style fallback) + maybe `_validate` bounds
  + sync committed `data/personas.json`. `as_dict()` auto-flows new fields into
  `/api/bot/status` → JS catalog (additive, safe).

## Request context (plan-salience) — additive, client-ready
- `BotMoveRequest`: fen, personaId?, ply=0, seed?. Client already owns full history
  (`botplay.js:695-706` builds body from descriptor `movesUci`/seed/ply). **B5 adds
  e.g. `recentMoves: list[str]` (default empty → bare request still B3-valid),
  sliced from `g.movesUci`.** Per-game `seed` already minted once at start — but
  **used opening-only today**; B5 must extend seeded selection past OPENING_PLIES.

## Isolation + second-pass cost
- `candidates()` on the ISOLATED BotEngine (own process/lock, never `app.engine`,
  no `note_interactive`). A 2nd ENGINE pass doubles bot latency (0.3s + 5s
  watchdog) — but a **pure-motif plausibility check is nearly free**. Prefer ONE
  higher-k `candidates()` + motif plausibility over a 2nd engine call. Don't pass
  `elo` on a same-persona 2nd call (needless cold TT respawn).

## Invariants (protect-list)
- **Deterministic/seeded**: derive all B5 RNG from `hash((seed, ply, ...))`, never
  bare `random`. **Server stateless**: plan context rides the request. **Engine
  isolation**: stay on `get_bot_engine()`. **Pure modules**: B5 gating in a NEW
  pure module, not by adding engine/I/O to motifs/analysis. **No DB change**.
- **CRITICAL — bot weakness ≠ user's analysis**: the gate lives ONLY in
  `/api/bot/move` selection. The eval shown to the user (`refreshAnalysis` via
  `app.engine`) must NEVER route through the gated/weakened path.
- **Legacy branch = B3 byte-identical** — gate only the persona branch.

## Sharp edges for B5
1. Input-side gate = mirror `review.py:461-499` (null-move threat surface + motifs)
   → drop threat-responding candidates. Maia-free, feasible.
2. motifs.py supplies the "threat to miss" (mate/hang/fork/pin/skewer/back-rank +
   severity). 3. Raise post-opening k. 4. Add `recentMoves` (additive) + extend
   seed past opening. 5. Pure-motif plausibility, not a 2nd engine pass.
   6. Two MATE_CP constants. 7. Persona schema extension touches the loader.
