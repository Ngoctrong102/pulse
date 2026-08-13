import * as vscode from "vscode";
import * as fs from "fs";
import {
  fetchExplainPrompt,
  fetchNextJson,
  fetchNextPrompt,
  fetchTagPrompt,
  fetchUntaggedCleanupPrompt,
  fetchDocsDriftPrompt,
  fetchCleancodeJson,
  fetchCleancodeScanPrompt,
  fetchCleancodeFixPrompt,
  runDetectInTerminal,
  runDriftInTerminal,
  runGenerateInTerminal,
  runSetFocus,
  runClearFocus,
  type NextPayload,
} from "./cli";
import {
  getFeature,
  loadCleancode,
  loadRegistry,
  patchFeatureComplete,
  registryPath,
  type CleancodeModule,
  type Feature,
  type Registry,
} from "./registry";
import { renderFocusSection, renderQueueSection } from "./overviewFocus";

type SortKey = "priority" | "roi" | "percent" | "phase" | "name";
/** Multi-select chips; empty = show all. Matching is OR across selected chips. */
type FilterChip = "mvp" | "partial" | "todo" | "done" | "blocked";

const TAG_NUDGE_KEY = "pulseStatus.tagNudges";
/** workspaceState key inside TagNudgeMap for whole-project untagged cleanup */
const PROJECT_UNTAGGED_NUDGE_ID = "__project_untagged__";

type TagNudgeMap = Record<string, string>; // featureId | __project_untagged__ -> ISO timestamp

export class StatusBoardPanel {
  public static current: StatusBoardPanel | undefined;
  private readonly panel: vscode.WebviewPanel;
  private filters: FilterChip[] = [];
  private sortKey: SortKey = "priority";
  private searchQuery = "";
  private focusId: string | undefined;
  private inventoryOpen = false;
  private disposables: vscode.Disposable[] = [];
  private lastRegistryMtimeMs = 0;
  private tagNudges: TagNudgeMap = {};
  private lastContinue: NextPayload["continue"] | undefined;

  private constructor(
    panel: vscode.WebviewPanel,
    private readonly folder: string,
    private readonly extensionUri: vscode.Uri,
    private readonly extensionContext: vscode.ExtensionContext,
    focusId?: string
  ) {
    this.panel = panel;
    this.focusId = focusId;
    this.tagNudges = loadTagNudges(extensionContext);
    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
    this.panel.onDidChangeViewState(
      (e) => {
        if (e.webviewPanel.visible) {
          void this.refreshIfRegistryChanged();
        }
      },
      null,
      this.disposables
    );
    this.panel.webview.onDidReceiveMessage(
      (msg) => this.onMessage(msg),
      null,
      this.disposables
    );
    const poll = setInterval(() => {
      if (this.panel.visible) {
        void this.refreshIfRegistryChanged();
      }
    }, 2500);
    this.disposables.push({ dispose: () => clearInterval(poll) });
    void this.refresh();
  }

  async refreshIfRegistryChanged(): Promise<void> {
    try {
      const m = fs.statSync(registryPath(this.folder)).mtimeMs;
      if (m === this.lastRegistryMtimeMs) {
        return;
      }
    } catch {
      return;
    }
    await this.refresh();
  }

  static createOrShow(
    context: vscode.ExtensionContext,
    folder: string,
    focusId?: string
  ): StatusBoardPanel {
    const column = vscode.ViewColumn.One;
    if (StatusBoardPanel.current) {
      StatusBoardPanel.current.panel.reveal(column);
      if (focusId !== undefined) {
        StatusBoardPanel.current.focusId = focusId;
        void StatusBoardPanel.current.refresh();
      } else {
        void StatusBoardPanel.current.refreshIfRegistryChanged();
      }
      return StatusBoardPanel.current;
    }
    const panel = vscode.window.createWebviewPanel(
      "pulseStatus.board",
      "Pulse",
      column,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [context.extensionUri],
      }
    );
    StatusBoardPanel.current = new StatusBoardPanel(
      panel,
      folder,
      context.extensionUri,
      context,
      focusId
    );
    return StatusBoardPanel.current;
  }

  async refresh(): Promise<void> {
    try {
      try {
        this.lastRegistryMtimeMs = fs.statSync(registryPath(this.folder)).mtimeMs;
      } catch {
        /* ignore */
      }
      const registry = loadRegistry(this.folder);
      let nextPayload: NextPayload;
      try {
        nextPayload = await fetchNextJson(this.folder, 7);
      } catch {
        nextPayload = {
          health: {
            updated: registry.updated,
            counts: countStatuses(registry),
            detect: { exists: false, critical: 0, warning: 0, info: 0 },
          },
          next: [],
          focus: null,
          continue: undefined,
          lane: "all",
          queue: [],
        };
      }
      this.lastContinue = nextPayload.continue;
      const features = filterSort(registry.features, this.filters, this.sortKey);
      let cleancode: CleancodeModule[] = [];
      try {
        // Prefer the CLI: it computes the deterministic `stale` flag (git diff
        // of each scanned module's globs since last_scan_commit).
        const payload = await fetchCleancodeJson(this.folder);
        cleancode = payload.modules as CleancodeModule[];
      } catch {
        try {
          cleancode = loadCleancode(this.folder);
        } catch {
          cleancode = [];
        }
      }
      this.panel.webview.html = this.html(
        registry,
        features,
        nextPayload,
        cleancode,
        this.focusId,
        this.inventoryOpen
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      this.panel.webview.html = `<html><body style="padding:16px;font-family:var(--vscode-font-family)">
        <p>Failed to load status board.</p><pre>${escapeHtml(msg)}</pre></body></html>`;
    }
  }

  private async onMessage(msg: {
    type: string;
    id?: string;
    filter?: string;
    sort?: string;
    search?: string;
    sub?: number | string;
    lane?: string;
  }): Promise<void> {
    switch (msg.type) {
      case "ready":
        break;
      case "openOverview":
        this.focusId = undefined;
        await this.refresh();
        break;
      case "openFeature":
        this.focusId = msg.id;
        await this.refresh();
        break;
      case "setFilter":
        this.filters = toggleFilter(this.filters, msg.filter);
        await this.refresh();
        break;
      case "clearFilters":
        this.filters = [];
        await this.refresh();
        break;
      case "setSort":
        this.sortKey = (msg.sort as SortKey) || "priority";
        await this.refresh();
        break;
      case "setSearch":
        // Persist only — do not rebuild (would steal focus / clear caret)
        this.searchQuery = msg.search ?? "";
        break;
      case "toggleInventory":
        this.inventoryOpen = !this.inventoryOpen;
        await this.refresh();
        break;
      case "setFocus": {
        if (!msg.id) return;
        try {
          await runSetFocus(this.folder, msg.id);
          vscode.window.showInformationMessage(`Focus → ${msg.id}`);
        } catch (e) {
          vscode.window.showErrorMessage(String(e));
        }
        await this.refresh();
        break;
      }
      case "clearFocus": {
        try {
          await runClearFocus(this.folder);
          vscode.window.showInformationMessage("Focus parked");
        } catch (e) {
          vscode.window.showErrorMessage(String(e));
        }
        await this.refresh();
        break;
      }
      case "copyContinue": {
        try {
          const cont = this.lastContinue;
          const id =
            cont?.kind === "focus_step" || cont?.kind === "unblock"
              ? cont.id || undefined
              : undefined;
          const text = await fetchNextPrompt(this.folder, id || undefined);
          await vscode.env.clipboard.writeText(text);
          vscode.window.showInformationMessage(
            `Continue prompt copied (${cont?.kind || "next"}${id ? `: ${id}` : ""})`
          );
        } catch (e) {
          vscode.window.showErrorMessage(String(e));
        }
        break;
      }
      case "refresh":
        await this.refresh();
        break;
      case "runDetect":
        runDetectInTerminal(this.folder);
        vscode.window.showInformationMessage(
          "Detect running in terminal. Refresh board when it finishes."
        );
        break;
      case "openRegistry":
        await vscode.window.showTextDocument(
          vscode.Uri.file(registryPath(this.folder))
        );
        break;
      case "explainProject": {
        const text = await fetchExplainPrompt(this.folder);
        await vscode.env.clipboard.writeText(text);
        vscode.window.showInformationMessage("Explain prompt copied — paste into chat.");
        break;
      }
      case "explainFeature": {
        if (!msg.id) return;
        const text = await fetchExplainPrompt(this.folder, msg.id);
        await vscode.env.clipboard.writeText(text);
        vscode.window.showInformationMessage(`Explain prompt for ${msg.id} copied.`);
        break;
      }
      case "copyAction": {
        const subRaw = msg.sub;
        const sub =
          subRaw === undefined || subRaw === "" || subRaw === null
            ? undefined
            : Number(subRaw);
        const text = await fetchNextPrompt(
          this.folder,
          msg.id,
          sub !== undefined && !Number.isNaN(sub) ? sub : undefined
        );
        await vscode.env.clipboard.writeText(text);
        const label =
          sub !== undefined && !Number.isNaN(sub)
            ? `Next-action prompt (sub #${sub + 1}) copied — paste into chat.`
            : "Next-action prompt copied — paste into chat.";
        vscode.window.showInformationMessage(label);
        break;
      }
      case "copyTag": {
        if (!msg.id) return;
        const text = await fetchTagPrompt(this.folder, msg.id);
        await vscode.env.clipboard.writeText(text);
        const iso = new Date().toISOString();
        this.tagNudges[msg.id] = iso;
        await saveTagNudges(this.extensionContext, this.tagNudges);
        await this.refresh();
        vscode.window.showInformationMessage(
          `Tag prompt for ${msg.id} copied — paste into chat. (nudged ${formatTagNudge(iso)})`
        );
        break;
      }
      case "copyUntaggedCleanup": {
        const text = await fetchUntaggedCleanupPrompt(this.folder);
        await vscode.env.clipboard.writeText(text);
        const iso = new Date().toISOString();
        this.tagNudges[PROJECT_UNTAGGED_NUDGE_ID] = iso;
        await saveTagNudges(this.extensionContext, this.tagNudges);
        await this.refresh();
        vscode.window.showInformationMessage(
          `Untagged-cleanup prompt copied — paste into chat. (nudged ${formatTagNudge(iso)})`
        );
        break;
      }
      case "copyDocsDrift": {
        const text = await fetchDocsDriftPrompt(this.folder);
        await vscode.env.clipboard.writeText(text);
        vscode.window.showInformationMessage(
          "Docs/spec drift prompt copied — paste into chat to sync board after doc changes."
        );
        break;
      }
      case "copyCleancodeScan": {
        if (!msg.id) return;
        const text = await fetchCleancodeScanPrompt(this.folder, msg.id);
        await vscode.env.clipboard.writeText(text);
        vscode.window.showInformationMessage(
          `Clean-code SCAN prompt for ${msg.id} copied — paste into chat.`
        );
        break;
      }
      case "copyCleancodeFix": {
        if (!msg.id) return;
        const text = await fetchCleancodeFixPrompt(this.folder, msg.id);
        await vscode.env.clipboard.writeText(text);
        vscode.window.showInformationMessage(
          `Clean-code FIX prompt for ${msg.id} copied — paste into chat.`
        );
        break;
      }
      case "runDrift": {
        runDriftInTerminal(this.folder);
        vscode.window.showInformationMessage(
          "Drift running in terminal (writes DRIFT.md). Refresh board when it finishes."
        );
        break;
      }
      case "complete": {
        if (!msg.id) return;
        const data = loadRegistry(this.folder);
        const feat = getFeature(data, msg.id);
        if (!feat) return;
        if ((feat.mocks || []).length) {
          vscode.window.showErrorMessage(
            `Cannot mark ${feat.id} done while mocks remain:\n• ${feat.mocks!.join("\n• ")}\nClose or remove mocks first (status stays partial).`
          );
          return;
        }
        const warns: string[] = [];
        if ((feat.remaining || []).length) {
          warns.push(`${feat.remaining!.length} remaining item(s) will move to done`);
        }
        const ok = await vscode.window.showWarningMessage(
          `Mark ${feat.id} complete (done / 100%)?${warns.length ? "\n" + warns.join("\n") : ""}`,
          { modal: true },
          "Complete"
        );
        if (ok !== "Complete") return;
        patchFeatureComplete(this.folder, msg.id);
        runGenerateInTerminal(this.folder);
        this.focusId = msg.id;
        await this.refresh();
        vscode.window.showInformationMessage(`Marked ${msg.id} done; generate running.`);
        break;
      }
      default:
        break;
    }
  }

  private html(
    registry: Registry,
    features: Feature[],
    nextPayload: NextPayload,
    cleancode: CleancodeModule[],
    focusId?: string,
    inventoryOpen = false
  ): string {
    const nonce = getNonce();
    const csp = [
      "default-src 'none'",
      `style-src 'nonce-${nonce}'`,
      `script-src 'nonce-${nonce}'`,
    ].join("; ");
    const detail = focusId ? getFeature(registry, focusId) : undefined;
    const body = detail
      ? renderDetail(detail, nextPayload, this.tagNudges)
      : renderOverview(
          features,
          nextPayload,
          this.filters,
          this.sortKey,
          this.searchQuery,
          this.tagNudges,
          cleancode,
          registry.backlog ?? [],
          inventoryOpen
        );
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta http-equiv="Content-Security-Policy" content="${csp}"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Pulse</title>
<style nonce="${nonce}">
  :root {
    --bg: var(--vscode-editor-background);
    --fg: var(--vscode-foreground);
    --muted: var(--vscode-descriptionForeground);
    --border: var(--vscode-widget-border, #444);
    --btn: var(--vscode-button-background);
    --btnFg: var(--vscode-button-foreground);
    --btn2: var(--vscode-button-secondaryBackground);
    --btn2Fg: var(--vscode-button-secondaryForeground);
    --input: var(--vscode-input-background);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 16px 20px 32px;
    font-family: var(--vscode-font-family);
    font-size: var(--vscode-font-size);
    color: var(--fg); background: var(--bg);
  }
  h1 { font-size: 1.25rem; font-weight: 600; margin: 0 0 4px; }
  h2 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.04em;
       color: var(--muted); font-weight: 600; margin: 0 0 10px; }
  .toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
             margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border); }
  .toolbar .spacer { flex: 1; }
  .hint { color: var(--muted); font-size: 0.8rem; }
  button, select {
    font: inherit; cursor: pointer; border: 1px solid transparent; border-radius: 4px;
    padding: 5px 10px; background: var(--btn); color: var(--btnFg);
  }
  button.secondary, select { background: var(--btn2); color: var(--btn2Fg); border-color: var(--border); }
  button:hover { filter: brightness(1.08); }
  .grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; margin-bottom: 20px; }
  @media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
  .card {
    border: 1px solid var(--border); border-radius: 6px; padding: 12px 14px; margin-bottom: 10px;
    background: var(--input);
  }
  .card h3 { margin: 0 0 6px; font-size: 0.95rem; }
  .meta { color: var(--muted); font-size: 0.85rem; margin-bottom: 8px; }
  .why { margin: 0 0 10px; font-size: 0.9rem; }
  .row-actions { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    display: inline-block; font-size: 0.75rem; padding: 2px 7px; border-radius: 3px;
    border: 1px solid var(--border); color: var(--muted); margin-right: 4px;
  }
  .chip.partial { color: #d4a017; }
  .chip.done { color: #3fa66b; }
  .chip.todo { color: var(--muted); }
  .chip.blocked { color: #c45; }
  .chip.lane-ship { color: #4a9eff; }
  .chip.lane-fix { color: #c45; }
  .chip.lane-debt { color: #d4a017; }
  .chip.lane-hygiene { color: var(--muted); }
  .chip.cc-clean { color: #3fa66b; }
  .chip.cc-warn { color: #d4a017; }
  .chip.cc-dirty { color: #c45; }
  .chip.cc-none { color: var(--muted); }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 500; font-size: 0.8rem; }
  tr.feature-row { cursor: default; }
  tr.feature-row:hover { background: color-mix(in srgb, var(--fg) 6%, transparent); }
  tr.feature-row td.name-cell { cursor: pointer; text-decoration: underline;
    text-decoration-color: color-mix(in srgb, var(--fg) 25%, transparent); text-underline-offset: 3px; }
  .table-tools { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }
  .table-tools input[type="search"] {
    flex: 1; min-width: 160px; max-width: 320px; font: inherit; padding: 5px 10px;
    border-radius: 4px; border: 1px solid var(--border); background: var(--input); color: var(--fg);
  }
  .table-tools .hint { color: var(--muted); font-size: 0.8rem; }
  th.sortable { cursor: pointer; user-select: none; }
  th.sortable:hover { color: var(--fg); }
  th.sortable[data-active="1"] { color: var(--fg); }
  td.actions { white-space: nowrap; }
  td.actions button { padding: 3px 8px; font-size: 0.8rem; margin-right: 4px; }
  tr.sub-actions-row td { background: color-mix(in srgb, var(--card) 80%, transparent); padding: 8px 10px 12px 28px; }
  .sub-table { width: 100%; border-collapse: collapse; margin: 4px 0; font-size: 0.9rem; }
  .sub-table th, .sub-table td { border-bottom: 1px solid var(--border); padding: 6px 8px; text-align: left; }
  .sub-table th { color: var(--muted); font-weight: 600; }
  .sub-wrap { margin-top: 10px; }
  .bar { height: 6px; background: color-mix(in srgb, var(--fg) 12%, transparent);
         border-radius: 3px; overflow: hidden; margin: 8px 0 12px; max-width: 280px; }
  .bar > i { display: block; height: 100%; background: var(--vscode-progressBar-background, #3a7); }
  .panes { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }
  @media (max-width: 700px) { .panes { grid-template-columns: 1fr; } }
  ul { margin: 6px 0 0; padding-left: 18px; }
  li { margin: 3px 0; }
  .back { margin-bottom: 12px; }
  .empty { color: var(--muted); font-style: italic; }
  .backlog-toggle { display: inline-flex; align-items: center; gap: 6px; margin: 0 0 10px;
    color: var(--muted); font-size: 0.82rem; cursor: pointer; user-select: none; }
  .backlog-toggle input { margin: 0; }
  section.backlog-hide-done tr[data-done="1"] { display: none !important; }
  tr[data-done="1"] { color: var(--muted); }
</style>
</head>
<body>
${body}
<script nonce="${nonce}">
  const vscode = acquireVsCodeApi();
  function post(type, extra={}) { vscode.postMessage({ type, ...extra }); }
  document.querySelectorAll('[data-act]').forEach(el => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const act = el.getAttribute('data-act');
      const id = el.getAttribute('data-id') || undefined;
      const subAttr = el.getAttribute('data-sub');
      const laneAttr = el.getAttribute('data-lane') || undefined;
      if (act === 'filter') post('setFilter', { filter: el.getAttribute('data-filter') });
      else if (act === 'clearFilters') post('clearFilters');
      else if (act === 'sort') post('setSort', { sort: el.getAttribute('data-sort') || el.value });
      else if (act === 'toggleSubActions') {
        const pid = el.getAttribute('data-id');
        let open = false;
        document.querySelectorAll('tr.sub-actions-row[data-parent=\"' + pid + '\"]').forEach(tr => {
          tr.hidden = !tr.hidden;
          if (!tr.hidden) open = true;
        });
        document.querySelectorAll('.sub-wrap[data-parent=\"' + pid + '\"]').forEach(box => {
          box.hidden = !box.hidden;
          if (!box.hidden) open = true;
        });
        document.querySelectorAll('[data-act=\"toggleSubActions\"][data-id=\"' + pid + '\"]').forEach(btn => {
          btn.textContent = open ? 'Hide actions' : 'Next actions';
        });
      }
      else post(act, { id, sub: subAttr != null ? subAttr : undefined, lane: laneAttr });
    });
  });
  document.querySelectorAll('td.name-cell').forEach(td => {
    td.addEventListener('click', () => {
      const id = td.closest('tr')?.getAttribute('data-id');
      if (id) post('openFeature', { id });
    });
  });
  const sortSel = document.getElementById('sort');
  if (sortSel) sortSel.addEventListener('change', () => post('setSort', { sort: sortSel.value }));
  const tableSort = document.getElementById('table-sort');
  if (tableSort) tableSort.addEventListener('change', () => post('setSort', { sort: tableSort.value }));
  const search = document.getElementById('feature-search');
  function applySearch() {
    const q = (search?.value || '').trim().toLowerCase();
    post('setSearch', { search: search?.value || '' });
    document.querySelectorAll('tr.feature-row').forEach(tr => {
      const hay = (tr.getAttribute('data-search') || '').toLowerCase();
      const show = !q || hay.includes(q);
      if (tr.classList.contains('sub-actions-row')) {
        // keep hidden unless parent visible and user expanded — search only filters parent
        if (!show) tr.hidden = true;
        return;
      }
      tr.style.display = show ? '' : 'none';
      if (!show) {
        const id = tr.getAttribute('data-id');
        document.querySelectorAll('tr.sub-actions-row[data-parent=\"' + id + '\"]').forEach(sub => {
          sub.hidden = true;
        });
      }
    });
    const visible = [...document.querySelectorAll('tr.feature-row')].filter(tr => tr.style.display !== 'none').length;
    const countEl = document.getElementById('feature-count');
    if (countEl) countEl.textContent = visible + ' shown';
  }
  if (search) {
    search.addEventListener('input', applySearch);
    applySearch();
  }
  document.querySelectorAll('th.sortable').forEach(th => {
    th.addEventListener('click', () => post('setSort', { sort: th.getAttribute('data-sort') }));
  });
  const backlogToggle = document.getElementById('backlog-show-done');
  const backlogSection = document.getElementById('backlog');
  if (backlogToggle && backlogSection) {
    backlogToggle.addEventListener('change', () => {
      backlogSection.classList.toggle('backlog-hide-done', !backlogToggle.checked);
    });
  }
</script>
</body>
</html>`;
  }

  dispose(): void {
    StatusBoardPanel.current = undefined;
    this.panel.dispose();
    while (this.disposables.length) {
      this.disposables.pop()?.dispose();
    }
  }
}

function countStatuses(registry: Registry): Record<string, number> {
  const counts: Record<string, number> = { done: 0, partial: 0, todo: 0, blocked: 0 };
  for (const f of registry.features) {
    if (counts[f.status] != null) counts[f.status]++;
  }
  return counts;
}

function toggleFilter(current: FilterChip[], raw?: string): FilterChip[] {
  const chip = raw as FilterChip;
  const allowed: FilterChip[] = ["mvp", "partial", "todo", "done", "blocked"];
  if (!allowed.includes(chip)) return current;
  if (current.includes(chip)) return current.filter((c) => c !== chip);
  return [...current, chip];
}

function matchesFilters(feat: Feature, filters: FilterChip[]): boolean {
  if (!filters.length) return true;
  return filters.some((chip) => {
    if (chip === "mvp") return Boolean(feat.mvp);
    return feat.status === chip;
  });
}

function filterSort(features: Feature[], filters: FilterChip[], sortKey: SortKey): Feature[] {
  let list = features.filter((f) => matchesFilters(f, filters));
  list.sort((a, b) => {
    if (sortKey === "name") {
      return String(a.name || "").localeCompare(String(b.name || ""));
    }
    if (sortKey === "roi" || sortKey === "percent") {
      return (b[sortKey] ?? 0) - (a[sortKey] ?? 0);
    }
    if (sortKey === "phase") return (a.phase ?? 0) - (b.phase ?? 0);
    return (a.priority ?? 99) - (b.priority ?? 99);
  });
  return list;
}

function renderOverview(
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

function renderBacklogSection(backlog: Feature[]): string {
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
    ? `<label class="backlog-toggle" title="Ẩn/hiện card đã hoàn tất (done/cancelled)">
        <input type="checkbox" id="backlog-show-done" /> Hiện ${doneCount} card đã done
      </label>`
    : "";
  return `
  <section id="backlog" class="backlog-hide-done">
    <h2>Backlog — ${openCount} mở${doneCount ? ` · ${doneCount} done` : ""} / ${backlog.length} (${debt} tech-debt · ${bugs} bug)</h2>
    <p class="hint">Bug + tech-debt cards. Sắp theo priority (P nhỏ = ưu tiên cao). Open = xem where/why/proposed_fix.</p>
    ${doneToggle}
    <table>
      <thead>
        <tr><th>Severity</th><th>Status</th><th>Name</th><th>Pri</th><th>ROI</th><th>Actions</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  </section>`;
}

function ccBand(score?: number | null): { emoji: string; label: string; cls: string } {
  if (score === null || score === undefined) {
    return { emoji: "⚪", label: "chưa quét", cls: "cc-none" };
  }
  if (score >= 85) return { emoji: "🟢", label: "clean", cls: "cc-clean" };
  if (score >= 60) return { emoji: "🟡", label: "warn", cls: "cc-warn" };
  return { emoji: "🔴", label: "dirty", cls: "cc-dirty" };
}

function renderCleancodeSection(cleancode: CleancodeModule[]): string {
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
  const rows = cleancode
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
          ? `<span class="chip cc-warn" title="${open} finding mở">${open}/${totalFnd} ⚠️</span>`
          : `${open}/${totalFnd}`;
      const scannedCell = m.stale
        ? `<span class="chip cc-warn" title="Code đã đổi kể từ lần quét">⚠️ cần quét lại</span>`
        : escapeHtml(String(m.scanned_at || "chưa chấm AI"));
      return `
    <tr class="feature-row">
      <td><span class="chip ${sb.cls}" title="Structure (deterministic): file quá LOC + finding mở">${structCell}</span></td>
      <td><span class="chip ${b.cls}" title="${escapeAttr(b.label)} (AI /100)">${scoreCell}</span></td>
      <td>${escapeHtml(m.name || m.id)}<div class="meta">${escapeHtml(m.id)} · ${escapeHtml(m.area || "")}</div></td>
      <td>${findingsCell}</td>
      <td>${scannedCell}</td>
      <td class="actions">
        <button data-act="copyCleancodeScan" data-id="${escapeAttr(m.id)}" title="Copy prompt quét thêm code dơ">Scan</button>
        <button class="secondary" data-act="copyCleancodeFix" data-id="${escapeAttr(m.id)}" title="Copy prompt dọn hết đám dơ">Fix</button>
      </td>
    </tr>`;
    })
    .join("");
  return `
  <section>
    <h2>Clean Code — struct avg ${structAvg ?? "—"}/100 · ${openTotal} finding mở · AI ${scored.length}/${cleancode.length}${avg !== null ? ` (avg ${avg})` : ""}${staleCount ? ` · ${staleCount} cần quét lại ⚠️` : ""}</h2>
    <p class="hint">Struct & Findings tự cập nhật mỗi generate (deterministic, như backlog): file vượt LOC + tech-debt card chưa done. Điểm AI /100 theo rubric quality-raise cần quét lại thủ công. Scan = quét thêm; Fix = dọn.</p>
    <table>
      <thead>
        <tr><th>Struct</th><th>AI</th><th>Module</th><th>Findings</th><th>Scanned</th><th>Actions</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  </section>`;
}

function renderDetail(
  feat: Feature,
  nextPayload: NextPayload,
  tagNudges: TagNudgeMap
): string {
  const ranked = (nextPayload.next || []).find((n) => n.id === feat.id);
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
    <p class="meta">Feature lớn — mỗi nút copy prompt chỉ cho một chunk.</p>
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

function listOrEmpty(items?: string[]): string {
  if (!items || !items.length) return `<p class="empty">(none)</p>`;
  return `<ul>${items.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>`;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(s: string): string {
  return escapeHtml(s).replace(/'/g, "&#39;");
}

function loadTagNudges(context: vscode.ExtensionContext): TagNudgeMap {
  const raw = context.workspaceState.get<TagNudgeMap>(TAG_NUDGE_KEY);
  return raw && typeof raw === "object" ? { ...raw } : {};
}

async function saveTagNudges(
  context: vscode.ExtensionContext,
  map: TagNudgeMap
): Promise<void> {
  await context.workspaceState.update(TAG_NUDGE_KEY, map);
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

function tagNudgeTitle(iso?: string): string {
  if (!iso) {
    return "Copy Tag prompt (TAG: retag) — never nudged";
  }
  return `Copy Tag prompt (TAG: retag) — last nudge: ${formatTagNudge(iso)}`;
}

function untaggedCleanupTitle(iso?: string): string {
  if (!iso) {
    return "Copy whole-project untagged / dirty TAG: cleanup prompt — never nudged";
  }
  return `Copy whole-project untagged cleanup prompt — last nudge: ${formatTagNudge(iso)}`;
}

function getNonce(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let n = "";
  for (let i = 0; i < 32; i++) n += chars.charAt(Math.floor(Math.random() * chars.length));
  return n;
}
