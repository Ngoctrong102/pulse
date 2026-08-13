import * as vscode from "vscode";
import { runDetectInTerminal } from "./cli";
import { featuresDir, loadRegistry, type Feature } from "./registry";
import { StatusBoardPanel } from "./statusBoardPanel";

type SortKey = "priority" | "roi" | "percent" | "phase";
type FilterMode = "all" | "partial" | "todo" | "done" | "mvp";

class FeatureItem extends vscode.TreeItem {
  constructor(public readonly feature: Feature) {
    super(feature.name, vscode.TreeItemCollapsibleState.Collapsed);
    const emoji =
      feature.status === "done"
        ? "✅"
        : feature.status === "partial"
          ? "🟡"
          : feature.status === "blocked"
            ? "🚫"
            : "⬜";
    this.description = `${emoji} ${feature.percent}% · P${feature.priority} · ROI ${feature.roi}`;
    this.tooltip = [
      feature.id,
      `phase ${feature.phase ?? "-"}`,
      feature.mvp ? "MVP" : "non-MVP",
      ...(feature.remaining ?? []).map((r) => `• ${r}`),
    ].join("\n");
    this.contextValue = "pulseFeature";
    this.command = {
      command: "pulseStatus.openBoard",
      title: "Open Status Board",
      arguments: [feature.id],
    };
  }
}

class DetailItem extends vscode.TreeItem {
  constructor(label: string) {
    super(label, vscode.TreeItemCollapsibleState.None);
  }
}

class BacklogItem extends vscode.TreeItem {
  constructor(public readonly feature: Feature) {
    super(feature.name, vscode.TreeItemCollapsibleState.None);
    const emoji = feature.status === "done" ? "✅" : feature.status === "partial" ? "🟡" : "⬜";
    this.description = `${emoji} ${feature.type ?? "backlog"} · ${feature.severity ?? "-"}`;
    this.tooltip = [feature.id, feature.where ?? "", feature.why ?? ""].filter(Boolean).join("\n");
    this.contextValue = "pulseBacklog";
    this.command = {
      command: "pulseStatus.openBoard",
      title: "Open Status Board",
      arguments: [feature.id],
    };
  }
}

class SectionItem extends vscode.TreeItem {
  constructor(label: string, public readonly kind: "features" | "backlog") {
    super(label, vscode.TreeItemCollapsibleState.Expanded);
    this.contextValue = "pulseSection";
  }
}

export class StatusTreeProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private _onDidChange = new vscode.EventEmitter<vscode.TreeItem | undefined>();
  readonly onDidChangeTreeData = this._onDidChange.event;
  sortKey: SortKey = "priority";
  filter: FilterMode = "all";

  constructor(private folder: string) {}

  refresh(): void {
    this._onDidChange.fire(undefined);
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: vscode.TreeItem): vscode.ProviderResult<vscode.TreeItem[]> {
    if (element instanceof FeatureItem) {
      const f = element.feature;
      const kids: vscode.TreeItem[] = [
        new DetailItem(`id: ${f.id}`),
        new DetailItem(`status: ${f.status} (${f.percent}%)`),
      ];
      for (const r of f.remaining ?? []) kids.push(new DetailItem(`remaining: ${r}`));
      for (const m of f.mocks ?? []) kids.push(new DetailItem(`mock: ${m}`));
      return kids;
    }

    try {
      const registry = loadRegistry(this.folder);
      const backlog = registry.backlog ?? [];
      if (element instanceof SectionItem && element.kind === "backlog") {
        return backlog.map((f) => new BacklogItem(f));
      }
      let list = [...registry.features];
      if (this.filter === "mvp") list = list.filter((f) => f.mvp);
      else if (this.filter !== "all") list = list.filter((f) => f.status === this.filter);
      list.sort((a, b) => {
        if (this.sortKey === "roi" || this.sortKey === "percent") {
          return (b[this.sortKey] ?? 0) - (a[this.sortKey] ?? 0);
        }
        if (this.sortKey === "phase") return (a.phase ?? 0) - (b.phase ?? 0);
        return (a.priority ?? 99) - (b.priority ?? 99);
      });
      const featureItems = list.map((f) => new FeatureItem(f));
      // Root: show a Backlog section only when backlog cards exist; otherwise flat feature list.
      if (!element && backlog.length) {
        const section = new SectionItem(`Backlog & Bugs (${backlog.length})`, "backlog");
        return [...featureItems, section];
      }
      return featureItems;
    } catch (e) {
      return [new DetailItem(`Error: ${e}`)];
    }
  }
}

export function activate(context: vscode.ExtensionContext): void {
  const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!folder) {
    return;
  }
  const provider = new StatusTreeProvider(folder);
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider("pulseStatus.features", provider)
  );

  const watch = vscode.workspace.createFileSystemWatcher(
    new vscode.RelativePattern(folder, ".pulse/features/**")
  );
  const refreshAll = () => {
    provider.refresh();
    void StatusBoardPanel.current?.refresh();
  };
  watch.onDidChange(refreshAll);
  watch.onDidCreate(refreshAll);
  watch.onDidDelete(refreshAll);
  context.subscriptions.push(watch);

  // Backup: save events (and some external writes that touch the cards)
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      if (doc.uri.fsPath.startsWith(featuresDir(folder))) {
        refreshAll();
      }
      if (doc.uri.fsPath.endsWith("mismatch-report.json")) {
        void StatusBoardPanel.current?.refresh();
      }
    })
  );

  const watchReport = vscode.workspace.createFileSystemWatcher(
    new vscode.RelativePattern(folder, ".pulse/mismatch-report.json")
  );
  watchReport.onDidChange(() => void StatusBoardPanel.current?.refresh());
  watchReport.onDidCreate(() => void StatusBoardPanel.current?.refresh());
  context.subscriptions.push(watchReport);

  const watchCleancode = vscode.workspace.createFileSystemWatcher(
    new vscode.RelativePattern(folder, ".pulse/cleancode/**")
  );
  watchCleancode.onDidChange(() => void StatusBoardPanel.current?.refresh());
  watchCleancode.onDidCreate(() => void StatusBoardPanel.current?.refresh());
  watchCleancode.onDidDelete(() => void StatusBoardPanel.current?.refresh());
  context.subscriptions.push(watchCleancode);

  context.subscriptions.push(
    vscode.commands.registerCommand("pulseStatus.openBoard", (featureId?: string) => {
      StatusBoardPanel.createOrShow(context, folder, featureId);
    }),
    vscode.commands.registerCommand("pulseStatus.refresh", () => {
      provider.refresh();
      void StatusBoardPanel.current?.refresh();
    }),
    vscode.commands.registerCommand("pulseStatus.openRegistry", async () => {
      await vscode.commands.executeCommand(
        "revealInExplorer",
        vscode.Uri.file(featuresDir(folder))
      );
    }),
    vscode.commands.registerCommand("pulseStatus.runDetect", () => {
      runDetectInTerminal(folder);
    }),
    vscode.commands.registerCommand("pulseStatus.setSort", async () => {
      const pick = await vscode.window.showQuickPick(
        ["priority", "roi", "percent", "phase"],
        { title: "Sort features by" }
      );
      if (pick) {
        provider.sortKey = pick as SortKey;
        provider.refresh();
      }
    }),
    vscode.commands.registerCommand("pulseStatus.setFilter", async () => {
      const pick = await vscode.window.showQuickPick(
        ["all", "partial", "todo", "done", "mvp"],
        { title: "Filter features" }
      );
      if (pick) {
        provider.filter = pick as FilterMode;
        provider.refresh();
      }
    })
  );
}

export function deactivate(): void {}
