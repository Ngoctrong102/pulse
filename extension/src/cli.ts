import * as cp from "child_process";
import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";

export type NextPayload = {
  health: {
    updated?: string;
    counts: Record<string, number>;
    open_work?: {
      remaining_bullets?: number;
      mocks?: number;
    };
    detect: {
      exists?: boolean;
      critical?: number;
      warning?: number;
      info?: number;
    };
    drift?: {
      exists?: boolean;
      critical?: number;
      warning?: number;
      info?: number;
      docs_ids_not_on_board?: number;
      spec_debt_items?: number;
      tag_gaps?: number;
      orphan_code_tags?: number;
      evidence_untagged_paths?: number;
      generated_at?: string;
    };
  };
  focus?: {
    id?: string;
    name?: string | null;
    status?: string | null;
    percent?: number | null;
    valid?: boolean;
    type?: string;
  } | null;
  continue?: {
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
  lane?: string;
  queue?: Array<{
    id?: string | null;
    name?: string | null;
    lane?: string;
    action?: string | null;
    why?: string | null;
    priority?: number | null;
    severity?: string | null;
    status?: string | null;
    percent?: number | null;
  }>;
  fix_urgent_count?: number;
  blocker_banner?: { id?: string; name?: string; message?: string } | null;
  next: Array<{
    id: string;
    name?: string;
    status?: string;
    percent?: number;
    priority?: number;
    roi?: number;
    mvp?: boolean;
    action?: string;
    why?: string;
    remaining?: string[];
    mocks?: string[];
    docs?: Record<string, string[]>;
    specs?: string[];
    finding_count?: number;
    multi?: boolean;
    sub_actions?: Array<{ key?: string; title?: string; kind?: string }>;
  }>;
};

function runStatus(folder: string, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    const script = path.join(folder, ".pulse", "bin", "pulse");
    if (!fs.existsSync(script)) {
      reject(new Error(`Missing ${script}`));
      return;
    }
    cp.execFile(
      script,
      args,
      { cwd: folder, maxBuffer: 4 * 1024 * 1024 },
      (err, stdout, stderr) => {
        if (err) {
          reject(new Error(stderr || err.message));
          return;
        }
        resolve(stdout);
      }
    );
  });
}

export async function fetchNextJson(
  folder: string,
  limit = 7,
  lane = "all"
): Promise<NextPayload> {
  const out = await runStatus(folder, [
    "next",
    "--json",
    "--limit",
    String(limit),
    "--lane",
    lane,
  ]);
  return JSON.parse(out) as NextPayload;
}

export async function runSetFocus(folder: string, id: string): Promise<void> {
  await runStatus(folder, ["set", "--focus", id]);
}

export async function runClearFocus(folder: string): Promise<void> {
  await runStatus(folder, ["set", "--clear-focus"]);
}

export async function fetchExplainPrompt(folder: string, featureId?: string): Promise<string> {
  const args = featureId ? ["explain", "--feature", featureId] : ["explain"];
  return (await runStatus(folder, args)).trimEnd();
}

export async function fetchNextPrompt(
  folder: string,
  featureId?: string,
  subIndex?: number
): Promise<string> {
  const args = ["next", "--prompt"];
  if (featureId) {
    args.push("--feature", featureId);
  }
  if (subIndex !== undefined && subIndex !== null && !Number.isNaN(subIndex)) {
    args.push("--sub", String(subIndex));
  }
  return (await runStatus(folder, args)).trimEnd();
}

export async function fetchTagPrompt(folder: string, featureId: string): Promise<string> {
  return (await runStatus(folder, ["tag", "--feature", featureId])).trimEnd();
}

export async function fetchUntaggedCleanupPrompt(folder: string): Promise<string> {
  return (await runStatus(folder, ["tag", "--untagged-cleanup"])).trimEnd();
}

export async function fetchDocsDriftPrompt(folder: string): Promise<string> {
  return (await runStatus(folder, ["drift", "--prompt"])).trimEnd();
}

export type CleancodePayload = {
  modules: Array<{
    id: string;
    name?: string;
    area?: string;
    score?: number | null;
    scanned_at?: string | null;
    summary?: string;
    findings?: string[];
    stale?: boolean;
  }>;
};

export async function fetchCleancodeJson(folder: string): Promise<CleancodePayload> {
  const out = await runStatus(folder, ["cleancode", "list", "--json"]);
  return JSON.parse(out) as CleancodePayload;
}

export async function fetchCleancodeScanPrompt(folder: string, moduleId: string): Promise<string> {
  return (await runStatus(folder, ["cleancode", "scan", "--module", moduleId])).trimEnd();
}

export async function fetchCleancodeFixPrompt(folder: string, moduleId: string): Promise<string> {
  return (await runStatus(folder, ["cleancode", "fix", "--module", moduleId])).trimEnd();
}

export function runDriftInTerminal(folder: string): void {
  const term = vscode.window.createTerminal({ name: "pulse docs-drift", cwd: folder });
  term.show();
  term.sendText("./.pulse/bin/pulse drift");
}

export function runDetectInTerminal(folder: string): void {
  const term = vscode.window.createTerminal({ name: "pulse mismatch-detect", cwd: folder });
  term.show();
  term.sendText("./.pulse/bin/pulse mismatch detect");
}

export function runGenerateInTerminal(folder: string): void {
  const term = vscode.window.createTerminal({ name: "pulse generate", cwd: folder });
  term.show();
  term.sendText("./.pulse/bin/pulse generate");
}
