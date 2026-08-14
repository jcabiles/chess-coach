"""Offline realism trace-audit harness (M3).

Measures how *human* each bot persona plays, against real lichess human games
sampled by ``tools/fetch_lichess_sample.py``. This is the instrument that must
exist BEFORE the ladder switches to Maia (M4): it produces the committed
weakened-SF before-picture and later becomes Chapter-5's frozen experiment
instrument.

Design contract (spec + dual-review folds):

* The bot's move is obtained through the SAME pipeline the API plays —
  ``app.main.select_persona_move`` is imported, never re-implemented (anti-drift
  fold). Engine access is ONLY through ``app.bot_engine`` (the bots' weakened SF)
  and ``app.maia_engine`` (lc0); the interactive analysis engine is never touched
  by the bots.
* Blunder / mistake scoring uses an INDEPENDENT loss oracle — a dedicated
  ``app.engine.StockfishEngine`` at a fixed strong budget (depth 14, multipv 1),
  NOT the 0.3s weak budget the bots play with (circularity fold). Oracle evals
  are cached per fen (before) and per (fen, move) (after) so they are shared
  across every persona in a band.
* Thresholds are the codebase's: loss > ``analysis.MISTAKE_MAX`` (250cp) =
  blunder, 50–250cp = mistake (fold #3, cites ``classify``).
* Metrics carry 95% Wilson confidence intervals so nobody over-reads a point
  estimate at these sample sizes (statistical-power fold).

``--engine sf-only`` points ``MAIA_WEIGHTS_DIR`` at an empty dir so
``maia_ready_for`` is False for every persona and ``select_persona_move`` takes
the weakened-SF path — the before-picture. ``--engine current`` leaves the
environment as-is (Maia plays for wired personas if lc0 + the net are present).

Usage::

    .venv/bin/python -m tools.realism_audit --set dev --personas casey --limit 20
    .venv/bin/python -m tools.realism_audit --set eval --personas all \
        --engine sf-only --report docs/analytics/realism-baseline.md

The pure surfaces (position loading, hashing, metric math, report rendering)
are unit-tested with no engine; the engine runner is exercised with fakes.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import chess

from app import analysis, personas
from app.main import select_persona_move
from tools.fetch_lichess_sample import BANDS, mate_in_one_exists

# A single fixed seed makes every (persona, position) selection reproducible
# run-to-run given the same binaries/nets. The route derives its randomness from
# hash((seed, ply)); a constant seed here keeps the audit deterministic.
AUDIT_SEED = 424242

# Independent loss oracle: strong, fixed. NOT the bots' 0.3s weak budget.
ORACLE_DEPTH = 14

# Loss thresholds — the codebase's own (analysis.classify boundaries).
BLUNDER_MIN = analysis.MISTAKE_MAX  # loss > 250cp -> blunder
MISTAKE_LO = 50  # 50..250cp inclusive -> mistake

DATA_DIR = Path("data/realism")
REQUIRED_KEYS = {"gameId", "fen", "ply", "humanMoveUci", "band", "eco"}

# The four rating bands, as "lo-hi" name strings (match the fetch script + roster).
BAND_NAMES = [f"{lo}-{hi}" for lo, hi in BANDS]


# ---------------------------------------------------------------------------
# Pure helpers — position loading, hashing, banding (no engine)
# ---------------------------------------------------------------------------


def band_for_elo(elo: int) -> Optional[str]:
    """The band-name whose ``[lo, hi)`` contains *elo*, or None if outside all.

    A persona is audited against ITS band's positions only (named limitation
    fold: cross-band diagnostics are deferred to the ladder-switch slice).
    """
    for lo, hi in BANDS:
        if lo <= elo < hi:
            return f"{lo}-{hi}"
    return None


def load_positions(set_name: str, band: str, data_dir: Path = DATA_DIR) -> list[dict]:
    """Load + validate one ``<set>-<band>.jsonl`` file into a list of records.

    Validates each line: required keys present, FEN parses, and the record's
    ``band`` matches the requested band (guards against a mislabeled/mismerged
    file). Raises ``ValueError`` on the first malformed line (a corrupt audit set
    should fail loudly, not silently skew a metric).
    """
    path = data_dir / f"{set_name}-{band}.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"missing audit set: {path}")
    rows: list[dict] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        missing = REQUIRED_KEYS - rec.keys()
        if missing:
            raise ValueError(f"{path}:{i + 1} missing keys {sorted(missing)}")
        try:
            chess.Board(rec["fen"])
        except ValueError as exc:
            raise ValueError(f"{path}:{i + 1} bad fen: {exc}") from exc
        if rec["band"] != band:
            raise ValueError(
                f"{path}:{i + 1} band {rec['band']!r} != file band {band!r}"
            )
        rows.append(rec)
    return rows


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_eval_hash(data_dir: Path = DATA_DIR) -> tuple[bool, list[str]]:
    """Check that eval/probe files match the committed ``EVAL_SHA256`` pins.

    Returns ``(ok, problems)``; ``ok`` is True only when every pinned file is
    present and its digest matches. Any mismatch means the sealed eval set was
    edited — the harness must refuse an ``--set eval`` acceptance run.
    """
    pin_file = data_dir / "EVAL_SHA256"
    if not pin_file.is_file():
        return False, [f"missing pin file: {pin_file}"]
    problems: list[str] = []
    for raw in pin_file.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        want, _, name = raw.partition("  ")
        p = data_dir / name.strip()
        if not p.is_file():
            problems.append(f"pinned file absent: {name}")
            continue
        got = _sha256_file(p)
        if got != want:
            problems.append(f"hash mismatch: {name} ({got[:12]} != {want[:12]})")
    return (not problems), problems


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion ``k/n``.

    Wilson (not normal-approx) because it stays inside ``[0, 1]`` and behaves at
    the small n / extreme p these audit sets hit. Returns ``(lo, hi)`` as
    proportions in ``[0, 1]``; ``(0.0, 0.0)`` when ``n == 0`` (caller renders
    N/A).
    """
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def classify_loss(loss_cp: int) -> str:
    """Bucket a (non-negative) mover-POV centipawn loss: blunder/mistake/clean.

    Uses the codebase thresholds directly (fold #3): ``> MISTAKE_MAX`` blunder,
    ``[MISTAKE_LO, MISTAKE_MAX]`` mistake, else clean.
    """
    if loss_cp > BLUNDER_MIN:
        return "blunder"
    if loss_cp >= MISTAKE_LO:
        return "mistake"
    return "clean"


# ---------------------------------------------------------------------------
# Per-persona result aggregation (pure over already-computed per-move rows)
# ---------------------------------------------------------------------------


@dataclass
class MoveResult:
    """One audited move: the raw facts a metric is computed from (pure)."""

    fen: str
    ply: int
    human_uci: str
    bot_uci: str
    engine: str  # "maia" | "stockfish"
    loss_cp: int  # mover-POV cp given up vs the strong oracle
    mate1_available: bool  # the position had a mate-in-1 for the mover
    mate1_converted: bool  # ... and the bot played a mating move


@dataclass
class PersonaReport:
    """Aggregated metrics for one persona over its band's set."""

    persona_id: str
    persona_name: str
    elo: int
    band: str
    n: int
    move_match: int
    blunders: int
    mistakes: int
    mean_loss: float
    mate1_available: int
    mate1_converted: int
    maia_moves: int  # how many moves the Maia engine produced (0 for sf-only)


def summarize(
    persona: personas.Persona, band: str, rows: list[MoveResult]
) -> PersonaReport:
    """Fold per-move rows into a persona's metric summary (pure)."""
    n = len(rows)
    losses = [r.loss_cp for r in rows]
    return PersonaReport(
        persona_id=persona.id,
        persona_name=persona.name,
        elo=persona.elo,
        band=band,
        n=n,
        move_match=sum(1 for r in rows if r.bot_uci == r.human_uci),
        blunders=sum(1 for r in rows if classify_loss(r.loss_cp) == "blunder"),
        mistakes=sum(1 for r in rows if classify_loss(r.loss_cp) == "mistake"),
        mean_loss=(sum(losses) / n if n else 0.0),
        mate1_available=sum(1 for r in rows if r.mate1_available),
        mate1_converted=sum(1 for r in rows if r.mate1_converted),
        maia_moves=sum(1 for r in rows if r.engine == "maia"),
    )


def _pct_ci(k: int, n: int) -> str:
    if n == 0:
        return "N/A"
    lo, hi = wilson_ci(k, n)
    return f"{100 * k / n:.1f}% [{100 * lo:.1f}–{100 * hi:.1f}]"


def render_markdown(reports: list[PersonaReport], header: dict) -> str:
    """Render the audit as a markdown report with a pinned run header (pure).

    ``header`` carries the reproducibility pins (fold #9): set name, engine mode,
    seed, binary versions, platform, wall-clock, eval-hash status.
    """
    lines: list[str] = []
    lines.append(f"# Realism audit — {header.get('set', '?')} set")
    lines.append("")
    lines.append(f"- Engine mode: **{header.get('engine', '?')}**")
    lines.append(f"- Audit seed: `{header.get('seed', AUDIT_SEED)}`")
    lines.append(f"- Oracle: Stockfish depth {ORACLE_DEPTH}, multipv 1")
    lines.append(
        f"- Thresholds: blunder loss > {BLUNDER_MIN}cp, "
        f"mistake {MISTAKE_LO}–{BLUNDER_MIN}cp (analysis.classify)"
    )
    for k in ("stockfish", "lc0", "platform", "wallClock", "evalHash"):
        if header.get(k):
            lines.append(f"- {k}: {header[k]}")
    lines.append("")
    lines.append(
        "| Persona | Elo | Band | n | Move-match (human) | Blunder % | "
        "Mistake % | Mean cp-loss | Mate-in-1 conv. | via Maia |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in reports:
        lines.append(
            f"| {r.persona_name} (`{r.persona_id}`) | {r.elo} | {r.band} | {r.n} "
            f"| {_pct_ci(r.move_match, r.n)} "
            f"| {_pct_ci(r.blunders, r.n)} "
            f"| {_pct_ci(r.mistakes, r.n)} "
            f"| {r.mean_loss:.0f} "
            f"| {_pct_ci(r.mate1_converted, r.mate1_available)} "
            f"| {r.maia_moves}/{r.n} |"
        )
    lines.append("")
    lines.append(
        "_Percentages carry 95% Wilson CIs. Move-match is against a single "
        "human reference move (high variance at small n — read the CI, not the "
        "point). Mate-in-1 conversion is N/A when the band's set has no "
        "mate-in-1 positions._"
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Engine runner — the ONLY part that touches binaries
# ---------------------------------------------------------------------------


async def _oracle_white_cp(oracle, fen: str, cache: dict[str, int]) -> int:
    """Strong-oracle White-POV cp of *fen*, cached (shared across personas)."""
    if fen not in cache:
        results = await oracle.analyze_multi(fen, depth=ORACLE_DEPTH, multipv=1)
        cache[fen] = analysis.pov_score_to_white_cp(results[0].score)
    return cache[fen]


async def audit_persona(
    persona: personas.Persona,
    band: str,
    positions: list[dict],
    bot,
    oracle,
    before_cache: dict[str, int],
    after_cache: dict[str, int],
) -> list[MoveResult]:
    """Run one persona over one band's positions; return per-move rows.

    Injection-friendly: ``bot`` and ``oracle`` are passed in (real engines in
    ``main``, fakes in tests). Uses the shared ``select_persona_move`` so the
    audited move is byte-identical to what the API plays.
    """
    rows: list[MoveResult] = []
    for rec in positions:
        fen = rec["fen"]
        board = chess.Board(fen)
        mover_is_white = board.turn == chess.WHITE
        mate1 = mate_in_one_exists(board)

        chosen = await select_persona_move(
            bot, persona, fen, int(rec["ply"]), AUDIT_SEED, []
        )
        if chosen is None:
            continue  # engine yielded no usable line — skip (rare)
        bot_uci = chosen["uci"]
        move = chess.Move.from_uci(bot_uci)

        # Loss vs the strong oracle: before-eval shared per fen; after-eval keyed
        # by (fen, move) since the move varies by persona.
        before = await _oracle_white_cp(oracle, fen, before_cache)
        after_board = board.copy()
        after_board.push(move)
        akey = f"{fen}|{bot_uci}"
        if akey not in after_cache:
            if after_board.is_game_over():
                # Terminal after the move: no search — checkmate is a decisive
                # White-POV eval on the mate axis, draw is 0.
                if after_board.is_checkmate():
                    # side to move is mated -> the mover just won.
                    after_cache[akey] = (
                        analysis.MATE_CP if mover_is_white else -analysis.MATE_CP
                    )
                else:
                    after_cache[akey] = 0
            else:
                res = await oracle.analyze_multi(
                    after_board.fen(), depth=ORACLE_DEPTH, multipv=1
                )
                after_cache[akey] = analysis.pov_score_to_white_cp(res[0].score)
        loss = analysis.cp_loss(before, after_cache[akey], mover_is_white)

        # Converted iff a mate-in-1 was on the board AND the bot's (legal,
        # engine-chosen) move actually delivers checkmate.
        mate1_converted = mate1 and after_board.is_checkmate()
        rows.append(
            MoveResult(
                fen=fen,
                ply=int(rec["ply"]),
                human_uci=rec["humanMoveUci"],
                bot_uci=bot_uci,
                engine=chosen["engine"],
                loss_cp=loss,
                mate1_available=mate1,
                mate1_converted=bool(mate1_converted),
            )
        )
    return rows


def _select_personas(spec: str) -> list[personas.Persona]:
    if spec == "all":
        return list(personas.all())
    out: list[personas.Persona] = []
    for pid in spec.split(","):
        pid = pid.strip()
        p = personas.get(pid)
        if p is None:
            raise SystemExit(f"unknown persona id: {pid!r}")
        out.append(p)
    return out


def _binary_versions() -> dict:
    """Best-effort engine version strings for the report header (fold #9)."""
    import re
    import shutil
    import subprocess

    ansi = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
    out: dict = {}
    for name, binary in (("stockfish", "stockfish"), ("lc0", "lc0")):
        path = shutil.which(binary)
        if not path:
            continue
        try:
            proc = subprocess.run(
                [path, "--version"], capture_output=True, text=True, timeout=5
            )
            text = ansi.sub("", proc.stdout or proc.stderr)
            # lc0 prints a banner before the version; keep the first line that
            # actually mentions a version-ish token, else the first non-empty.
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            pick = next((ln for ln in lines if any(c.isdigit() for c in ln)), "")
            out[name] = (pick or (lines[0] if lines else path))[:80]
        except Exception:  # pragma: no cover - version probe is best-effort
            out[name] = path
    return out


async def _run(args) -> int:
    from app import bot_engine, engine

    set_name = args.set
    if set_name == "eval":
        print(
            "WARNING: running against the SEALED eval set — for ACCEPTANCE/"
            "BASELINE only, never tuning.",
            file=sys.stderr,
        )
        ok, problems = verify_eval_hash(Path(args.data))
        if not ok:
            for p in problems:
                print(f"EVAL_SHA256: {p}", file=sys.stderr)
            return 2

    # sf-only: point MAIA_WEIGHTS_DIR at an empty dir so maia_ready_for is False
    # for every persona and select_persona_move takes the weakened-SF path.
    tmp_empty: Optional[str] = None
    if args.engine == "sf-only":
        tmp_empty = tempfile.mkdtemp(prefix="realism-sf-only-")
        os.environ["MAIA_WEIGHTS_DIR"] = tmp_empty

    personas.init()
    selected = _select_personas(args.personas)

    bot = bot_engine.get_bot_engine()
    oracle = engine.StockfishEngine()
    try:
        oracle.start()
    except engine.EngineUnavailable as exc:
        print(f"loss oracle unavailable: {exc}", file=sys.stderr)
        return 3

    before_cache: dict[str, int] = {}
    after_cache: dict[str, int] = {}
    reports: list[PersonaReport] = []
    try:
        for persona in selected:
            band = band_for_elo(persona.elo)
            if band is None:
                print(f"persona {persona.id} elo {persona.elo} outside all bands; skip",
                      file=sys.stderr)
                continue
            positions = load_positions(set_name, band, Path(args.data))
            if args.limit:
                positions = positions[: args.limit]
            rows = await audit_persona(
                persona, band, positions, bot, oracle, before_cache, after_cache
            )
            reports.append(summarize(persona, band, rows))
    finally:
        oracle.close()
        await bot.close()

    header = {
        "set": set_name,
        "engine": args.engine,
        "seed": AUDIT_SEED,
        "platform": platform.platform(),
        **_binary_versions(),
    }
    if set_name == "eval":
        header["evalHash"] = "verified against EVAL_SHA256"
    md = render_markdown(reports, header)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(md, encoding="utf-8")
        print(f"wrote {args.report}")
    else:
        print(md)
    if args.json:
        payload = {"header": header, "personas": [vars(r) for r in reports]}
        Path(args.json).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Offline realism trace-audit (M3).")
    ap.add_argument("--set", choices=["dev", "eval"], default="dev")
    ap.add_argument("--personas", default="all", help="'all' or comma-separated ids")
    ap.add_argument("--engine", choices=["current", "sf-only"], default="current")
    ap.add_argument("--limit", type=int, default=0, help="cap positions/persona (smoke)")
    ap.add_argument("--data", default=str(DATA_DIR))
    ap.add_argument("--report", default="", help="write markdown here (else stdout)")
    ap.add_argument("--json", default="", help="also write a json payload here")
    args = ap.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
