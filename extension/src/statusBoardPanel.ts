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
import type { FilterChip, SortKey, TagNudgeMap } from "./boardTypes";
import { PROJECT_UNTAGGED_NUDGE_ID } from "./boardTypes";
import { countStatuses, filterSort, toggleFilter } from "./boardFilters";
import { renderOverview } from "./boardOverview";
import { renderDetail } from "./boardDetail";
import {
  escapeAttr,
  escapeHtml,
  formatTagNudge,
  getNonce,
  tagNudgeTitle,
  untaggedCleanupTitle,
} from "./boardHtmlUtils";

const TAG_NUDGE_KEY = "pulseStatus.tagNudges";

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

