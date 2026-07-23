"""
Data tests for the opening book — validates data/book.json against the REAL
lichess openings + traps. No Stockfish needed (the book path never touches it).
"""

from __future__ import annotations

import json

import chess
import pytest

from app import book, openings, traps


@pytest.fixture(scope="module")
def real_book():
    openings.init("data/openings")
    traps.init("data/traps.json")
    book.load(
        "data/book.json",
        lines=openings.iter_lines(),
        trap_ucis=traps.iter_mainline_ucis(),
        blocklist_epds=traps.iter_victim_epds(),  # mirror the real startup wiring
    )
    yield book
    book.load("tests/fixtures/does_not_exist.json")  # reset to empty afterwards


def _all_book(sans: list[str]) -> bool:
    b = chess.Board()
    for san in sans:
        mv = b.parse_san(san)
        if not book.is_book_move(b.fen(), mv.uci()):
            return False
        b.push(mv)
    return True


def test_config_shape():
    cfg = json.loads(open("data/book.json", encoding="utf-8").read())
    assert {"firstMoves", "includeTraps", "extraLines"} <= set(cfg)
    assert "e2e4" in cfg["firstMoves"] and "d2d4" in cfg["firstMoves"]


def test_index_non_empty(real_book):
    assert not book._index.empty


def test_italian_is_book(real_book):
    assert _all_book(["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5"])


def test_najdorf_is_book(real_book):
    assert _all_book(["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6"])


def test_kings_indian_is_book(real_book):
    assert _all_book(["d4", "Nf6", "c4", "g6", "Nc3", "Bg7"])


def test_in_scope_first_moves_are_book(real_book):
    b = chess.Board()
    assert book.is_book_move(b.fen(), "e2e4") is True
    assert book.is_book_move(b.fen(), "d2d4") is True


def test_flank_and_offbeat_not_book(real_book):
    b = chess.Board()
    assert book.is_book_move(b.fen(), "c2c4") is False   # flank, excluded by config
    assert book.is_book_move(b.fen(), "a2a4") is False   # offbeat


def test_trap_lead_in_and_trapper_moves_are_book(real_book):
    # A trap's setup (lead-in) and trapper-side replies stay book — only the victim's
    # losing moves are un-booked. Blackburne Shilling: lead-in all book; 4...Qg5 (the
    # trapper's winning reply, played after 4.Nxe5) stays book.
    assert _all_book(["e4", "e5", "Nf3", "Nc6", "Bc4", "Nd4"])
    b = chess.Board()
    for san in ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nd4", "Nxe5"]:
        b.push_san(san)
    assert book.is_book_move(b.fen(), b.parse_san("Qg5").uci()) is True


def test_no_trap_victim_position_is_book(real_book):
    # Regression guard for the core bug: EVERY trap's victim-side (losing) position
    # must be un-booked so the blunder falls through to the engine and gets a quality
    # label in live play. Covers all 19 traps, including transposition-escape traps
    # whose victim position is ALSO reachable via a sound opening-DB line (the
    # blocklist subtraction is what handles those).
    checked = 0
    for trap in traps.traps_by_id.values():
        lead = chess.Board()
        try:
            for san in trap.get("leadInSan", []):
                lead.push_san(san)
        except ValueError:
            continue
        for variation in trap.get("variations", []):
            b = lead.copy()
            for step in variation.get("mainLine", []):
                uci = step.get("uci")
                if not uci:
                    break
                fen_before = b.fen()
                b.push_uci(uci)
                if step.get("side") == "victim":
                    assert book.is_book_move(fen_before, uci) is False, (
                        f"{trap.get('id')}: victim move {uci} is still in book"
                    )
                    checked += 1
    assert checked > 0, "expected at least one victim-side trap move to check"


def test_fried_liver_victim_not_book_despite_opening_db(real_book):
    # Fried Liver's 5...Nxd5?! is a real opening-DB line AND a trap victim move. A
    # naive "skip victim plies in the trap seed" would leave it booked by the opening
    # DB; the blocklist subtraction un-books it regardless of source.
    b = chess.Board()
    for san in ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "Ng5", "d5", "exd5"]:
        b.push_san(san)
    assert book.is_book_move(b.fen(), b.parse_san("Nxd5").uci()) is False
