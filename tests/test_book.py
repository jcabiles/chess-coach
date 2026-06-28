"""
Unit tests for app/book.py — opening-book fast-path (no engine, no network).

Uses tests/fixtures/book_sample.json + synthetic UCI lines; no Stockfish needed.
"""

from __future__ import annotations

import chess
import pytest

from app import book

FIXTURE = "tests/fixtures/book_sample.json"   # firstMoves = ["e2e4"], includeTraps
MISSING = "tests/fixtures/does_not_exist.json"
START = chess.STARTING_FEN


@pytest.fixture
def loaded():
    # One in-scope Ruy line, one out-of-scope d4 line, one synthetic trap line.
    book.load(
        FIXTURE,
        lines=[
            ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"],  # Ruy Lopez (first move in scope)
            ["d2d4", "d7d5"],                            # d4 (first move NOT in scope)
        ],
        trap_ucis=[["e2e4", "e7e5", "f1c4", "d8h4"]],   # folded-in trap line
    )
    yield book
    book.load(MISSING)  # reset to empty so other modules start clean


def test_first_move_in_scope_is_book(loaded):
    assert book.is_book_move(START, "e2e4") is True


def test_out_of_scope_first_move_not_book(loaded):
    # The d4 line is excluded by firstMoves, so 1.d4 is not book in this fixture.
    assert book.is_book_move(START, "d2d4") is False


def test_deeper_continuation_is_book(loaded):
    after_e4e5nf3 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"
    assert book.is_book_move(after_e4e5nf3, "b8c6") is True


def test_transposition_recognized(loaded):
    # Reach the Ruy position (after 1.e4 e5 2.Nf3 Nc6 3.Bb5) by a DIFFERENT move
    # order: 1.e4 Nc6 2.Nf3 e5 3.Bb5. The final move lands on a known position, so
    # it's book even though the path was not the stored line.
    b = chess.Board()
    for u in ["e2e4", "b8c6", "g1f3", "e7e5"]:
        b.push_uci(u)
    assert book.is_book_move(b.fen(), "f1b5") is True


def test_trap_line_folded_in(loaded):
    b = chess.Board()
    for u in ["e2e4", "e7e5", "f1c4"]:
        b.push_uci(u)
    assert book.is_book_move(b.fen(), "d8h4") is True


def test_illegal_move_not_book(loaded):
    assert book.is_book_move(START, "e2e5") is False


def test_bad_fen_not_book(loaded):
    assert book.is_book_move("not a fen", "e2e4") is False


def test_empty_index_never_book():
    book.load(MISSING)
    assert book._index.empty is True
    assert book.is_book_move(START, "e2e4") is False
