"""Unit tests for app.moments — pure module, no Stockfish binary required.

Written as an independent CHECKER against docs/ai-dlc/specs/narrative-review.md
(section "New pure module app/moments.py") and
docs/ai-dlc/contracts/narrative-review.md (sections 1, 2, 7): tests pin the
spec's POV rules, thresholds, and cap/priority behavior — not whatever the
implementation happens to do.
"""

from __future__ import annotations

import json

import pytest

from app import moments
from app.analysis import win_prob_from_cp
from app.moments import extract_moments

# ---------------------------------------------------------------------------
# Convenience FENs (same trick as tests/test_accuracy.py: differ only in the
# active-color field, or in material for phase testing).
# ---------------------------------------------------------------------------

FEN_WHITE = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
FEN_BLACK = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1"
FEN_ENDGAME_WHITE = "8/8/8/4k3/8/4K3/4P3/8 w - - 0 1"


def _ply(n, san="e4", uci="e2e4", fen=FEN_WHITE, cp=None, mate=None, is_user=0, clock=None):
    return {
        "game_id": 1,
        "ply": n,
        "san": san,
        "uci": uci,
        "fen_before": fen,
        "eval_cp_white": cp,
        "mate_white": mate,
        "win_prob": None,  # mover-POV; moments.py does not read this field
        "is_user_move": is_user,
        "clock_centis": clock,
    }


def _leak(
    ply,
    color="white",
    severity="blunder",
    category="hanging",
    phase="middlegame",
    wp_before=0.6,
    wp_after=0.3,
    wp_drop=0.3,
    hung_square="e5",
    threat_motif="hanging",
    best_uci="d2d4",
    best_san="d4",
    lead_in_ply=None,
):
    return {
        "id": 1,
        "game_id": 1,
        "ply": ply,
        "color": color,
        "severity": severity,
        "category": category,
        "motif_json": None,
        "phase": phase,
        "win_prob_before": wp_before,
        "win_prob_after": wp_after,
        "win_prob_drop": wp_drop,
        "hung_square": hung_square,
        "threat_uci": None,
        "threat_motif": threat_motif,
        "best_uci": best_uci,
        "best_san": best_san,
        "lead_in_ply": ply - 1 if lead_in_ply is None else lead_in_ply,
        "tags_json": None,
        "explanation_json": None,
    }


def _pos_row(eval_cp_white=None, mate_white=None, best_uci="e2e4", best_san="e4",
             pv_san=None, pv2_cp_white=None):
    return {
        "epd_key": "unused",
        "depth": 10,
        "eval_cp_white": eval_cp_white,
        "mate_white": mate_white,
        "best_uci": best_uci,
        "best_san": best_san,
        "pv_san_json": json.dumps(pv_san) if pv_san is not None else None,
        "pv2_cp_white": pv2_cp_white,
    }


def _epd(fen):
    import chess
    return chess.Board(fen).epd()


# ---------------------------------------------------------------------------
# Empty / short input never raises
# ---------------------------------------------------------------------------

def test_empty_plies_returns_empty_payload_no_raise():
    payload = extract_moments([], [], {}, "white", None)
    assert payload["moments"] == []
    assert payload["moments_dropped"] == 0
    assert payload["eval_arc"] == {}


def test_single_ply_no_raise():
    plies = [_ply(1, fen=FEN_WHITE, cp=0, is_user=1)]
    payload = extract_moments(plies, [], {}, "white", None)
    assert payload["moments"] == []


def test_missing_fen_graceful_skip_no_raise():
    """A ply with no fen_before and no my_color must be skipped, not crash."""
    plies = [
        _ply(1, fen=None, cp=0, is_user=0),
        _ply(2, fen=None, cp=500, is_user=1),
    ]
    payload = extract_moments(plies, [], {}, None, None)
    assert payload["moments"] == []


# ---------------------------------------------------------------------------
# User mistakes/blunders: straight passthrough from leaks
# ---------------------------------------------------------------------------

def test_user_leak_passthrough_facts():
    plies = [_ply(1, san="Nf3", fen=FEN_WHITE, cp=0, is_user=1)]
    leaks = [_leak(
        ply=1, color="white", severity="blunder", category="hanging",
        phase="middlegame", wp_drop=0.35, hung_square="e5",
        threat_motif="fork", best_san="Bxe5", best_uci="f3e5",
    )]
    payload = extract_moments(plies, leaks, {}, "white", None)
    assert len(payload["moments"]) == 1
    m = payload["moments"][0]
    assert m["kind"] == "user_blunder"
    assert m["severity"] == "blunder"
    assert m["side"] == "white"
    assert m["is_user_move"] is True
    assert m["san"] == "Nf3"
    assert m["move_number"] == 1
    assert m["facts"]["category"] == "hanging"
    assert m["facts"]["hung_square"] == "e5"
    assert m["facts"]["best_san"] == "Bxe5"
    assert m["facts"]["win_prob_drop"] == 0.35
    assert m["facts"]["fen_before"] == FEN_WHITE


# ---------------------------------------------------------------------------
# POV correctness — opponent mistakes/blunders (the acceptance-critical test:
# a BLACK-mover blunder must be detected correctly from White-POV eval data).
# ---------------------------------------------------------------------------

def test_opponent_blunder_black_mover_pov_correctness():
    """Black blunders (White-POV eval swings sharply positive) while
    my_color='white' — must surface as an OPPONENT blunder, side='black'."""
    plies = [
        _ply(1, fen=FEN_WHITE, cp=0, is_user=1),
        _ply(2, san="Bg4??", fen=FEN_BLACK, cp=0, is_user=0),   # black to move, blunders
        _ply(3, fen=FEN_WHITE, cp=600, is_user=1),               # after-eval: White way up
    ]
    payload = extract_moments(plies, [], {}, "white", None)
    opp = [m for m in payload["moments"] if m["kind"].startswith("opponent_")]
    assert len(opp) == 1
    m = opp[0]
    assert m["kind"] == "opponent_blunder"
    assert m["side"] == "black"
    assert m["is_user_move"] is False
    assert m["ply"] == 2
    assert m["san"] == "Bg4??"

    # Independently derive the expected win-prob drop (opponent/black POV).
    expected_drop = round((win_prob_from_cp(600) - 0.5), 4)
    assert m["facts"]["win_prob_drop"] == pytest.approx(expected_drop, abs=1e-4)


def test_opponent_blunder_white_mover_pov_correctness():
    """Symmetric case: White (opponent, my_color='black') blunders — eval
    swings sharply negative in White-POV terms must read as an opponent loss."""
    plies = [
        _ply(1, fen=FEN_BLACK, cp=0, is_user=1),   # black (user) moves first here
        _ply(2, san="Qh5??", fen=FEN_WHITE, cp=0, is_user=0),  # white (opponent) blunders
        _ply(3, fen=FEN_BLACK, cp=-600, is_user=1),
    ]
    payload = extract_moments(plies, [], {}, "black", None)
    opp = [m for m in payload["moments"] if m["kind"].startswith("opponent_")]
    assert len(opp) == 1
    assert opp[0]["kind"] == "opponent_blunder"
    assert opp[0]["side"] == "white"
    assert opp[0]["ply"] == 2


def test_depth_noise_floor_no_moment_for_small_swing():
    """A small eval swing (well under the mistake threshold) must not fire."""
    plies = [
        _ply(1, fen=FEN_WHITE, cp=0, is_user=1),
        _ply(2, fen=FEN_BLACK, cp=0, is_user=0),
        _ply(3, fen=FEN_WHITE, cp=30, is_user=1),  # tiny swing, not a mistake
    ]
    payload = extract_moments(plies, [], {}, "white", None)
    assert payload["moments"] == []


def test_last_ply_boundary_no_swing_computed():
    """The final ply has no 'after' position; must not raise or fabricate a swing."""
    plies = [
        _ply(1, fen=FEN_WHITE, cp=0, is_user=1),
        _ply(2, fen=FEN_BLACK, cp=0, is_user=0),  # last ply: no next row
    ]
    payload = extract_moments(plies, [], {}, "white", None)
    assert payload["moments"] == []


# ---------------------------------------------------------------------------
# Mate-ply NULL cp handling
# ---------------------------------------------------------------------------

def test_mate_ply_null_cp_no_raise_and_correct_severity():
    """eval_cp_white is NULL when mate_white is set; must NULL-guard via
    analysis.win_prob_white and still classify correctly (near-certain loss)."""
    plies = [
        _ply(1, fen=FEN_WHITE, cp=0, is_user=1),
        _ply(2, fen=FEN_BLACK, cp=0, mate=None, is_user=0),
        _ply(3, fen=FEN_WHITE, cp=None, mate=5, is_user=1),  # White has mate-in-5
    ]
    payload = extract_moments(plies, [], {}, "white", None)
    opp = [m for m in payload["moments"] if m["kind"].startswith("opponent_")]
    assert len(opp) == 1
    assert opp[0]["kind"] == "opponent_blunder"
    assert opp[0]["facts"]["win_prob_drop"] == pytest.approx(0.5, abs=1e-4)


# ---------------------------------------------------------------------------
# lead_in_ply relative guard (insights.py:648-658 pattern)
# ---------------------------------------------------------------------------

def test_lead_in_ply_default_is_not_foreseeable():
    """lead_in_ply == ply - 1 is the display-timing DEFAULT; carries no signal."""
    plies = [_ply(5, fen=FEN_WHITE, cp=0, is_user=1)]
    leaks = [_leak(ply=5, lead_in_ply=4)]  # default: ply - 1
    payload = extract_moments(plies, leaks, {}, "white", None)
    m = payload["moments"][0]
    assert m["facts"]["foreseeable"] is False
    assert "lead_in_ply" not in m["facts"]


def test_lead_in_ply_genuine_signal_is_foreseeable():
    """lead_in_ply strictly before ply - 1 is a genuine foresight signal."""
    plies = [_ply(5, fen=FEN_WHITE, cp=0, is_user=1)]
    leaks = [_leak(ply=5, lead_in_ply=2)]  # 2 < 5 - 1 = 4
    payload = extract_moments(plies, leaks, {}, "white", None)
    m = payload["moments"][0]
    assert m["facts"]["foreseeable"] is True
    assert m["facts"]["lead_in_ply"] == 2


# ---------------------------------------------------------------------------
# Tide turns
# ---------------------------------------------------------------------------

def test_tide_turn_crossing_with_sufficient_swing():
    plies = [
        _ply(1, fen=FEN_WHITE, cp=-300, is_user=1),  # White-POV: black better
        _ply(2, fen=FEN_BLACK, cp=400, is_user=0),    # crosses to White better
    ]
    payload = extract_moments(plies, [], {}, "white", None)
    tide = [m for m in payload["moments"] if m["kind"] == "tide_turn"]
    assert len(tide) == 1
    assert tide[0]["ply"] == 1


def test_tide_turn_crossing_but_insufficient_swing_not_flagged():
    plies = [
        _ply(1, fen=FEN_WHITE, cp=-10, is_user=1),   # barely below even
        _ply(2, fen=FEN_BLACK, cp=10, is_user=0),     # barely above even
    ]
    payload = extract_moments(plies, [], {}, "white", None)
    assert [m for m in payload["moments"] if m["kind"] == "tide_turn"] == []


def test_tide_turn_no_crossing_not_flagged_despite_big_swing():
    plies = [
        _ply(1, fen=FEN_WHITE, cp=200, is_user=1),   # White already ahead
        _ply(2, fen=FEN_BLACK, cp=900, is_user=0),    # still White ahead, bigger
    ]
    payload = extract_moments(plies, [], {}, "white", None)
    assert [m for m in payload["moments"] if m["kind"] == "tide_turn"] == []


# ---------------------------------------------------------------------------
# narrow_choice (never names a 2nd-best move)
# ---------------------------------------------------------------------------

def test_narrow_choice_gap_flagged_without_second_move():
    plies = [_ply(1, fen=FEN_WHITE, cp=0, is_user=1)]
    pos_by_epd = {
        _epd(FEN_WHITE): _pos_row(
            eval_cp_white=50, best_uci="g1f3", best_san="Nf3",
            pv_san=["Nf3", "Nf6"], pv2_cp_white=-400,
        )
    }
    payload = extract_moments(plies, [], pos_by_epd, "white", None)
    narrow = [m for m in payload["moments"] if m["kind"] == "narrow_choice"]
    assert len(narrow) == 1
    facts = narrow[0]["facts"]
    assert facts["best_san"] == "Nf3"
    assert facts["gap"] >= moments.NARROW_CHOICE_GAP
    assert facts["pv_san"] == ["Nf3", "Nf6"]
    # Never a second-best move anywhere in the facts.
    forbidden = {"pv2_san", "pv2_uci", "second_best_san", "second_best_uci", "second_best_move"}
    assert forbidden.isdisjoint(facts.keys())


def test_narrow_choice_no_pv2_row_not_flagged():
    """No pv2_cp_white (incl. true single-legal-move positions) -> out of scope."""
    plies = [_ply(1, fen=FEN_WHITE, cp=0, is_user=1)]
    pos_by_epd = {_epd(FEN_WHITE): _pos_row(eval_cp_white=50, pv2_cp_white=None)}
    payload = extract_moments(plies, [], pos_by_epd, "white", None)
    assert [m for m in payload["moments"] if m["kind"] == "narrow_choice"] == []


def test_narrow_choice_small_gap_not_flagged():
    plies = [_ply(1, fen=FEN_WHITE, cp=0, is_user=1)]
    pos_by_epd = {_epd(FEN_WHITE): _pos_row(eval_cp_white=50, pv2_cp_white=20)}
    payload = extract_moments(plies, [], pos_by_epd, "white", None)
    assert [m for m in payload["moments"] if m["kind"] == "narrow_choice"] == []


# ---------------------------------------------------------------------------
# Missed capitalization
# ---------------------------------------------------------------------------

def _missed_cap_plies():
    return [
        _ply(1, fen=FEN_WHITE, cp=0, is_user=1),
        _ply(2, fen=FEN_BLACK, cp=0, is_user=0),    # opponent (black) about to blunder
        _ply(3, fen=FEN_WHITE, cp=600, is_user=1),  # after black's blunder: White way up
        _ply(4, fen=FEN_BLACK, cp=50, is_user=0),   # after White's ply-3 reply: back to ~even
    ]


def test_missed_capitalization_flagged_when_user_gives_back_most_of_swing():
    plies = _missed_cap_plies()
    swing = win_prob_from_cp(600) - 0.5  # opponent's blunder handed the user this much
    leaks = [_leak(ply=3, severity="mistake", wp_drop=round(swing * 0.9, 4), best_san="Nc3")]
    payload = extract_moments(plies, leaks, {}, "white", None)
    missed = [m for m in payload["moments"] if m["kind"] == "missed_capitalization"]
    assert len(missed) == 1
    assert missed[0]["ply"] == 3
    assert missed[0]["facts"]["opponent_blunder_ply"] == 2
    assert missed[0]["facts"]["fraction_given_back"] >= moments.MISSED_CAPITALIZATION_FRACTION


def test_missed_capitalization_not_flagged_when_user_keeps_advantage():
    plies = _missed_cap_plies()
    # No leak recorded for the user's ply-3 reply at all — the honest
    # real-world shape when the user's move wasn't itself a mistake/blunder.
    payload = extract_moments(plies, [], {}, "white", None)
    assert [m for m in payload["moments"] if m["kind"] == "missed_capitalization"] == []


# ---------------------------------------------------------------------------
# Time-trouble flag
# ---------------------------------------------------------------------------

def test_time_trouble_flag_added_for_low_clock_mistake():
    plies = [_ply(1, fen=FEN_WHITE, cp=0, is_user=1, clock=3000)]
    leaks = [_leak(ply=1, severity="blunder")]
    payload = extract_moments(plies, leaks, {}, "white", None)
    kinds = {m["kind"] for m in payload["moments"]}
    assert kinds == {"user_blunder", "time_trouble"}
    tt = next(m for m in payload["moments"] if m["kind"] == "time_trouble")
    assert tt["facts"]["clock_centis"] == 3000
    assert tt["facts"]["underlying_kind"] == "user_blunder"


def test_time_trouble_flag_absent_without_clock_data():
    plies = [_ply(1, fen=FEN_WHITE, cp=0, is_user=1, clock=None)]
    leaks = [_leak(ply=1, severity="blunder")]
    payload = extract_moments(plies, leaks, {}, "white", None)
    assert {m["kind"] for m in payload["moments"]} == {"user_blunder"}


def test_time_trouble_flag_absent_with_plenty_of_clock():
    plies = [_ply(1, fen=FEN_WHITE, cp=0, is_user=1, clock=8000)]
    leaks = [_leak(ply=1, severity="blunder")]
    payload = extract_moments(plies, leaks, {}, "white", None)
    assert {m["kind"] for m in payload["moments"]} == {"user_blunder"}


# ---------------------------------------------------------------------------
# Cap + priority
# ---------------------------------------------------------------------------

def test_cap_keeps_the_biggest_swings_and_reports_dropped_count():
    """14 opponent blunders of increasing severity; cap=12 keeps the 12
    biggest and drops the 2 smallest, reporting moments_dropped == 2."""
    plies = []
    n_blunders = 14
    for k in range(n_blunders):
        base = 4 * k
        plies.append(_ply(base + 1, fen=FEN_WHITE, cp=0, is_user=1))
        plies.append(_ply(base + 2, fen=FEN_BLACK, cp=0, is_user=0))       # blunder ply
        plies.append(_ply(base + 3, fen=FEN_WHITE, cp=500 + 20 * k, is_user=1))
        plies.append(_ply(base + 4, fen=FEN_WHITE, cp=0, is_user=1))       # reset

    payload = extract_moments(plies, [], {}, "white", None)
    assert len(payload["moments"]) == 12
    assert payload["moments_dropped"] == 2
    assert all(m["kind"] == "opponent_blunder" for m in payload["moments"])

    kept_plies = {m["ply"] for m in payload["moments"]}
    # Blunder k is at ply 4k + 2; the two smallest swings (k=0, k=1) must be
    # the ones dropped.
    assert (4 * 0 + 2) not in kept_plies
    assert (4 * 1 + 2) not in kept_plies
    assert (4 * 13 + 2) in kept_plies  # biggest swing always survives


def test_priority_order_blunders_beat_lower_tiers_under_cap(monkeypatch):
    """Force a tiny cap and verify the tier ordering: blunders > tide_turn >
    narrow_choice > missed_capitalization > time_trouble."""
    monkeypatch.setattr(moments, "MAX_MOMENTS", 1)

    plies = [
        _ply(1, fen=FEN_WHITE, cp=-300, is_user=1),
        _ply(2, fen=FEN_BLACK, cp=400, is_user=0),   # tide_turn candidate
        _ply(3, fen=FEN_WHITE, cp=0, is_user=1, clock=3000),
    ]
    leaks = [_leak(ply=3, severity="blunder")]  # top-tier moment + time_trouble flag
    pos_by_epd = {
        _epd(FEN_WHITE): _pos_row(eval_cp_white=50, pv2_cp_white=-400),
    }
    payload = extract_moments(plies, leaks, pos_by_epd, "white", None)
    assert len(payload["moments"]) == 1
    assert payload["moments"][0]["kind"] == "user_blunder"
    assert payload["moments_dropped"] >= 2  # at least tide_turn + one more were trimmed


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_deterministic_ordering_across_repeated_calls():
    plies = [
        _ply(1, fen=FEN_WHITE, cp=-300, is_user=1),
        _ply(2, fen=FEN_BLACK, cp=400, is_user=0),
        _ply(3, fen=FEN_WHITE, cp=0, is_user=1),
    ]
    leaks = [_leak(ply=3, severity="mistake", wp_drop=0.15)]
    payload1 = extract_moments(plies, leaks, {}, "white", None)
    payload2 = extract_moments(plies, leaks, {}, "white", None)
    assert payload1 == payload2


# ---------------------------------------------------------------------------
# header / profile_context passthrough convention
# ---------------------------------------------------------------------------

def test_header_lifted_from_profile_context_and_full_context_passed_through():
    ctx = {"header": {"white": "Alice", "black": "Bob"}, "clusters": [{"category": "hanging"}]}
    payload = extract_moments([], [], {}, "white", ctx)
    assert payload["header"] == {"white": "Alice", "black": "Bob"}
    assert payload["profile_context"] == ctx


def test_header_none_when_profile_context_missing_or_not_a_dict():
    assert extract_moments([], [], {}, "white", None)["header"] is None
    assert extract_moments([], [], {}, "white", {"clusters": []})["header"] is None


# ---------------------------------------------------------------------------
# eval-arc summary
# ---------------------------------------------------------------------------

def test_eval_arc_per_phase_min_max_end():
    plies = [
        _ply(1, fen=FEN_WHITE, cp=100, is_user=1),   # opening (full material)
        _ply(2, fen=FEN_WHITE, cp=-50, is_user=0),   # opening again
        _ply(3, fen=FEN_ENDGAME_WHITE, cp=0, is_user=1),  # endgame (bare K+P)
    ]
    payload = extract_moments(plies, [], {}, "white", None)
    arc = payload["eval_arc"]
    assert "opening" in arc and "endgame" in arc
    assert "middlegame" not in arc
    assert arc["opening"]["max"] == pytest.approx(win_prob_from_cp(100), abs=1e-4)
    assert arc["opening"]["min"] == pytest.approx(win_prob_from_cp(-50), abs=1e-4)
    assert arc["opening"]["end"] == pytest.approx(win_prob_from_cp(-50), abs=1e-4)
    assert arc["endgame"]["end"] == pytest.approx(win_prob_from_cp(0), abs=1e-4)
