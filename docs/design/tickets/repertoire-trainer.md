# Tickets — Repertoire Trainer (tree + jump + practice)

Spec: `docs/design/specs/repertoire-trainer.md`. Contracts:
`docs/design/contracts/repertoire-trainer.md`. Slug: `repertoire-trainer`.
8 tickets. "Owns" = the only files that ticket may edit (one file = one owner).
Refuter-folded fixes are flagged inline.

---

### TR1 — Curated repertoire data  ·  owns `data/repertoire.json`
A `{ "lines": [...] }` file: ~8–15 named lines covering the repertoire (1.e4 — Italian
vs ...e5, Open Sicilian vs ...c5, Scandinavian vs ...d5; Black — Sicilian vs 1.e4, Indian
vs 1.d4) + trap leaves via `"trapId"`. Each line: `id`, `name`, `parentOpening`,
`yourColor`, and either a SAN `line` **or** a `trapId` (+ optional `variation`). **Content
is seeded WITH the user**: research the lines (a python-chess-verified research sub-agent,
maker≠checker), then the **user approves the final list** before it lands (same
verify-before-ship discipline as the traps).
**Done:** valid JSON; every SAN `line` replays legally from the start (python-chess); every
`trapId` matches a real trap; user has signed off on the line list.
**Dep:** none (format); content gate = user approval. **Parallel with** TR2, TR4, TR6.

### TR2 — Per-trap mainline accessor  ·  owns `app/traps.py`
Add `mainline_ucis_for(trap_id, variation=0) -> list[str]`: `traps.get(trap_id)` → convert
`leadInSan` SAN→UCI and **prepend** to `variations[variation].mainLine[].uci` (the same
build `iter_mainline_ucis` does internally, `traps.py:250-272`). **Why (refuter):**
`iter_mainline_ucis()` returns *all* variations of *all* traps at once and can't be filtered
by id, so repertoire trap-leaves need this. Exception-safe: unknown id / out-of-range
variation / malformed lead-in ⇒ `[]`, never raise. (Optionally refactor
`iter_mainline_ucis` to call it — keep behavior identical.)
**Done:** `mainline_ucis_for("ruy-lopez-trap")` starts `["e2e4","e7e5","g1f3","b8c6",...]`
and replays legally; bad id ⇒ `[]`; existing traps tests still pass.
**Dep:** none. **Parallel with** TR1, TR4, TR6.

### TR3 — `app/repertoire.py` loader + tree  ·  owns `app/repertoire.py`
Module singleton mirroring `traps.py` (import-safe, reset-first, never raise). `load(path)`
/ `init(path)`. Per line: validate required fields + `yourColor`; replay SAN `line` (or
resolve `trapId` via `traps.mainline_ucis_for`) → UCI sequence + per-ply data; **drop
malformed/illegal lines with a warning**. Build: (a) **catalog** `color → parentOpening →
{id,name,line}`; (b) per-color **move prefix tree** (nodes `{uci,san,ply,yourTurn,leaf,
name?,children}`). Enforce the **your-turn-single-child invariant**: a node where
side-to-move == `yourColor` must have exactly one child; on conflict, **log loudly (name the
dropped line + position)** and drop the conflicting line. Expose `tree() -> {"white","black",
"catalog"}` (well-formed + empty when no data) and `iter_lines() -> list[list[str]]` (full
UCI lines incl. trap leaves; exception-safe). **No engine/network import; trap moves only
via `app.traps`.**
**Done:** `import app.repertoire` ok; against TR1 data, `tree()` groups by color→opening→line
and the move tree is single-child at your nodes / branching at opponent nodes; a conflicting
fixture line is dropped (logged), not raised; `iter_lines()` returns full UCI lists; empty
file ⇒ `tree()` empty + well-formed.
**Dep:** TR1 (format), TR2 (trap accessor).

### TR4 — Model field  ·  owns `app/models.py`
`Analysis.bestMoveUci: str | None = None` (optional, default None). **Backward-safe
(refuter):** no exact-dict test breaks — the lone exact-dict test (`test_api.py:65`) is on a
`MoveResponse` with `analysis=None`; `bestMoveUci` is *inside* `Analysis`.
**Done:** models import; default None; existing API tests still pass unedited.
**Dep:** none. **Parallel with** TR1, TR2, TR6.

### TR5 — API wiring  ·  owns `app/main.py`
(1) Lifespan: `repertoire.init(str(REPERTOIRE_FILE))` after `openings`/`traps` init; fold
repertoire lines into the **`trap_ucis`** book slot (refuter):
`trap_ucis=list(traps.iter_mainline_ucis()) + list(repertoire.iter_lines())` (bypasses
`firstMoves`), inside the existing try/except guard. (2) `_build_analysis`:
`bestMoveUci = result.pv[0].uci() if result.pv else None`. (3) NEW route
`GET /api/repertoire` → `{"tree": repertoire.tree()}` (plain dict like `/api/traps`;
well-formed + empty when absent; never 500).
**Done:** `/api/repertoire` returns the grouped tree (empty well-formed with no data);
`/api/analyze` + `/api/move` carry `bestMoveUci`; a curated line's positions are recognized
by `book.is_book_move`; startup survives a malformed repertoire line.
**Dep:** TR3, TR4.

### TR6 — Tree + practice-bar markup & styles  ·  owns `static/index.html`, `static/style.css`
`index.html`: a **"My Repertoire"** panel section (mirror `#traps-section`) for the
collapsible tree, and a **repertoire-practice bar** in the board column (mirror `#trap-bar`):
status line, **Take back**, **Reveal move**, **Return to my game**. `style.css`: tree +
practice-bar styles, **tokens only**, mirroring trap/setup-bar + traps-section classes; AA
contrast in dark theme.
**Done:** markup present + hidden by default; styles load; no raw hex (tokens only); visually
confirmed alongside TR7.
**Dep:** none (presentation). **Parallel with** TR1, TR2, TR4.

### TR7 — Frontend logic: tree + jump + practice  ·  owns `static/app.js`
Single owner of the client logic. **Milestone A (the MVP — ship/verify first):** fetch
`/api/repertoire`; render the collapsible tree (color→opening→line); each line **Jump** =
full-history jump (`baseFen=START`, `moves=<line UCIs>`, `cursor=moves.length`, then
`syncBoard()`+`refreshAnalysis()` — verified sound, no redo stack). **Milestone B
(practice):** new `'rep-practice'` mode per the traversal model — gate `onUserMove`;
**new move-application primitive** that plays an arbitrary runtime UCI via
`positionFromFen()`+`pos.play(parseUci(uci))` (the trap-practice script engine is NOT
reusable — refuter); auto-opponent = random in-scope prepared child, then engine
`bestMoveUci` after prep (handle absent-engine / terminal / empty-PV per spec); deviation ⇒
reject + take-back + reveal; reuse trap-practice UX scaffolding (snapshot, body class, bar);
exit restores the play snapshot. **Add `'rep-practice'` to the `persist()` early-return
guard** (`app.js:72-73`) so practice never persists; confirm `restore()` never resurrects it.
**Done (A):** tree renders grouped + collapsible; leaf jump lands with full history (Undo
steps back, opening name + Book Move badge show) — browser-verified. **Done (B):** opponent
auto-replies with a random in-scope prepared move; a non-prepared move is rejected with
take-back/reveal; end-of-prep hands off to the engine (a Stockfish move appears); "Return to
my game" restores the prior game; refresh does not resurrect practice — browser-verified.
**Dep:** TR5 (API + `bestMoveUci`), TR6 (markup).

### TR8 — Tests (maker ≠ checker)  ·  owns `tests/test_repertoire.py`, `tests/test_repertoire_api.py`, `tests/fixtures/repertoire_sample.json`
Data/loader (`test_repertoire.py`): against shipped data — every `line` replays legally;
`yourColor` valid; **your-turn-single-child invariant holds**; trap leaves resolve to a real
mainline; `iter_lines()` returns full UCI lines; a curated line's positions are recognized by
`book.is_book_move` (book-extension check lives here, not in the book feature's tests). Fixture
cases: grouped `tree()` shape; opponent-branch vs your-single-child; a conflicting/illegal
fixture line is **dropped, not raised**; empty file ⇒ well-formed empty tree. API
(`test_repertoire_api.py`): `GET /api/repertoire` returns `{"tree":{...}}` grouped, empty
well-formed with no data (never 500); `Analysis.bestMoveUci` present (UCI) via a fake engine
and `None` when no PV. **No existing test edits needed** (refuter: `bestMoveUci` doesn't break
`test_move_illegal`). Written by an agent **other** than TR3/TR5/TR7's author.
**Done:** `pytest` green; invariant + drop-on-conflict + degrade-empty all covered;
book-extension assertion passes.
**Dep:** TR3, TR5 (overlaps TR7).

---

## Parallelization

- **Phase 1 (parallel, disjoint files):** TR1 ‖ TR2 ‖ TR4 ‖ TR6.
- **Phase 2:** TR3 (after TR1 format + TR2 accessor).
- **Phase 3:** TR5 (after TR3, TR4) — hotspot `app/main.py`.
- **Phase 4:** TR7 (after TR5, TR6) — hotspot `static/app.js`; do **Milestone A, verify,
  then B**. Largest review surface; the only genuinely new control flow (auto-opponent).
- **Phase 5:** TR8 (after TR3, TR5; overlaps TR7).

Real parallelism is Phase 1; the rest is the usual `repertoire.py → main.py → app.js` chain.

## Suggested model assignment (lock at "go")

- **Opus** — TR3 (tree/invariant correctness), TR5 (book-fold + wiring), TR7-B (practice FSM
  + engine auto-opponent), TR8 (verification).
- **Sonnet** — TR1 (data, then user-approved), TR2, TR4, TR6, TR7-A (pattern-following jump).

## Staging note

TR7 bundles the **stated MVP** (tree + jump, Milestone A) and the **new-in-scope** practice
mode (Milestone B). A is shippable on its own; if you want to commit the MVP first and tackle
practice as a follow-up, stop after TR1–TR6 + TR7-A + the data/API parts of TR8, then do
TR7-B + its practice tests as a second commit. (Both keep `app.js` single-owner.)
