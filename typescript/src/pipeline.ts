import { CompileError, type RejectionReason } from "./errors.js";
import { mergeFilters } from "./agrid/filters.js";
import { isIsoInstant, validCalendar } from "./agrid/dates.js";
import type { ParsedSetValues } from "./agrid/request.js";
import type { AggregationIr, ComparisonIr, FilterNodeIr, GroupSpecIr, Ir, PageIr, TypedValueIr } from "./ir.js";
import { DEFAULT_LIMITS, type Limits } from "./limits.js";
import type { Field, GridSchema } from "./schema.js";

/**
 * The stages between parsing and a compiler, in the order of `spec/conformance-runner.md` §3: the allowlist (SC-1, SC-2), the limits
 * (SEC-3) and the coercion (SEM-5). Coercion and parsing errors raised while the request is read come first, as they do in the C# library.
 * Injecting the schema's static filter (SC-5) belongs to the compilers.
 */
type Node = FilterNodeIr;
type Refusal = { readonly reason: RejectionReason; readonly message: string };

function allowlistRefusal(refusals: readonly Refusal[]): CompileError | undefined {
  const first = refusals[0];
  return first === undefined ? undefined : new CompileError("UnknownField", first.message, { rejectedAt: "allowlist", reason: first.reason as "unknown-field" | "field-not-filterable" });
}

function structuralColumns(schema: GridSchema, group: GroupSpecIr | undefined, aggregations: readonly AggregationIr[] | undefined, setValuesColId?: string): void {
  const refusals: Refusal[] = [];
  if (setValuesColId !== undefined) {
    const field = schema.fields.get(setValuesColId);
    if (field === undefined) refusals.push({ reason: "unknown-field", message: `'${setValuesColId}' (setValuesRequest.colId) is not a declared field.` });
    else if (!field.filterable) refusals.push({ reason: "field-not-filterable", message: `'${setValuesColId}' (setValuesRequest.colId) is declared filterable: false.` });
  }
  const consumed = group?.groupKeys.length ?? 0;
  (group?.groupCols ?? []).forEach((colId, i) => {
    const field = schema.fields.get(colId);
    if (field === undefined) {
      refusals.push({ reason: "unknown-field", message: `'${colId}' (rowGroupCols) is not a declared field.` });
      return;
    }
    if (!field.groupable) refusals.push({ reason: "unknown-field", message: `'${colId}' (rowGroupCols) is declared groupable: false.` });
    // A consumed key becomes a drill-down predicate, so it is held to the filterable flag; an unconsumed group column is not.
    if (i < consumed && !field.filterable) refusals.push({ reason: "field-not-filterable", message: `'${colId}' (rowGroupCols) is a drill-down key and is declared filterable: false.` });
  });
  for (const aggregation of aggregations ?? []) {
    const field = schema.fields.get(aggregation.field);
    if (field === undefined) refusals.push({ reason: "unknown-field", message: `'${aggregation.field}' (valueCols) is not a declared field.` });
    else if (!field.aggregatable.includes(aggregation.func)) refusals.push({ reason: "unknown-field", message: `'${aggregation.field}' (valueCols): '${aggregation.func}' is not in its declared aggregatable set.` });
  }
  const error = allowlistRefusal(refusals);
  if (error !== undefined) throw error;
}

function fieldsOf(node: Node | undefined, into: Set<string> = new Set()): Set<string> {
  if (node === undefined) return into;
  if (node.type === "comparison") into.add(node.field);
  else if (node.type === "not") fieldsOf(node.node, into);
  else node.nodes.forEach((child) => fieldsOf(child, into));
  return into;
}

function strip(node: Node | undefined, fields: ReadonlySet<string>): Node | undefined {
  if (node === undefined || fields.size === 0) return node;
  if (node.type === "comparison") return fields.has(node.field) ? undefined : node;
  if (node.type === "not") {
    const inner = strip(node.node, fields);
    return inner === undefined ? undefined : { type: "not", node: inner };
  }
  const kept = node.nodes.map((child) => strip(child, fields)).filter((child): child is Node => child !== undefined);
  if (kept.length === 0) return undefined;
  return kept.length === 1 ? kept[0] : { type: node.type, nodes: kept };
}

/** SC-1 and SC-2 over the filter: refused in strict mode, stripped in lenient mode. */
function allowlistFilter(filter: Node | undefined, schema: GridSchema): Node | undefined {
  const refusals: Refusal[] = [];
  const stripped = new Set<string>();
  for (const colId of fieldsOf(filter)) {
    const field = schema.fields.get(colId);
    if (field === undefined) refusals.push({ reason: "unknown-field", message: `The column '${colId}' is not a declared field of the schema.` });
    else if (!field.filterable) refusals.push({ reason: "field-not-filterable", message: `The column '${colId}' is declared filterable: false.` });
    else continue;
    stripped.add(colId);
  }
  if (schema.mode !== "lenient") {
    const error = allowlistRefusal(refusals);
    if (error !== undefined) throw error;
  }
  return strip(filter, stripped);
}

function drillDownOf(group: GroupSpecIr | undefined): Node | undefined {
  const predicates: Node[] = (group?.groupKeys ?? []).map((value, i) => ({ type: "comparison", field: group!.groupCols[i]!, op: "eq", value }));
  if (predicates.length === 0) return undefined;
  return predicates.length === 1 ? predicates[0] : { type: "and", nodes: predicates };
}

function both(a: Node | undefined, b: Node | undefined): Node | undefined {
  if (a === undefined) return b;
  if (b === undefined) return a;
  return { type: "and", nodes: [a, b] };
}

function limitError(reason: RejectionReason, message: string): CompileError {
  return new CompileError("LimitExceeded", message, { rejectedAt: "resourceLimits", reason });
}

/** SEC-3 over the whole predicate, drill-down included: the first limit broken is the one reported. */
function checkLimits(filter: Node | undefined, page: PageIr, limits: Limits): void {
  let inValues: number | undefined;
  const walk = (node: Node): { depth: number; leaves: number } => {
    if (node.type === "comparison") {
      if (node.values !== undefined && node.values.length > limits.maxInValues && inValues === undefined) inValues = node.values.length;
      return { depth: 1, leaves: 1 };
    }
    const children = node.type === "not" ? [node.node] : node.nodes;
    let depth = 0;
    let leaves = 0;
    for (const child of children) {
      const measured = walk(child);
      depth = Math.max(depth, measured.depth);
      leaves += measured.leaves;
    }
    return { depth: depth + 1, leaves };
  };
  const { depth, leaves } = filter === undefined ? { depth: 0, leaves: 0 } : walk(filter);
  if (inValues !== undefined) throw limitError("max-in-values-exceeded", `A set condition has ${inValues} values; the limit is ${limits.maxInValues}.`);
  if (depth > limits.maxDepth) throw limitError("max-depth-exceeded", `The filter tree is ${depth} levels deep; the limit is ${limits.maxDepth}.`);
  if (leaves > limits.maxLeaves) throw limitError("max-leaves-exceeded", `The filter has ${leaves} conditions; the limit is ${limits.maxLeaves}.`);
  if (page.mode === "range" && page.endRow - page.startRow > limits.maxPageSize) {
    throw limitError("max-page-size-exceeded", `A page of ${page.endRow - page.startRow} rows is above the limit of ${limits.maxPageSize}.`);
  }
}

const INT64_MIN = -(2n ** 63n);
const INT64_MAX = 2n ** 63n - 1n;
const DECIMAL = /^-?[0-9]+(\.[0-9]+)?$/;
const DATE = /^([0-9]{4})-([0-9]{2})-([0-9]{2})$/;

function uncoercible(field: string, type: string, value: TypedValueIr): CompileError {
  const shown = "value" in value ? String(value.value).slice(0, 64) : "null";
  return new CompileError("InvalidRequest", `The value '${shown}' of '${field}' cannot be read as ${type}.`, { rejectedAt: "typeCoercion", reason: "uncoercible-value" });
}

function parseText(raw: string, type: Field["type"]): TypedValueIr | undefined {
  const text = raw.trim();
  switch (type) {
    case "int64": {
      if (!/^[+-]?[0-9]+$/.test(text)) return undefined;
      const big = BigInt(text);
      if (big < INT64_MIN || big > INT64_MAX) return undefined;
      return { type: "int64", value: Number.isSafeInteger(Number(big)) ? Number(big) : big.toString() };
    }
    case "decimal":
      return DECIMAL.test(raw) && raw.length <= 128 ? { type: "decimal", value: raw } : undefined;
    case "double": {
      if (text.length === 0 || [...text].some((c) => !"0123456789.eE+-".includes(c))) return undefined;
      const parsed = Number(text);
      return Number.isFinite(parsed) ? { type: "double", value: parsed } : undefined;
    }
    case "boolean": {
      const lower = text.toLowerCase();
      return lower === "true" || lower === "false" ? { type: "boolean", value: lower === "true" } : undefined;
    }
    case "date": {
      const match = DATE.exec(raw);
      return match !== null && validCalendar(Number(match[1]), Number(match[2]), Number(match[3])) ? { type: "date", value: raw } : undefined;
    }
    case "datetime":
      return isIsoInstant(raw) ? { type: "datetime", value: raw, zone: "UTC" } : undefined;
    default:
      return undefined;
  }
}

function coerceValue(value: TypedValueIr, field: string, type: Field["type"]): TypedValueIr {
  if (value.type === "null" || value.type === type) return value;
  if (value.type === "string") {
    const parsed = parseText(value.value, type);
    if (parsed !== undefined) return parsed;
  }
  throw uncoercible(field, type, value);
}

function coerce(node: Node, schema: GridSchema): Node {
  if (node.type === "not") return { type: "not", node: coerce(node.node, schema) };
  if (node.type !== "comparison") return { type: node.type, nodes: node.nodes.map((child) => coerce(child, schema)) };
  const type = schema.fields.get(node.field)!.type;
  const one = (value: TypedValueIr | undefined) => (value === undefined ? undefined : coerceValue(value, node.field, type));
  const value = one(node.value);
  const from = one(node.from);
  const to = one(node.to);
  const values = node.values?.map((item) => coerceValue(item, node.field, type));
  const next: ComparisonIr = { ...node, ...(value === undefined ? {} : { value }), ...(from === undefined ? {} : { from }), ...(to === undefined ? {} : { to }), ...(values === undefined ? {} : { values }) };
  return next;
}

/** A group key is already typed on the wire: it must match its column's declared type exactly, and is never repaired. */
function checkDeclaredTypes(node: Node | undefined, schema: GridSchema): void {
  if (node === undefined) return;
  if (node.type === "comparison") {
    const type = schema.fields.get(node.field)!.type;
    for (const value of [node.value, node.from, node.to, ...(node.values ?? [])]) {
      if (value !== undefined && value.type !== "null" && value.type !== type) throw uncoercible(node.field, type, value);
    }
  } else if (node.type === "not") checkDeclaredTypes(node.node, schema);
  else node.nodes.forEach((child) => checkDeclaredTypes(child, schema));
}

/** A row request after the allowlist, the limits and the coercion: the IR with its filter checked and typed. */
export function processRow(ir: Ir, schema: GridSchema, limits: Readonly<Limits> = DEFAULT_LIMITS): Ir {
  structuralColumns(schema, ir.group, ir.aggregations);
  const allowed = allowlistFilter(ir.filter, schema);
  const drillDown = drillDownOf(ir.group);
  checkLimits(both(drillDown, allowed), ir.page, limits);
  const coerced = allowed === undefined ? undefined : coerce(allowed, schema);
  checkDeclaredTypes(drillDown, schema);
  const next: { -readonly [K in keyof Ir]: Ir[K] } = { ...ir };
  delete next.filter;
  if (coerced !== undefined) next.filter = coerced;
  return next;
}

/** BM-3 and GRP-6: the filter of a distinct-values query and the cap it compiles with. */
export function processSetValues(parsed: ParsedSetValues, schema: GridSchema, limits: Readonly<Limits> = DEFAULT_LIMITS): { filter?: Node; rowLimit: number } {
  const { colId, searchPrefix, limit } = parsed.setValues;
  structuralColumns(schema, undefined, undefined, colId);
  const scoped = strip(mergeFilters(parsed.nativeFilter, parsed.customFilters), new Set([colId]));
  let prefix: Node | undefined;
  if (searchPrefix !== undefined) {
    const field = schema.fields.get(colId)!;
    if (field.type !== "string") throw uncoercible(colId, field.type, { type: "string", value: searchPrefix });
    prefix = { type: "comparison", field: colId, op: "startsWith", value: { type: "string", value: searchPrefix } };
  }
  const allowed = allowlistFilter(both(scoped, prefix), schema);
  checkLimits(allowed, { mode: "none" }, limits);
  const filter = allowed === undefined ? undefined : coerce(allowed, schema);
  const rowLimit = Math.min(limit ?? limits.defaultSetValuesResults, limits.maxSetValuesResults);
  return { ...(filter === undefined ? {} : { filter }), rowLimit };
}
