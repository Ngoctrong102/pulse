import type { Feature, Registry } from "./registry";
import type { FilterChip, SortKey } from "./boardTypes";

export function countStatuses(registry: Registry): Record<string, number> {
  const counts: Record<string, number> = { done: 0, partial: 0, todo: 0, blocked: 0 };
  for (const f of registry.features) {
    if (counts[f.status] != null) counts[f.status]++;
  }
  return counts;
}

export function toggleFilter(current: FilterChip[], raw?: string): FilterChip[] {
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

export function filterSort(features: Feature[], filters: FilterChip[], sortKey: SortKey): Feature[] {
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

