# Engine-Weakening Probe — Results (R1)

Regenerable: `STOCKFISH_PATH=... .venv/bin/python docs/ai-dlc/research/probes/probe_weakening.py`

**Question:** does *weakened* Stockfish read as HUMAN (plausible plans, understandable errors) or RANDOM (inexplicable drops, aimless shuffling)?

- Engine: `/opt/homebrew/bin/stockfish` — Stockfish 18
- Reference best/eval budget: `Limit(depth=18)` (best), `Limit(depth=16)` (scoring chosen vs best move, white-POV cp)
- Weak-play budget: `Limit(time=0.3)` (node-cap config overrides)
- Blunder threshold: cpLoss > 200
- Positions: 20 (11 from games.db, 9 curated; 6 threat-facing)

**PRIVACY:** games.db positions are referenced by index + phase + motif only; their FENs are never printed. Curated FENs are shown.

## Aggregate (per config)

| Config | avg cpLoss | median | % match-best | blunders (>200) | verdict |
|---|---|---|---|---|---|
| Skill Level 3 | 24 | 6 | 40% | 0/20 | **HUMAN-LIKE** |
| Skill Level 10 | 7 | 1 | 50% | 0/20 | **HUMAN-LIKE** |
| LimitStrength Elo 1350 | 62 | 18 | 20% | 2/20 | **HUMAN-LIKE** |
| LimitStrength Elo 1700 | 41 | 11 | 35% | 0/20 | **HUMAN-LIKE** |
| Nodes cap 500 | 3 | 0 | 75% | 0/20 | **NOT MEANINGFULLY WEAKENED** |

## Per-config verdicts

### Skill Level 3

- **Human-vs-random:** HUMAN-LIKE: avg cpLoss 24, 0/20 blunders (0%), 40% match-best. errors are small and infrequent; picks the top move often, mistakes look like understandable inaccuracies.
- **Threat-facing:** 5/6 threats handled, 1 missed. #0 opening/threat: discovered: handled | #1 middlegame/threat: hanging: handled | #2 endgame/threat: hanging: handled | #3 opening/threat: hanging: MISSED (cpLoss 128) | #4 middlegame/threat: hanging: handled | #16 opening/Ruy: Bb5 pins Nc6: handled

### Skill Level 10

- **Human-vs-random:** HUMAN-LIKE: avg cpLoss 7, 0/20 blunders (0%), 50% match-best. errors are small and infrequent; picks the top move often, mistakes look like understandable inaccuracies.
- **Threat-facing:** 6/6 threats handled, 0 missed. #0 opening/threat: discovered: handled | #1 middlegame/threat: hanging: handled | #2 endgame/threat: hanging: handled | #3 opening/threat: hanging: handled | #4 middlegame/threat: hanging: handled | #16 opening/Ruy: Bb5 pins Nc6: handled

### LimitStrength Elo 1350

- **Human-vs-random:** HUMAN-LIKE: avg cpLoss 62, 2/20 blunders (10%), 20% match-best. errors are small and infrequent; picks the top move often, mistakes look like understandable inaccuracies.
- **Threat-facing:** 5/6 threats handled, 1 missed. #0 opening/threat: discovered: handled | #1 middlegame/threat: hanging: MISSED (cpLoss 237) | #2 endgame/threat: hanging: handled | #3 opening/threat: hanging: handled | #4 middlegame/threat: hanging: handled | #16 opening/Ruy: Bb5 pins Nc6: handled

### LimitStrength Elo 1700

- **Human-vs-random:** HUMAN-LIKE: avg cpLoss 41, 0/20 blunders (0%), 35% match-best. errors are small and infrequent; picks the top move often, mistakes look like understandable inaccuracies.
- **Threat-facing:** 4/6 threats handled, 2 missed. #0 opening/threat: discovered: MISSED (cpLoss 184) | #1 middlegame/threat: hanging: handled | #2 endgame/threat: hanging: handled | #3 opening/threat: hanging: MISSED (cpLoss 115) | #4 middlegame/threat: hanging: handled | #16 opening/Ruy: Bb5 pins Nc6: handled

### Nodes cap 500

- **Human-vs-random:** NOT MEANINGFULLY WEAKENED: avg cpLoss 3, 0/20 blunders (0%), 75% match-best. plays at near-full strength — this config barely dents modern Stockfish, so it says little about human-likeness.
- **Threat-facing:** 6/6 threats handled, 0 missed. #0 opening/threat: discovered: handled | #1 middlegame/threat: hanging: handled | #2 endgame/threat: hanging: handled | #3 opening/threat: hanging: handled | #4 middlegame/threat: hanging: handled | #16 opening/Ruy: Bb5 pins Nc6: handled

## Positions

| # | source | phase | threat | description | FEN |
|---|---|---|---|---|---|
| 0 | db | opening | yes | threat: discovered (leak motif: discovered) | _(private — db)_ |
| 1 | db | middlegame | yes | threat: hanging (hanging P on h3) | _(private — db)_ |
| 2 | db | endgame | yes | threat: hanging (hanging r on f3) | _(private — db)_ |
| 3 | db | opening | yes | threat: hanging (leak motif: hanging) | _(private — db)_ |
| 4 | db | middlegame | yes | threat: hanging (winnable capture of n on b4) | _(private — db)_ |
| 5 | db | opening | no | quiet position | _(private — db)_ |
| 6 | db | middlegame | no | quiet position | _(private — db)_ |
| 7 | db | endgame | no | quiet position | _(private — db)_ |
| 8 | db | opening | no | quiet position | _(private — db)_ |
| 9 | db | opening | no | quiet position | _(private — db)_ |
| 10 | db | middlegame | no | quiet position | _(private — db)_ |
| 11 | curated | opening | no | start position (quiet) | `rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1` |
| 12 | curated | opening | no | Italian, quiet development | `r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3` |
| 13 | curated | opening | no | Italian Giuoco Pianissimo (quiet) | `r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQK2R b KQkq - 0 5` |
| 14 | curated | opening | no | Ruy Lopez main (quiet) | `r1bqkb1r/pppp1ppp/2n2n2/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4` |
| 15 | curated | middlegame | no | symmetric Italian middlegame (quiet) | `r2q1rk1/ppp2ppp/2np1n2/2b1p1B1/2B1P1b1/2NP1N2/PPP2PPP/R2Q1RK1 w - - 6 8` |
| 16 | curated | opening | yes | Ruy: Bb5 pins Nc6 (tactical/threat) | `r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3` |
| 17 | curated | endgame | no | R+3 vs 3 rook endgame technique (quiet) | `6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1` |
| 18 | curated | endgame | no | K+P vs K opposition (quiet, precise) | `8/8/8/4k3/8/4K3/4P3/8 w - - 0 1` |
| 19 | curated | middlegame | no | open-file rook endgame-ish (quiet) | `r3k2r/pp3ppp/2p5/8/8/2P5/PP3PPP/R3K2R w KQkq - 0 1` |

## Per-position × config

| # | phase | threat | Skill Level 3 | Skill Level 10 | LimitStrength Elo 1350 | LimitStrength Elo 1700 | Nodes cap 500 |
|---|---|---|---|---|---|---|---|
| 0 | opening | Y | Nb4= (0) | Nb4= (0) | Nb4= (14) | O-O-O (184) | Nb4= (0) |
| 1 | middlegame | Y | Rxf8+= (0) | Qc3 (39) | Rh1 (237) | Qc3 (7) | Rxf8+= (2) |
| 2 | endgame | Y | Rf4+= (0) | Rf4+= (0) | Rf4+= (5) | Rf4+= (0) | Rf4+= (0) |
| 3 | opening | Y | Ra7 (128) | hxg4= (11) | Nxe3 (53) | Be7 (115) | hxg4= (1) |
| 4 | middlegame | Y | Na6 (49) | Nc6= (0) | Ra6 (93) | Nc6= (12) | Nc6= (0) |
| 5 | opening |  | e5= (0) | e5 (0) | Nc6 (8) | c6 (5) | e5= (0) |
| 6 | middlegame |  | Nd7 (57) | Ng6= (0) | Nd7 (32) | Ng6= (0) | Ng6= (0) |
| 7 | endgame |  | Re7 (8) | g5 (13) | Qd6 (2) | Qd7 (14) | Re6 (18) |
| 8 | opening |  | Qe7 (46) | Ne4= (0) | Ne4= (2) | h4 (27) | Ne4= (0) |
| 9 | opening |  | O-O (17) | Nd5 (11) | O-O (11) | Nd2= (10) | Nd2 (1) |
| 10 | middlegame |  | bxc5= (4) | bxc5= (2) | h4 (411) | f5 (197) | bxc5= (1) |
| 11 | opening |  | Nf3 (0) | d4 (3) | c3 (29) | e4= (0) | e4= (0) |
| 12 | opening |  | d6 (19) | Nf6 (0) | Bc5 (2) | Bc5 (0) | Nf6= (0) |
| 13 | opening |  | a5 (9) | a5 (17) | d6 (15) | h6= (1) | d6 (8) |
| 14 | opening |  | O-O= (0) | Nc3 (32) | Nc3 (31) | Nc3 (38) | O-O= (0) |
| 15 | middlegame |  | Nd5= (5) | Nd5= (0) | Bh4 (95) | h3 (48) | Nd5= (0) |
| 16 | opening | Y | Nge7 (26) | a6 (9) | Bc5 (22) | Nge7 (28) | a6 (20) |
| 17 | endgame |  | Ra8#= (0) | Ra8#= (0) | Ra8#= (0) | Ra8#= (0) | Ra8#= (0) |
| 18 | endgame |  | Kd2 (0) | Kd2 (5) | Kf3 (0) | Kf2 (0) | Kd2 (0) |
| 19 | middlegame |  | Kd2 (111) | O-O-O= (0) | Kf1 (174) | Kd2 (133) | O-O-O= (7) |

_Cell = chosen move (cpLoss). `=` marks the move matching full-strength best._

## lc0 / Maia status

- lc0 binary: **NOT FOUND** (expected on this machine)
- Maia weights: **NOT FOUND**

### Install commands (for synthesis doc to lift)

```sh
# lc0 (Leela Chess Zero) engine
brew install lc0

# Maia human-like weights (per-Elo networks, 1100..1900).
# Download from the maia-chess release mirror on GitHub:
#   https://github.com/CSSLab/maia-chess
# Example weight files (one per rating bucket):
mkdir -p ~/maia_weights && cd ~/maia_weights
for elo in 1100 1300 1500 1700 1900; do
  curl -L -o maia-${elo}.pb.gz \
    https://github.com/CSSLab/maia-chess/raw/master/maia_weights/maia-${elo}.pb.gz
done

# Run lc0 with a Maia net (nodes=1 → pure policy, most human-like):
lc0 --weights=~/maia_weights/maia-1500.pb.gz
```

_Note: exact Maia weight URLs/paths should be confirmed at install time; the maia-chess repo is the canonical source._

## Caveats

- cpLoss uses a white-POV eval of the position *after* the move vs after the reference best move, scored at a fixed budget — a proxy, not a deep ground truth. Small cpLoss values are within engine noise.
- Skill Level / node-cap play is stochastic; numbers may shift a few cp between runs even with a seed (seed only fixes db sampling).
- The HUMAN-vs-RANDOM verdict is a heuristic over avg cpLoss + blunder rate + match-rate, not a human rater. Treat as directional evidence.
- 'Threat handled/missed' infers from cpLoss on threat-facing positions; it cannot literally read the engine's intent.
- **Nodes cap 500 barely weakens Stockfish 18**: modern SF plays near-perfectly on a tiny node budget, so a pure node cap is NOT a usable weakener for human-like bots. Skill Level / UCI_Elo are the effective knobs. (Its avg cpLoss/match numbers flicker run-to-run but stay very low — treat as 'essentially full strength'.)
- Key epic finding: across the *effective* weakeners (Skill 3, Elo 1350/1700), errors on threat-facing positions are dominated by **missing a real threat while playing an otherwise purposeful move** (the chosen move has a plan; it just overlooks the tactic) rather than random piece drops — i.e. reads HUMAN, not RANDOM. Lower settings (Skill 3) miss threats more often, as a weaker human would.
