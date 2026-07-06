// repertoire.js — repertoire trainer (browse tree + Jump + rep-practice).
// Receives the injected `api` from app.js at init and never imports app.js
// back (one-directional: hub → feature → leaf).
//
// Two features off one data model (GET /api/repertoire):
//   * Jump — click a line to fast-forward the board there with full move history
//            (Undo back through it; opening name + Book Move badge ride on it).
//   * rep-practice — play your lines: you move, the app auto-plays the opponent.
//            While in prep it plays a RANDOM prepared reply within the chosen scope;
//            a non-prepared move of yours is rejected (take-back / reveal); once prep
//            is exhausted the engine takes over as the opponent.
//
// The trap-practice MOVE engine is script/FEN-driven and not reusable here, so this
// has its own primitive (repPlayApply) that plays an arbitrary runtime UCI on a live
// chessops position. Only the UX scaffolding (snapshot, bar, body class) is shared.
//
// Owns: `rep` (active session), `repTree`, `repSnapshot` (in-memory only — never
// persisted, unlike setup's hub-owned playSnapshot), and `repEngineToken` (guards
// stale async engine replies across take-back/restart/exit).

import { INITIAL_FEN } from 'https://esm.sh/chessops@0.14.2/fen';
import { chessgroundDests } from 'https://esm.sh/chessops@0.14.2/compat';
import { parseUci } from 'https://esm.sh/chessops@0.14.2/util';

let _api = null;
let repTree = null;      // /api/repertoire tree: { white, black, catalog }
let rep = null;          // active rep-practice session (see startRepPractice)
let repSnapshot = null;  // saved play game captured when entering rep-practice
let repEngineToken = 0;  // guards stale async engine-opponent replies

const byId = (id) => document.getElementById(id);
const state = () => _api.actions.getState();
const ground = () => _api.actions.getGround();

async function loadRepertoire() {
  try {
    const res = await fetch('/api/repertoire');
    const data = await res.json();
    repTree = (data && data.tree) ? data.tree : null;
  } catch (_) {
    repTree = null; // degraded — section hidden, no crash
  }
  renderRepertoireTree();
}

// Build the collapsible tree from repTree.catalog. Section hidden when empty.
function renderRepertoireTree() {
  const host = byId('repertoire-tree');
  host.replaceChildren();
  const cat = repTree && repTree.catalog;
  const total = cat ? (cat.white.length + cat.black.length) : 0;
  byId('repertoire-section').hidden = !total;
  if (!total) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'No repertoire lines loaded.';
    host.appendChild(empty);
    return;
  }

  for (const color of ['white', 'black']) {
    const groups = cat[color];
    if (!groups.length) continue;

    const colorWrap = document.createElement('div');
    colorWrap.className = 'rep-color';
    const colorHdr = document.createElement('button');
    colorHdr.className = 'rep-color-hdr';
    colorHdr.textContent = color === 'white' ? 'As White' : 'As Black';
    const colorBody = document.createElement('div');
    colorBody.className = 'rep-color-body';
    colorHdr.addEventListener('click', () => colorBody.classList.toggle('collapsed'));
    colorWrap.append(colorHdr, colorBody);

    for (const g of groups) {
      const op = document.createElement('div');
      op.className = 'rep-opening';

      const opHdr = document.createElement('div');
      opHdr.className = 'rep-opening-hdr';
      const opName = document.createElement('button');
      opName.className = 'rep-opening-name';
      opName.textContent = g.parentOpening;
      const opBody = document.createElement('div');
      opBody.className = 'rep-opening-body';
      opName.addEventListener('click', () => opBody.classList.toggle('collapsed'));

      const practiceBtn = document.createElement('button');
      practiceBtn.className = 'rep-practice-btn';
      practiceBtn.textContent = 'Practice';
      practiceBtn.title = 'Practice this opening (opponent varies its prepared replies)';
      const scopeIds = g.lines.map((l) => l.id);
      practiceBtn.addEventListener('click', () => startRepPractice(scopeIds, color, g.parentOpening));
      opHdr.append(opName, practiceBtn);

      for (const line of g.lines) {
        const row = document.createElement('div');
        row.className = 'rep-line';
        const jump = document.createElement('button');
        jump.className = 'rep-line-jump' + (line.isTrap ? ' is-trap' : '');
        jump.textContent = line.name + (line.isTrap ? ' (trap)' : '');
        jump.title = 'Jump to this position';
        jump.addEventListener('click', () => repJump(line, color));
        const pr = document.createElement('button');
        pr.className = 'rep-line-practice';
        pr.textContent = '▶';
        pr.title = 'Practice this exact line';
        pr.addEventListener('click', () => startRepPractice([line.id], color, line.name));
        row.append(jump, pr);
        opBody.append(row);
      }
      op.append(opHdr, opBody);
      colorBody.append(op);
    }
    host.append(colorWrap);
  }
}

// Jump: fast-forward to a line's end WITH full history (Undo steps back through it;
// opening name + Book Move badge ride on baseFen+moves).
function repJump(line, color) {
  const { hub } = _api;
  hub.ensurePlay();
  const s = state();
  s.baseFen = INITIAL_FEN;
  s.moves = line.ucis.slice();
  s.moveQuality = [];
  s.moveRetro = [];
  s.cursor = line.ucis.length;
  s.orientation = color;
  ground().set({ orientation: color });
  hub.syncBoard();
  hub.refreshAnalysis();
  hub.refreshOpeningThenTraps();
  hub.persist();
  hub.setStatus(`Jumped to ${line.name}.`);
}

// --- rep-practice ----------------------------------------------------------

function repChild(node, uci) {
  return node && node.children ? node.children.find((c) => c.uci === uci) : undefined;
}

// Children of `node` belonging to at least one line in the current scope.
function repScopedChildren(node) {
  if (!node || !node.children) return [];
  return node.children.filter((c) => c.lineIds.some((id) => rep.scope.has(id)));
}

function repSetNote(msg) { byId('rep-note').textContent = msg || ''; }
function repSetMove(msg) { byId('rep-move').textContent = msg || ''; }
function repSetFeedback(msg, kind) {
  const el = byId('rep-feedback');
  el.hidden = !msg;
  el.textContent = msg || '';
  el.classList.remove('feedback-good', 'feedback-bad');
  if (kind === 'good') el.classList.add('feedback-good');
  else if (kind === 'bad') el.classList.add('feedback-bad');
}

function showRepUI(on) {
  byId('rep-bar').hidden = !on;
  document.body.classList.toggle('rep-mode', on);
  if (on) byId('trap-chip').hidden = true;
}

// Render the live practice board (frozen) at rep.board, highlighting lastUci.
function repRenderBoard(lastUci) {
  const { hub } = _api;
  const fen = hub.fenOf(rep.board);
  ground().set({
    fen: fen.split(' ')[0],
    turnColor: rep.board.turn,
    orientation: rep.color,
    lastMove: lastUci ? hub.lastMoveSquares(lastUci) : undefined,
    movable: { free: false, color: undefined, dests: undefined },
    draggable: { enabled: false },
  });
}

// Arm the board for YOUR move (your color's legal dests).
function repSetInteractive() {
  const { hub } = _api;
  const pos = rep.board;
  const fen = hub.fenOf(pos);
  const last = rep.moves.length ? rep.moves[rep.moves.length - 1] : null;
  ground().set({
    fen: fen.split(' ')[0],
    turnColor: pos.turn,
    orientation: rep.color,
    lastMove: last ? hub.lastMoveSquares(last) : undefined,
    movable: { free: false, color: rep.color, dests: chessgroundDests(pos) },
    draggable: { enabled: true, deleteOnDropOff: false },
  });
}

function repSetFrozen() {
  ground().set({ movable: { free: false, color: undefined, dests: undefined }, draggable: { enabled: false } });
}

// Play one arbitrary UCI on the live position (the primitive trap-practice lacks).
function repPlayApply(uci) {
  rep.board.play(parseUci(uci));
  rep.moves.push(uci);
  rep.node = rep.node ? (repChild(rep.node, uci) || null) : null;
  repRenderBoard(uci);
}

// Enter (or re-enter) practice for a scope of line ids.
function startRepPractice(scopeIds, color, label) {
  const { hub } = _api;
  if (!repTree || !repTree[color]) return;
  hub.ensurePlay();
  repEngineToken++;            // invalidate any in-flight engine reply
  repSnapshot = hub.snapshotPlay();
  hub.setMode('rep-practice');
  state().orientation = color;
  rep = {
    scope: new Set(scopeIds),
    color,
    label,
    root: repTree[color],
    node: repTree[color],
    board: hub.positionFromFen(INITIAL_FEN),
    moves: [],
    engineMode: false,
    expected: null,
    expectedSan: null,
  };
  showRepUI(true);
  byId('rep-title').textContent = `Practice: ${label}`;
  repSetFeedback('', null);
  repSetNote('');
  repSetMove('');
  ground().set({ orientation: color });
  repRenderBoard(null);
  repAdvance();
}

// Restart the current practice from the start (same scope) — no snapshot churn.
function repRestart() {
  if (!rep) return;
  repEngineToken++;            // invalidate any in-flight engine reply
  rep.board = _api.hub.positionFromFen(INITIAL_FEN);
  rep.node = rep.root;
  rep.moves = [];
  rep.engineMode = false;
  rep.expected = null;
  repSetFeedback('Restarted.', null);
  repRenderBoard(null);
  repAdvance();
}

function exitRepPractice() {
  const { hub } = _api;
  repEngineToken++;            // invalidate any in-flight engine reply
  hub.restorePlay(repSnapshot || { baseFen: INITIAL_FEN, moves: [], cursor: 0 });
  hub.setMode('play');
  repSnapshot = null;
  rep = null;
  showRepUI(false);
  hub.syncBoard();
  hub.refreshAnalysis();
  hub.refreshOpeningThenTraps();
  hub.persist();
}

// Drive the practice loop from the current position.
function repAdvance() {
  if (!rep || state().mode !== 'rep-practice') return;
  const yourTurn = rep.board.turn === rep.color;

  if (rep.engineMode) {
    if (yourTurn) {
      repSetInteractive();
      repSetMove('Engine game — your move.');
    } else {
      repEngineReply();
    }
    return;
  }

  const kids = repScopedChildren(rep.node);

  if (yourTurn) {
    if (!kids.length) {           // your-turn leaf → handoff (you play, engine replies)
      rep.engineMode = true;
      repSetNote('Prep complete — the engine takes over as your opponent. Play on.');
      repSetMove('Your move.');
      repSetInteractive();
      return;
    }
    rep.expected = kids[0].uci;    // exactly one by invariant
    rep.expectedSan = kids[0].san;
    repSetMove('Your move — play your prepared move.');
    repSetInteractive();
  } else {
    if (!kids.length) {           // opponent-turn leaf → handoff (engine replies now)
      rep.engineMode = true;
      repSetNote('Prep complete — the engine takes over as your opponent. Play on.');
      repEngineReply();
      return;
    }
    const pick = kids[Math.floor(Math.random() * kids.length)];
    repSetFrozen();
    const scheduledLen = rep.moves.length;
    setTimeout(() => {
      if (!rep || state().mode !== 'rep-practice') return;
      if (rep.moves.length !== scheduledLen) return; // took back / exited while waiting
      repPlayApply(pick.uci);
      repSetFeedback(`Opponent played ${pick.san}.`, null);
      repAdvance();
    }, 400);
  }
}

// Engine opponent (post-prep). Plays Stockfish's best move; degrades gracefully.
async function repEngineReply() {
  const { hub } = _api;
  if (!rep || state().mode !== 'rep-practice') return;
  repSetFrozen();
  const fen = hub.fenOf(rep.board);
  // Guard against a stale reply landing after the position changed (take-back /
  // restart / a newer engine request) — otherwise we'd play a move computed for a
  // different FEN onto the current board.
  const token = ++repEngineToken;
  let data;
  try {
    data = await hub.postJSON('/api/analyze', { fen });
  } catch (_) {
    if (token !== repEngineToken) return;
    repSetNote('Prep complete — engine unavailable. Use Take back or Return to my game.');
    return;
  }
  if (!rep || state().mode !== 'rep-practice' || token !== repEngineToken) return;
  const uci = data && data.analysis && data.analysis.bestMoveUci;
  if (!uci) {
    repSetNote('Game over — no engine move available.');
    return;
  }
  repPlayApply(uci);
  repSetFeedback(`Engine played ${data.analysis.bestMoveSan || uci}.`, null);
  repAdvance();
}

// Your move handler in rep-practice (registered with the hub's mode registry).
async function onRepMove(orig, dest) {
  const { hub } = _api;
  if (state().mode !== 'rep-practice' || !rep) return;
  const posBefore = hub.positionFromFen(hub.fenOf(rep.board));
  let promo = '';
  if (hub.isPromotion(posBefore, orig, dest)) promo = await hub.askPromotion();
  const attempted = orig + dest + promo;

  if (rep.engineMode) {                 // free play vs engine
    repPlayApply(attempted);
    repAdvance();
    return;
  }

  if (attempted === rep.expected) {
    repPlayApply(attempted);
    repSetFeedback(`Good — ${rep.expectedSan}.`, 'good');
    repAdvance();
  } else {
    repSetInteractive();                // snap back
    repSetFeedback('Not a prepared move — try again.', 'bad');
  }
}

// Reveal: play your prepared move for you (prep mode only).
function revealRepMove() {
  if (state().mode !== 'rep-practice' || !rep || rep.engineMode) return;
  if (!rep.expected) return;
  const san = rep.expectedSan;
  repPlayApply(rep.expected);
  repSetFeedback(`Revealed: ${san}.`, 'good');
  repAdvance();
}

// Take back: undo your last move AND the opponent's reply → re-face your prior
// decision. Rebuilds the position from the truncated move list.
function repBack() {
  if (!rep || state().mode !== 'rep-practice') return;
  if (rep.moves.length < 2) { repSetFeedback('Already at the first decision.', null); return; }
  repEngineToken++;            // invalidate any in-flight engine reply
  const kept = rep.moves.slice(0, rep.moves.length - 2);
  rep.board = _api.hub.positionFromFen(INITIAL_FEN);
  rep.node = rep.root;
  rep.engineMode = false;
  rep.expected = null;
  rep.moves = [];
  for (const u of kept) {
    rep.board.play(parseUci(u));
    rep.node = rep.node ? (repChild(rep.node, u) || null) : null;
    rep.moves.push(u);
  }
  repRenderBoard(rep.moves.length ? rep.moves[rep.moves.length - 1] : null);
  repSetFeedback('Took back — try again.', null);
  repAdvance();
}

// --- init --------------------------------------------------------------------

export function initRepertoire(api) {
  _api = api;

  // Repertoire practice bar controls
  byId('rep-return').addEventListener('click', exitRepPractice);
  byId('rep-back').addEventListener('click', repBack);
  byId('rep-reveal').addEventListener('click', revealRepMove);
  byId('rep-restart').addEventListener('click', repRestart);

  // The hub's dispatcher and ensurePlay() route through this registration.
  api.hub.registerModeHandlers('rep-practice', { onMove: onRepMove, exit: exitRepPractice });

  // Load browse data (non-blocking — section degrades gracefully).
  loadRepertoire();
}
