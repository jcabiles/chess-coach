# AI-DLC profile — chess-training

stack:        mixed (Python 3 / FastAPI backend · vanilla-ESM JS frontend — chessground/chessops SPA)
artifact_dir: docs/ai-dlc            # base dir for roadmap/ prd/ contracts/ specs/ tickets/

verify:
  test:  .venv/bin/python -m pytest -q          # full suite; runs engine-free via the get_engine fake seam
  lint:  .venv/bin/ruff check app               # (ruff used in prior specs' verify-by)
  boot:  uvicorn app.main:app --reload --port 8001   # → GET / 200; exercise UI in browser (Playwright/manual)

hotspots:
  - app/main.py        # FastAPI router — single owner of API routes
  - app/engine.py      # one Stockfish process, all access serialized behind one asyncio.Lock
  - app/models.py      # Pydantic request/response shapes (Analysis, MoveResponse, …)
  - app/analysis.py    # pure eval/classify helpers
  - static/app.js      # SPA controller (state, refreshAnalysis, onUserMove)
  - static/panel.js    # analysis-panel render (eval/quality/best-move/PV)
  - static/prefs.js    # ui-prefs read/write seam (chess-training:ui:v1)

invariants:
  - Server is stateless per request for play + opening/traps/repertoire trainers (move history lives client-side); ONLY game-review persists (SQLite data/games.db).
  - One Stockfish process; all engine access serialized behind a single asyncio.Lock (SimpleEngine is not thread-safe). Import-safe if the binary is absent (EngineUnavailable).
  - app/analysis.py, motifs.py, pgn.py, coaching.py, profile.py are PURE — unit-testable with no Stockfish binary; the full suite runs engine-free via the get_engine fake seam.
  - Reuse analysis.pov_score_to_white_cp / classify — all evals are White-POV before classification; never re-derive the mover-sign rule.
  - analyzeColor (Both/White/Black) 'both' MUST reproduce prior behavior bit-for-bit; the color-only skip must never add engine load beyond today.
  - Tokens-only CSS (no raw hex); persist UI prefs only via the chess-training:ui:v1 key (prefs.js).
  - User game data (data/games.db, data/games/) is gitignored — never commit it.

auth:         local single-user tool; no external auth. (If an LLM is ever added: API key or claude CLI only — Max/Pro OAuth is ToS-blocked.)

hygiene:      no debug artifacts on commit (no console.log, window.__dbg, screenshots, .playwright-mcp/); Conventional Commits; never push to main.
