/**
 * Focus + Queue overview fragments for Pulse Board (specs/016).
 * Kept separate from statusBoardPanel.ts to limit god-file growth (TECH-DEBT-011).
 * Queue is a single unified list (severity → priority → roi); lane is a row badge only.
 */

export type ContinueTarget = {
  kind?: string;
  id?: string | null;
  focus_id?: string | null;
  blocker_id?: string | null;
  action?: string | null;
  why?: string | null;
  name?: string | null;
  multi?: boolean;
  sub_actions?: Array<{ key?: string; title?: string; kind?: string }>;
  severity?: string | null;
};

export type FocusSnap = {
  id?: string;
  name?: string | null;
  status?: string | null;
  percent?: number | null;
  valid?: boolean;
  type?: string;
} | null;

export type QueueItem = {
  id?: string | null;
  name?: string | null;
  lane?: string;
  action?: string | null;
  why?: string | null;
  priority?: number | null;
  severity?: string | null;
  status?: string | null;
  percent?: number | null;
};

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function renderFocusSection(
  focus: FocusSnap,
  cont: ContinueTarget | undefined
): string {
  const c = cont || {};
  const blocked = c.kind === "unblock";
  if (focus && focus.valid) {
    const subs =
      c.kind === "focus_step" && c.multi && (c.sub_actions || []).length >= 2
        ? `<ol class="focus-steps">${(c.sub_actions || [])
            .map(
              (s, j) =>
                `<li>${esc(String(s.title || ""))} ${
                  j === 0
                    ? `<button data-act="copyAction" data-id="${esc(String(focus.id))}" data-sub="${j}">Continue step</button>`
                    : ""
                }</li>`
            )
            .join("")}</ol>`
        : "";
    return `
    <section class="focus-hero">
      <h2>Focus</h2>
      <div class="card focus-card">
        <h3>${esc(String(focus.name || focus.id))}
          <span class="chip ${esc(String(focus.status || ""))}">${esc(String(focus.status || ""))}</span>
          ${blocked ? `<span class="chip blocked">blocked</span>` : ""}
        </h3>
        <div class="meta">${esc(String(focus.id))} · ${focus.percent ?? 0}%</div>
        ${
          blocked
            ? `<p class="why"><strong>Blocked by</strong> ${esc(String(c.blocker_id || c.id))} — ${esc(String(c.action || ""))}</p>`
            : `<p class="why"><strong>Continue:</strong> ${esc(String(c.action || ""))}</p>`
        }
        <p class="meta">${esc(String(c.why || ""))}</p>
        ${subs}
        <div class="row-actions">
          <button data-act="copyContinue">Continue</button>
          <button class="secondary" data-act="clearFocus">Park</button>
          <button class="secondary" data-act="openFeature" data-id="${esc(String(focus.id))}">Open</button>
          ${
            blocked
              ? `<button class="secondary" data-act="openFeature" data-id="${esc(String(c.id || ""))}">Open blocker</button>`
              : ""
          }
        </div>
      </div>
    </section>`;
  }
  const promoteId = c.kind === "promote_queue" ? c.id : null;
  return `
    <section class="focus-hero">
      <h2>Focus</h2>
      <div class="card focus-card empty-focus">
        <p class="why">No focus — pick Queue #1 or Promote a feature.</p>
        <p class="meta">${esc(String(c.why || ""))}</p>
        <div class="row-actions">
          ${
            promoteId
              ? `<button data-act="setFocus" data-id="${esc(String(promoteId))}">Promote ${esc(String(promoteId))}</button>
                 <button class="secondary" data-act="copyContinue">Copy queue #1 action</button>`
              : `<span class="empty">Queue empty</span>`
          }
        </div>
      </div>
    </section>`;
}

export function renderQueueSection(
  queue: QueueItem[],
  fixUrgent: number,
  blockerBanner: { id?: string; message?: string } | null | undefined
): string {
  const banner = blockerBanner
    ? `<p class="hint">⚠️ ${esc(String(blockerBanner.message || ""))} (${esc(String(blockerBanner.id || ""))})</p>`
    : "";
  const urgentHint =
    fixUrgent > 0
      ? `<p class="hint">${fixUrgent} high/blocker bug(s) in backlog — ranked into Queue by severity.</p>`
      : "";
  const rows =
    queue
      .map(
        (q, i) => `
    <tr>
      <td>#${i + 1}</td>
      <td><span class="chip lane-${esc(String(q.lane || ""))}">${esc(String(q.lane || ""))}</span></td>
      <td>${esc(String(q.name || q.id))}<div class="meta">${esc(String(q.id || ""))}${
          q.severity ? ` · ${esc(String(q.severity))}` : ""
        }${q.priority != null ? ` · P${esc(String(q.priority))}` : ""}</div></td>
      <td class="meta">${esc(String(q.action || "").slice(0, 80))}</td>
      <td class="actions">
        <button data-act="setFocus" data-id="${esc(String(q.id || ""))}">Focus</button>
        <button class="secondary" data-act="copyAction" data-id="${esc(String(q.id || ""))}">Action</button>
      </td>
    </tr>`
      )
      .join("") || `<tr><td colspan="5" class="empty">Empty queue</td></tr>`;
  return `
  <section class="queue-section">
    <h2>Queue</h2>
    <p class="hint">Unified · severity → priority → roi. Badge = source type.</p>
    ${banner}
    ${urgentHint}
    <table>
      <thead><tr><th>#</th><th>Type</th><th>Item</th><th>Action</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </section>`;
}
