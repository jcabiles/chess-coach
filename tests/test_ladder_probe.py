"""Pure tests for tools/ladder_probe.py — no engines, no lc0.

Covers the scoring-adjacent pure pieces a sign slip would silently break:
Wilson CI, rung grouping, and the render verdict line. Game play itself
needs binaries and is exercised by running the tool (see the committed
report under docs/analytics/).
"""

from __future__ import annotations

from app import personas
from tools.ladder_probe import maia_rungs, render, wilson_ci


def test_wilson_ci_sane_bounds():
    lo, hi = wilson_ci(12, 24)
    assert 0.0 <= lo < 0.5 < hi <= 1.0
    assert wilson_ci(0, 0) == (0.0, 1.0)  # zero-denominator guard
    lo_all, hi_all = wilson_ci(24, 24)
    assert lo_all > 0.8 and hi_all == 1.0


def test_wilson_ci_tightens_with_n():
    lo_s, hi_s = wilson_ci(6, 12)
    lo_l, hi_l = wilson_ci(50, 100)
    assert (hi_l - lo_l) < (hi_s - lo_s)


def test_maia_rungs_grouping():
    personas.init("tests/fixtures/does_not_exist_personas.json")  # built-in
    rungs = maia_rungs()
    assert [r[0].elo for r in rungs] == [800, 1000, 1200, 1400, 1600, 1800]
    assert all(len(r) == 2 for r in rungs)
    # Ascending and Maia-only.
    for rung in rungs:
        for p in rung:
            assert p.maiaBand is not None


def _row(pct):
    games = 24
    return {
        "lower": 800, "higher": 1000, "games": games,
        "higherScore": pct * games, "pct": pct,
        "ci95": (max(0.0, pct - 0.2), min(1.0, pct + 0.2)),
        "adjudicated": 0, "fallbacks": 0, "seconds": 1.0,
    }


def test_render_verdicts():
    md = render([_row(0.75)])
    assert "PASS" in md and "FAIL" not in md
    md = render([_row(0.5)])  # exactly 50% is NOT monotone — must fail
    assert "FAIL" in md
