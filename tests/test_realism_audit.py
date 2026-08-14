"""Pure + fake-engine tests for the realism trace-audit harness (M3).

No Stockfish/lc0 binary is required: the pure surfaces (loading, hashing,
banding, metric math, rendering) are tested directly, and the engine runner is
exercised with fake ``bot`` / ``oracle`` objects. Data-backed acceptance (the
real eval-set run) is a separate offline step, not part of the suite.

Fixtures live in ``tests/fixtures/realism/`` (small, synthetic, ECO-disjoint);
they stand in for the committed ``data/realism/`` sets until the lichess fetch
is run.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import chess
import chess.engine as ce
import pytest

from app import personas
from tools import realism_audit as ra
from tools.fetch_lichess_sample import MAX_POS_PER_GAME, mate_in_one_exists

FIX = Path(__file__).parent / "fixtures" / "realism"
BAND = "1300-1500"


# --- position loading -------------------------------------------------------


def test_load_positions_valid():
    rows = ra.load_positions("dev", BAND, FIX)
    assert len(rows) == 2
    assert ra.REQUIRED_KEYS <= rows[0].keys()
    assert all(r["band"] == BAND for r in rows)


def test_load_positions_rejects_wrong_band(tmp_path):
    bad = {"gameId": "x", "fen": chess.STARTING_FEN, "ply": 12,
           "humanMoveUci": "e2e4", "band": "9999-9999", "eco": "A00"}
    (tmp_path / "dev-1300-1500.jsonl").write_text(json.dumps(bad) + "\n")
    with pytest.raises(ValueError, match="band"):
        ra.load_positions("dev", BAND, tmp_path)


def test_load_positions_rejects_bad_fen(tmp_path):
    bad = {"gameId": "x", "fen": "not a fen", "ply": 12,
           "humanMoveUci": "e2e4", "band": BAND, "eco": "A00"}
    (tmp_path / "dev-1300-1500.jsonl").write_text(json.dumps(bad) + "\n")
    with pytest.raises(ValueError, match="fen"):
        ra.load_positions("dev", BAND, tmp_path)


def test_load_positions_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        ra.load_positions("dev", BAND, tmp_path)


# --- sealed-eval hash pin ---------------------------------------------------


def test_eval_hash_matches_fixtures():
    ok, problems = ra.verify_eval_hash(FIX)
    assert ok, problems


def test_eval_hash_detects_tamper(tmp_path):
    for f in FIX.iterdir():
        (tmp_path / f.name).write_bytes(f.read_bytes())
    # Flip one byte of the sealed eval file.
    ev = tmp_path / "eval-1300-1500.jsonl"
    ev.write_text(ev.read_text().replace("d2d4", "g1f3"))
    ok, problems = ra.verify_eval_hash(tmp_path)
    assert not ok
    assert any("mismatch" in p for p in problems)


def test_eval_hash_missing_pin(tmp_path):
    ok, problems = ra.verify_eval_hash(tmp_path)
    assert not ok and problems


# --- dev/eval disjointness + clustering caps (on the fixture sets) ----------


def test_dev_eval_eco_disjoint():
    dev_eco = {r["eco"] for r in ra.load_positions("dev", BAND, FIX)}
    eval_eco = {r["eco"] for r in ra.load_positions("eval", BAND, FIX)}
    assert dev_eco.isdisjoint(eval_eco), (dev_eco, eval_eco)


def test_positions_per_game_capped():
    for set_name in ("dev", "eval"):
        rows = ra.load_positions(set_name, BAND, FIX)
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["gameId"]] = counts.get(r["gameId"], 0) + 1
        assert all(c <= MAX_POS_PER_GAME for c in counts.values()), counts


# --- banding + stats math ---------------------------------------------------


def test_band_for_elo():
    assert ra.band_for_elo(1350) == "1300-1500"
    assert ra.band_for_elo(1500) == "1500-1700"
    assert ra.band_for_elo(2000) == "1900-2100"
    assert ra.band_for_elo(800) is None


def test_wilson_ci_edges():
    assert ra.wilson_ci(0, 0) == (0.0, 0.0)
    lo, hi = ra.wilson_ci(10, 10)
    assert hi == pytest.approx(1.0, abs=1e-9)
    assert lo < 1.0
    lo0, _ = ra.wilson_ci(0, 10)
    assert lo0 == pytest.approx(0.0, abs=1e-9)


def test_classify_loss_thresholds():
    assert ra.classify_loss(0) == "clean"
    assert ra.classify_loss(49) == "clean"
    assert ra.classify_loss(50) == "mistake"
    assert ra.classify_loss(250) == "mistake"
    assert ra.classify_loss(251) == "blunder"
    assert ra.classify_loss(900) == "blunder"


def test_mate_in_one_scanner():
    assert mate_in_one_exists(chess.Board("6k1/5ppp/8/8/8/8/8/R6K w - - 0 1"))
    assert not mate_in_one_exists(chess.Board(chess.STARTING_FEN))


# --- aggregation + rendering ------------------------------------------------


def _rows():
    return [
        ra.MoveResult("f1", 12, "e2e4", "e2e4", "stockfish", 0, False, False),
        ra.MoveResult("f2", 14, "d7d5", "g8f6", "stockfish", 300, False, False),
        ra.MoveResult("f3", 16, "a7a6", "b8c6", "stockfish", 120, True, True),
    ]


def test_summarize_counts():
    p = personas.get("casey")
    rep = ra.summarize(p, BAND, _rows())
    assert rep.n == 3
    assert rep.move_match == 1
    assert rep.blunders == 1  # the 300cp row
    assert rep.mistakes == 1  # the 120cp row
    assert rep.mate1_available == 1 and rep.mate1_converted == 1
    assert rep.mean_loss == pytest.approx((0 + 300 + 120) / 3)


def test_render_markdown_smoke():
    p = personas.get("casey")
    rep = ra.summarize(p, BAND, _rows())
    md = ra.render_markdown([rep], {"set": "dev", "engine": "sf-only"})
    assert "Realism audit" in md
    assert "Ming Ling" in md
    assert "sf-only" in md
    # A persona with mate1 available renders a real conversion %, not N/A.
    assert "100.0%" in md


def test_render_markdown_mate_denominator_na():
    p = personas.get("casey")
    rows = [ra.MoveResult("f1", 12, "e2e4", "e2e4", "stockfish", 0, False, False)]
    md = ra.render_markdown([ra.summarize(p, BAND, rows)], {"set": "dev"})
    assert "N/A" in md  # zero mate-in-1 positions -> conversion N/A, never 0/0


# --- fake-engine runner (no binary) -----------------------------------------


class FakeBot:
    """Returns the position's first legal move (best-first, length 1)."""

    async def candidates(self, fen, k=1, elo=None):
        board = chess.Board(fen)
        move = next(iter(board.legal_moves))
        return [{"uci": move.uci(), "san": board.san(move), "scoreCp": 0}]

    async def close(self):
        pass


class FakeOracle:
    """Fixed-eval loss oracle: every position is dead even (White cp = 0)."""

    def __init__(self):
        self.calls = 0

    async def analyze_multi(self, fen, depth=14, multipv=1):
        self.calls += 1
        score = ce.PovScore(ce.Cp(0), chess.WHITE)
        return [_Res(score)]


class _Res:
    def __init__(self, score):
        self.score = score


def test_audit_persona_with_fakes():
    p = personas.get("casey")
    positions = ra.load_positions("dev", BAND, FIX)
    bot, oracle = FakeBot(), FakeOracle()
    rows = asyncio.run(
        ra.audit_persona(p, BAND, positions, bot, oracle, {}, {})
    )
    assert len(rows) == len(positions)
    assert all(r.engine == "stockfish" for r in rows)  # _maia_off -> SF path
    assert all(r.loss_cp >= 0 for r in rows)


def test_oracle_before_cache_shared(monkeypatch):
    # Same fen audited twice -> the before-eval oracle call happens once.
    p = personas.get("casey")
    positions = ra.load_positions("dev", BAND, FIX)
    bot, oracle = FakeBot(), FakeOracle()
    before: dict = {}
    asyncio.run(ra.audit_persona(p, BAND, positions, bot, oracle, before, {}))
    # Two distinct fens in the fixture -> two cached before-evals.
    assert len(before) == 2


def test_sf_only_never_calls_maia(monkeypatch):
    # _maia_off already makes maia_ready_for False; make any maia access explode
    # so a regression that reaches for Maia in sf-only conditions fails loudly.
    import app.main as main

    def _boom():
        raise AssertionError("Maia must not be touched in sf-only conditions")

    monkeypatch.setattr(main, "get_maia_engine", _boom)
    p = personas.get("casey")
    positions = ra.load_positions("dev", BAND, FIX)
    rows = asyncio.run(
        ra.audit_persona(p, BAND, positions, FakeBot(), FakeOracle(), {}, {})
    )
    assert all(r.engine == "stockfish" for r in rows)
