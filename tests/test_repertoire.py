"""
Tests for app/repertoire.py — Repertoire Trainer backend logic.

No Stockfish needed. Uses the shipped data/repertoire.json (with data/traps.json
loaded for trap-leaf resolution) and tests/fixtures/repertoire_sample.json.
"""

from __future__ import annotations

import chess
import pytest

from app import book, repertoire, traps

SHIPPED = "data/repertoire.json"
FIXTURE = "tests/fixtures/repertoire_sample.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _walk(node):
    """Yield every node in a serialized move tree (depth-first)."""
    yield node
    for child in node["children"]:
        yield from _walk(child)


def _replay_legal(ucis):
    """Replay a UCI list from the start; raises on any illegal move."""
    board = chess.Board()
    for u in ucis:
        board.push_uci(u)
    return board


def _catalog_ids(catalog):
    return {ln["id"] for color in ("white", "black") for g in catalog[color] for ln in g["lines"]}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def shipped():
    traps.init("data/traps.json")        # needed for trapId leaves
    repertoire.init(SHIPPED)
    yield


@pytest.fixture
def sample():
    traps.init("data/traps.json")
    repertoire.init(FIXTURE)
    yield
    repertoire.init(SHIPPED)             # restore for any later test


# ---------------------------------------------------------------------------
# Shipped-data tests
# ---------------------------------------------------------------------------


def test_shipped_lines_replay_legally(shipped):
    """Every shipped line is a legal sequence from the standard start."""
    lines = repertoire.iter_lines()
    assert len(lines) >= 8           # the curated set (~8-15)
    for ucis in lines:
        assert ucis, "empty line"
        _replay_legal(ucis)          # raises if any move is illegal


def test_shipped_invariant_your_turn_single_child(shipped):
    """At any your-turn node, there is at most one prepared child (per color)."""
    t = repertoire.tree()
    for color in ("white", "black"):
        for node in _walk(t[color]):
            if node["yourTurn"]:
                assert len(node["children"]) <= 1, (
                    f"{color}: your-turn node {node['uci']} has "
                    f"{len(node['children'])} children"
                )


def test_shipped_white_root_single_first_move(shipped):
    """As White your first move is forced single (1.e4)."""
    white = repertoire.tree()["white"]
    assert [c["uci"] for c in white["children"]] == ["e2e4"]


def test_shipped_opponent_branches(shipped):
    """After 1.e4 (White repertoire) the opponent has several prepared replies."""
    white = repertoire.tree()["white"]
    e4 = white["children"][0]
    opts = {c["uci"] for c in e4["children"]}
    assert {"e7e5", "c7c5", "d7d5"} <= opts


def test_shipped_trap_leaf_present(shipped):
    """A trap line resolves and appears as an isTrap leaf with a real UCI line."""
    cat = repertoire.tree()["catalog"]
    trap_lines = [ln for g in cat["white"] for ln in g["lines"] if ln["isTrap"]]
    assert trap_lines, "expected at least one trap leaf"
    for ln in trap_lines:
        assert len(ln["ucis"]) >= 4
        _replay_legal(ln["ucis"])


def test_shipped_book_extension(shipped):
    """A curated line's reached positions are recognized by the opening book.

    Builds the book from the repertoire lines ALONE (no lichess lines) so the
    assertion isolates the repertoire->book fold.
    """
    book.load("data/book.json", lines=[], trap_ucis=list(repertoire.iter_lines()))
    try:
        ucis = repertoire.iter_lines()[0]
        before = _replay_legal(ucis[:-1])
        assert book.is_book_move(before.fen(), ucis[-1]) is True
    finally:
        book.load("tests/fixtures/does_not_exist.json")  # reset book state


# ---------------------------------------------------------------------------
# Fixture tests (conflict drop, illegal drop, branching, grouping)
# ---------------------------------------------------------------------------


def test_sample_drops_conflict_and_illegal(sample):
    """wbad (your-turn conflict) and willegal (illegal SAN) are dropped."""
    ids = _catalog_ids(repertoire.tree()["catalog"])
    assert ids == {"w-italian", "w-sicilian", "b-french"}
    assert "wbad" not in ids and "willegal" not in ids
    assert len(repertoire.iter_lines()) == 3


def test_sample_opponent_branch_after_e4(sample):
    """1.e4 is a single your-turn child; the opponent then branches e5 / c5."""
    white = repertoire.tree()["white"]
    assert [c["uci"] for c in white["children"]] == ["e2e4"]
    e4 = white["children"][0]
    assert sorted(c["uci"] for c in e4["children"]) == ["c7c5", "e7e5"]


def test_sample_your_turn_single_child(sample):
    """The conflict drop keeps the invariant intact (e.g. Nf3 only after 1.e4 e5)."""
    for color in ("white", "black"):
        for node in _walk(repertoire.tree()[color]):
            if node["yourTurn"]:
                assert len(node["children"]) <= 1


def test_sample_catalog_grouping(sample):
    """Catalog groups by color -> parentOpening."""
    cat = repertoire.tree()["catalog"]
    white_groups = {g["parentOpening"] for g in cat["white"]}
    black_groups = {g["parentOpening"] for g in cat["black"]}
    assert {"Italian Game", "Sicilian Defense"} <= white_groups
    assert "French Defense" in black_groups


# ---------------------------------------------------------------------------
# Degradation
# ---------------------------------------------------------------------------


def test_missing_file_well_formed_empty():
    """A missing file yields a well-formed empty tree (roots present, no children)."""
    repertoire.load("/nonexistent/repertoire.json")
    t = repertoire.tree()
    assert t["white"]["children"] == [] and t["black"]["children"] == []
    assert t["catalog"] == {"white": [], "black": []}
    assert repertoire.iter_lines() == []
    repertoire.init(SHIPPED)  # restore
