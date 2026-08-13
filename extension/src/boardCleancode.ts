import type { CleancodeModule } from "./registry";
import { escapeAttr, escapeHtml } from "./boardHtmlUtils";

function ccBand(score?: number | null): { emoji: string; label: string; cls: string } {
  if (score === null || score === undefined) {
    return { emoji: "⚪", label: "unscanned", cls: "cc-none" };
  }
  if (score >= 85) return { emoji: "🟢", label: "clean", cls: "cc-clean" };
  if (score >= 60) return { emoji: "🟡", label: "warn", cls: "cc-warn" };
  return { emoji: "🔴", label: "dirty", cls: "cc-dirty" };
}

function sortModules(mods: CleancodeModule[]): CleancodeModule[] {
  return [...mods].sort((a, b) => {
    const staleA = a.stale ? 0 : 1;
    const staleB = b.stale ? 0 : 1;
    if (staleA !== staleB) return staleA - staleB;
    const structA = typeof a.structure_score === "number" ? a.structure_score : 999;
    const structB = typeof b.structure_score === "number" ? b.structure_score : 999;
    if (structA !== structB) return structA - structB;
    const openA = a.open_findings || 0;
    const openB = b.open_findings || 0;
    if (openA !== openB) return openB - openA;
    return String(a.id || "").localeCompare(String(b.id || ""));
  });
}

export function renderCleancodeSection(cleancode: CleancodeModule[]): string {
  if (!cleancode.length) return "";
  const scored = cleancode.filter((m) => typeof m.score === "number");
  const avg = scored.length
    ? Math.round((scored.reduce((s, m) => s + (m.score as number), 0) / scored.length) * 10) / 10
    : null;
  const structScores = cleancode
    .map((m) => m.structure_score)
    .filter((s): s is number => typeof s === "number");
  const structAvg = structScores.length
    ? Math.round((structScores.reduce((s, n) => s + n, 0) / structScores.length) * 10) / 10
    : null;
  const openTotal = cleancode.reduce((s, m) => s + (m.open_findings || 0), 0);
  const staleCount = cleancode.filter((m) => m.stale).length;
  const rows = sortModules(cleancode)
    .map((m) => {
      const b = ccBand(m.score);
      const scoreCell =
        typeof m.score === "number" ? `${b.emoji} ${m.score}` : `${b.emoji} —`;
      const sb = ccBand(m.structure_score);
      const structCell =
        typeof m.structure_score === "number"
          ? `${sb.emoji} ${m.structure_score}`
          : "—";
      const open = m.open_findings || 0;
      const totalFnd = m.total_findings ?? (m.findings || []).length;
      const findingsCell =
        open > 0
          ? `<span class="chip cc-warn" title="${open} open findings">${open}/${totalFnd} ⚠️</span>`
          : `${open}/${totalFnd}`;
      const scannedCell = m.stale
        ? `<span class="chip cc-warn" title="Code changed since last scan">⚠️ needs rescan</span>`
        : escapeHtml(String(m.scanned_at || "never"));
      return `
    <tr class="feature-row">
      <td><span class="chip ${sb.cls}" title="Structure (deterministic): over-LOC files + open findings">${structCell}</span></td>
      <td><span class="chip ${b.cls}" title="${escapeAttr(b.label)} (AI /100)">${scoreCell}</span></td>
      <td>${escapeHtml(m.name || m.id)}<div class="meta">${escapeHtml(m.id)} · ${escapeHtml(m.area || "")}</div></td>
      <td>${findingsCell}</td>
      <td>${scannedCell}</td>
      <td class="actions">
        <button data-act="copyCleancodeScan" data-id="${escapeAttr(m.id)}" title="Copy scan prompt">Scan</button>
        <button class="secondary" data-act="copyCleancodeFix" data-id="${escapeAttr(m.id)}" title="Copy fix prompt">Fix</button>
      </td>
    </tr>`;
    })
    .join("");
  return `
  <section>
    <h2>Clean Code — struct avg ${structAvg ?? "—"}/100 · ${openTotal} open findings · AI ${scored.length}/${cleancode.length}${avg !== null ? ` (avg ${avg})` : ""}${staleCount ? ` · ${staleCount} need rescan ⚠️` : ""}</h2>
    <p class="hint">Struct &amp; Findings auto-update each generate (deterministic, like the backlog): over-LOC files + open tech-debt cards. AI /100 needs a manual rescan. Scan = survey; Fix = clean.</p>
    <table>
      <thead>
        <tr><th>Struct</th><th>AI</th><th>Module</th><th>Findings</th><th>Scanned</th><th>Actions</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  </section>`;
}
