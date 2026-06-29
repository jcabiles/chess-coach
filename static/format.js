// format.js — shared display formatters. No DOM, no imports from app.js
// (so any module can import it without a cycle).

// formatEval — eval object → display string. evalCp is White-POV
// (positive = White advantage); mate → "M+N" / "M-N".
export function formatEval(a) {
  if (a == null) return '—';
  if (a.mate != null) {
    const sign = a.mate > 0 ? '+' : '-';
    return `M${sign}${Math.abs(a.mate)}`;
  }
  if (a.evalCp != null) {
    const pawns = a.evalCp / 100;
    return (pawns >= 0 ? '+' : '') + pawns.toFixed(2);
  }
  return '—';
}
