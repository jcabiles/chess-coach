// feedback.js — Move feedback / toast UI module.
// Receives all dependencies via the injected `api` argument (no imports from app.js).
// Exports: initFeedback(api)

const TOAST_DURATION_MS = 3000;   // auto-dismiss after 3 s
const TOAST_MAX = 3;               // at most 3 toasts stacked at once

export function initFeedback(api) {
  // -------------------------------------------------------------------------
  // Toasts
  // -------------------------------------------------------------------------
  const toastMount = api && api.mounts && api.mounts.toasts;

  // Show a toast for a given message + optional kind ('info'|'success'|'error').
  // Replaces the oldest toast when the stack is at capacity.
  function showToast(message, kind) {
    if (!toastMount) return;

    // Enforce max stack size: remove the oldest when at capacity.
    const existing = toastMount.querySelectorAll('.toast');
    if (existing.length >= TOAST_MAX) {
      dismissToast(existing[0]);
    }

    const toast = document.createElement('div');
    toast.className = 'toast';
    if (kind === 'success' || kind === 'error') {
      toast.classList.add(`toast--${kind}`);
    }
    // Default to 'info' accent when kind is absent or 'info'.

    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'polite');
    toast.setAttribute('aria-atomic', 'true');

    const msg = document.createElement('span');
    msg.className = 'toast__msg';
    msg.textContent = message;

    const closeBtn = document.createElement('button');
    closeBtn.className = 'toast__close';
    closeBtn.setAttribute('aria-label', 'Dismiss');
    closeBtn.textContent = '×'; // ×

    toast.append(msg, closeBtn);
    toastMount.appendChild(toast);

    // Trigger slide-in on next paint (so the CSS transition fires).
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        toast.classList.add('toast--visible');
      });
    });

    // Auto-dismiss.
    const timer = setTimeout(() => dismissToast(toast), TOAST_DURATION_MS);
    toast._dismissTimer = timer;

    // Click anywhere on the toast (including the close button) to dismiss.
    toast.addEventListener('click', () => {
      clearTimeout(toast._dismissTimer);
      dismissToast(toast);
    });
  }

  // Slide the toast out, then remove it from the DOM.
  function dismissToast(toast) {
    if (!toast || !toast.isConnected) return;
    toast.classList.remove('toast--visible');
    // Wait for the CSS transition to finish before removing.
    // transitionend may not fire under reduced-motion (transition-duration ≈ 0),
    // so we also set a short fallback timeout.
    const cleanup = () => toast.remove();
    toast.addEventListener('transitionend', cleanup, { once: true });
    setTimeout(cleanup, 350); // fallback
  }

  if (api && api.on) {
    api.on('toast:show', (message, kind) => {
      showToast(message, kind);
    });
  }

  // -------------------------------------------------------------------------
  // Analysis loading indicator
  // -------------------------------------------------------------------------
  const statusMount = api && api.mounts && api.mounts.analysisStatus;

  function showAnalyzing() {
    if (!statusMount) return;
    statusMount.innerHTML =
      '<span class="analysis-spinner" aria-hidden="true"></span>' +
      '<span class="analysis-spinner__label">Analyzing…</span>';
    statusMount.classList.add('analysis-status--active');
    statusMount.setAttribute('aria-busy', 'true');
  }

  function clearAnalyzing() {
    if (!statusMount) return;
    statusMount.innerHTML = '';
    statusMount.classList.remove('analysis-status--active');
    statusMount.removeAttribute('aria-busy');
  }

  if (api && api.on) {
    api.on('analysis:start', showAnalyzing);
    api.on('analysis:end', clearAnalyzing);
  }
}
