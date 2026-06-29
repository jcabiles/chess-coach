# Contracts — UX/UI Modernization

Read-only architecture map (cavecrew-investigator pass) for the front-end UX rework.
Defines the seams ticket boundaries must respect.

## Invariants a rework MUST NOT break

- **Stateless per request.** `state.moves` (client) is the sole game history. `/api/move`
  sends the FEN-before-move, never a game id. Keep history client-side.
- **EPD/identity server-side only.** Client sends `{baseFen, moves}` to `/api/opening`
  and `/api/traps/check`; server derives EPD. Client never computes/sends an EPD.
- **`app/analysis.py` is pure.** A pure UX rework needs **no** API/contract change.
- **Wire-format field names are frozen** (consumed by `renderAnalysis` app.js:347):
  `evalCp`, `mate`, `quality`, `bestMoveSan`, `bestMoveUci`, `pvSan`, `book`, `openingName`.
- **`app.js` is `type="module"`** (index.html:196) — all top-level vars are module-private,
  not on `window`. Any split into ES modules must explicitly export/import every shared
  var (`state`, `ground`, `trap`, `rep`, and 10+ guard tokens). No global bus exists.
- **Board move handler** (app.js:1690-1699): the `movable.events.after` trampoline must
  stay a single closure that reads `state.mode` **at call time**, dispatching to
  `onTrapMove | onRepMove | onUserMove`.
- **`restore()` replays all moves through chessops** (app.js:134-136). Do NOT change the
  persisted shape (`{baseFen, moves, cursor, orientation}` / setup variant) or existing
  localStorage sessions silently break. Key: `chess-training:session:v1`.

## State (app.js:42-65)

`state = { mode, baseFen, moves[], cursor, orientation, setupColor }`.
`state.mode ∈ {play, setup, trap-watch, trap-practice, rep-practice}` — the single FSM
value, but **read/written at ~13 scattered sites** (no reducer/dispatch table).
Side-car module vars: `ground, playSnapshot, brush, studySnapshot, studyEvalToken,
trapsData, trapsCheckToken, trapChipDismissedFen, trap, repTree, rep, repEngineToken`.

## Key render/hook points

- **Analysis panel writer:** `renderAnalysis(a, opts)` app.js:347-361 → `#eval`, `#quality`
  (+`q-{quality}` class), `#best-move`, `#pv` (`a.pvSan.join(' ')`). `renderBookMove` 366-374
  and `applyMoveResponse` 379-382 share the path. **Eval-bar, PV reformat, move-quality
  chip all hook here.**
- **Board sync (play):** `syncBoard` app.js:179-190 (sole authoritative play-mode sync;
  8 callers). Other modes call `ground.set` directly.
- **Opening:** `renderOpening` 632-638 → `#opening-name`.
- **refreshAnalysis** 232-251 posts `/api/analyze`|`/api/move`; called by undo/redo/reset/
  exit*/init.

## Mode gating (NOT centralized — two parallel mechanisms)

1. **Body classes + CSS `display:none`**: `body.setup-mode` (css:82), `.trap-watch-mode`/
   `.trap-practice-mode` (css:184-195), `.rep-mode` (css:304-309).
2. **`hidden` attr** on bars: `#setup-bar`, `#trap-bar`/`#trap-stepper`/`#trap-reveal`,
   `#rep-bar` — toggled by `showSetupUI` (468), `showTrapUI` (989), `applyTrapModeUI` (862),
   `showRepUI` (1435).

Known issue (live-observed): in trap/rep modes the **right `<aside>` panel is not scoped** —
it keeps showing play-mode analysis (eval/PV/repertoire/traps), which can contradict the
mode (two different evals on screen).

## style.css structure (css line ranges)

`:root` tokens 1-19 (all 12 semantic colors ARE custom props) · base/header/board/buttons
21-77 · setup 80-129 · panel/eval/quality/pv 131-175 · opening 178-179 · traps+trap-bar
181-295 · repertoire 301-405 · promo overlay 408-431 · responsive 433-443.
**Raw-hex literals remaining** (promote to tokens): `#222` (css:66,101,362), `#1f3a5f`
(244), `#10243f` (124,258,353), `rgba(0,0,0,.55)` scrim (413).

## Hotspots (parallel-edit collision risk)

- **app.js:** `state` decl 42-65 · `renderAnalysis`/`applyMoveResponse` 347-382 ·
  `syncBoard` 179-190 · `init` wiring 1674-1783 · `persist`/`restore` 76-147 ·
  `applyTrapModeUI`/`showTrapUI` 864-876.
- **index.html:** `<head>` 2-22 · board-col 29-129 (all mode bars) · `<aside class="panel">`
  131-180 (all analysis widgets) · `<script>` 196.
- **style.css:** `:root` 1-19 (all theming) · traps block 181-295.

## Implication for orchestration

The three shared files are the parallelization bottleneck. Genuine parallelism requires
either (a) extracting new work into NEW files/modules with a small declared export surface
on the hub, or (b) a full app.js module split first (riskier per the invariants above).
Foundation (tokens + layout shell + the analysis hook surface) must land before
feature/integration tickets that depend on it.
