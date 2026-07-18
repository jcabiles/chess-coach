"""Causal, engine-free blunder gate (pure python-chess, seedable).

This is the *input-side* mechanism for the persona bots (B5): the bot fails
because its attention was elsewhere (its plan) and it therefore didn't see the
opponent's threat — never via an output-side dice roll on the final move.

Everything here is PURE: no engine, no I/O, no ``await``. All randomness derives
from ``random.Random(hash((seed, ply)))`` so the same inputs always produce the
same output. It reuses :mod:`app.motifs` (also pure) read-only for threat
detection and never touches the shared analysis engine.

The four public functions map to the anti-randomness triple:

* :func:`plan_attention_set` — *what the bot was attending to* (its plan).
* :func:`opponent_threat` — *what it therefore might miss* (the threat).
* :func:`should_blunder` — *whether the miss is plausible here* (the gate).
* :func:`pick_survivor` — the engine candidate that actually ignores the threat.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import chess

from app import motifs

# ---------------------------------------------------------------------------
# Tunable module constants
# ---------------------------------------------------------------------------

#: How many of the bot's own recent moves form its "plan" attention set.
PLAN_MOVES = 4

#: Sentinel severity for a forced mate — dominates all material threats.
MATE_SEVERITY = 100_000

#: Threats worth less than this (a bare pawn) don't count as a blunder to miss.
MIN_MISSABLE = 200

#: Reference severity for the damping curve. A threat at MISS_REF is missed at
#: full base rate; anything bigger (rook/queen/mate) is damped below it, so a
#: strong bot doesn't "miss mate-in-1 every time".
MISS_REF = 350

#: Hazard ramp: no induced blunders before this ply, ...
FIRST_BLUNDER_PLY = 24

#: ... rising linearly to full rate over this many plies afterwards.
RAMP = 20

#: Material value of the strongest forked/threatened piece, keyed by piece type.
#: Uses the standard motifs values but collapses minors to a single 300 band so
#: the spec's ordering (queen 900 > rook 500 > minor 300 > pawn 100) holds.
_THREAT_VALUE = {
    chess.PAWN: 100,
    chess.KNIGHT: 300,
    chess.BISHOP: 300,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: MATE_SEVERITY,
}


# ---------------------------------------------------------------------------
# Threat model
# ---------------------------------------------------------------------------


@dataclass
class Threat:
    """A single material (or mate) threat for the side to move.

    Attributes:
        type: Threat kind — ``'mate'`` or a :mod:`app.motifs` motif type
            (``'hanging'``, ``'fork'``, ``'knight_fork'``, ``'back_rank'`` ...).
        squares: The threat's key squares (target square(s) + the threatened
            piece's square, or for mate the mating-move squares + mated king).
        severity_cp: Material at risk in centipawns (mate → ``MATE_SEVERITY``).
        detail: Human-readable one-liner (internal / test use).
    """

    type: str
    squares: set[int]
    severity_cp: int
    detail: str = ""
    #: The single most-valuable threatened square (used by the same-threat rule
    #: in :func:`pick_survivor`). Falls back to any square in ``squares``.
    target: int = field(default=-1)


# ---------------------------------------------------------------------------
# 1. Plan attention set
# ---------------------------------------------------------------------------


def plan_attention_set(recent_bot_moves: list[str], board: chess.Board) -> set[int]:
    """Return the squares the bot is "attending to" (its plan).

    The set is the from+to squares of the last ``PLAN_MOVES`` of the bot's own
    moves (given as UCI strings), UNION the squares currently attacked by the
    bot's pieces standing on those to-squares (its active pieces' influence).

    Empty when there are few/no own moves (the opening) — which means the gate
    can't fire yet, matching "survive the opening".

    Args:
        recent_bot_moves: The bot's own recent moves in UCI, oldest-first.
        board: The current position (used to read the bot's active pieces).

    Returns:
        A set of square ints (0-63).
    """
    attention: set[int] = set()

    for uci in recent_bot_moves[-PLAN_MOVES:]:
        try:
            move = chess.Move.from_uci(uci)
        except (ValueError, chess.InvalidMoveError):
            continue
        attention.add(move.from_square)
        attention.add(move.to_square)

        # The bot's active piece that (probably) now stands on the to-square:
        # add the squares it currently attacks (its influence on the board).
        # Only count the bot's OWN piece — if the opponent recaptured on that
        # square, its influence is not the bot's plan (refuter LOW). On the bot's
        # move it is the side to move, so `board.turn` is the bot's color.
        piece = board.piece_at(move.to_square)
        if piece is not None and piece.color == board.turn:
            for sq in board.attacks(move.to_square):
                attention.add(sq)

    return attention


# ---------------------------------------------------------------------------
# 2. Opponent threat detection (engine-free)
# ---------------------------------------------------------------------------


def _square_from_name(name: str) -> int | None:
    try:
        return chess.parse_square(name)
    except ValueError:
        return None


def opponent_threat(board: chess.Board) -> Threat | None:
    """Return the strongest threat for the side to move on *board*, or None.

    This is deliberately generic: it detects threats for whichever side is to
    move on the board it is given. The route passes a null-move board so that
    "the side to move" is the opponent of the bot.

    Detection is entirely engine-free:

    1. A pure mate-in-1 scan over the side-to-move's legal moves.
    2. Otherwise the strongest MATERIAL threat from :mod:`app.motifs`
       (``detect_motifs`` / ``hanging_pieces``), ordered by material at risk
       (queen 900 > rook 500 > minor 300 > pawn 100).

    Args:
        board: The position whose side-to-move threats we want.

    Returns:
        The single strongest :class:`Threat`, or ``None`` if there is none.
    """
    # --- 1. Mate-in-1 scan (pure, ~30 pushes) ------------------------------
    for move in board.legal_moves:
        board.push(move)
        mated = board.is_checkmate()
        board.pop()
        if mated:
            king_sq = board.king(not board.turn)
            squares = {move.from_square, move.to_square}
            if king_sq is not None:
                squares.add(king_sq)
            return Threat(
                type="mate",
                squares=squares,
                severity_cp=MATE_SEVERITY,
                detail=f"Mate in 1 via {move.uci()}",
                target=king_sq if king_sq is not None else move.to_square,
            )

    # --- 2. Strongest material threat --------------------------------------
    best: Threat | None = None
    opponent = not board.turn  # whose pieces the side-to-move threatens

    # Hanging pieces (opponent's pieces the side-to-move can win).
    for h in motifs.hanging_pieces(board, opponent):
        sq = h["square"]
        piece = board.piece_at(sq)
        if piece is None:
            continue
        sev = _THREAT_VALUE.get(piece.piece_type, 0)
        cand = Threat(
            type="hanging",
            squares={sq},
            severity_cp=sev,
            detail=f"{h['piece']} on {chess.square_name(sq)} is hanging",
            target=sq,
        )
        if best is None or cand.severity_cp > best.severity_cp:
            best = cand

    # Motif threats (fork / back_rank / etc.).
    for m in motifs.detect_motifs(board):
        mtype = m["type"]
        target_names: list[str] = m.get("targets", [])
        target_sqs = [s for s in (_square_from_name(n) for n in target_names) if s is not None]
        if not target_sqs:
            continue

        squares = set(target_sqs)
        by = m.get("by")
        by_sq = _square_from_name(by) if by else None
        if by_sq is not None:
            squares.add(by_sq)

        if mtype == "back_rank":
            sev = MATE_SEVERITY
            target = target_sqs[0]
        else:
            # Fork / skewer / discovered / pin / hanging-as-motif: severity is
            # the value of the most valuable threatened (target) piece.
            valued = [
                (_THREAT_VALUE.get(p.piece_type, 0), sq)
                for sq in target_sqs
                if (p := board.piece_at(sq)) is not None
            ]
            if not valued:
                continue
            valued.sort(reverse=True)
            sev, target = valued[0]

        cand = Threat(
            type=mtype,
            squares=squares,
            severity_cp=sev,
            detail=m.get("detail", ""),
            target=target,
        )
        if best is None or cand.severity_cp > best.severity_cp:
            best = cand

    return best


# ---------------------------------------------------------------------------
# 3. The gate
# ---------------------------------------------------------------------------


def off_plan_score(threat_squares: set[int], plan_set: set[int]) -> float:
    """Fraction of the threat's key squares OUTSIDE the bot's attention.

    ``|threat.squares \\ plan_set| / |threat.squares|`` ∈ [0, 1]. An empty
    threat set (shouldn't happen) scores 1.0.
    """
    if not threat_squares:
        return 1.0
    off = len(threat_squares - plan_set)
    return off / max(1, len(threat_squares))


def phase_gate(phase: str) -> float:
    """Phase multiplier: 0 in the opening, 1.0 in middlegame and endgame."""
    return 0.0 if phase == "opening" else 1.0


def hazard(ply: int) -> float:
    """Monotone ramp: ~0 before ``FIRST_BLUNDER_PLY``, rising to 1.0.

    ``clamp((ply - FIRST_BLUNDER_PLY) / RAMP, 0, 1)`` — no induced blunders
    early, full hazard once the game is properly underway.
    """
    return max(0.0, min(1.0, (ply - FIRST_BLUNDER_PLY) / RAMP))


def severity_damp(severity_cp: int) -> float:
    """Bigger threats are missed LESS often: ``min(1, MISS_REF / severity)``.

    A minor (~300) is near full rate; a queen/rook/mate is heavily damped, so
    the bot rarely misses the biggest threats.
    """
    if severity_cp <= 0:
        return 1.0
    return min(1.0, MISS_REF / severity_cp)


def should_blunder(
    persona,
    phase: str,
    ply: int,
    seed: int,
    threat: Threat | None,
    plan_set: set[int],
) -> bool:
    """Return True iff the bot should miss *threat* at this ply (mechanism A).

    Fires iff ALL hold:

    * a threat exists with ``severity_cp >= MIN_MISSABLE`` (trivial pawn
      threats don't count),
    * it is off-plan: ``off_plan_score > persona.threatDistance``,
    * a seeded draw hits: ``Random(hash((seed, ply))).random() < fire_prob``
      where ``fire_prob = blunderRate * phase_gate * hazard * severity_damp``.

    Args:
        persona: Frozen persona with ``.blunderRate`` and ``.threatDistance``.
        phase: ``'opening'`` / ``'middlegame'`` / ``'endgame'``.
        ply: The current ply number (0-based full-game ply).
        seed: The per-game seed.
        threat: The threat from :func:`opponent_threat`, or ``None``.
        plan_set: The bot's attention set from :func:`plan_attention_set`.

    Returns:
        ``True`` if a causal blunder should be induced this move.
    """
    if threat is None or threat.severity_cp < MIN_MISSABLE:
        return False

    if off_plan_score(threat.squares, plan_set) <= persona.threatDistance:
        return False

    fire_prob = (
        persona.blunderRate
        * phase_gate(phase)
        * hazard(ply)
        * severity_damp(threat.severity_cp)
    )
    if fire_prob <= 0.0:
        return False

    rng = random.Random(hash((seed, ply)))
    return rng.random() < fire_prob


# ---------------------------------------------------------------------------
# 4. Survivor selection
# ---------------------------------------------------------------------------


def _same_threat(original: Threat, new: Threat | None) -> bool:
    """A candidate's after-threat is the SAME threat as the original iff it has
    the same ``type`` AND the original target square still lies in the new
    threat's squares (capturing/blocking/defending/moving the piece all break
    this → they count as neutralizing)."""
    if new is None:
        return False
    if new.type != original.type:
        return False
    return original.target in new.squares


def pick_survivor(candidates: list[dict], board: chess.Board, threat: Threat | None) -> int | None:
    """Return the index of the best candidate that IGNORES *threat*, or None.

    A candidate NEUTRALIZES the threat when, after playing it, the opponent's
    threat is gone or is a *different* threat (see :func:`_same_threat`).
    SURVIVORS are candidates that leave the ORIGINAL threat intact — those are
    the ones the bot could play while "not seeing" the threat.

    Among survivors, pick the best by mover-POV ``scoreCp`` (candidates carry
    White-POV ``scoreCp``; flip by ``board.turn``), tie-broken by lowest index
    for determinism.

    Args:
        candidates: ``[{uci, san, scoreCp}]``, White-POV, best-first.
        board: The position the candidates are played from (the bot to move).
        threat: The original threat the bot is (potentially) missing.

    Returns:
        Index into *candidates* of the best survivor, or ``None`` if every
        candidate addresses the threat (or *threat* is ``None``).
    """
    if threat is None:
        return None

    white_to_move = board.turn == chess.WHITE

    best_idx: int | None = None
    best_mover_cp: int | None = None

    for idx, cand in enumerate(candidates):
        try:
            move = chess.Move.from_uci(cand["uci"])
        except (ValueError, KeyError, chess.InvalidMoveError):
            continue

        after = board.copy()
        after.push(move)
        # After the bot's move it is the opponent's turn on `after`; the same
        # side-to-move threat detection now reports the opponent's threats.
        new_threat = opponent_threat(after)
        if not _same_threat(threat, new_threat):
            continue  # candidate neutralized the threat → not a survivor

        score = cand.get("scoreCp", 0)
        mover_cp = score if white_to_move else -score
        if best_mover_cp is None or mover_cp > best_mover_cp:
            best_mover_cp = mover_cp
            best_idx = idx

    return best_idx
