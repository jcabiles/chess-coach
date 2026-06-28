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


def test_trap_continuation_recognized(real_book):
    lines = traps.iter_mainline_ucis()
    assert lines, "expected trap mainlines to be available"
    line = lines[0]
    b = chess.Board()
    for u in line[:-1]:
        b.push_uci(u)
    assert book.is_book_move(b.fen(), line[-1]) is True
