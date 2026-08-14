"""Fetch band-filtered human positions from a lichess monthly dump (M3).

Streams ONE month's standard rated dump (never downloads the full ~30GB:
``curl | zstd -d`` is read incrementally and the stream stops when quotas
fill), filters games to the audit's rating bands, and samples mid-game
positions with the human's actually-played move as ground truth.

Bias mitigations (spec review folds):
* a head-skip plus systematic thinning (every ``THIN_K``-th matching game)
  spreads the sample across a long stream window instead of the dump head;
* ≤ ``MAX_POS_PER_GAME`` positions per game (clustering);
* dev/eval split unit = ECO code — every position of an ECO code lands
  wholly in dev or wholly in eval (opening-family leakage), decided by a
  seeded hash;
* dump id recorded on every line; use a recent month (Maia nets trained on
  ≤2019 games — temporal separation documented in the baseline report).

Outputs (committed): data/realism/{dev,eval}-<band>.jsonl,
probe-<band>.jsonl (mate-in-1 probe set with the human's conversion move),
and EVAL_SHA256 pinning the eval + probe files. Raw stream is never written
to disk.

Line schema: {gameId, fen, ply, humanMoveUci, band, eco, timeControl,
whiteElo, blackElo, dump}.

Usage (network):
    .venv/bin/python -m tools.fetch_lichess_sample \
        --dump https://database.lichess.org/standard/lichess_db_standard_rated_2026-05.pgn.zst
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import subprocess
import sys
from pathlib import Path

import chess
import chess.pgn

BANDS: list[tuple[int, int]] = [(1300, 1500), (1500, 1700), (1700, 1900), (1900, 2100)]
DEV_QUOTA = 200  # positions per band
EVAL_QUOTA = 500
PROBE_QUOTA = 50  # mate-in-1 positions per band
MAX_POS_PER_GAME = 3
PLY_MIN, PLY_MAX = 12, 60
HEAD_SKIP = 5_000  # matching games skipped before sampling starts
THIN_K = 5  # keep every k-th matching game
SPLIT_SEED = 20260718  # ECO-split + per-game sampling seed
EVAL_SHARE = 0.7  # ECO codes hashed into eval vs dev

OUT_DIR = Path("data/realism")


def band_of(white_elo: int, black_elo: int) -> tuple[int, int] | None:
    """The band containing BOTH players, or None."""
    for lo, hi in BANDS:
        if lo <= white_elo < hi and lo <= black_elo < hi:
            return (lo, hi)
    return None


def eco_side(eco: str) -> str:
    """Deterministic dev/eval split by ECO code (seeded, hash-based)."""
    h = hashlib.sha256(f"{SPLIT_SEED}:{eco}".encode()).digest()
    return "eval" if h[0] / 255.0 < EVAL_SHARE else "dev"


def mate_in_one_exists(board: chess.Board) -> bool:
    """Engine-free scan: does the side to move have a mate-in-1?"""
    for mv in board.legal_moves:
        board.push(mv)
        mate = board.is_checkmate()
        board.pop()
        if mate:
            return True
    return False


def harvest(game: chess.pgn.Game, band: tuple[int, int], meta: dict, rng: random.Random):
    """Yield (kind, record) for sampled mid-game + probe positions."""
    board = game.board()
    rows = []  # (ply, fen, human_uci, mate1)
    for ply, move in enumerate(game.mainline_moves()):
        if PLY_MIN <= ply <= PLY_MAX and board.is_valid():
            rows.append((ply, board.fen(), move.uci(), None, board.copy(stack=False)))
        board.push(move)

    if not rows:
        return

    picks = rng.sample(rows, min(MAX_POS_PER_GAME, len(rows)))
    for ply, fen, uci, _, snap in picks:
        rec = {**meta, "fen": fen, "ply": ply, "humanMoveUci": uci}
        yield "sample", rec
    # Probe scan (mate-in-1) only on a couple of positions per game to keep
    # the stream fast — the rarity is in the position, not the scan budget.
    for ply, fen, uci, _, snap in picks:
        if mate_in_one_exists(snap):
            rec = {**meta, "fen": fen, "ply": ply, "humanMoveUci": uci}
            yield "probe", rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dump", required=True, help="URL of a .pgn.zst monthly dump")
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    dump_id = args.dump.rsplit("/", 1)[-1]

    # curl | zstd -d, both streaming; python reads decompressed text lazily.
    curl = subprocess.Popen(
        ["curl", "-fsSL", args.dump], stdout=subprocess.PIPE
    )
    zstd = subprocess.Popen(
        ["zstd", "-d", "-c"], stdin=curl.stdout, stdout=subprocess.PIPE
    )
    curl.stdout.close()
    stream = io.TextIOWrapper(zstd.stdout, encoding="utf-8", errors="replace")

    quotas = {
        (band, split): (EVAL_QUOTA if split == "eval" else DEV_QUOTA)
        for band in BANDS
        for split in ("dev", "eval")
    }
    counts = {k: 0 for k in quotas}
    probe_counts = {band: 0 for band in BANDS}
    files = {}

    def sink(name: str):
        if name not in files:
            files[name] = open(out_dir / f"{name}.jsonl", "w", encoding="utf-8")
        return files[name]

    matching = 0
    kept = 0
    try:
        while True:
            if all(counts[k] >= q for k, q in quotas.items()) and all(
                probe_counts[b] >= PROBE_QUOTA for b in BANDS
            ):
                break
            game = chess.pgn.read_game(stream)
            if game is None:
                print("stream ended before quotas filled", file=sys.stderr)
                break
            h = game.headers
            event = h.get("Event", "")
            if "Rated" not in event or not ("Blitz" in event or "Rapid" in event):
                continue
            if h.get("Termination") != "Normal":
                continue
            eco = h.get("ECO", "")
            if not eco:
                continue
            try:
                we, be = int(h["WhiteElo"]), int(h["BlackElo"])
            except (KeyError, ValueError):
                continue
            band = band_of(we, be)
            if band is None:
                continue

            matching += 1
            if matching <= HEAD_SKIP or matching % THIN_K != 0:
                continue

            split = eco_side(eco)
            band_name = f"{band[0]}-{band[1]}"
            game_id = h.get("Site", "").rsplit("/", 1)[-1] or f"g{matching}"
            meta = {
                "gameId": game_id,
                "band": band_name,
                "eco": eco,
                "timeControl": h.get("TimeControl", ""),
                "whiteElo": we,
                "blackElo": be,
                "dump": dump_id,
            }
            need_samples = counts[(band, split)] < quotas[(band, split)]
            need_probe = probe_counts[band] < PROBE_QUOTA
            if not (need_samples or need_probe):
                continue

            # sha256-derived int seed: str hash() is PYTHONHASHSEED-randomized
            # (B9 lesson) — a digest keeps re-runs reproducible.
            gseed = int.from_bytes(
                hashlib.sha256(f"{SPLIT_SEED}:{game_id}".encode()).digest()[:8], "big"
            )
            rng = random.Random(gseed)
            for kind, rec in harvest(game, band, meta, rng):
                if kind == "sample" and counts[(band, split)] < quotas[(band, split)]:
                    sink(f"{split}-{band_name}").write(json.dumps(rec) + "\n")
                    counts[(band, split)] += 1
                    kept += 1
                elif kind == "probe" and probe_counts[band] < PROBE_QUOTA:
                    sink(f"probe-{band_name}").write(json.dumps(rec) + "\n")
                    probe_counts[band] += 1
            if kept and kept % 200 == 0:
                print(f"kept={kept} matching={matching} {counts}", file=sys.stderr)
    finally:
        for f in files.values():
            f.close()
        zstd.terminate()
        curl.terminate()

    # Pin the sealed sets.
    pins = []
    for p in sorted(out_dir.glob("eval-*.jsonl")) + sorted(out_dir.glob("probe-*.jsonl")):
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        pins.append(f"{digest}  {p.name}")
    (out_dir / "EVAL_SHA256").write_text("\n".join(pins) + "\n", encoding="utf-8")

    print(json.dumps({"counts": {f"{b[0]}-{b[1]}/{s}": counts[(b, s)] for b, s in counts},
                      "probes": {f"{b[0]}-{b[1]}": probe_counts[b] for b in BANDS},
                      "matchingGamesSeen": matching}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
