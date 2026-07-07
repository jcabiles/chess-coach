"""Pure key-moments extractor for AI game commentary (narrative-review feature).

Digests already-persisted Stockfish analysis (``game_plies`` + ``leaks`` rows,
plus a prefetched ``pos_cache`` lookup) into a JSON-serializable, facts-only
payload. This payload is the ONLY chess content the narrative LLM ever sees
(``app/narrative.py`` turns it into a prompt) — nothing here invents a move,
a plan, or an evaluation that isn't already in the stored data.

Pure module — no engine, no storage/SQLite, no network, no ``anthropic``.
Importable and fully unit-testable without a Stockfish binary present.
``chess`` (python-chess) is used the same way ``app/analysis.py`` and
``app/accuracy.py`` already do: for ``chess.Board`` FEN parsing/EPD keys and
``.turn``, never ``chess.engine.SimpleEngine`` (no live engine process).

POV discipline (do not re-derive; see ``app/analysis.py``)
------------------------------------------------------------
- ``game_plies.eval_cp_white`` / ``mate_white`` are **White-POV**, and are
  mutually exclusive (``mate_white`` set implies ``eval_cp_white`` is
  ``NULL``). Always read both through ``analysis.win_prob_white``, which
  already NULL-guards.
- ``game_plies.win_prob`` (if present on a row) is **mover-POV** — this
  module does not read it; White-POV win probability is recomputed directly
  from ``eval_cp_white``/``mate_white`` via ``analysis.win_prob_white`` and
  converted to whichever POV a given detector needs.
- ``leaks.win_prob_before/after/drop`` are **user-POV** (leaks are only ever
  written for the user's own moves) and are passed through unchanged.
- ``leaks.lead_in_ply`` defaults to ``ply - 1`` when there is no genuine
  foresight signal (a display-timing default, not a real warning). The
  relative guard ``lead_in_ply < ply - 1`` (mirroring
  ``app/insights.py:648-658``) is the only correct test; an absolute
  ``>= 2`` check would wrongly flag nearly every leak as foreseeable.

Last-ply boundary
------------------
``game_plies`` stores the position *before* each ply; there is no "after" for
the game's final move. Detectors that need a next-ply eval (opponent
mistakes/blunders, tide turns) simply do not fire past the last index — same
fallback as ``app/review.py:383-393`` (no next position -> no computed swing).

Depth-10 noise floor
----------------------
Background evals are shallow (``REVIEW_BG_DEPTH``, default 10). All
mistake/blunder detection goes through ``analysis.leak_severity``'s
win-probability-drop thresholds (10%/20%), which — except very close to a
dead-even position — already corresponds to well over 60 centipawns of
swing (at cp=0, the steepest point of the win-prob curve, a 10% win-prob
drop needs roughly 108cp). No separate cp-delta computation is performed;
this is the single source of the "no moment below 60cp" guarantee.

``narrow_choice`` (NOT "only-move")
--------------------------------------
``pos_cache.pv2_cp_white`` is the 2nd-best line's score only — there is no
2nd-best move/UCI/SAN stored anywhere. A moment fires when the win-probability
gap between the best line and the 2nd-best line is >= 0.15, but its facts
never include a "second-best move". True single-legal-move positions have no
``pv2_cp_white`` row at all (multipv is capped by the legal-move count) and
are correctly out of scope here — this is a different detector from
``review.py``'s ``_is_only_move`` (100cp gap, used for lead-in seeding).

Calling convention for ``header`` / ``profile_context``
----------------------------------------------------------
``extract_moments`` takes exactly the five arguments named in the ticket —
there is no separate ``header`` parameter. Callers that have game-header
facts (players, ECO/opening, result, accuracy summary, etc.) should nest them
under a ``"header"`` key inside ``profile_context``, e.g.
``profile_context={"header": {...}, "clusters": [...]}``. This module lifts
``profile_context["header"]`` (if present) into the payload's own top-level
``"header"`` key for convenience, and also passes the full ``profile_context``
dict through unchanged under ``"profile_context"`` so callers keep access to
everything else (e.g. cross-game cluster summaries) they put in it.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import chess

from app.analysis import game_phase, leak_severity, win_prob_white

# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

MAX_MOMENTS: int = 12

# clock_centis is centiseconds; "< 60s" per spec.
TIME_TROUBLE_CENTIS: int = 6000

# Tide-turn: White-POV win prob crosses 0.5 with a total swing >= this.
TIDE_TURN_SWING: float = 0.20

# Narrow-choice: win-prob gap between best and 2nd-best line >= this.
NARROW_CHOICE_GAP: float = 0.15

# Missed capitalization: user's next-move win-prob drop must give back at
# least this fraction of what the opponent's blunder just handed over.
MISSED_CAPITALIZATION_FRACTION: float = 0.5

# Cap priority tiers (lower sorts first = kept preferentially under the cap).
# "blunders" per the ticket's priority list covers ALL leak-derived moments
# (user + opponent, both 'mistake' and 'blunder' severity) — there is no
# separate top-level tier for plain mistakes; within this tier, blunders are
# ordered ahead of mistakes via _SEVERITY_RANK below.
_KIND_PRIORITY: dict[str, int] = {
    "user_blunder": 0,
    "user_mistake": 0,
    "opponent_blunder": 0,
    "opponent_mistake": 0,
    "tide_turn": 1,
    "narrow_choice": 2,
    "missed_capitalization": 3,
    "time_trouble": 4,
}
_SEVERITY_RANK: dict[str, int] = {"blunder": 0, "mistake": 1}

# Fact keys (checked in this order) used as the intra-tier "how big a deal is
# this" magnitude for sorting/capping — the first key present on a moment's
# facts wins.
_MAGNITUDE_KEYS: tuple[str, ...] = (
    "win_prob_drop",
    "swing",
    "gap",
    "fraction_given_back",
)


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------

def _move_number(ply: int) -> int:
    """Standard chess move number for a 1-based ply index (ply 1,2 -> move 1)."""
    return (ply + 1) // 2


def _epd(fen: Optional[str]) -> Optional[str]:
    """Return the EPD key (board.epd()) for a FEN string, or None if invalid/absent.

    Mirrors ``app/review.py``'s ``epd_key = board.epd()`` exactly (same
    stripped fields: placement, active color, castling rights, en-passant
    square), so lookups against a caller-built ``pos_by_epd`` line up.
    """
    if not fen:
        return None
    try:
        return chess.Board(fen).epd()
    except ValueError:
        return None


def _mover_color(row: dict, mover_white: Optional[bool], my_color: Optional[str]) -> Optional[str]:
    """Resolve the color that made this ply's move.

    Prefers the FEN-derived side-to-move (``mover_white``, from the position
    BEFORE the move — the side to move there is the mover). Falls back to
    ``is_user_move`` + ``my_color`` when the FEN was missing/unparseable.
    """
    if mover_white is not None:
        return "white" if mover_white else "black"
    if my_color in ("white", "black"):
        is_user = bool(row.get("is_user_move"))
        if is_user:
            return my_color
        return "black" if my_color == "white" else "white"
    return None


def _pv_san(pv_san_json: Optional[str]) -> Optional[list]:
    """Parse a pos_cache ``pv_san_json`` column into a list, or None."""
    if not pv_san_json:
        return None
    try:
        pv = json.loads(pv_san_json)
    except (TypeError, ValueError):
        return None
    return pv or None


def _pos_facts(fen_before: Optional[str], pos_by_epd: dict) -> dict:
    """Best move + stored PV facts for a position, when available in pos_by_epd.

    Never includes a 2nd-best move — pos_cache only stores the 2nd-best
    line's *score* (``pv2_cp_white``), no move/UCI/SAN.
    """
    epd = _epd(fen_before)
    row = pos_by_epd.get(epd) if epd and pos_by_epd else None
    if not row:
        return {}
    facts: dict[str, Any] = {}
    if row.get("best_uci"):
        facts["best_uci"] = row["best_uci"]
    if row.get("best_san"):
        facts["best_san"] = row["best_san"]
    pv = _pv_san(row.get("pv_san_json"))
    if pv:
        facts["pv_san"] = pv
    return facts


def _analyze_plies(plies: list[dict]) -> list[dict]:
    """Per-ply derived fields aligned 1:1 with ``plies``: mover color, phase,
    and White-POV win probability (recomputed from eval_cp_white/mate_white,
    NULL-safe via analysis.win_prob_white)."""
    derived = []
    for row in plies:
        fen = row.get("fen_before")
        mover_white: Optional[bool] = None
        phase: Optional[str] = None
        if fen:
            try:
                board = chess.Board(fen)
                mover_white = board.turn
                phase = game_phase(board)
            except ValueError:
                pass
        wp_white = win_prob_white(row.get("eval_cp_white"), row.get("mate_white"))
        derived.append({"mover_white": mover_white, "phase": phase, "wp_white": wp_white})
    return derived


# ---------------------------------------------------------------------------
# Detectors — each returns a list of moment dicts
# ---------------------------------------------------------------------------

def _user_leak_moments(leaks: list[dict], plies_by_ply: dict) -> list[dict]:
    """User mistakes/blunders: straight passthrough from ``leaks`` rows."""
    moments = []
    for lk in leaks:
        sev = lk.get("severity")
        if sev not in ("mistake", "blunder"):
            continue
        ply_num = lk["ply"]
        ply_row = plies_by_ply.get(ply_num, {})
        fen_before = ply_row.get("fen_before")

        lead_in = lk.get("lead_in_ply")
        foreseeable = lead_in is not None and lead_in < ply_num - 1

        facts: dict[str, Any] = {
            "fen_before": fen_before,
            "category": lk.get("category"),
            "phase": lk.get("phase"),
            "win_prob_drop": lk.get("win_prob_drop"),
            "hung_square": lk.get("hung_square"),
            "threat_motif": lk.get("threat_motif"),
            "best_uci": lk.get("best_uci"),
            "best_san": lk.get("best_san"),
            "foreseeable": foreseeable,
        }
        if foreseeable:
            facts["lead_in_ply"] = lead_in
        moments.append({
            "ply": ply_num,
            "san": ply_row.get("san"),
            "move_number": _move_number(ply_num),
            "side": lk.get("color"),
            "is_user_move": True,
            "kind": f"user_{sev}",
            "severity": sev,
            "facts": facts,
        })
    return moments


def _attach_pv(moments: list[dict], pos_by_epd: dict) -> None:
    """Attach a stored PV (from pos_by_epd) to moments that don't already have one."""
    for m in moments:
        facts = m["facts"]
        if facts.get("pv_san"):
            continue
        pv = _pos_facts(facts.get("fen_before"), pos_by_epd).get("pv_san")
        if pv:
            facts["pv_san"] = pv


def _opponent_moments(
    plies: list[dict], derived: list[dict], my_color: Optional[str], pos_by_epd: dict
) -> list[dict]:
    """Opponent mistakes/blunders on is_user_move=0 plies.

    Computed the same way review.py computes user leaks (win-prob drop from
    the mover's own POV via analysis.leak_severity), generalized to any
    mover: White-POV win prob is recomputed per ply, converted to the
    opponent's POV, and compared before/after using the *next* ply's
    before-eval as this ply's after-eval (last-ply boundary: no next ply ->
    no computed swing, so the final ply never fires here).
    """
    moments = []
    n = len(plies)
    for i, row in enumerate(plies):
        if row.get("is_user_move"):
            continue  # opponent moves only
        if i + 1 >= n:
            continue  # last-ply boundary: no "after" position exists
        mover_color = _mover_color(row, derived[i]["mover_white"], my_color)
        if mover_color is None:
            continue  # can't safely resolve POV; skip rather than guess

        wp_white_before = derived[i]["wp_white"]
        wp_white_after = derived[i + 1]["wp_white"]
        if mover_color == "white":
            wp_before, wp_after = wp_white_before, wp_white_after
        else:
            wp_before, wp_after = 1.0 - wp_white_before, 1.0 - wp_white_after

        drop = max(0.0, wp_before - wp_after)
        sev = leak_severity(drop)
        if sev not in ("mistake", "blunder"):
            continue

        ply_num = row["ply"]
        facts: dict[str, Any] = {
            "fen_before": row.get("fen_before"),
            "phase": derived[i]["phase"],
            "win_prob_drop": round(drop, 4),
        }
        moments.append({
            "ply": ply_num,
            "san": row.get("san"),
            "move_number": _move_number(ply_num),
            "side": mover_color,
            "is_user_move": False,
            "kind": f"opponent_{sev}",
            "severity": sev,
            "facts": facts,
        })
    _attach_pv(moments, pos_by_epd)
    return moments


def _tide_turn_moments(
    plies: list[dict], derived: list[dict], my_color: Optional[str], pos_by_epd: dict
) -> list[dict]:
    """Plies where White-POV win prob crosses 0.5 with total swing >= 0.20."""
    moments = []
    n = len(plies)
    for i in range(n - 1):  # last-ply boundary: need a "next" eval
        wp_before = derived[i]["wp_white"]
        wp_after = derived[i + 1]["wp_white"]
        crosses = (wp_before - 0.5) * (wp_after - 0.5) < 0
        swing = wp_after - wp_before
        if not crosses or abs(swing) < TIDE_TURN_SWING:
            continue

        row = plies[i]
        ply_num = row["ply"]
        mover_color = _mover_color(row, derived[i]["mover_white"], my_color)
        facts = {
            "fen_before": row.get("fen_before"),
            "phase": derived[i]["phase"],
            "wp_white_before": round(wp_before, 4),
            "wp_white_after": round(wp_after, 4),
            "swing": round(abs(swing), 4),
        }
        moments.append({
            "ply": ply_num,
            "san": row.get("san"),
            "move_number": _move_number(ply_num),
            "side": mover_color,
            "is_user_move": bool(row.get("is_user_move")),
            "kind": "tide_turn",
            "severity": None,
            "facts": facts,
        })
    _attach_pv(moments, pos_by_epd)
    return moments


def _narrow_choice_moments(
    plies: list[dict], derived: list[dict], my_color: Optional[str], pos_by_epd: dict
) -> list[dict]:
    """Positions where the gap (win-prob space) between the best and 2nd-best
    line is >= 0.15. Never names a 2nd-best move — only its score exists."""
    moments = []
    for i, row in enumerate(plies):
        epd = _epd(row.get("fen_before"))
        pos_row = pos_by_epd.get(epd) if epd and pos_by_epd else None
        if not pos_row or pos_row.get("pv2_cp_white") is None:
            continue  # no 2nd-best line (incl. true single-legal-move positions)

        best_wp = win_prob_white(pos_row.get("eval_cp_white"), pos_row.get("mate_white"))
        pv2_wp = win_prob_white(pos_row.get("pv2_cp_white"), None)
        gap = abs(best_wp - pv2_wp)
        if gap < NARROW_CHOICE_GAP:
            continue

        ply_num = row["ply"]
        mover_color = _mover_color(row, derived[i]["mover_white"], my_color)
        facts: dict[str, Any] = {
            "fen_before": row.get("fen_before"),
            "phase": derived[i]["phase"],
            "gap": round(gap, 4),
            "best_uci": pos_row.get("best_uci"),
            "best_san": pos_row.get("best_san"),
        }
        pv = _pv_san(pos_row.get("pv_san_json"))
        if pv:
            facts["pv_san"] = pv
        moments.append({
            "ply": ply_num,
            "san": row.get("san"),
            "move_number": _move_number(ply_num),
            "side": mover_color,
            "is_user_move": bool(row.get("is_user_move")),
            "kind": "narrow_choice",
            "severity": None,
            "facts": facts,
        })
    return moments


def _missed_capitalization_moments(
    plies: list[dict], opponent_moments: list[dict], leaks_by_ply: dict
) -> list[dict]:
    """Opponent blunder immediately followed by the user giving most of it back."""
    plies_idx_by_ply = {row["ply"]: idx for idx, row in enumerate(plies)}
    moments = []
    for om in opponent_moments:
        if om["severity"] != "blunder":
            continue
        idx = plies_idx_by_ply.get(om["ply"])
        if idx is None or idx + 1 >= len(plies):
            continue
        next_row = plies[idx + 1]
        if not next_row.get("is_user_move"):
            continue  # plies alternate; this should not happen, but guard anyway
        next_ply = next_row["ply"]
        user_leak = leaks_by_ply.get(next_ply)
        if user_leak is None:
            continue  # user's reply wasn't itself a classified mistake/blunder

        swing = om["facts"]["win_prob_drop"]
        if not swing:
            continue
        user_drop = user_leak.get("win_prob_drop") or 0.0
        fraction = user_drop / swing
        if fraction < MISSED_CAPITALIZATION_FRACTION:
            continue

        facts = {
            "fen_before": next_row.get("fen_before"),
            "opponent_blunder_ply": om["ply"],
            "swing_given_by_opponent": round(swing, 4),
            "win_prob_given_back": round(user_drop, 4),
            "fraction_given_back": round(fraction, 4),
            "category": user_leak.get("category"),
            "best_uci": user_leak.get("best_uci"),
            "best_san": user_leak.get("best_san"),
        }
        moments.append({
            "ply": next_ply,
            "san": next_row.get("san"),
            "move_number": _move_number(next_ply),
            "side": user_leak.get("color"),
            "is_user_move": True,
            "kind": "missed_capitalization",
            "severity": user_leak.get("severity"),
            "facts": facts,
        })
    return moments


def _time_trouble_moments(leak_like_moments: list[dict], plies_by_ply: dict) -> list[dict]:
    """Flag mistake/blunder plies (user or opponent) played with < 60s on the clock."""
    moments = []
    for m in leak_like_moments:
        row = plies_by_ply.get(m["ply"], {})
        clock = row.get("clock_centis")
        if clock is None or clock >= TIME_TROUBLE_CENTIS:
            continue
        moments.append({
            "ply": m["ply"],
            "san": m["san"],
            "move_number": m["move_number"],
            "side": m["side"],
            "is_user_move": m["is_user_move"],
            "kind": "time_trouble",
            "severity": m["severity"],
            "facts": {
                "fen_before": m["facts"].get("fen_before"),
                "clock_centis": clock,
                "underlying_kind": m["kind"],
            },
        })
    return moments


def _eval_arc(derived: list[dict]) -> dict:
    """Per-phase min/max/end White-POV win probability across the game."""
    buckets: dict[str, list[float]] = {"opening": [], "middlegame": [], "endgame": []}
    for d in derived:
        phase = d["phase"]
        if phase in buckets:
            buckets[phase].append(d["wp_white"])
    arc = {}
    for phase, values in buckets.items():
        if not values:
            continue
        arc[phase] = {
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "end": round(values[-1], 4),
        }
    return arc


def _magnitude(m: dict) -> float:
    facts = m["facts"]
    for key in _MAGNITUDE_KEYS:
        val = facts.get(key)
        if val is not None:
            return val
    return 0.0


def _sort_key(m: dict) -> tuple:
    tier = _KIND_PRIORITY[m["kind"]]
    sev_rank = _SEVERITY_RANK.get(m["severity"], 2)
    return (tier, sev_rank, -_magnitude(m), m["ply"])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_moments(
    plies: list[dict],
    leaks: list[dict],
    pos_by_epd: dict,
    my_color: Optional[str],
    profile_context: Optional[dict] = None,
) -> dict:
    """Digest stored per-ply analysis into a facts-only commentary payload.

    Args:
        plies: Ordered ``game_plies`` rows for one game (``storage.get_plies``
            shape: ``ply``, ``san``, ``uci``, ``fen_before``, ``eval_cp_white``,
            ``mate_white``, ``win_prob``, ``is_user_move``, ``clock_centis``).
        leaks: ``leaks`` rows for the same game (``storage.get_leaks`` shape).
            User-only, mistakes/blunders only, by construction upstream.
        pos_by_epd: ``dict[epd_str -> pos_cache row dict]`` prefetched by the
            caller (this module never touches SQLite). A miss for a given
            position simply means that moment's facts omit best-move/PV.
        my_color: ``'white'`` or ``'black'`` (or ``None`` if unknown).
        profile_context: Optional dict of caller-supplied context. If it has
            a ``"header"`` key, that is lifted into the payload's own
            top-level ``"header"``; the full dict is also passed through
            unchanged under ``"profile_context"`` (see module docstring).

    Returns:
        A JSON-serializable dict::

            {
                "header": <profile_context.get("header")>,
                "profile_context": <profile_context, unchanged>,
                "my_color": my_color,
                "eval_arc": {"opening": {"min", "max", "end"}, ...},
                "moments": [
                    {
                        "ply": int, "san": str | None, "move_number": int,
                        "side": "white" | "black", "is_user_move": bool,
                        "kind": str, "severity": "mistake" | "blunder" | None,
                        "facts": {...kind-specific, always includes "fen_before"},
                    },
                    ...
                ],  # capped at MAX_MOMENTS, ply-ascending
                "moments_dropped": int,
            }

    Never raises on empty/short input: an empty ``plies`` list returns an
    empty-moments payload.
    """
    plies = plies or []
    leaks = leaks or []
    pos_by_epd = pos_by_epd or {}

    header = profile_context.get("header") if isinstance(profile_context, dict) else None

    if not plies:
        return {
            "header": header,
            "profile_context": profile_context,
            "my_color": my_color,
            "eval_arc": {},
            "moments": [],
            "moments_dropped": 0,
        }

    plies_by_ply = {row["ply"]: row for row in plies}
    leaks_by_ply = {lk["ply"]: lk for lk in leaks}
    derived = _analyze_plies(plies)

    user_moments = _user_leak_moments(leaks, plies_by_ply)
    _attach_pv(user_moments, pos_by_epd)
    opponent_moments = _opponent_moments(plies, derived, my_color, pos_by_epd)
    tide_moments = _tide_turn_moments(plies, derived, my_color, pos_by_epd)
    narrow_moments = _narrow_choice_moments(plies, derived, my_color, pos_by_epd)
    missed_moments = _missed_capitalization_moments(plies, opponent_moments, leaks_by_ply)
    leak_like = user_moments + opponent_moments
    time_moments = _time_trouble_moments(leak_like, plies_by_ply)

    all_moments = (
        user_moments + opponent_moments + tide_moments + narrow_moments
        + missed_moments + time_moments
    )

    ordered = sorted(all_moments, key=_sort_key)
    kept = ordered[:MAX_MOMENTS]
    dropped = max(0, len(ordered) - MAX_MOMENTS)
    kept_sorted = sorted(kept, key=lambda m: (m["ply"], m["kind"]))

    return {
        "header": header,
        "profile_context": profile_context,
        "my_color": my_color,
        "eval_arc": _eval_arc(derived),
        "moments": kept_sorted,
        "moments_dropped": dropped,
    }
