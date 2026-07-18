"""Offline ladder-monotonicity harness for the B5 causal-blunder gate (T5).

Pure, deterministic, no engine binary needed. Validates the coherence
invariant across the REAL persona ladder (``app.personas.all()``, the
research-calibrated dials — not stubs): a HIGHER-rated persona misses a
fixed off-plan threat LESS often than a lower-rated one (stronger bot
blunders less). See ``docs/ai-dlc/specs/causal-blunder.md`` Verify-by #2.
"""

from __future__ import annotations

import chess

from app import bot_blunder as bb
from app import personas

# A fixed, real off-plan threat: a hanging knight (severity_cp=300, a "minor"
# per the spec's ordering) whose key square is disjoint from the plan set
# below, so off_plan_score == 1.0 for every persona (fully off-plan).
_THREAT_SQUARE = chess.parse_square("d4")
_THREAT = bb.Threat(
    type="hanging",
    squares={_THREAT_SQUARE},
    severity_cp=300,
    target=_THREAT_SQUARE,
)

# The bot's attention is on the kingside (e4/e5) — disjoint from d4.
_PLAN_SET = {chess.parse_square("e4"), chess.parse_square("e5")}

# A mid/late middlegame ply, well past FIRST_BLUNDER_PLY+RAMP so hazard() == 1.0.
_PLY = 60
_PHASE = "middlegame"

# Fixed, deterministic seed range for the empirical miss-rate estimate.
_SEEDS = range(200)

# The real ladder, ordered lowest→highest Elo (Casey -> Morgan -> Alex -> Vera).
_LADDER = sorted(personas.all(), key=lambda p: p.elo)


def _miss_rate(persona) -> float:
    """Empirical fraction of seeds where the gate fires (the bot misses the threat)."""
    hits = sum(
        bb.should_blunder(persona, _PHASE, _PLY, seed=s, threat=_THREAT, plan_set=_PLAN_SET)
        for s in _SEEDS
    )
    return hits / len(_SEEDS)


def test_ladder_is_the_expected_four_personas_by_elo():
    # Sanity: the real ladder is Casey(1350) < Morgan(1550) < Alex(1800) < Vera(2000).
    ids = [p.id for p in _LADDER]
    assert ids == ["casey", "morgan", "alex", "vera"]


def test_miss_rate_monotone_non_increasing_across_ladder():
    """Higher elo => lower (or equal) empirical miss-rate on a fixed off-plan threat."""
    rates = [_miss_rate(p) for p in _LADDER]

    for i in range(len(rates) - 1):
        lower, higher = _LADDER[i], _LADDER[i + 1]
        assert rates[i] >= rates[i + 1], (
            f"expected miss-rate({lower.id}, elo={lower.elo})={rates[i]:.3f} >= "
            f"miss-rate({higher.id}, elo={higher.elo})={rates[i + 1]:.3f} "
            "(coherence invariant: stronger personas should blunder no more often)"
        )

    # Not degenerate: the ladder should actually spread (Casey misses noticeably
    # more than Vera) — guards against an all-zero or all-equal false pass.
    assert rates[0] > rates[-1]


def test_off_plan_threshold_monotone_across_ladder():
    """A threat at a fixed off_plan_score gates OUT high personas, allows low ones.

    threatDistance is monotone increasing across the real ladder (Casey lowest ->
    Vera highest), so a score strictly below Vera's threshold but at/above the
    others' is allowed for Casey/Morgan/Alex and gated out for Vera.
    """
    thresholds = [p.threatDistance for p in _LADDER]
    assert thresholds == sorted(thresholds), "threatDistance must be monotone across the ladder"

    # Squares 3/5 off-plan: exceeds casey/morgan/alex's threatDistance but not vera's.
    threat_squares = {1, 2, 3, 4, 5}
    on_plan = {1, 2}  # 2 of 5 on-plan -> off_plan_score = 0.6
    score = bb.off_plan_score(threat_squares, on_plan)
    assert score == 0.6

    casey, morgan, alex, vera = _LADDER
    assert score > casey.threatDistance
    assert score > morgan.threatDistance
    assert score > alex.threatDistance
    assert score <= vera.threatDistance  # gated OUT for the strongest persona


def test_ladder_harness_is_deterministic():
    """Running the whole miss-rate estimate twice yields identical counts."""
    run1 = [_miss_rate(p) for p in _LADDER]
    run2 = [_miss_rate(p) for p in _LADDER]
    assert run1 == run2
