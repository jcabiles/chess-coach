"""
Tests for app/openings.py — Opening Trainer backend logic.

No Stockfish needed. Uses tests/fixtures/openings_sample.tsv only.
"""

from __future__ import annotations

import chess
import pytest

from app import openings

FIXTURE_DIR = "tests/fixtures"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STARTING_FEN = chess.STARTING_FEN


def _epd_after(uci_str: str) -> str:
    """Replay a space-separated UCI string and return the final EPD."""
    board = chess.Board()
    for m in uci_str.split():
        board.push_uci(m)
    return board.epd()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def idx():
    """Load the sample fixture TSV once for the whole module."""
    return openings.load(FIXTURE_DIR)


# ---------------------------------------------------------------------------
# EPD-convention assertion (guards the canonical-producer requirement)
# ---------------------------------------------------------------------------


def test_epd_convention_matches_tsv(idx):
    """Replaying a fixture row's UCI and calling board.epd() must equal the TSV epd column.

    Samples the C01 French Defense: Exchange Variation row.
    """
    # C01 French Defense: Exchange Variation
    uci = "e2e4 e7e6 d2d4 d7d5 e4d5"
    expected_epd = "rnbqkbnr/ppp2ppp/4p3/3P4/3P4/8/PPP2PPP/RNBQKBNR b KQkq -"
    derived_epd = _epd_after(uci)
    assert derived_epd == expected_epd, (
        f"EPD mismatch: derived={derived_epd!r}, expected={expected_epd!r}"
    )
    # Also verify the EPD is in the index (meaning the TSV was parsed correctly).
    assert derived_epd in idx.name_by_epd


def test_ep_epd_convention(idx):
    """The EP-line row must produce an EPD with a real en-passant square (f6)."""
    # C44 King's Pawn Game: EP line — 1.e4 d5 2.e5 f5 -> ep square f6
    uci = "e2e4 d7d5 e4e5 f7f5"
    epd = _epd_after(uci)
    # python-chess emits the ep square only when the capture is legal
    assert epd.endswith("f6"), f"Expected ep square f6, got: {epd!r}"
    assert epd in idx.name_by_epd


# ---------------------------------------------------------------------------
# Name detection
# ---------------------------------------------------------------------------


def test_identify_ruy_lopez(idx):
    """identify() returns the Ruy Lopez name for the standard move order."""
    result = openings.identify(STARTING_FEN, ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"])
    assert result is not None
    assert result["eco"] == "C60"
    assert "Ruy Lopez" in result["name"]


def test_identify_returns_deepest_match(idx):
    """identify() returns the deepest (most-specific) named opening on the line.

    After e4 e5 Nf3 Nc6 Bb5 the position is Ruy Lopez (C60, 5 plies),
    which should beat King's Pawn Game: Center Game (3 plies) and
    Alekhine's Defense (2 plies) etc.
    """
    result = openings.identify(STARTING_FEN, ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"])
    assert result is not None
    # C60 Ruy Lopez is the deepest match (5 plies) on this line
    assert result["eco"] == "C60"


def test_identify_returns_none_for_unknown(idx):
    """identify() returns None when no named opening matches the line."""
    result = openings.identify(STARTING_FEN, ["g1f3", "g8f6", "g2g3"])
    assert result is None


def test_identify_partial_match(idx):
    """identify() returns a shallower match when the line goes past known data."""
    # Play the Italian Game (C50, 5 plies) then an extra unknown move
    result = openings.identify(
        STARTING_FEN, ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "d7d6"]
    )
    # The line after 6 plies is not in the fixture, but C50 Italian matches at ply 5
    assert result is not None
    assert result["eco"] == "C50"


# ---------------------------------------------------------------------------
# Transposition test
# ---------------------------------------------------------------------------


def test_transposition_same_result(idx):
    """Two move orders reaching the same position must return the same {eco, name}.

    Standard order: 1.e4 e5 2.Nf3 Nc6 3.Bb5
    Transposition:  1.Nf3 Nc6 2.e4 e5 3.Bb5
    Both arrive at the Ruy Lopez EPD.
    """
    standard = openings.identify(
        STARTING_FEN, ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"]
    )
    transposition = openings.identify(
        STARTING_FEN, ["g1f3", "b8c6", "e2e4", "e7e5", "f1b5"]
    )
    assert standard is not None
    assert transposition is not None
    assert standard == transposition, (
        f"Transposition mismatch: standard={standard}, transposition={transposition}"
    )


# ---------------------------------------------------------------------------
# Missing-data degradation
# ---------------------------------------------------------------------------


def test_load_nonexistent_dir_returns_empty():
    """load() with a nonexistent directory returns empty structures without raising."""
    idx = openings.load("/nonexistent/path/for/openings/test")
    assert idx.name_by_epd == {}


def test_identify_with_empty_index_returns_none():
    """identify() returns None when the index is empty (no data loaded)."""
    openings.load("/nonexistent/path/for/openings/test")
    result = openings.identify(STARTING_FEN, ["e2e4", "e7e5"])
    assert result is None
    # Restore
    openings.load(FIXTURE_DIR)


def test_load_empty_dir_returns_empty(tmp_path):
    """load() with an existing but empty directory returns empty structures."""
    idx = openings.load(str(tmp_path))
    assert idx.name_by_epd == {}
    # Restore
    openings.load(FIXTURE_DIR)


def test_no_exception_on_bad_fen():
    """identify() does not raise on an invalid FEN."""
    openings.load(FIXTURE_DIR)
    result = openings.identify("not a valid fen", ["e2e4"])
    assert result is None
