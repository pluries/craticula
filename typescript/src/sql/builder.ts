import { CompileError } from "../errors.js";
import type { AggregationIr, ComparisonIr, FilterNodeIr, GroupSpecIr, PageIr, SortItemIr } from "../ir.js";
import type { Field, GridSchema } from "../schema.js";
import { effectiveSort, groupedSort } from "../sort.js";
import { columnId, outputName, resolveGrouping, type GroupingPlan } from "./grouping.js";
import type { Anchor, Dialect, DialectName, Param, ScalarOp } from "./dialect.js";
import { ParameterBag } from "./params.js";
import { blankCondition, caseSensitivity, isNullInclusive, orderingCaseSensitivity } from "./semantics.js";
import { encodeValue, type Rounding } from "./values.js";

export interface Artifact {
  readonly dialect: DialectName;
  readonly sql: string;
  readonly params: Param[];
}

export interface BuildRequest {
  readonly schema: GridSchema;
  readonly filter?: FilterNodeIr | undefined;
  readonly sort?: readonly SortItemIr[] | undefined;
  readonly page: PageIr;
  /** EXP-1(b): the export columns, in order. Absent means every field (`SELECT *`). */
  readonly projection?: readonly string[] | undefined;
  readonly group?: GroupSpecIr | undefined;
  readonly aggregations?: readonly AggregationIr[] | undefined;
}

interface Context {
  readonly schema: GridSchema;
  readonly dialect: Dialect;
  readonly bag: ParameterBag;
  /** A drill-down condition: an exact match on the group key, so no case folding (SEM-1). */
  readonly groupKeyMatch?: boolean;
}

function precondition(message: string): CompileError {
  return new CompileError("InvalidRequest", message);
}

function fieldOf(name: string, context: Context): Field {
  const field = context.schema.fields.get(name);
  if (field === undefined) throw precondition(`Field '${name}' is not declared in the GridSchema: the allowlist runs before a compiler.`);
  return field;
}

/** The only place a schema name becomes SQL text: the field's plain column, quoted by the dialect. */
function columnOf(name: string, context: Context): string {
  const field = fieldOf(name, context);
  if (field.sql === undefined) return context.dialect.quoteIdentifier(name);
  if (field.sql.kind !== "column") {
    throw new CompileError("Unsupported", `Field '${name}' maps to a qualified column or an expression; no fixture pins their rendering, so this compiler reads plain columns only.`);
  }
  return context.dialect.quoteIdentifier(field.sql.text);
}

const SCALAR: Readonly<Record<string, ScalarOp>> = { eq: "eq", neq: "neq", gt: "gt", gte: "gte", lt: "lt", lte: "lte" };
const ANCHOR: Readonly<Record<string, Anchor>> = { contains: "anywhere", notContains: "anywhere", startsWith: "start", endsWith: "end" };

function fieldsIn(node: FilterNodeIr, into: Set<string> = new Set()): Set<string> {
  if (node.type === "comparison") into.add(node.field);
  else if (node.type === "not") fieldsIn(node.node, into);
  else node.nodes.forEach((child) => fieldsIn(child, into));
  return into;
}

function rounding(op: string): Rounding {
  if (op === "gt" || op === "lte") return "floor";
  return op === "gte" || op === "lt" ? "ceiling" : "none";
}

function requireValue(node: ComparisonIr): NonNullable<ComparisonIr["value"]> {
  if (node.value === undefined) throw precondition(`Operator '${node.op}' on field '${node.field}' requires 'value'.`);
  return node.value;
}

function scalar(column: string, field: Field, op: string, value: NonNullable<ComparisonIr["value"]>, context: Context): string {
  const mode = context.groupKeyMatch === true ? orderingCaseSensitivity(field, true) : caseSensitivity(field, op).mode;
  return context.dialect.scalar(column, SCALAR[op]!, encodeValue(value, field, context.dialect, rounding(op)), field.type, mode, context.bag);
}

function blank(column: string, field: Field, context: Context): string {
  if (blankCondition(field.type) === "nullOrEmptyString" && !context.dialect.emptyStringIsNull) return `(${column} IS NULL OR ${column} = '')`;
  return `${column} IS NULL`;
}

function comparison(node: ComparisonIr, context: Context): string {
  const field = fieldOf(node.field, context);
  const column = columnOf(node.field, context);
  const nullInclusive = (predicate: string) => (isNullInclusive(node.op) ? `(${predicate} OR ${column} IS NULL)` : predicate);
  switch (node.op) {
    case "blank":
      return blank(column, field, context);
    case "notBlank":
      return `NOT (${blank(column, field, context)})`;
    case "true":
      return scalar(column, field, "eq", { type: "boolean", value: true }, context);
    case "false":
      return scalar(column, field, "eq", { type: "boolean", value: false }, context);
    case "eq":
      if (node.value?.type === "null") return `${column} IS NULL`;
      return scalar(column, field, node.op, requireValue(node), context);
    case "neq":
    case "gt":
    case "gte":
    case "lt":
    case "lte":
      return nullInclusive(scalar(column, field, node.op, requireValue(node), context));
    case "contains":
    case "notContains":
    case "startsWith":
    case "endsWith": {
      if (field.type !== "string") throw precondition(`Field '${node.field}' is declared '${field.type}', but '${node.op}' is a substring match and needs a string field.`);
      const value = requireValue(node);
      if (value.type !== "string") throw precondition(`Operator '${node.op}' on field '${node.field}' needs a string value: the coercion stage runs before a compiler.`);
      const mode = caseSensitivity(field, node.op).mode;
      return nullInclusive(context.dialect.substring(column, ANCHOR[node.op]!, node.op === "notContains", value.value, mode, context.bag));
    }
    case "in":
    case "notIn": {
      const values = node.values;
      if (values === undefined) throw precondition(`Operator '${node.op}' on field '${node.field}' requires 'values'.`);
      if (values.length === 0) return node.op === "notIn" ? "1 = 1" : "1 = 0";
      const mode = caseSensitivity(field, node.op).mode;
      const encoded = values.map((value) => encodeValue(value, field, context.dialect));
      return nullInclusive(context.dialect.setMembership(column, node.op === "notIn", encoded, field.type, mode, context.bag));
    }
    case "inRange": {
      if (node.from === undefined || node.to === undefined || node.fromInclusive === undefined || node.toInclusive === undefined) {
        throw precondition(`Operator 'inRange' on field '${node.field}' requires 'from', 'to', 'fromInclusive' and 'toInclusive'.`);
      }
      const lower = scalar(column, field, node.fromInclusive ? "gte" : "gt", node.from, context);
      const upper = scalar(column, field, node.toInclusive ? "lte" : "lt", node.to, context);
      return `(${lower} AND ${upper})`;
    }
    default:
      throw precondition(`Unknown comparison operator '${node.op}'.`);
  }
}

function node(filter: FilterNodeIr, context: Context): string {
  switch (filter.type) {
    case "and":
      return `(${filter.nodes.map((child) => node(child, context)).join(" AND ")})`;
    case "or":
      return `(${filter.nodes.map((child) => node(child, context)).join(" OR ")})`;
    case "not": {
      // SEM-2: a NOT keeps the rows whose column is NULL, once per distinct column of the subtree in first-appearance order.
      const nulls = [...fieldsIn(filter.node)].map((name) => ` OR ${columnOf(name, context)} IS NULL`).join("");
      return `(NOT (${node(filter.node, context)})${nulls})`;
    }
    default:
      return comparison(filter, context);
  }
}

function columnList(names: readonly string[], context: Context): string {
  return names
    .map((name) => {
      const column = columnOf(name, context);
      const alias = context.dialect.quoteIdentifier(name);
      return column === alias ? column : `${column} AS ${alias}`;
    })
    .join(", ");
}

const FUNCTION: Readonly<Record<AggregationIr["func"], string>> = { sum: "SUM", min: "MIN", max: "MAX", avg: "AVG", count: "COUNT" };

function aggregateCall(aggregation: AggregationIr, context: Context): string {
  const call = `${FUNCTION[aggregation.func]}(${columnOf(aggregation.field, context)})`;
  return aggregation.func === "sum" ? `COALESCE(${call}, 0)` : call;
}

/** GRP-4: a grouped level orders only by its group column or one of its aggregates; a key that names two is ambiguous. */
function groupedTarget(sortField: string, plan: GroupingPlan & { groupColumn: string }, context: Context): { column: string; field: Field } {
  const matches = plan.aggregations.filter((aggregation) => columnId(aggregation) === sortField);
  if (matches.length > 1) {
    throw precondition(`Ambiguous ORDER BY target for a grouped level: '${sortField}' matches ${matches.length} aggregations (${matches.map((a) => a.func).join(", ")}). Give each valueCol a distinct id.`);
  }
  if (matches.length > 0 && sortField === plan.groupColumn) {
    throw precondition(`Ambiguous ORDER BY target for a grouped level: '${sortField}' is this level's group column and the id of an aggregation. Give the aggregation a distinct id.`);
  }
  const [match] = matches;
  if (match !== undefined) return { column: aggregateCall(match, context), field: fieldOf(match.field, context) };
  if (sortField === plan.groupColumn) return { column: columnOf(sortField, context), field: fieldOf(sortField, context) };
  throw precondition(`A grouped query can be ordered only by its group column ('${plan.groupColumn}') or by one of its aggregations, not by '${sortField}'.`);
}

function orderBy(request: BuildRequest, plan: GroupingPlan | undefined, context: Context): string {
  const items = (request.sort ?? []).map((item) => ({ field: item.field, direction: item.direction, nulls: item.nullsPosition }));
  const groupColumn = plan?.groupColumn;
  if (plan !== undefined && groupColumn !== undefined) {
    const grouped = { ...plan, groupColumn };
    return groupedSort(items, groupColumn, plan.aggregations.map(columnId))
      .map((key) => {
        const { column, field } = groupedTarget(key.field, grouped, context);
        return context.dialect.sortKey(column, key.direction, key.nulls, orderingCaseSensitivity(field, true, key.appended));
      })
      .join(", ");
  }
  return effectiveSort(items, request.schema)
    .map((key) => {
      const field = fieldOf(key.field, context);
      return context.dialect.sortKey(columnOf(key.field, context), key.direction, key.nulls, orderingCaseSensitivity(field, false, key.appended));
    })
    .join(", ");
}

/** GRP-5: the drill-down path and the user's filter, the path first, as one condition. */
function where(filter: FilterNodeIr | undefined, drillDown: FilterNodeIr | undefined, context: Context): string | undefined {
  const path = drillDown === undefined ? undefined : node(drillDown, { ...context, groupKeyMatch: true });
  const user = filter === undefined ? undefined : node(filter, context);
  if (path !== undefined && user !== undefined) return `(${path} AND ${user})`;
  return path ?? user;
}

function projectionOf(request: BuildRequest, plan: GroupingPlan | undefined, context: Context): string {
  if (plan === undefined) return request.projection === undefined ? "*" : columnList(request.projection, context);
  if (plan.groupColumn === undefined) return columnList([...request.schema.fields.keys()], context);
  const items = [`${columnOf(plan.groupColumn, context)} AS ${context.dialect.quoteIdentifier(plan.groupColumn)}`];
  for (const aggregation of plan.aggregations) items.push(`${aggregateCall(aggregation, context)} AS ${context.dialect.quoteIdentifier(outputName(aggregation))}`);
  return items.join(", ");
}

/** The page query (`SqlQueryBuilder.Build`): projection, WHERE, GROUP BY, ORDER BY with its tiebreaker, and the row window. */
export function build(request: BuildRequest, dialect: Dialect): Artifact {
  if (request.projection?.length === 0) throw precondition("An export projection is empty: leave it out for the default.");
  if (request.projection !== undefined && request.group !== undefined) {
    throw precondition("A request carries both a group and an export projection: an export discards group state before it gets here.");
  }
  const context: Context = { schema: request.schema, dialect, bag: new ParameterBag(dialect) };
  const plan = resolveGrouping(request.group, request.aggregations);
  let sql = `SELECT ${projectionOf(request, plan, context)} FROM ${dialect.quoteIdentifier(request.schema.source)}`;
  const predicate = where(request.filter, plan?.drillDown, context);
  if (predicate !== undefined) sql += ` WHERE ${predicate}`;
  if (plan?.groupColumn !== undefined) sql += ` GROUP BY ${columnOf(plan.groupColumn, context)}`;
  sql += ` ORDER BY ${orderBy(request, plan, context)}`;
  if (request.page.mode === "range") {
    sql += ` ${dialect.paging(request.page.startRow, request.page.endRow - request.page.startRow, context.bag)}`;
  }
  return { dialect: dialect.name, sql, params: context.bag.values };
}

/** CNT-1 to CNT-8: the number of rows the request would page through, or of groups at a grouped level. No sort, no page. */
export function buildCount(request: BuildRequest, dialect: Dialect): Artifact {
  const context: Context = { schema: request.schema, dialect, bag: new ParameterBag(dialect) };
  const plan = resolveGrouping(request.group, request.aggregations);
  const table = dialect.quoteIdentifier(request.schema.source);
  const grouped = plan?.groupColumn === undefined ? undefined : columnOf(plan.groupColumn, context);
  let inner = grouped === undefined ? `SELECT COUNT(*) FROM ${table}` : `SELECT ${grouped} FROM ${table}`;
  const predicate = where(request.filter, plan?.drillDown, context);
  if (predicate !== undefined) inner += ` WHERE ${predicate}`;
  if (grouped === undefined) return { dialect: dialect.name, sql: inner, params: context.bag.values };
  return { dialect: dialect.name, sql: `SELECT COUNT(*) FROM (${inner} GROUP BY ${grouped}) craticula_count`, params: context.bag.values };
}

export interface SetValuesBuildRequest {
  readonly schema: GridSchema;
  readonly colId: string;
  readonly filter?: FilterNodeIr | undefined;
  /** The resolved cap: `min(requested or default, maximum)`, always positive. */
  readonly rowLimit: number;
}

/** GRP-6: the distinct values of one column, ordered by it, capped, with no offset and no tiebreaker. */
export function buildSetValues(request: SetValuesBuildRequest, dialect: Dialect): Artifact {
  if (!Number.isInteger(request.rowLimit) || request.rowLimit <= 0) throw precondition(`A set-values row limit must be positive, not ${request.rowLimit}.`);
  const context: Context = { schema: request.schema, dialect, bag: new ParameterBag(dialect) };
  const column = columnOf(request.colId, context);
  let sql = `${dialect.distinctValuesUseGroupBy ? "SELECT" : "SELECT DISTINCT"} ${column} FROM ${dialect.quoteIdentifier(request.schema.source)}`;
  const predicate = where(request.filter, undefined, context);
  if (predicate !== undefined) sql += ` WHERE ${predicate}`;
  if (dialect.distinctValuesUseGroupBy) sql += ` GROUP BY ${column}`;
  const mode = orderingCaseSensitivity(fieldOf(request.colId, context), true);
  sql += ` ORDER BY ${dialect.sortKey(column, "asc", "last", mode)} ${dialect.rowLimit(request.rowLimit, context.bag)}`;
  return { dialect: dialect.name, sql, params: context.bag.values };
}
