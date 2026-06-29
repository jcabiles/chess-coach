// shortcuts.js — Keyboard shortcut bindings module.
// Receives all dependencies via the injected `api` argument (no imports from app.js).
// Exports: initShortcuts(api)

export function initShortcuts(api) {
  const actions = api && api.actions;
  if (!actions) return;

  document.addEventListener('keydown', (e) => {
    // Guard: ignore all shortcuts when focus is in an editable field.
    const target = e.target;
    if (
      target instanceof HTMLInputElement ||
      target instanceof HTMLTextAreaElement ||
      target instanceof HTMLSelectElement ||
      (target instanceof HTMLElement && target.isContentEditable)
    ) {
      return;
    }

    const ctrl = e.ctrlKey || e.metaKey;
    const shift = e.shiftKey;
    const key = e.key;

    // Determine current mode. 'play' is the default when the attribute is absent.
    const mode = document.body.dataset.mode || 'play';
    const isPlayMode = mode === 'play' || mode === '';

    // Ctrl/Cmd+Shift+Z  →  redo
    if (ctrl && shift && key === 'Z') {
      if (!isPlayMode) return;
      e.preventDefault();
      if (actions.redo) actions.redo();
      return;
    }

    // Ctrl/Cmd+Y  →  redo
    if (ctrl && !shift && key === 'y') {
      if (!isPlayMode) return;
      e.preventDefault();
      if (actions.redo) actions.redo();
      return;
    }

    // Ctrl/Cmd+Z  →  undo (must come after Ctrl+Shift+Z check)
    if (ctrl && !shift && key === 'z') {
      if (!isPlayMode) return;
      e.preventDefault();
      if (actions.undo) actions.undo();
      return;
    }

    // From here: no modifier combos — reject any Ctrl/Cmd/Alt/Meta keys.
    if (ctrl || e.altKey || e.metaKey) return;

    switch (key) {
      case 'F':
      case 'f':
        // Flip works in any mode.
        e.preventDefault();
        if (actions.flip) actions.flip();
        break;

      case 'ArrowLeft':
        if (!isPlayMode) return;
        e.preventDefault();
        if (actions.stepBack) actions.stepBack();
        break;

      case 'ArrowRight':
        if (!isPlayMode) return;
        e.preventDefault();
        if (actions.stepForward) actions.stepForward();
        break;

      case 'Home':
        if (!isPlayMode) return;
        e.preventDefault();
        if (actions.goto) actions.goto(0);
        break;

      case 'End':
        if (!isPlayMode) return;
        e.preventDefault();
        if (actions.goto && actions.getState) actions.goto(actions.getState().moves.length);
        break;

      case 'Escape': {
        // If a native <dialog open> exists, do nothing — let the browser handle it.
        const openDialog = document.querySelector('dialog[open]');
        if (openDialog) return;
        // No other overlay needs Esc handling here; no-op.
        break;
      }

      default:
        break;
    }
  });
}
