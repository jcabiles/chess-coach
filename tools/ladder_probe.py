"""Monotonic ladder probe for the M6 Maia roster (pragmatic rigor tier).

Plays head-to-head matches between ADJACENT rungs of the Maia-backed ladder
(800 vs 1000, 1000 vs 1200, … 1600 vs 1800) through the REAL move pipeline
(``app.main.select_persona_move`` — anti-drift, same import as the realism
audit) and reports the higher rung's score per pair. Ship gate (cite
docs/design/research/rating-calibration/honest-bot-rating-assignment.md):
the higher-labeled rung must score > 50% against the rung below it — if the
ladder is not even monotonic, the labels are meaningless.

This is NOT the ±150 effective-Elo calibration (full-rigor follow-up ticket
covers that); it is the cheap local validation the research doc calls the
"only hard requirement to ship".

Engine plumbing:

* One ``MaiaEngine`` instance PER BAND, swapped into ``main.get_maia_engine``
  before each move — two lc0 processes per pair instead of a weights-swap
  restart every ply (the singleton would restart ~1s × every move).
* One shared bot Stockfish (injection tiers; every probe persona clamps to
  UCI_Elo 1320, so there is no respawn churn).
* Unfinished games at the ply cap are adjudicated by a dedicated strong
  oracle (``app.engine.StockfishEngine``, depth 12): |White cp| >= 150 is a
  win for the leader, else a draw (realism-audit oracle idiom).

Seeding: per-game seed = hash((pair_index, game_index)) (all-int tuple —
PYTHONHASHSEED-stable); colors alternate per game; each rung is represented
by its two styles alternately. The seeded draws (policy sampling, gate
fires) are reproducible, but full games are NOT run-to-run deterministic:
injected plies depend on Stockfish candidate evals, whose multithreaded
search varies between runs — treat results as a statistical sample, not a
replayable trace. Sandboxed runs need MAIA_BACKEND=eigen.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Optional

import chess

from app import maia_engine, personas
from app import main as app_main
from app.main import select_persona_move

#: Ply cap before oracle adjudication (weak bots can shuffle forever).
DEFAULT_PLY_CAP = 220
#: Oracle adjudication: |White-POV cp| at/over this = win for the leader.
ADJUDICATE_CP = 150
ORACLE_DEPTH = 12
#: How many of the mover's own recent moves feed plan_attention_set.
RECENT_WINDOW = 8


def maia_rungs() -> list[list[personas.Persona]]:
    """The Maia-backed ladder grouped by elo rung, ascending (2 styles/rung)."""
    maia = [p for p in personas.all() if p.maiaBand is not None]
    by_elo: dict[int, list[personas.Persona]] = {}
    for p in maia:
        by_elo.setdefault(p.elo, []).append(p)
    return [by_elo[e] for e in sorted(by_elo)]


def wilson_ci(k: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% CI for a score fraction (draws counted as half-wins)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (max(0.0, center - half), min(1.0, center + half))


class BandEngines:
    """One MaiaEngine per band, swapped into main.get_maia_engine per move."""

    def __init__(self) -> None:
        self._by_band: dict[int, maia_engine.MaiaEngine] = {}

    def for_persona(self, p: personas.Persona) -> maia_engine.MaiaEngine:
        assert p.maiaBand is not None
        if p.maiaBand not in self._by_band:
            self._by_band[p.maiaBand] = maia_engine.MaiaEngine()
        return self._by_band[p.maiaBand]

    async def close(self) -> None:
        for e in self._by_band.values():
            await e.close()
        self._by_band.clear()


async def play_game(
    white: personas.Persona,
    black: personas.Persona,
    seed: int,
    bot,
    engines: BandEngines,
    ply_cap: int,
    oracle,
) -> tuple[float, dict]:
    """One game. Returns (white_score, stats) — 1/0.5/0 for the White side."""
    board = chess.Board()
    recent: dict[bool, list[str]] = {chess.WHITE: [], chess.BLACK: []}
    fallbacks = 0
    ply = 0
    while ply < ply_cap:
        if board.is_game_over(claim_draw=True):
            break
        persona = white if board.turn == chess.WHITE else black
        engine = engines.for_persona(persona)
        app_main.get_maia_engine = lambda e=engine: e
        chosen = await select_persona_move(
            bot, persona, board.fen(), ply, seed,
            recent[board.turn][-RECENT_WINDOW:],
        )
        if chosen is None:
            raise RuntimeError(f"no move for {persona.id} at ply {ply}")
        if chosen["engine"] != "maia":
            fallbacks += 1
        recent[board.turn].append(chosen["uci"])
        board.push(chess.Move.from_uci(chosen["uci"]))
        ply += 1

    stats = {"plies": ply, "fallbacks": fallbacks, "adjudicated": False}
    outcome = board.outcome(claim_draw=True)
    if outcome is not None:
        if outcome.winner is None:
            return 0.5, stats
        return (1.0 if outcome.winner == chess.WHITE else 0.0), stats

    # Ply cap reached — oracle adjudication (realism-audit oracle idiom:
    # results are AnalysisResult objects; pov_score_to_white_cp normalizes).
    stats["adjudicated"] = True
    results = await oracle.analyze_multi(board.fen(), depth=ORACLE_DEPTH, multipv=1)
    from app.analysis import pov_score_to_white_cp

    white_cp = pov_score_to_white_cp(results[0].score)
    if white_cp >= ADJUDICATE_CP:
        return 1.0, stats
    if white_cp <= -ADJUDICATE_CP:
        return 0.0, stats
    return 0.5, stats


async def probe_pair(
    pair_index: int,
    lower: list[personas.Persona],
    higher: list[personas.Persona],
    games: int,
    bot,
    engines: BandEngines,
    ply_cap: int,
    oracle,
) -> dict:
    """N games between two rungs; returns the higher rung's aggregate score."""
    higher_score = 0.0
    adjudicated = 0
    fallbacks = 0
    t0 = time.monotonic()
    for g in range(games):
        # Decouple color from style (Sol review fold): color flips every
        # game while the style combo cycles lower-style every 2 games and
        # higher-style every 4 — all four style pairings appear under both
        # colors every 8 games, so no persona is locked to one color.
        lo = lower[(g // 2) % len(lower)]
        hi = higher[(g // 4) % len(higher)]
        seed = hash((pair_index, g))
        higher_is_white = g % 2 == 0
        white, black = (hi, lo) if higher_is_white else (lo, hi)
        white_score, stats = await play_game(
            white, black, seed, bot, engines, ply_cap, oracle
        )
        higher_score += white_score if higher_is_white else 1.0 - white_score
        adjudicated += int(stats["adjudicated"])
        fallbacks += stats["fallbacks"]
        print(
            f"  [{lower[0].elo} vs {higher[0].elo}] game {g + 1}/{games}: "
            f"{white.id} vs {black.id} → white {white_score} "
            f"({stats['plies']} plies"
            f"{', adjudicated' if stats['adjudicated'] else ''})",
            file=sys.stderr,
        )
    lo_ci, hi_ci = wilson_ci(higher_score, games)
    return {
        "lower": lower[0].elo,
        "higher": higher[0].elo,
        "games": games,
        "higherScore": higher_score,
        "pct": higher_score / games,
        "ci95": (lo_ci, hi_ci),
        "adjudicated": adjudicated,
        "fallbacks": fallbacks,
        "seconds": round(time.monotonic() - t0, 1),
    }


def render(results: list[dict]) -> str:
    lines = [
        "# Ladder probe — adjacent-rung monotonicity (M6 pragmatic gate)",
        "",
        "Higher rung must score > 50% vs the rung below. Draws = half a point.",
        "Point estimates with Wilson 95% CIs — at small n a PASS is a sanity",
        "check, not a calibration (see the full-rigor follow-up ticket).",
        "",
        "| pair | games | higher score | 95% CI | adjudicated | SF fallbacks | verdict |",
        "|------|-------|--------------|--------|-------------|--------------|---------|",
    ]
    for r in results:
        verdict = "PASS" if r["pct"] > 0.5 else "FAIL"
        lines.append(
            f"| {r['lower']} vs {r['higher']} | {r['games']} "
            f"| {r['higherScore']:.1f} ({r['pct']:.0%}) "
            f"| {r['ci95'][0]:.0%}–{r['ci95'][1]:.0%} "
            f"| {r['adjudicated']} | {r['fallbacks']} | {verdict} |"
        )
    lines.append("")
    return "\n".join(lines)


async def _run(args) -> int:
    from app import bot_engine, engine

    personas.init()
    rungs = maia_rungs()
    if len(rungs) < 2:
        print("need at least two Maia rungs", file=sys.stderr)
        return 2
    for rung in rungs:
        for p in rung:
            if not maia_engine.maia_ready_for(p.id):
                print(f"maia not ready for {p.id} (lc0/net missing)", file=sys.stderr)
                return 3

    bot = bot_engine.get_bot_engine()
    oracle = engine.StockfishEngine()
    try:
        oracle.start()
    except engine.EngineUnavailable as exc:
        print(f"adjudication oracle unavailable: {exc}", file=sys.stderr)
        return 3

    if args.games < 1:
        print("--games must be >= 1", file=sys.stderr)
        return 2
    pair_names = [
        f"{rungs[i][0].elo}-{rungs[i + 1][0].elo}" for i in range(len(rungs) - 1)
    ]
    if args.pair and args.pair not in pair_names:
        print(f"unknown --pair {args.pair!r}; valid: {pair_names}", file=sys.stderr)
        return 2

    engines = BandEngines()
    results = []
    try:
        for i in range(len(rungs) - 1):
            if args.pair and pair_names[i] != args.pair:
                continue
            results.append(
                await probe_pair(
                    i, rungs[i], rungs[i + 1], args.games, bot, engines,
                    args.cap, oracle,
                )
            )
    finally:
        await engines.close()
        oracle.close()
        await bot.close()

    if not results:
        print("no pairs were probed — refusing a vacuous pass", file=sys.stderr)
        return 2
    md = render(results)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(md, encoding="utf-8")
        print(f"wrote {args.report}")
    print(md)
    return 0 if all(r["pct"] > 0.5 for r in results) else 1


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Adjacent-rung ladder probe (M6).")
    ap.add_argument("--games", type=int, default=24, help="games per pair")
    ap.add_argument("--cap", type=int, default=DEFAULT_PLY_CAP, help="ply cap")
    ap.add_argument("--pair", default="", help='only one pair, e.g. "800-1000"')
    ap.add_argument("--report", default="", help="write markdown here")
    args = ap.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
