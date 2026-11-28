import { CompileError } from "../errors.js";
import type { AggregationFunc, AggregationIr, GroupSpecIr, TypedValueIr } from "../ir.js";
import { readTypedValue } from "./filter-node.js";
import { isRecord, malformed, requiredString, unknownOperator, type Obj } from "./values.js";

const MAX_GROUP_COLS = 64;
const MAX_GROUP_KEYS = 64;
const MAX_FIELD = 256;
const MAX_ALIAS = 64;
const ALIAS = /^[A-Za-z_][A-Za-z0-9_]*$/;
const FUNCS: ReadonlySet<string> = new Set(["sum", "min", "max", "avg", "count"]);

export const AUTO_GROUP_COLUMN = "ag-Grid-AutoColumn";

interface ColumnVo {
  readonly id: string;
  readonly field: string;
  readonly aggFunc: unknown;
}

function readColumns(root: Obj, name: string, max: number): ColumnVo[] {
  const raw = root[name];
  if (raw === undefined || raw === null) return [];
  if (!Array.isArray(raw)) throw malformed(`'${name}' must be an array.`);
  if (raw.length > max) throw malformed(`'${name}' has more than ${max} entries.`);
  return (raw as unknown[]).map((entry, i) => {
    if (!isRecord(entry)) throw malformed(`'${name}[${i}]' must be an object.`);
    const id = requiredString(entry, "id", `${name}[${i}]`);
    const field = entry["field"] === undefined || entry["field"] === null ? id : requiredString(entry, "field", `${name}[${i}]`);
    if (id.length === 0 || field.length === 0 || field.length > MAX_FIELD) throw malformed(`'${name}[${i}]' needs a non-empty id and a field of at most ${MAX_FIELD} characters.`);
    return { id, field, aggFunc: entry["aggFunc"] };
  });
}

function readGroupKeys(root: Obj): TypedValueIr[] {
  const raw = root["groupKeys"];
  if (raw === undefined || raw === null) return [];
  if (!Array.isArray(raw)) throw malformed("'groupKeys' must be an array.");
  if (raw.length > MAX_GROUP_KEYS) throw malformed(`'groupKeys' has more than ${MAX_GROUP_KEYS} entries.`);
  return (raw as unknown[]).map((key, i) => readTypedValue(key, `groupKeys[${i}]`));
}

function readAggregations(root: Obj): AggregationIr[] {
  const seen = new Set<string>();
  return readColumns(root, "valueCols", Number.MAX_SAFE_INTEGER).map((column) => {
    const func = column.aggFunc;
    if (typeof func !== "string") throw malformed(`The value column '${column.id}' needs an 'aggFunc'.`);
    if (!FUNCS.has(func)) throw unknownOperator(`The aggregation function '${func}' is not one of sum, min, max, avg, count.`);
    const alias = column.id === column.field ? undefined : column.id;
    if (alias !== undefined && (alias.length > MAX_ALIAS || !ALIAS.test(alias))) throw malformed(`The alias '${alias}' is not an identifier of at most ${MAX_ALIAS} characters.`);
    const output = alias ?? `${column.field}_${func}`;
    if (seen.has(output)) {
      throw new CompileError("InvalidRequest", `Two aggregations resolve to the output name '${output}'.`, { rejectedAt: "requestParsing", reason: "duplicate-output-name" });
    }
    seen.add(output);
    return { field: column.field, func: func as AggregationFunc, ...(alias === undefined ? {} : { alias }) };
  });
}

/** The row-group state and the aggregations of a request. An export discards both after the sort has read them (the caller decides). */
export function parseGroups(root: Obj): { group?: GroupSpecIr; aggregations?: AggregationIr[] } {
  const groupCols = readColumns(root, "rowGroupCols", MAX_GROUP_COLS).map((column) => column.field);
  const groupKeys = readGroupKeys(root);
  if (groupCols.length === 0 && groupKeys.length > 0) throw malformed("'groupKeys' needs 'rowGroupCols'.");
  if (groupKeys.length > groupCols.length) throw malformed("'groupKeys' has more entries than 'rowGroupCols'.");
  const aggregations = readAggregations(root);
  return {
    ...(groupCols.length > 0 ? { group: { groupCols, groupKeys } } : {}),
    ...(aggregations.length > 0 ? { aggregations } : {}),
  };
}

/** Maps a sort on the auto group column to the group column of the level on show, or of the named source. Returns undefined when it is no auto column or names nothing. */
export function resolveAutoColumn(colId: string, group: GroupSpecIr | undefined): { field: string | null } | undefined {
  if (!colId.startsWith(AUTO_GROUP_COLUMN) || group === undefined) return undefined;
  const level = group.groupKeys?.length ?? 0;
  if (colId === AUTO_GROUP_COLUMN) return { field: group.groupCols[level] ?? null };
  const source = colId.startsWith(`${AUTO_GROUP_COLUMN}-`) ? colId.slice(AUTO_GROUP_COLUMN.length + 1) : undefined;
  if (source !== undefined && group.groupCols.includes(source)) return { field: source };
  return undefined;
}
