import { CompileError } from "../errors.js";
import type { AggregationIr, ComparisonIr, FilterNodeIr, GroupSpecIr, PageIr, SortItemIr } from "../ir.js";
import type { Field, GridSchema } from "../schema.js";
import { effectiveSort } from "../sort.js";
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
  const mode = caseSensitivity(field, op).mode;
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

function orderBy(request: BuildRequest, context: Context): string {
  const keys = effectiveSort((request.sort ?? []).map((item) => ({ field: item.field, direction: item.direction, nulls: item.nullsPosition })), request.schema);
  return keys
    .map((key) => {
      const field = fieldOf(key.field, context);
      const mode = orderingCaseSensitivity(field, false, key.appended);
      return context.dialect.sortKey(columnOf(key.field, context), key.direction, key.nulls, mode);
    })
    .join(", ");
}

/** The page query (`SqlQueryBuilder.Build`): projection, WHERE, ORDER BY with the stable-key tiebreaker, and the row window. */
export function build(request: BuildRequest, dialect: Dialect): Artifact {
  if (request.group !== undefined || request.aggregations !== undefined) {
    throw new CompileError("Unsupported", "Grouping and aggregation are not compiled yet.");
  }
  if (request.projection?.length === 0) throw precondition("An export projection is empty: leave it out for the default.");
  const context: Context = { schema: request.schema, dialect, bag: new ParameterBag(dialect) };
  const projection = request.projection === undefined ? "*" : columnList(request.projection, context);
  let sql = `SELECT ${projection} FROM ${dialect.quoteIdentifier(request.schema.source)}`;
  if (request.filter !== undefined) sql += ` WHERE ${node(request.filter, context)}`;
  sql += ` ORDER BY ${orderBy(request, context)}`;
  if (request.page.mode === "range") {
    sql += ` ${dialect.paging(request.page.startRow, request.page.endRow - request.page.startRow, context.bag)}`;
  }
  return { dialect: dialect.name, sql, params: context.bag.values };
}
