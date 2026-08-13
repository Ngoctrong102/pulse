import type { Feature } from "./registry";
import type { NextPayload } from "./cli";
import type { TagNudgeMap } from "./boardTypes";
import { escapeAttr, escapeHtml, listOrEmpty, tagNudgeTitle } from "./boardHtmlUtils";

export function renderDetail(
  feat: Feature,
  nextPayload: NextPayload,
  tagNudges: TagNudgeMap
): string {
  const ranked =
    (nextPayload.queue || []).find((n) => n.id === feat.id) ||
    (nextPayload.continue?.id === feat.id ? nextPayload.continue : undefined);
  const findingsNote = ranked?.finding_count || 0;
  const multi = Boolean(ranked?.multi && (ranked.sub_actions || []).length >= 2);
  const docs = feat.docs
    ? Object.entries(feat.docs)
        .map(([k, v]) => `${k}: ${(v || []).join(", ")}`)
        .join(" · ")
    : "";
  const subTable = multi
    ? `<div class="card" style="margin-top:12px">
    <h2 style="margin-top:0">Next actions (${(ranked!.sub_actions || []).length} chunks)</h2>
    <p class="meta">Large feature — each button copies a prompt for one chunk only.</p>
    <table class="sub-table">
      <thead><tr><th>#</th><th>Chunk</th><th></th></tr></thead>
      <tbody>
        ${(ranked!.sub_actions || [])
          .map(
            (s, j) => `<tr>
          <td>${j + 1}</td>
          <td>${escapeHtml(String(s.title || ""))}</td>
          <td><button data-act="copyAction" data-id="${escapeAttr(feat.id)}" data-sub="${j}">Next action</button></td>
        </tr>`
          )
          .join("")}
      </tbody>
    </table>
  </div>`
    : "";
  return `
  <div class="back"><button class="secondary" data-act="openOverview">← Overview</button></div>
  <div class="toolbar" style="border:none;padding:0;margin-bottom:8px">
    <div>
      <div class="meta">${escapeHtml(feat.id)}</div>
      <h1>${escapeHtml(feat.name)}</h1>
      <div>
        <span class="chip ${escapeHtml(feat.status)}">${escapeHtml(feat.status)}</span>
        ${feat.mvp ? `<span class="chip">MVP</span>` : ""}
        ${multi ? `<span class="chip">multi</span>` : ""}
        <span class="meta">P${feat.priority} · ROI ${feat.roi} · phase ${feat.phase ?? "—"}</span>
      </div>
      <div class="bar"><i style="width:${Math.min(100, Math.max(0, feat.percent))}%"></i></div>
      <div class="meta">${feat.percent}% · ${escapeHtml(docs || "no docs map")}</div>
    </div>
  </div>
  <div class="card">
    <h2 style="margin-top:0">Primary actions</h2>
    <div class="row-actions">
      <button data-act="explainFeature" data-id="${escapeAttr(feat.id)}">Explain this status</button>
      ${
        multi
          ? ""
          : `<button data-act="copyAction" data-id="${escapeAttr(feat.id)}">Copy next-action prompt</button>`
      }
      <button class="secondary" data-act="copyTag" data-id="${escapeAttr(feat.id)}" title="${escapeAttr(tagNudgeTitle(tagNudges[feat.id]))}">Tag (TAG:)</button>
      <button class="secondary" data-act="complete" data-id="${escapeAttr(feat.id)}">Mark complete…</button>
      <button class="secondary" data-act="openRegistry">Open in YAML</button>
    </div>
  </div>
  ${multi ? subTable : ""}
  <div class="panes">
    <div class="card">
      <h2>Remaining</h2>
      ${listOrEmpty(feat.remaining)}
      <h2 style="margin-top:14px">Mocks</h2>
      ${listOrEmpty(feat.mocks)}
    </div>
    <div class="card">
      <h2>Done</h2>
      ${listOrEmpty(feat.done)}
      <h2 style="margin-top:14px">Specs</h2>
      ${listOrEmpty(feat.specs)}
      <p class="meta" style="margin-top:12px">Detect findings linked in next ranking: ${findingsNote}</p>
    </div>
  </div>`;
}

