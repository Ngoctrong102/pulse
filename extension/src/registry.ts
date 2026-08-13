import * as fs from "fs";
import * as path from "path";
import * as yaml from "js-yaml";

export type Feature = {
  id: string;
  type?: string;
  name: string;
  phase?: number;
  status: string;
  percent: number;
  priority: number;
  roi: number;
  mvp?: boolean;
  next_chunks?: string;
  remaining?: string[];
  mocks?: string[];
  done?: string[];
  docs?: Record<string, string[]>;
  specs?: string[];
  evidence?: Record<string, unknown>;
  // backlog (bug | tech-debt) fields
  severity?: string;
  where?: string;
  why?: string;
  proposed_fix?: string;
  refs?: string[];
  blocks?: string[];
};

export type Registry = {
  version?: number;
  updated?: string;
  project?: string;
  tag_prefix?: string;
  speckit?: boolean;
  focus_id?: string | null;
  plugins?: Record<string, unknown>;
  features: Feature[];
  backlog?: Feature[];
  /** Extra _meta.yaml keys preserved on save */
  [key: string]: unknown;
};

export type CleancodeModule = {
  id: string;
  name: string;
  area?: string;
  globs?: string[];
  score?: number | null;
  scanned_at?: string | null;
  summary?: string;
  subscores?: Record<string, number>;
  findings?: string[];
  stale?: boolean;
  // Deterministic metrics from `cleancode list --json` (auto-updated each generate).
  structure_score?: number;
  open_findings?: number;
  total_findings?: number;
  oversized_files?: number;
  loc_budget?: number;
};

const BACKLOG_TYPES = new Set(["bug", "tech-debt"]);
const META_EXCLUDE = new Set(["features", "backlog"]);
const META_KEY_ORDER = [
  "version",
  "project",
  "tag_prefix",
  "speckit",
  "updated",
  "focus_id",
  "plugins",
];

function preferPulseOrLegacy(folder: string, pulseRel: string, legacyRel: string): string {
  const pulsePath = path.join(folder, ...pulseRel.split("/"));
  const legacyPath = path.join(folder, ...legacyRel.split("/"));
  if (fs.existsSync(pulsePath)) {
    return pulsePath;
  }
  if (fs.existsSync(legacyPath)) {
    return legacyPath;
  }
  return pulsePath;
}

/** The per-card source-of-truth directory (.pulse/features; legacy docs/status/features). */
export function featuresDir(folder: string): string {
  return preferPulseOrLegacy(folder, ".pulse/features", "docs/status/features");
}

/** Back-compat alias — the registry is the per-card directory now. */
export function registryPath(folder: string): string {
  return featuresDir(folder);
}

/** The per-module clean-code scoreboard directory. */
export function cleancodeDir(folder: string): string {
  return preferPulseOrLegacy(folder, ".pulse/cleancode", "docs/status/cleancode");
}

export function loadCleancode(folder: string): CleancodeModule[] {
  const dir = cleancodeDir(folder);
  let entries: string[];
  try {
    entries = fs.readdirSync(dir);
  } catch {
    return [];
  }
  const mods: CleancodeModule[] = [];
  for (const name of entries.sort()) {
    if (!name.endsWith(".yaml") || name.startsWith("_")) {
      continue;
    }
    const mod = yaml.load(fs.readFileSync(path.join(dir, name), "utf8")) as CleancodeModule;
    if (mod && mod.id) {
      mods.push(mod);
    }
  }
  mods.sort((a, b) => (a.area ?? "").localeCompare(b.area ?? "") || (a.id > b.id ? 1 : -1));
  return mods;
}

export function loadRegistry(folder: string): Registry {
  const dir = featuresDir(folder);
  let meta: Record<string, unknown> = {};
  const metaFile = path.join(dir, "_meta.yaml");
  if (fs.existsSync(metaFile)) {
    const loaded = yaml.load(fs.readFileSync(metaFile, "utf8"));
    if (loaded && typeof loaded === "object" && !Array.isArray(loaded)) {
      meta = loaded as Record<string, unknown>;
    }
  }
  let entries: string[];
  try {
    entries = fs.readdirSync(dir);
  } catch {
    throw new Error(`Missing status folder: ${dir}`);
  }
  const features: Feature[] = [];
  const backlog: Feature[] = [];
  for (const name of entries.sort()) {
    if (!name.endsWith(".yaml") || name === "_meta.yaml") {
      continue;
    }
    const card = yaml.load(fs.readFileSync(path.join(dir, name), "utf8")) as Feature;
    if (!card || !card.id) {
      continue;
    }
    if (!card.type) {
      card.type = "feature";
    }
    if (BACKLOG_TYPES.has(card.type)) {
      backlog.push(card);
    } else {
      features.push(card);
    }
  }
  features.sort((a, b) => (a.phase ?? 0) - (b.phase ?? 0) || (a.id > b.id ? 1 : -1));
  backlog.sort((a, b) => (a.id > b.id ? 1 : -1));
  const focusRaw = meta.focus_id;
  const focus_id =
    focusRaw === undefined || focusRaw === null || String(focusRaw).trim() === ""
      ? null
      : String(focusRaw);
  const out: Registry = {
    ...meta,
    version: meta.version as number | undefined,
    updated: meta.updated as string | undefined,
    project: meta.project as string | undefined,
    tag_prefix: meta.tag_prefix as string | undefined,
    speckit: meta.speckit as boolean | undefined,
    focus_id,
    plugins: meta.plugins as Record<string, unknown> | undefined,
    features,
    backlog,
  };
  return out;
}

function metaPayloadFromRegistry(data: Registry, existingMeta: Record<string, unknown>): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...existingMeta };
  for (const [k, v] of Object.entries(data)) {
    if (META_EXCLUDE.has(k)) {
      continue;
    }
    merged[k] = v;
  }
  const ordered: Record<string, unknown> = {};
  for (const k of META_KEY_ORDER) {
    if (!(k in merged)) {
      continue;
    }
    if (k === "focus_id" && (merged[k] === null || merged[k] === undefined || String(merged[k]).trim() === "")) {
      continue;
    }
    ordered[k] = merged[k];
  }
  for (const [k, v] of Object.entries(merged)) {
    if (k in ordered || META_EXCLUDE.has(k)) {
      continue;
    }
    if (k === "focus_id" && (v === null || v === undefined || String(v).trim() === "")) {
      continue;
    }
    ordered[k] = v;
  }
  return ordered;
}

export function saveRegistry(folder: string, data: Registry): void {
  const dir = featuresDir(folder);
  fs.mkdirSync(dir, { recursive: true });
  const metaFile = path.join(dir, "_meta.yaml");
  let existingMeta: Record<string, unknown> = {};
  if (fs.existsSync(metaFile)) {
    const loaded = yaml.load(fs.readFileSync(metaFile, "utf8"));
    if (loaded && typeof loaded === "object" && !Array.isArray(loaded)) {
      existingMeta = loaded as Record<string, unknown>;
    }
  }
  const meta = metaPayloadFromRegistry(data, existingMeta);
  fs.writeFileSync(metaFile, yaml.dump(meta, { noRefs: true, sortKeys: false }), "utf8");
  const all = [...(data.features ?? []), ...(data.backlog ?? [])];
  for (const card of all) {
    fs.writeFileSync(
      path.join(dir, `${card.id}.yaml`),
      yaml.dump(card, { lineWidth: 100, noRefs: true, sortKeys: false }),
      "utf8"
    );
  }
}

export function getFeature(data: Registry, id: string): Feature | undefined {
  return [...data.features, ...(data.backlog ?? [])].find((f) => f.id === id);
}

/** Mark feature done/100%; move remaining into done; clear remaining. Refuses if mocks remain. */
export function patchFeatureComplete(folder: string, featureId: string): Feature {
  const data = loadRegistry(folder);
  const feat = getFeature(data, featureId);
  if (!feat) {
    throw new Error(`Unknown feature: ${featureId}`);
  }
  if ((feat.mocks || []).length) {
    throw new Error(
      `Cannot mark ${featureId} done while mocks remain: ${feat.mocks!.join("; ")}`
    );
  }
  const leftover = [...(feat.remaining || [])];
  feat.done = [...(feat.done || []), ...leftover];
  feat.remaining = [];
  feat.status = "done";
  feat.percent = 100;
  data.updated = new Date().toISOString().slice(0, 10);
  saveRegistry(folder, data);
  return feat;
}
