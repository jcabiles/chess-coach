"""Unit tests for app.bot_blunder — the pure, engine-free causal-blunder gate.

No Stockfish binary is required: every function is pure python-chess. Threats
are detected on a board where the *threatening* side is to move (the route uses
a null-move board); tests follow that convention.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

from app import bot_blunder as bb

# ---------------------------------------------------------------------------
# Lightweight persona stub (do NOT depend on personas.py / T2)
# ---------------------------------------------------------------------------


@dataclass
class StubPersona:
    elo: int
    blunderRate: float
    threatDistance: float


def weak_persona(blunder_rate=0.9, threat_distance=0.1):
    return StubPersona(elo=1350, blunderRate=blunder_rate, threatDistance=threat_distance)


# ---------------------------------------------------------------------------
# 1. plan_attention_set
# ---------------------------------------------------------------------------


def test_plan_attention_set_from_known_moves():
    board = chess.Board()
    # From/to of the last PLAN_MOVES own moves are always present.
    moves = ["e2e4", "g1f3", "f1c4", "e1g1"]
    plan = bb.plan_attention_set(moves, board)
    for uci in moves:
        m = chess.Move.from_uci(uci)
        assert m.from_square in plan
        assert m.to_square in plan


def test_plan_attention_set_includes_active_piece_influence():
    # A bishop the bot just moved to c4 attacks the a2-g8 / a6-f1 diagonals.
    board = chess.Board("rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
    plan = bb.plan_attention_set(["f1c4"], board)
    # c4 bishop attacks f7 (a classic Italian target) — influence must be in the set.
    assert chess.parse_square("f7") in plan
    assert chess.parse_square("c4") in plan


def test_plan_attention_set_empty_in_opening():
    board = chess.Board()
    assert bb.plan_attention_set([], board) == set()


def test_plan_attention_set_only_last_four():
    board = chess.Board()
    moves = ["e2e4", "g1f3", "f1c4", "b1c3", "d2d4"]  # 5 moves
    plan = bb.plan_attention_set(moves, board)
    # The oldest move (e2e4) is dropped; e2 should not be present via that move.
    # (e4 could still be reachable via other pieces' influence, so assert e2.)
    assert chess.parse_square("e2") not in plan


# ---------------------------------------------------------------------------
# 2. opponent_threat
# ---------------------------------------------------------------------------


def test_opponent_threat_mate_in_1_engine_free():
    # White to move: Ra1-a8 is mate (Black king g8 walled by f7/g7/h7 pawns).
    board = chess.Board("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
    t = bb.opponent_threat(board)
    assert t is not None
    assert t.type == "mate"
    assert t.severity_cp == bb.MATE_SEVERITY
    king_sq = chess.parse_square("g8")
    assert king_sq in t.squares
    assert chess.parse_square("a8") in t.squares  # the mating-move to-square


def test_opponent_threat_hanging_queen():
    # White to move can play exd5 winning the undefended black queen.
    board = chess.Board("4k3/8/8/3q4/4P3/8/8/4K3 w - - 0 1")
    t = bb.opponent_threat(board)
    assert t is not None
    assert t.type == "hanging"
    assert t.severity_cp == 900
    assert chess.parse_square("d5") in t.squares


def test_opponent_threat_fork():
    # White knight on e6 forks the black king (g7) and rook (c7).
    board = chess.Board("8/2r3k1/4N3/8/8/8/8/4K3 w - - 0 1")
    t = bb.opponent_threat(board)
    assert t is not None
    # Forking the king is at least as strong as a mate-value target.
    assert t.severity_cp >= 500


def test_opponent_threat_back_rank_severity():
    # Classic back-rank: White Re1 mates on e8; black king g8 walled by pawns.
    board = chess.Board("6k1/5ppp/8/8/8/8/8/4R1K1 w - - 0 1")
    t = bb.opponent_threat(board)
    assert t is not None
    # Re8 is mate-in-1 → detected as a mate (top severity), which dominates.
    assert t.severity_cp == bb.MATE_SEVERITY


def test_opponent_threat_pawn_below_min_missable():
    # White to move wins only a hanging black pawn on b5 — below MIN_MISSABLE.
    board = chess.Board("4k3/8/8/1p6/P7/8/8/4K3 w - - 0 1")
    t = bb.opponent_threat(board)
    assert t is not None
    assert t.severity_cp == 100
    assert t.severity_cp < bb.MIN_MISSABLE


def test_opponent_threat_none_in_quiet_position():
    board = chess.Board("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
    assert bb.opponent_threat(board) is None


def test_opponent_threat_severity_ordering():
    # A position where a rook AND a minor both hang; the rook (500) must win.
    # White to move; black rook a5 hangs to pawn b4? use two hanging blacks.
    board = chess.Board("4k3/8/8/r7/1n6/8/8/4K1R1 w - - 0 1")
    # Black rook a5 hanging to Rg1? No — build explicit: white rook a1 hits a5 rook,
    # white bishop hits b4 knight. Keep simple: pieces both attacked & undefended.
    board = chess.Board("4k3/8/8/r7/1n6/8/8/R3K3 w - - 0 1")
    t = bb.opponent_threat(board)
    assert t is not None
    # Ra1xa5 wins the rook (500) — strictly more than the minor (300).
    assert t.severity_cp == 500


# ---------------------------------------------------------------------------
# 3. should_blunder
# ---------------------------------------------------------------------------


def _minor_threat():
    return bb.Threat(type="hanging", squares={chess.parse_square("d4")}, severity_cp=300, target=chess.parse_square("d4"))


def test_should_blunder_never_in_opening():
    threat = _minor_threat()
    assert not bb.should_blunder(weak_persona(), "opening", 30, seed=1, threat=threat, plan_set=set())


def test_should_blunder_below_min_missable_never_fires():
    pawn_threat = bb.Threat(type="hanging", squares={12}, severity_cp=100, target=12)
    # Even with everything maxed, a sub-200 threat can't be a blunder.
    assert not bb.should_blunder(
        weak_persona(blunder_rate=1.0, threat_distance=0.0),
        "middlegame", 60, seed=1, threat=pawn_threat, plan_set=set(),
    )


def test_should_blunder_requires_off_plan():
    threat = _minor_threat()
    plan_on = {chess.parse_square("d4")}  # threat square is fully on-plan
    # off_plan_score = 0 <= threatDistance → cannot fire.
    persona = weak_persona(blunder_rate=1.0, threat_distance=0.1)
    assert not bb.should_blunder(persona, "middlegame", 60, seed=1, threat=threat, plan_set=plan_on)


def test_should_blunder_fires_off_plan_seeded_hit():
    threat = _minor_threat()
    # Fully off-plan, high blunderRate, late ply, minor severity → high fire_prob.
    persona = weak_persona(blunder_rate=1.0, threat_distance=0.1)
    # Find a seed that hits (deterministic given ply).
    fired = any(
        bb.should_blunder(persona, "middlegame", 60, seed=s, threat=threat, plan_set=set())
        for s in range(50)
    )
    assert fired


def test_should_blunder_mate_damped_far_below_minor():
    persona = weak_persona(blunder_rate=1.0, threat_distance=0.1)
    minor = _minor_threat()
    mate = bb.Threat(type="mate", squares={1, 2, 3}, severity_cp=bb.MATE_SEVERITY, target=1)

    n = 300
    minor_hits = sum(
        bb.should_blunder(persona, "middlegame", 60, seed=s, threat=minor, plan_set=set())
        for s in range(n)
    )
    mate_hits = sum(
        bb.should_blunder(persona, "middlegame", 60, seed=s, threat=mate, plan_set=set())
        for s in range(n)
    )
    # severity_damp: minor ~ MISS_REF/300 -> clamped to 1.0; mate ~ MISS_REF/1e5 -> tiny.
    assert minor_hits > mate_hits
    assert mate_hits <= 5  # mate is missed almost never


def test_should_blunder_queen_damped_below_minor():
    persona = weak_persona(blunder_rate=1.0, threat_distance=0.1)
    minor = _minor_threat()
    queen = bb.Threat(type="hanging", squares={35}, severity_cp=900, target=35)
    n = 300
    minor_hits = sum(
        bb.should_blunder(persona, "middlegame", 60, seed=s, threat=minor, plan_set=set())
        for s in range(n)
    )
    queen_hits = sum(
        bb.should_blunder(persona, "middlegame", 60, seed=s, threat=queen, plan_set=set())
        for s in range(n)
    )
    assert queen_hits < minor_hits


def test_should_blunder_none_threat():
    assert not bb.should_blunder(weak_persona(), "middlegame", 60, seed=1, threat=None, plan_set=set())


def test_should_blunder_deterministic():
    threat = _minor_threat()
    persona = weak_persona(blunder_rate=0.6, threat_distance=0.1)
    a = bb.should_blunder(persona, "middlegame", 42, seed=7, threat=threat, plan_set=set())
    b = bb.should_blunder(persona, "middlegame", 42, seed=7, threat=threat, plan_set=set())
    assert a == b


def test_hazard_ramp_zero_early_full_late():
    assert bb.hazard(0) == 0.0
    assert bb.hazard(bb.FIRST_BLUNDER_PLY) == 0.0
    assert bb.hazard(bb.FIRST_BLUNDER_PLY + bb.RAMP) == 1.0
    assert bb.hazard(200) == 1.0
    # Monotone.
    assert bb.hazard(bb.FIRST_BLUNDER_PLY + 5) < bb.hazard(bb.FIRST_BLUNDER_PLY + 15)


def test_phase_gate_opening_zero():
    assert bb.phase_gate("opening") == 0.0
    assert bb.phase_gate("middlegame") == 1.0
    assert bb.phase_gate("endgame") == 1.0


def test_off_plan_score_bounds():
    sq = {1, 2, 3, 4}
    assert bb.off_plan_score(sq, set()) == 1.0
    assert bb.off_plan_score(sq, sq) == 0.0
    assert bb.off_plan_score(sq, {1, 2}) == 0.5


# ---------------------------------------------------------------------------
# 4. pick_survivor
# ---------------------------------------------------------------------------


def _hanging_queen_setup():
    """Return (bot_board, threat) where Black (bot) to move, White threatens Qxd5.

    The threat is detected on the null-move board (White to move), matching the
    route's convention.
    """
    null_board = chess.Board("4k3/8/8/3q4/4P3/8/8/4K3 w - - 0 1")
    threat = bb.opponent_threat(null_board)
    bot_board = chess.Board("4k3/8/8/3q4/4P3/8/8/4K3 b - - 0 1")
    return bot_board, threat


def test_pick_survivor_drops_neutralizers():
    bot_board, threat = _hanging_queen_setup()
    # Qd8 saves the queen (neutralizes); Ke7 ignores it (survivor).
    cands = [
        {"uci": "d5d8", "san": "Qd8", "scoreCp": 50},
        {"uci": "e8e7", "san": "Ke7", "scoreCp": -800},
    ]
    idx = bb.pick_survivor(cands, bot_board, threat)
    assert idx == 1  # only Ke7 leaves the queen hanging


def test_pick_survivor_best_by_mover_pov_tiebreak_index():
    bot_board, threat = _hanging_queen_setup()
    # Two survivors that both ignore the queen; pick best mover-POV score.
    # Black to move → mover_cp = -scoreCp; the LOWER (more negative for white)
    # White-POV score is BEST for Black.
    cands = [
        {"uci": "e8e7", "san": "Ke7", "scoreCp": -100},  # mover_cp = +100
        {"uci": "e8d7", "san": "Kd7", "scoreCp": -50},   # mover_cp = +50
    ]
    idx = bb.pick_survivor(cands, bot_board, threat)
    assert idx == 0  # Ke7 is better for Black (mover_cp +100 > +50)


def test_pick_survivor_tiebreak_by_index():
    bot_board, threat = _hanging_queen_setup()
    cands = [
        {"uci": "e8e7", "san": "Ke7", "scoreCp": -100},
        {"uci": "e8d7", "san": "Kd7", "scoreCp": -100},  # tie → lower index wins
    ]
    idx = bb.pick_survivor(cands, bot_board, threat)
    assert idx == 0


def test_pick_survivor_none_when_all_address():
    bot_board, threat = _hanging_queen_setup()
    # Every candidate moves the queen to safety → all neutralize → None.
    cands = [
        {"uci": "d5d8", "san": "Qd8", "scoreCp": 50},
        {"uci": "d5a5", "san": "Qa5", "scoreCp": 40},
    ]
    assert bb.pick_survivor(cands, bot_board, threat) is None


def test_pick_survivor_none_threat():
    bot_board, _ = _hanging_queen_setup()
    cands = [{"uci": "e8e7", "san": "Ke7", "scoreCp": 0}]
    assert bb.pick_survivor(cands, bot_board, None) is None


def test_pick_survivor_deterministic():
    bot_board, threat = _hanging_queen_setup()
    cands = [
        {"uci": "e8e7", "san": "Ke7", "scoreCp": -100},
        {"uci": "e8f8", "san": "Kf8", "scoreCp": -90},
    ]
    a = bb.pick_survivor(cands, bot_board, threat)
    b = bb.pick_survivor(cands, bot_board, threat)
    assert a == b


def test_pick_survivor_white_bot_mover_pov():
    # White (bot) to move, Black threatens Qxe4 on the null-move board.
    null_board = chess.Board("4k3/8/4p3/3Q4/8/8/8/4K3 b - - 0 1")  # black to move (opponent)
    threat = bb.opponent_threat(null_board)
    assert threat is not None and threat.severity_cp == 900
    bot_board = chess.Board("4k3/8/4p3/3Q4/8/8/8/4K3 w - - 0 1")  # white bot to move
    cands = [
        {"uci": "e1e2", "san": "Ke2", "scoreCp": 100},  # mover_cp = +100 (white)
        {"uci": "e1d2", "san": "Kd2", "scoreCp": 50},   # mover_cp = +50
    ]
    idx = bb.pick_survivor(cands, bot_board, threat)
    assert idx == 0  # higher White-POV score is best for the White bot
