import type { GridSchema } from "./schema.js";

export interface SortItem {
  readonly field: string;
  readonly direction: "asc" | "desc";
  readonly nulls: "first" | "last";
}

export interface SortKey extends SortItem {
  /** True for the implicit stable-key tiebreaker the compiler added (SEM-6). */
  readonly appended: boolean;
}

/** SEM-3: the adapter's default null position, last on ascending and first on descending. */
export function defaultNulls(direction: "asc" | "desc"): "first" | "last" {
  return direction === "asc" ? "last" : "first";
}

/**
 * SEM-6: the effective sort. Every field is listed once (a later occurrence is dropped); when the stable key orders exactly (any
 * non-text type, or text declared case-sensitive) everything after its first occurrence is dropped; when the sort does not reach the
 * stable key the tiebreaker `{stableKey, asc, last}` is appended. A case-insensitive text stable key keeps the keys after it and is
 * appended unless the sort already ends in it. All keys are known to the schema: the caller refused any other.
 */
export function effectiveSort(items: readonly SortItem[], schema: GridSchema): SortKey[] {
  const stable = schema.fields.get(schema.stableKey);
  const stopAtStableKey = stable !== undefined && (stable.type !== "string" || stable.caseSensitive);

  const seen = new Set<string>();
  const kept: SortKey[] = [];
  let reachedStableKey = false;
  for (const item of items) {
    if (seen.has(item.field)) {
      continue;
    }
    seen.add(item.field);
    kept.push({ ...item, appended: false });
    if (stopAtStableKey && item.field === schema.stableKey) {
      reachedStableKey = true;
      break;
    }
  }

  const total = stopAtStableKey ? reachedStableKey : kept.at(-1)?.field === schema.stableKey;
  if (total) {
    return kept;
  }
  return [...kept, { field: schema.stableKey, direction: "asc", nulls: "last", appended: true }];
}

/**
 * GRP-4: the effective sort of a grouped level. The keys can name only the group column or an aggregate, and the group column is
 * the stable key: a sort that names only those stops at the group column and otherwise gets it appended as the tiebreaker.
 */
export function groupedSort(items: readonly SortItem[], groupColumn: string, aggregateColumnIds: readonly string[]): SortKey[] {
  const stop = items.every((item) => item.field === groupColumn || aggregateColumnIds.includes(item.field));
  const seen = new Set<string>();
  const kept: SortKey[] = [];
  let reached = false;
  for (const item of items) {
    if (seen.has(item.field)) continue;
    seen.add(item.field);
    kept.push({ ...item, appended: false });
    if (stop && item.field === groupColumn) {
      reached = true;
      break;
    }
  }
  const total = stop ? reached : kept.at(-1)?.field === groupColumn;
  return total ? kept : [...kept, { field: groupColumn, direction: "asc", nulls: "last", appended: true }];
}
