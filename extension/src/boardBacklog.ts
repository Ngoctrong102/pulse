import type { Feature } from "./registry";
import { escapeAttr, escapeHtml } from "./boardHtmlUtils";

function sevBand(sev?: string): { emoji: string; cls: string } {
  switch ((sev || "").toLowerCase()) {
    case "blocker":
      return { emoji: "🛑", cls: "cc-dirty" };
    case "high":
      return { emoji: "🔴", cls: "cc-dirty" };
    case "medium":
      return { emoji: "🟡", cls: "cc-warn" };
    case "low":
      return { emoji: "🟢", cls: "cc-clean" };
    default:
      return { emoji: "⚪", cls: "cc-none" };
  }
}

const BACKLOG_DONE_STATUSES = new Set(["done", "cancelled", "wontfix"]);

function isBacklogDone(status?: string): boolean {
  return BACKLOG_DONE_STATUSES.has((status || "").trim().toLowerCase());
}

// Backlog cards use issue-tracker words; mirror tools/pulse_lib BACKLOG_STATUS_LABEL.
function backlogStatusChip(status?: string): { label: string; cls: string } {
  const s = (status || "").trim().toLowerCase();
  switch (s) {
    case "done":
      return { label: "done", cls: "done" };
    case "cancelled":
      return { label: "cancelled", cls: "todo" };
    case "wontfix":
      return { label: "wontfix", cls: "todo" };
    case "partial":
      return { label: "in-progress", cls: "partial" };
    case "blocked":
      return { label: "blocked", cls: "blocked" };
    case "todo":
      return { label: "deferred", cls: "todo" };
    case "":
      return { label: "—", cls: "todo" };
    default:
      return { label: s, cls: "todo" };
  }
}

export function renderBacklogSection(backlog: Feature[]): string {
  if (!backlog.length) return "";
  const bugs = backlog.filter((b) => b.type === "bug").length;
  const debt = backlog.filter((b) => b.type === "tech-debt").length;
  const doneCount = backlog.filter((b) => isBacklogDone(b.status)).length;
  const openCount = backlog.length - doneCount;
  const sorted = [...backlog].sort(
    (a, b) =>
      (a.priority ?? 99) - (b.priority ?? 99) ||
      (b.roi ?? 0) - (a.roi ?? 0) ||
      (a.id > b.id ? 1 : -1)
  );
  const rows = sorted
    .map((b) => {
      const s = sevBand(b.severity);
      const st = backlogStatusChip(b.status);
      const where = b.where ? `<div class="meta">${escapeHtml(b.where)}</div>` : "";
      const done = isBacklogDone(b.status) ? "1" : "0";
      return `
    <tr class="feature-row" data-done="${done}">
      <td><span class="chip ${s.cls}" title="${escapeAttr(b.severity || "—")}">${s.emoji} ${escapeHtml(b.severity || "—")}</span></td>
      <td><span class="chip ${st.cls}" title="${escapeAttr(b.status || "—")}">${escapeHtml(st.label)}</span></td>
      <td>${escapeHtml(b.name || b.id)}<div class="meta">${escapeHtml(b.id)} · ${escapeHtml(b.type || "")}</div>${where}</td>
      <td>P${b.priority ?? "—"}</td>
      <td>${b.roi ?? "—"}</td>
      <td class="actions">
        <button data-act="copyAction" data-id="${escapeAttr(b.id)}">Next action</button>
        <button class="secondary" data-act="explainFeature" data-id="${escapeAttr(b.id)}">Explain</button>
        <button class="secondary" data-act="openFeature" data-id="${escapeAttr(b.id)}">Open</button>
      </td>
    </tr>`;
    })
    .join("");
  const doneToggle = doneCount
    ? `<label class="backlog-toggle" title="Show/hide done cards">
        <input type="checkbox" id="backlog-show-done" /> Show ${doneCount} done
      </label>`
    : "";
  return `
  <section id="backlog" class="backlog-hide-done">
    <h2>Backlog — ${openCount} open${doneCount ? ` · ${doneCount} done` : ""} / ${backlog.length} (${debt} tech-debt · ${bugs} bug)</h2>
    <p class="hint">Bug + tech-debt cards. Sorted by priority (lower P = higher urgency). Open = where/why/proposed_fix.</p>
    ${doneToggle}
    <table>
      <thead>
        <tr><th>Severity</th><th>Status</th><th>Name</th><th>Pri</th><th>ROI</th><th>Actions</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  </section>`;
}

