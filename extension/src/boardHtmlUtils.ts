/** Shared HTML helpers for the status board webview. */

export function listOrEmpty(items?: string[]): string {
  if (!items || !items.length) return `<p class="empty">(none)</p>`;
  return `<ul>${items.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>`;
}

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function escapeAttr(s: string): string {
  return escapeHtml(s).replace(/'/g, "&#39;");
}

function formatTagNudge(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export { formatTagNudge };

export function tagNudgeTitle(iso?: string): string {
  if (!iso) {
    return "Copy Tag prompt (TAG: retag) — never nudged";
  }
  return `Copy Tag prompt (TAG: retag) — last nudge: ${formatTagNudge(iso)}`;
}

export function untaggedCleanupTitle(iso?: string): string {
  if (!iso) {
    return "Copy whole-project untagged / dirty TAG: cleanup prompt — never nudged";
  }
  return `Copy whole-project untagged cleanup prompt — last nudge: ${formatTagNudge(iso)}`;
}

export function getNonce(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let n = "";
  for (let i = 0; i < 32; i++) n += chars.charAt(Math.floor(Math.random() * chars.length));
  return n;
}
