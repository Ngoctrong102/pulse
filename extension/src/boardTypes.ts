import type { CleancodeModule, Feature, Registry } from "./registry";
import type { NextPayload } from "./cli";

export type SortKey = "priority" | "roi" | "percent" | "phase" | "name";
/** Multi-select chips; empty = show all. Matching is OR across selected chips. */
export type FilterChip = "mvp" | "partial" | "todo" | "done" | "blocked";

export type TagNudgeMap = Record<string, string>; // featureId | __project_untagged__ -> ISO timestamp

/** workspaceState key inside TagNudgeMap for whole-project untagged cleanup */
export const PROJECT_UNTAGGED_NUDGE_ID = "__project_untagged__";

export type { CleancodeModule, Feature, Registry, NextPayload };
