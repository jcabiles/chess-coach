// cmdk.js — Cmd/Ctrl-K command palette.
//
// Injected-api module (never imports app.js). A <dialog> with a filter input
// and a listbox of commands: tab switches, board actions, and deep links into
// traps ('traps:open') and repertoire practice ('repertoire:practice') via the
// api bus — those modules own the actual entry paths; the palette only emits.
//
// Static commands run through the SAME wiring a user click would take (tab
// buttons get requestModeExit handling, theme button cycles prefs), so the
// palette adds zero new state transitions of its own.
//
// Catalogs (traps, repertoire lines) are fetched lazily on first open and
// cached for the session — the palette costs nothing until used.

const byId = (id) => document.getElementById(id);

let _api = null;
let _commands = null;        // built lazily; null until first open
let _filtered = [];          // current match list [{cmd, score}]
let _selected = 0;           // index into _filtered
let _catalogsLoaded = false;

const TAB_LABELS = {
  analysis: 'Analysis', opening: 'Opening', traps: 'Traps',
  repertoire: 'Repertoire', review: 'Review', insights: 'Insights',
};

// ---------------------------------------------------------------------------
// Fuzzy matching — ordered-subsequence scoring, generous but deterministic:
// +3 for a match on a word start, +2 for consecutive matches, +1 otherwise.
// Case-insensitive; returns null when the query isn't a subsequence.
// ---------------------------------------------------------------------------
function fuzzyScore(query, text) {
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  if (!q) return 0;
  let score = 0;
  let ti = 0;
  let prevMatch = -2;
  for (let qi = 0; qi < q.length; qi++) {
    const ch = q[qi];
    if (ch === ' ') { continue; } // spaces are free separators
    let found = -1;
    for (; ti < t.length; ti++) {
      if (t[ti] === ch) { found = ti; break; }
    }
    if (found === -1) return null;
    const wordStart = found === 0 || t[found - 1] === ' ' || t[found - 1] === ':' || t[found - 1] === '—';
    score += wordStart ? 3 : (found === prevMatch + 1 ? 2 : 1);
    prevMatch = found;
    ti = found + 1;
  }
  return score;
}

// ---------------------------------------------------------------------------
// Command registry
// ---------------------------------------------------------------------------

function clickIfPresent(id) {
  const elBtn = byId(id);
  if (elBtn) elBtn.click();
}

function staticCommands() {
  const cmds = [];

  for (const [tab, label] of Object.entries(TAB_LABELS)) {
    cmds.push({
      label: `Go to ${label} tab`,
      hint: 'tab',
      run: () => clickIfPresent(`tab-btn-${tab}`),
    });
  }

  cmds.push(
    { label: 'Flip board', hint: 'board', run: () => _api.actions.flip() },
    { label: 'Undo move', hint: 'board', run: () => _api.actions.undo() },
    { label: 'Redo move', hint: 'board', run: () => _api.actions.redo() },
    { label: 'Reset to start', hint: 'board', run: () => _api.actions.reset() },
    {
      label: 'Load FEN…',
      hint: 'board',
      // Focus the FEN input rather than duplicating its load path — the
      // palette navigates; #load-fen stays the single owner of FEN parsing.
      run: () => { const f = byId('fen-input'); if (f) { f.focus(); f.select(); } },
    },
    { label: 'Set up position', hint: 'board', run: () => clickIfPresent('setup-toggle') },
    { label: 'Toggle theme (light / dark / system)', hint: 'ui', run: () => clickIfPresent('theme-toggle') },
    { label: 'Restart engine', hint: 'engine', run: () => clickIfPresent('engine-restart-btn') },
  );

  return cmds;
}

async function loadCatalogCommands() {
  const cmds = [];

  // Traps — deep link into watch mode via the bus; traps.js owns entry.
  try {
    const res = await fetch('/api/traps');
    const data = await res.json();
    for (const t of (data.traps || [])) {
      cmds.push({
        label: `Trap: ${t.name}`,
        hint: t.color === 'white' ? 'as White' : 'as Black',
        run: () => _api.emit('traps:open', t.id),
      });
    }
  } catch (_) { /* degraded — palette just has no trap entries */ }

  // Repertoire lines — deep link into practice via the bus.
  try {
    const res = await fetch('/api/repertoire');
    const data = await res.json();
    const cat = data && data.tree && data.tree.catalog;
    for (const color of ['white', 'black']) {
      for (const group of ((cat && cat[color]) || [])) {
        for (const line of (group.lines || [])) {
          cmds.push({
            label: `Practice: ${group.parentOpening} — ${line.name}`,
            hint: `as ${color}`,
            run: () => _api.emit('repertoire:practice', {
              lineId: line.id, color, name: line.name,
            }),
          });
        }
      }
    }
  } catch (_) { /* degraded */ }

  return cmds;
}

async function ensureCommands() {
  if (_commands === null) _commands = staticCommands();
  if (!_catalogsLoaded) {
    _catalogsLoaded = true; // set first — a failed fetch shouldn't refetch every keystroke
    _commands = _commands.concat(await loadCatalogCommands());
    refilter(); // catalogs may arrive after the dialog painted
  }
}

// ---------------------------------------------------------------------------
// Rendering + selection
// ---------------------------------------------------------------------------

function refilter() {
  const input = byId('cmdk-input');
  const query = input ? input.value.trim() : '';
  const scored = [];
  for (const cmd of (_commands || [])) {
    const s = fuzzyScore(query, cmd.label);
    if (s !== null) scored.push({ cmd, score: s });
  }
  scored.sort((a, b) => b.score - a.score);
  _filtered = scored.slice(0, 12);
  _selected = 0;
  renderList();
}

function renderList() {
  const list = byId('cmdk-list');
  const input = byId('cmdk-input');
  if (!list) return;
  list.replaceChildren();
  _filtered.forEach(({ cmd }, i) => {
    const li = document.createElement('li');
    li.id = `cmdk-opt-${i}`;
    li.setAttribute('role', 'option');
    li.setAttribute('aria-selected', String(i === _selected));
    li.className = 'cmdk-item' + (i === _selected ? ' is-selected' : '');
    const label = document.createElement('span');
    label.className = 'cmdk-label';
    label.textContent = cmd.label;
    li.appendChild(label);
    if (cmd.hint) {
      const hint = document.createElement('span');
      hint.className = 'cmdk-hint';
      hint.textContent = cmd.hint;
      li.appendChild(hint);
    }
    li.addEventListener('click', () => runCommand(i));
    // Hovering moves the selection so pointer + keyboard agree on Enter.
    li.addEventListener('mousemove', () => {
      if (_selected !== i) { _selected = i; renderList(); }
    });
    list.appendChild(li);
  });
  if (!_filtered.length) {
    const empty = document.createElement('li');
    empty.className = 'cmdk-empty';
    empty.textContent = 'No matching command.';
    list.appendChild(empty);
  }
  if (input) {
    input.setAttribute(
      'aria-activedescendant',
      _filtered.length ? `cmdk-opt-${_selected}` : '',
    );
  }
}

function runCommand(index) {
  const entry = _filtered[index];
  closePalette();
  if (entry) entry.cmd.run();
}

// ---------------------------------------------------------------------------
// Open / close
// ---------------------------------------------------------------------------

function openPalette() {
  const dlg = byId('cmdk');
  if (!dlg || dlg.open) return;
  if (_api.actions.closeAnyDialog) _api.actions.closeAnyDialog();
  const input = byId('cmdk-input');
  if (input) input.value = '';
  dlg.showModal();
  ensureCommands(); // async; refilters again when catalogs land
  refilter();
  if (input) input.focus();
}

function closePalette() {
  const dlg = byId('cmdk');
  if (dlg && dlg.open) dlg.close();
}

export function initCmdk(api) {
  _api = api;
  const dlg = byId('cmdk');
  const input = byId('cmdk-input');
  if (!dlg || !input) return;

  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'k') {
      e.preventDefault(); // browsers grab Cmd/Ctrl-K for their own search
      if (dlg.open) closePalette(); else openPalette();
    }
  });

  input.addEventListener('input', refilter);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (_filtered.length) { _selected = (_selected + 1) % _filtered.length; renderList(); }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (_filtered.length) { _selected = (_selected - 1 + _filtered.length) % _filtered.length; renderList(); }
    } else if (e.key === 'Enter') {
      e.preventDefault();
      runCommand(_selected);
    }
  });

  // Click on the backdrop closes (native <dialog> Esc already works).
  dlg.addEventListener('click', (e) => {
    if (e.target === dlg) closePalette();
  });
}
