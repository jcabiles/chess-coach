"""
repertoire.py — Repertoire Trainer backend logic (pure, no engine, no network).

Loads data/repertoire.json at startup and exposes:
  - load(path=None) -> None
  - init(path=None) -> None  (convenience wrapper for lifespan wiring)
  - tree() -> dict   ({"white": <move-tree>, "black": <move-tree>, "catalog": {...}})
  - iter_lines() -> list[list[str]]  (full UCI lines, for folding into the opening book)

Each line in the data file is either a SAN ``line`` (replayed from the standard start
with python-chess, which validates legality and derives UCIs) or a ``trapId`` reference
(its mainline is pulled from :mod:`app.traps`). The loader groups lines by
color -> parentOpening -> line (the **catalog**, for the browse/jump UI) and builds a
per-color **move prefix tree** (for practice traversal: randomize the opponent among
prepared children, check your move against the single prepared child).

Invariant (enforced + logged): at a node where it is YOUR turn (side-to-move ==
yourColor) there is exactly ONE prepared child. A line that would add a second, different
child at a your-turn node is an authoring conflict — it is dropped with a loud warning so
practice deviation-checking stays unambiguous. Opponent-turn nodes may branch.

All position handling uses python-chess; like openings.py / traps.py this module never
computes anything the client must trust — it only replays legal UCI/SAN moves.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import chess

from app import traps

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singletons — initialised to empty so imports never raise.
# ---------------------------------------------------------------------------

# Accepted line records: {id, name, parentOpening, yourColor, note, ucis, isTrap}
_records: list[dict] = []

_REQUIRED = {"id", "name", "parentOpening", "yourColor"}
_VALID_COLORS = {"white", "black"}


def _empty_tree() -> dict:
    """A well-formed empty tree: both color roots present with no children."""
    return {
        "white": {"uci": None, "san": None, "ply": 0, "yourTurn": True,
                  "leaf": True, "lineIds": [], "endsLines": [], "children": []},
        "black": {"uci": None, "san": None, "ply": 0, "yourTurn": False,
                  "leaf": True, "lineIds": [], "endsLines": [], "children": []},
        "catalog": {"white": [], "black": []},
    }


# Serialized move trees per color + the grouped catalog, rebuilt on each load().
_tree: dict = _empty_tree()


# ---------------------------------------------------------------------------
# Parsing / building helpers
# ---------------------------------------------------------------------------


def _color_bool(color: str) -> bool:
    """Map 'white'/'black' to the python-chess turn boolean (white == True)."""
    return color == "white"


def _resolve_ucis(line: dict) -> Optional[list[str]]:
    """Return the full UCI sequence for *line*, or None if it can't be resolved.

    SAN ``line`` is replayed from the start (validates legality); a ``trapId`` is
    resolved via ``traps.mainline_ucis_for``. Returns None (caller drops the line) on
    any problem — never raises.
    """
    san_line = line.get("line")
    trap_id = line.get("trapId")

    if san_line is not None and trap_id is not None:
        return None  # ambiguous: exactly one of line / trapId allowed
    if san_line is None and trap_id is None:
        return None

    if trap_id is not None:
        variation = line.get("variation", 0)
        if not isinstance(variation, int):
            return None
        ucis = traps.mainline_ucis_for(trap_id, variation)
        return ucis or None

    # SAN line: replay from the standard start.
    if not isinstance(san_line, list) or not san_line:
        return None
    try:
        board = chess.Board()
        ucis = [board.push_san(san).uci() for san in san_line]
    except Exception:
        return None
    return ucis or None


def _has_conflict(root: dict, ucis: list[str], your_bool: bool) -> bool:
    """True if inserting *ucis* would add a 2nd child at an existing your-turn node.

    A conflict can only arise against an EXISTING child (once we reach all-new
    territory, every your-turn node we create gets exactly our one move). So we walk
    the existing tree and stop as soon as the path leaves it.
    """
    board = chess.Board()
    node = root
    for uci in ucis:
        your_to_move = board.turn == your_bool
        children = node["children"]
        if your_to_move and children and uci not in children:
            return True  # your-turn node already has a different prepared move
        nxt = children.get(uci)
        try:
            board.push_uci(uci)
        except Exception:
            return True  # illegal mid-line (shouldn't happen post-resolve) -> reject
        if nxt is None:
            return False  # rest is fresh -> no further existing-child conflict
        node = nxt
    return False


def _insert(root: dict, rec: dict, your_bool: bool) -> None:
    """Insert an accepted line's UCIs into the move tree, tagging lineIds.

    Assumes :func:`_has_conflict` already returned False for this line.
    """
    board = chess.Board()
    node = root
    ucis = rec["ucis"]
    for i, uci in enumerate(ucis):
        move = chess.Move.from_uci(uci)
        child = node["children"].get(uci)
        if child is None:
            san = board.san(move)
            child = {
                "uci": uci,
                "san": san,
                "ply": i + 1,
                "yourTurn": None,   # set after the push (turn at this node)
                "lineIds": set(),
                "endsLines": set(),
                "children": {},
            }
            node["children"][uci] = child
        child["lineIds"].add(rec["id"])
        board.push(move)
        child["yourTurn"] = board.turn == your_bool
        node = child
    node["endsLines"].add(rec["id"])


def _new_root(your_bool: bool) -> dict:
    return {
        "uci": None,
        "san": None,
        "ply": 0,
        "yourTurn": chess.WHITE == your_bool,  # start position: White to move
        "lineIds": set(),
        "endsLines": set(),
        "children": {},
    }


def _serialize(node: dict) -> dict:
    """Convert an internal node (sets + dict children) to a JSON-able structure."""
    children = [_serialize(c) for c in node["children"].values()]
    return {
        "uci": node["uci"],
        "san": node["san"],
        "ply": node["ply"],
        "yourTurn": bool(node["yourTurn"]),
        "leaf": not children,
        "lineIds": sorted(node["lineIds"]),
        "endsLines": sorted(node["endsLines"]),
        "children": children,
    }


def _build_catalog(records: list[dict]) -> dict:
    """Group records by color -> parentOpening (preserving first-seen order)."""
    catalog: dict[str, list[dict]] = {"white": [], "black": []}
    index: dict[tuple[str, str], dict] = {}
    for rec in records:
        color = rec["yourColor"]
        key = (color, rec["parentOpening"])
        group = index.get(key)
        if group is None:
            group = {"parentOpening": rec["parentOpening"], "lines": []}
            index[key] = group
            catalog[color].append(group)
        group["lines"].append({
            "id": rec["id"],
            "name": rec["name"],
            "note": rec.get("note", ""),
            "ucis": rec["ucis"],
            "isTrap": rec["isTrap"],
        })
    return catalog


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load(path: Optional[str] = None) -> None:
    """Parse *path* (a JSON file) and rebuild the module-level structures.

    Import-safe: a missing/unreadable/invalid file logs one warning and resets to empty
    without raising. Individual malformed or conflicting lines are dropped with a
    warning; the rest still load. (Requires :mod:`app.traps` to be loaded first for any
    ``trapId`` lines — the lifespan calls ``traps.init`` before ``repertoire.init``.)
    """
    global _records, _tree

    if path is None:
        path = os.environ.get("REPERTOIRE_FILE", "data/repertoire.json")
    file_path = Path(path)

    # Reset first so a failed reload leaves a clean, empty state.
    _records = []
    _tree = _empty_tree()

    if not file_path.exists():
        logger.warning("repertoire: file '%s' not found — feature disabled", file_path)
        return
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("repertoire: cannot read/parse '%s': %s — feature disabled", file_path, exc)
        return
    if not isinstance(data, dict) or not isinstance(data.get("lines"), list):
        logger.warning("repertoire: '%s' has no top-level 'lines' list — feature disabled", file_path)
        return

    roots = {"white": _new_root(True), "black": _new_root(False)}
    seen_ids: set[str] = set()
    accepted: list[dict] = []

    for line in data["lines"]:
        if not isinstance(line, dict):
            logger.warning("repertoire: skipping non-dict entry")
            continue
        line_id = line.get("id", "<unknown>")

        missing = _REQUIRED - set(line.keys())
        if missing:
            logger.warning("repertoire: dropping %r: missing fields %s", line_id, missing)
            continue
        if line["yourColor"] not in _VALID_COLORS:
            logger.warning("repertoire: dropping %r: invalid yourColor %r", line_id, line["yourColor"])
            continue
        if line["id"] in seen_ids:
            logger.warning("repertoire: dropping %r: duplicate id", line_id)
            continue

        ucis = _resolve_ucis(line)
        if not ucis:
            logger.warning("repertoire: dropping %r: could not resolve a legal line", line_id)
            continue

        color = line["yourColor"]
        your_bool = _color_bool(color)
        if _has_conflict(roots[color], ucis, your_bool):
            logger.warning(
                "repertoire: dropping %r: your-turn conflict (two prepared moves at one "
                "position) — line not loaded", line_id,
            )
            continue

        rec = {
            "id": line["id"],
            "name": line["name"],
            "parentOpening": line["parentOpening"],
            "yourColor": color,
            "note": line.get("note", ""),
            "ucis": ucis,
            "isTrap": line.get("trapId") is not None,
        }
        _insert(roots[color], rec, your_bool)
        seen_ids.add(line["id"])
        accepted.append(rec)

    _records = accepted
    _tree = {
        "white": _serialize(roots["white"]),
        "black": _serialize(roots["black"]),
        "catalog": _build_catalog(accepted),
    }
    logger.info("repertoire: loaded %d lines from '%s'", len(accepted), file_path)


def init(path: Optional[str] = None) -> None:
    """Convenience wrapper — call load() at app startup."""
    load(path)


def tree() -> dict:
    """Return the serialized repertoire: per-color move trees + the grouped catalog.

    Always well-formed; empty (roots present with no children, empty catalog) when no
    data is loaded.
    """
    return _tree


def iter_lines() -> list[list[str]]:
    """Return every accepted line as a full UCI list from the start.

    Used to fold repertoire positions into the opening book. Exception-safe: returns a
    best-effort list, never raises.
    """
    try:
        return [list(rec["ucis"]) for rec in _records]
    except Exception:  # pragma: no cover - defensive
        return []
