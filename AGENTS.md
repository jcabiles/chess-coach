# AGENTS.md

Rules for every coding agent in this repo (Claude Code, Codex, Gemini). Claude also reads
`CLAUDE.md`, which imports this file. The shared rules in `~/.claude/AGENTS.md` apply too; this
file adds the repo's specifics and how to work a ticket.

- **Check command:** `make check` (lint plus the full test suite, about 4 minutes). Run it
  before you stop; a red or unrun check means the work is not done.
- **Tickets for agents** are in `docs/ai-dlc/agent-tickets.md`. Take one at a time, in its own
  worktree. Roadmap items not listed there are not ready for agents.
- **Never push, merge or check a roadmap box.** A reviewer re-runs the check and records the
  review; only then can the branch be pushed.

## What this is

A local, single-user Stockfish chess training app: a FastAPI and python-chess backend driving
Stockfish, and a chessground frontend (one single-page app with tab panels). It has play, an
opening trainer (lichess openings TSVs plus `data/commentary.json`), an opening-traps trainer
(`data/traps.json`), a repertoire trainer (`data/repertoire.json`) and a game-review coach backed
by SQLite. The game-review coach is a deterministic Stockfish and python-chess pipeline with
template narration and no LLM, in `storage`, `pgn`, `motifs`, `review`, `coaching`, `profile`,
`insights`, `accuracy` and `endgame`. `ARCHITECTURE.md` maps the modules.

## Commands

```sh
make check                       # lint (ruff check) + tests (pytest), same as CI
make test                        # tests only
.venv/bin/python -m pytest tests/test_analysis.py   # one file (pure logic, no Stockfish needed)
make ticket ID=<ticket id>       # claim a ticket: creates .worktrees/<id> on branch ticket/<id>

# One-time setup (the project owner's machine already has it)
brew install stockfish                 # engine binary (or set STOCKFISH_PATH)
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

# Run the app in the background on port 8001 (8000 is often taken)
chess-coach start | stop | restart | status   # or scripts/serve.sh start, without direnv
uvicorn app.main:app --reload --port 8001     # foreground with auto-reload
```

The virtualenv lives in the main checkout (`.venv/`); `make` finds it from any worktree. When a
live server is not available, check routes in-process with FastAPI's `TestClient`.

## Constraints that are not obvious from the code

- **The server is stateless per request** for play and the opening, traps and repertoire
  trainers (move history lives client-side). Game review is the exception: it persists to
  SQLite (`app/storage.py`, `data/games.db`) and runs a background analysis task
  (`app/review.py`).
- **User game data is never committed:** `data/games.db` and `data/games/` are gitignored.
- **`app/engine.py` runs one Stockfish process** behind a single `asyncio.Lock`, because the
  engine wrapper is not thread-safe. It imports safely when the binary is absent
  (`EngineUnavailable`). Never pass `game=` or send `ucinewgame` casually: it cold-starts the
  warm transposition table.
- **Engine budgets:** interactive analyses use the `SPEED_PRESETS` node budgets (the `speed`
  request field: fast, balanced or deep), and both `/api/move` evals must share one preset so
  their centipawn-loss comparison stays fair. `analyze_multi(fen, depth, multipv)` stays
  depth-only for reviews and shares the same lock; the review job goes through it and yields to
  interactive `/api/move` calls (`review.note_interactive_start` / `note_interactive_end`).
- **Pure modules stay pure:** `analysis.py`, `motifs.py`, `pgn.py`, `accuracy.py` and
  `endgame.py` have no engine or I/O; `coaching.py` imports only storage's `LeakRecord` type;
  `profile.py` and `insights.py` read SQLite without the engine. The full test suite runs with
  no engine through the `get_engine` fake.
- **Reuse `analysis.pov_score_to_white_cp` and `classify`:** every eval is from White's point
  of view before classification; never re-derive the mover-sign rule.

## Working an agent ticket

1. **Pick.** Use the ticket your prompt names. Otherwise take the first unchecked ticket in
   `docs/ai-dlc/agent-tickets.md` whose branch does not exist yet (`git branch --list 'ticket/*'`).
   If none is left, stop and say so.
2. **Claim it** from the repo root with `make ticket ID=<id>`. It refuses a ticket whose branch
   already exists, which means another session has it.
   - Codex: this writes to `.git`, so it asks the project owner's approval.
   - Gemini (agy) cannot run commands. Work only if you were started inside that ticket's
     worktree (`.worktrees/<id>`); otherwise stop and say which ticket you would take.
3. **Work only inside `.worktrees/<id>`.** Start the session from the repo root (Codex) so the
   main checkout's `.venv` stays readable.
4. **Write the failing test first.** Add a test that fails because of the bug, then fix the code,
   then confirm the test passes. Change only what the ticket needs.
5. **Run `make check` inside the worktree** and report its last lines. Gemini cannot run it: say
   so, and the caller runs it.
6. **Commit** (Codex asks approval; Gemini never commits and lists its changed files instead):
   - Subject: Conventional Commits (`fix:`, `test:`, `refactor:`, `docs:`, `chore:`),
     imperative, at most 50 characters. The body says why when it is not obvious.
   - End with the two trailer lines from the shared rules (`Agent-Vendor:`, `Agent-Model:`).
   - One logical change per commit; never commit work in progress.
7. **Stop and report:** the ticket, the commit hash, the check result and anything left undone.

## Git checks on every commit

`core.hooksPath` points this repo at shared hooks outside the repo. They refuse a commit with no
`Agent-Vendor`/`Agent-Model` trailers, any text naming the project owner, staged secrets or
private notes. They run no repo code, so lint and tests are not checked at commit time;
`make check` and the review cover them. The push hook refuses any commit without a
review record. Never bypass them (`--no-verify`, `-n`, or changing `core.hooksPath`).
