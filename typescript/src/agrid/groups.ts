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

export interface ColumnVo {
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
    const field = typeof entry["field"] === "string" ? entry["field"] : id;
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

function readAggregations(root: Obj, exporting: boolean): AggregationIr[] {
  const seen = new Set<string>();
  return readColumns(root, "valueCols", Number.MAX_SAFE_INTEGER).map((column) => {
    const func = column.aggFunc;
    if (typeof func !== "string") throw malformed(`The value column '${column.id}' needs an 'aggFunc'.`);
    if (!FUNCS.has(func)) throw unknownOperator(`The aggregation function '${func}' is not one of sum, min, max, avg, count.`);
    const alias = column.id === column.field ? undefined : column.id;
    if (exporting) return { field: column.field, func: func as AggregationFunc };
    if (alias !== undefined && (alias.length > MAX_ALIAS || !ALIAS.test(alias))) throw malformed(`The alias '${alias}' is not an identifier of at most ${MAX_ALIAS} characters.`);
    const output = alias ?? `${column.field}_${func}`;
    if (seen.has(output)) {
      throw new CompileError("InvalidRequest", `Two aggregations resolve to the output name '${output}'.`, { rejectedAt: "requestParsing", reason: "duplicate-output-name" });
    }
    seen.add(output);
    return { field: column.field, func: func as AggregationFunc, ...(alias === undefined ? {} : { alias }) };
  });
}

/**
 * The row-group state and the aggregations of a request. An export discards both (EXP-1(a)), so it skips the checks that only
 * concern a grouped query: duplicate names, aliases and a drill-down path longer than the group columns.
 */
export function parseGroups(root: Obj, exporting = false): { group?: GroupSpecIr; aggregations?: AggregationIr[]; rowGroupCols: ColumnVo[] } {
  const rowGroupCols = readColumns(root, "rowGroupCols", MAX_GROUP_COLS);
  const groupCols = rowGroupCols.map((column) => column.field);
  const groupKeys = readGroupKeys(root);
  if (groupCols.length === 0 && groupKeys.length > 0) throw malformed("'groupKeys' needs 'rowGroupCols'.");
  if (!exporting && groupKeys.length > groupCols.length) throw malformed("'groupKeys' has more entries than 'rowGroupCols'.");
  const aggregations = readAggregations(root, exporting);
  return {
    rowGroupCols,
    ...(groupCols.length > 0 ? { group: { groupCols, groupKeys } } : {}),
    ...(aggregations.length > 0 ? { aggregations } : {}),
  };
}

/**
 * Resolves a sort on an auto group column (`ag-Grid-AutoColumn`, `ag-Grid-AutoColumn-<ColumnVO.id>`). Returns `null` for a column the
 * request cannot resolve to anything to order by (the drill-down leaf, where every group column is consumed), and otherwise the field
 * to sort by plus the group fields AG Grid's sort coupling sends beside it. An auto column that names no group column stays as
 * written, to fail as the unknown column it is.
 */
export function resolveAutoColumn(colId: string, group: GroupSpecIr | undefined, rowGroupCols: readonly ColumnVo[]): { field: string; coupled: readonly string[] } | null {
  if (colId.length > AUTO_GROUP_COLUMN.length) {
    const sourceId = colId.slice(AUTO_GROUP_COLUMN.length + 1);
    const match = rowGroupCols.find((column) => column.id === sourceId);
    return match === undefined ? { field: colId, coupled: [] } : { field: match.field, coupled: [match.field] };
  }
  if (group === undefined) return { field: colId, coupled: [] };
  const level = group.groupKeys.length;
  const field = group.groupCols[level];
  return field === undefined ? null : { field, coupled: rowGroupCols.map((column) => column.field) };
}
