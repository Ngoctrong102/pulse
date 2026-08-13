import type { CleancodeModule, Feature } from "./registry";
import type { NextPayload } from "./cli";
import type { FilterChip, SortKey, TagNudgeMap } from "./boardTypes";
import { PROJECT_UNTAGGED_NUDGE_ID } from "./boardTypes";
import { renderFocusSection, renderQueueSection } from "./overviewFocus";
import { renderBacklogSection } from "./boardBacklog";
import { renderCleancodeSection } from "./boardCleancode";
import { escapeAttr, escapeHtml, untaggedCleanupTitle } from "./boardHtmlUtils";

export function renderOverview(
  features: Feature[],
  nextPayload: NextPayload,
  filters: FilterChip[],
  sortKey: SortKey,
  searchQuery: string,
  tagNudges: TagNudgeMap,
  cleancode: CleancodeModule[],
  backlog: Feature[],
  inventoryOpen = false
): string {
  const h = nextPayload.health;
  const det = h.detect || {};
  const drift = h.drift || {};
  const openWork = h.open_work || {};
  const detectLine = det.exists
    ? `detect: ${det.critical ?? 0} critical · ${det.warning ?? 0} warning`
    : `detect: no report — run Detect`;
  const driftLine = drift.exists
    ? `drift: ${drift.critical ?? 0}c / ${drift.warning ?? 0}w · unmapped ${drift.docs_ids_not_on_board ?? "—"} · spec debt ${drift.spec_debt_items ?? "—"} · tag gaps ${drift.tag_gaps ?? "—"} · orphan ${drift.orphan_code_tags ?? "—"} · evidence untagged ${drift.evidence_untagged_paths ?? "—"}`
    : `drift: no report — run Docs/spec drift`;
  const openLine = `open work: ${openWork.remaining_bullets ?? 0} remaining · ${openWork.mocks ?? 0} mocks`;
  const focusHtml = renderFocusSection(
    nextPayload.focus ?? null,
    nextPayload.continue
  );
  const queueHtml = renderQueueSection(
    nextPayload.queue || [],
    nextPayload.fix_urgent_count || 0,
    nextPayload.blocker_banner
  );

  const rows = features
    .map((f) => {
      const searchBlob = `${f.id} ${f.name} ${f.status} ${(f.remaining || []).join(" ")} ${(f.mocks || []).join(" ")}`;
      return `
    <tr class="feature-row" data-id="${escapeAttr(f.id)}" data-search="${escapeAttr(searchBlob)}">
      <td><span class="chip ${escapeHtml(f.status)}">${escapeHtml(f.status)}</span></td>
      <td class="name-cell" title="Open detail">${escapeHtml(f.name)}<div class="meta">${escapeHtml(f.id)}</div></td>
      <td>${f.percent}%</td>
      <td>P${f.priority}</td>
      <td>ROI ${f.roi}</td>
      <td>${(f.remaining || []).length} remaining · ${(f.mocks || []).length} mocks</td>
      <td class="actions">
        <button data-act="setFocus" data-id="${escapeAttr(f.id)}">Focus</button>
        <button class="secondary" data-act="openFeature" data-id="${escapeAttr(f.id)}">Open</button>
        <button class="secondary" data-act="explainFeature" data-id="${escapeAttr(f.id)}">Explain</button>
      </td>
    </tr>`;
    })
    .join("");

  const filterBtns: FilterChip[] = ["mvp", "partial", "todo", "done", "blocked"];
  const sortOptions = (["priority", "roi", "percent", "phase", "name"] as const)
    .map(
      (s) =>
        `<option value="${s}" ${sortKey === s ? "selected" : ""}>${s}</option>`
    )
    .join("");
  const invHidden = inventoryOpen ? "" : " hidden";
  return `
  <div class="toolbar">
    <h1>Pulse</h1>
    <div class="spacer"></div>
    ${filterBtns
      .map(
        (f) =>
          `<button class="${filters.includes(f) ? "" : "secondary"}" data-act="filter" data-filter="${f}" title="Toggle (OR)">${f}</button>`
      )
      .join("")}
    <button class="secondary" data-act="clearFilters" title="Clear filters">all</button>
    <button class="secondary" data-act="refresh">Refresh</button>
    <button class="secondary" data-act="runDetect">Detect</button>
    <button class="secondary" data-act="runDrift" title="Docs/spec ↔ board leftover work">Drift</button>
  </div>
  ${focusHtml}
  <div class="grid">
    <div>${queueHtml}</div>
    <section>
      <h2>Health</h2>
      <div class="card">
        <div class="meta">updated ${escapeHtml(String(h.updated || "—"))}</div>
        <p>done ${(h.counts && h.counts.done) || 0} · partial ${(h.counts && h.counts.partial) || 0}
           · todo ${(h.counts && h.counts.todo) || 0} · blocked ${(h.counts && h.counts.blocked) || 0}</p>
        <p class="meta">${escapeHtml(openLine)}</p>
        <p class="meta">${escapeHtml(detectLine)}</p>
        <p class="meta">${escapeHtml(driftLine)}</p>
        <div class="row-actions">
          <button data-act="explainProject">Explain project status</button>
          <button class="secondary" data-act="copyDocsDrift" title="Copy prompt to sync board after docs/spec changes">Docs/spec drift</button>
          <button class="secondary" data-act="copyUntaggedCleanup" title="${escapeAttr(untaggedCleanupTitle(tagNudges[PROJECT_UNTAGGED_NUDGE_ID]))}">Review untagged code</button>
          <button class="secondary" data-act="openRegistry">Open status folder</button>
        </div>
      </div>
    </section>
  </div>
  <section>
    <h2>Inventory
      <button class="secondary" data-act="toggleInventory">${inventoryOpen ? "Hide" : "Show"} features / backlog / clean-code</button>
    </h2>
    <div class="inventory"${invHidden}>
    <h3 class="hint">All features</h3>
    <div class="table-tools">
      <input id="feature-search" type="search" placeholder="Search name, id, remaining…" autocomplete="off" value="${escapeAttr(searchQuery)}"/>
      <label class="meta">Sort
        <select id="table-sort">${sortOptions}</select>
      </label>
      <span class="hint" id="feature-count">${features.length} shown</span>
    </div>
    <table>
      <thead>
        <tr>
          <th>Status</th>
          <th class="sortable" data-sort="name" data-active="${sortKey === "name" ? "1" : "0"}">Name</th>
          <th class="sortable" data-sort="percent" data-active="${sortKey === "percent" ? "1" : "0"}">%</th>
          <th class="sortable" data-sort="priority" data-active="${sortKey === "priority" ? "1" : "0"}">Pri</th>
          <th class="sortable" data-sort="roi" data-active="${sortKey === "roi" ? "1" : "0"}">ROI</th>
          <th title="remaining = open work bullets; mocks = still faked/stubbed">Open</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  ${renderBacklogSection(backlog)}
  ${renderCleancodeSection(cleancode)}
    </div>
  </section>`;
}

