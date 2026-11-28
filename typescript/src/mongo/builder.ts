import { CompileError } from "../errors.js";
import type { AggregationIr, ComparisonIr, FilterNodeIr, GroupSpecIr, PageIr, SortItemIr } from "../ir.js";
import type { Field, GridSchema } from "../schema.js";
import { effectiveSort, groupedSort } from "../sort.js";
import { doc, type Doc, type Value } from "../doc/ordered.js";
import { columnId, outputName, resolveGrouping, type GroupingPlan } from "../sql/grouping.js";
import { blankCondition, caseSensitivity, isNullInclusive, orderingCaseSensitivity, type CaseMechanism } from "../sql/semantics.js";
import type { CaseMode } from "../sql/dialect.js";
import { encodeEjson } from "./ejson.js";
import { escapeRegex } from "./regex.js";

export interface MongoRequest {
  readonly schema: GridSchema;
  readonly filter?: FilterNodeIr | undefined;
  readonly sort?: readonly SortItemIr[] | undefined;
  readonly page: PageIr;
  /** EXP-1(b): the export columns, in order. */
  readonly projection?: readonly string[] | undefined;
  readonly group?: GroupSpecIr | undefined;
  readonly aggregations?: readonly AggregationIr[] | undefined;
  readonly maxQueryTimeMs?: number | undefined;
}

export interface MongoQuery {
  readonly pipeline: readonly Doc[];
  readonly collation?: Doc;
  readonly maxTimeMs?: number;
}

const GROUP_KEY_BUCKET = "__groupNullBucket";
const GROUP_KEY_PATH = "_id";
const COUNT_DROPPED = new Set(["$skip", "$limit", "$project", "$sort", "$addFields", "$unset"]);
const SCALAR_OPERATOR: Readonly<Record<string, string>> = { eq: "$eq", neq: "$ne", gt: "$gt", gte: "$gte", lt: "$lt", lte: "$lte" };

class CollationSink {
  required = false;
  exactStringComparisons = false;
  readonly exactStringSortKeys: string[] = [];
}

interface Context {
  readonly schema: GridSchema;
  readonly sink: CollationSink;
  readonly groupKeyMatch?: boolean;
  readonly exactStringComparison?: boolean;
}

interface SortKeyPlan {
  readonly bucket: string;
  readonly path: string;
  readonly direction: "asc" | "desc";
  readonly nulls: "first" | "last";
  readonly exactField?: string;
}

function failure(message: string): CompileError {
  return new CompileError("InvalidRequest", message);
}

function fieldOf(name: string, context: Context): Field {
  const field = context.schema.fields.get(name);
  if (field === undefined) throw failure(`Field '${name}' is not declared in the GridSchema: the allowlist runs before a compiler.`);
  return field;
}

/** The only place a schema name becomes a document key or a field reference: the field's `mongoPath`, else its name. */
function pathOf(name: string, context: Context): string {
  return fieldOf(name, context).mongoPath ?? name;
}

const reference = (path: string): Value => `$${path}`;
const isNull = (value: Value): Doc => doc(["$eq", [value, null]]);
const expr = (value: Value): Doc => doc(["$expr", value]);
const literal = (value: Value): Doc => doc(["$literal", value]);
const stage = (name: string, body: Value): Doc => doc([name, body]);

function recordCollationNeed(mode: CaseMode, context: Context): void {
  if (mode === "insensitive") context.sink.required = true;
}

function resolveMode(field: Field, fieldName: string, op: string, family: CaseMechanism, context: Context): CaseMode {
  let mode: CaseMode;
  if (context.groupKeyMatch === true) {
    mode = orderingCaseSensitivity(field, true);
  } else {
    const decision = caseSensitivity(field, op);
    if (decision.mode === "insensitive" && decision.mechanism !== family) {
      throw failure(`Operator '${op}' on field '${fieldName}' resolves to the '${decision.mechanism}' case-insensitivity mechanism, but is rendered through the '${family}' family: SEM-1 requires one mechanism per field.`);
    }
    mode = decision.mode;
  }
  if (family === "collation") {
    recordCollationNeed(mode, context);
    if (mode === "sensitive") context.sink.exactStringComparisons = true;
  }
  return mode;
}

const needsExactEscape = (mode: CaseMode, context: Context): boolean => context.exactStringComparison === true && mode === "sensitive";

function requireValue(node: ComparisonIr): NonNullable<ComparisonIr["value"]> {
  if (node.value === undefined) throw failure(`Operator '${node.op}' on field '${node.field}' requires 'value'.`);
  return node.value;
}

function scalar(path: string, field: Field, fieldName: string, op: string, value: NonNullable<ComparisonIr["value"]>, context: Context): Doc {
  const mode = resolveMode(field, fieldName, op, "collation", context);
  const encoded = encodeEjson(value, field, fieldName);
  const operator = SCALAR_OPERATOR[op]!;
  if (needsExactEscape(mode, context)) return expr(doc([operator, [reference(path), literal(encoded)]]));
  return doc([path, doc([operator, encoded])]);
}

function blank(path: string, field: Field, negated: boolean): Doc {
  if (blankCondition(field.type) === "nullOrEmptyString") return doc([path, doc([negated ? "$nin" : "$in", [null, ""]])]);
  return doc([path, negated ? doc(["$ne", null]) : null]);
}

function nullInclusive(predicate: Doc, op: string, path: string): Doc {
  return isNullInclusive(op) ? doc(["$or", [predicate, doc([path, null])]]) : predicate;
}

function anchored(op: string, escaped: string): string {
  if (op === "startsWith") return `^${escaped}`;
  return op === "endsWith" ? `${escaped}$` : escaped;
}

function substring(path: string, field: Field, node: ComparisonIr, context: Context): Doc {
  const mode = resolveMode(field, node.field, node.op, "patternMatch", context);
  if (field.type !== "string") throw failure(`Field '${node.field}' is declared '${field.type}', but '${node.op}' is a substring match and needs a string field.`);
  const value = requireValue(node);
  if (value.type !== "string") throw failure(`Operator '${node.op}' on field '${node.field}' needs a string value: the coercion stage runs before a compiler.`);
  const escaped = escapeRegex(value.value);
  const pattern = anchored(node.op, escaped);
  const regex = mode === "insensitive" ? doc(["$regex", pattern], ["$options", "i"]) : doc(["$regex", pattern]);
  return doc([path, node.op === "notContains" ? doc(["$not", regex]) : regex]);
}

function setCondition(path: string, field: Field, node: ComparisonIr, context: Context): Doc {
  const mode = resolveMode(field, node.field, node.op, "collation", context);
  const values = node.values;
  if (values === undefined) throw failure(`Operator '${node.op}' on field '${node.field}' requires 'values'.`);
  const negated = node.op === "notIn";
  if (needsExactEscape(mode, context)) {
    const members = values.map((value) => literal(encodeEjson(value, field, node.field)));
    const membership = doc(["$in", [reference(path), members]]);
    return expr(negated ? doc(["$not", [membership]]) : membership);
  }
  return doc([path, doc([negated ? "$nin" : "$in", values.map((value) => encodeEjson(value, field, node.field))])]);
}

function rangeCondition(path: string, field: Field, node: ComparisonIr, context: Context): Doc {
  if (node.from === undefined || node.to === undefined || node.fromInclusive === undefined || node.toInclusive === undefined) {
    throw failure(`Operator 'inRange' on field '${node.field}' requires 'from', 'to', 'fromInclusive' and 'toInclusive'.`);
  }
  const lowerOp = node.fromInclusive ? "gte" : "gt";
  const upperOp = node.toInclusive ? "lte" : "lt";
  const mode = resolveMode(field, node.field, lowerOp, "collation", context);
  const lower = encodeEjson(node.from, field, node.field);
  const upper = encodeEjson(node.to, field, node.field);
  if (needsExactEscape(mode, context)) {
    return expr(doc(["$and", [doc([SCALAR_OPERATOR[lowerOp]!, [reference(path), literal(lower)]]), doc([SCALAR_OPERATOR[upperOp]!, [reference(path), literal(upper)]])]]));
  }
  return doc([path, doc([SCALAR_OPERATOR[lowerOp]!, lower], [SCALAR_OPERATOR[upperOp]!, upper])]);
}

function comparison(node: ComparisonIr, context: Context): Doc {
  const field = fieldOf(node.field, context);
  const path = pathOf(node.field, context);
  switch (node.op) {
    case "blank":
      return blank(path, field, false);
    case "notBlank":
      return blank(path, field, true);
    case "true":
      return scalar(path, field, node.field, "eq", { type: "boolean", value: true }, context);
    case "false":
      return scalar(path, field, node.field, "eq", { type: "boolean", value: false }, context);
    case "eq":
    case "neq":
    case "gt":
    case "gte":
    case "lt":
    case "lte":
      return nullInclusive(scalar(path, field, node.field, node.op, requireValue(node), context), node.op, path);
    case "contains":
    case "notContains":
    case "startsWith":
    case "endsWith":
      return nullInclusive(substring(path, field, node, context), node.op, path);
    case "in":
    case "notIn":
      if (node.values?.length === 0) return doc([path, doc([node.op === "notIn" ? "$nin" : "$in", []])]);
      return nullInclusive(setCondition(path, field, node, context), node.op, path);
    case "inRange":
      return rangeCondition(path, field, node, context);
    default:
      throw failure(`Unknown comparison operator '${node.op}'.`);
  }
}

function fieldsIn(node: FilterNodeIr, into: Set<string> = new Set()): Set<string> {
  if (node.type === "comparison") into.add(node.field);
  else if (node.type === "not") fieldsIn(node.node, into);
  else node.nodes.forEach((child) => fieldsIn(child, into));
  return into;
}

function node(filter: FilterNodeIr, context: Context): Doc {
  switch (filter.type) {
    case "and":
    case "or":
      return doc([filter.type === "and" ? "$and" : "$or", filter.nodes.map((child) => node(child, context))]);
    case "not": {
      const clauses: Value[] = [doc(["$nor", [node(filter.node, context)]])];
      for (const name of fieldsIn(filter.node)) clauses.push(doc([pathOf(name, context), null]));
      return doc(["$or", clauses]);
    }
    default:
      return comparison(filter, context);
  }
}

function match(filter: FilterNodeIr | undefined, drillDown: FilterNodeIr | undefined, context: Context): Doc | undefined {
  const path = drillDown === undefined ? undefined : node(drillDown, { ...context, groupKeyMatch: true });
  const user = filter === undefined ? undefined : node(filter, context);
  if (path !== undefined && user !== undefined) return doc(["$and", [path, user]]);
  return path ?? user;
}

function accumulator(aggregation: AggregationIr, context: Context): Doc {
  const ref = reference(pathOf(aggregation.field, context));
  switch (aggregation.func) {
    case "sum":
      return doc(["$sum", ref]);
    case "min":
      return doc(["$min", ref]);
    case "max":
      return doc(["$max", ref]);
    case "avg":
      return doc(["$avg", ref]);
    default:
      return doc(["$sum", doc(["$cond", [isNull(ref), 0, 1]])]);
  }
}

function groupStage(groupColumn: string, aggregations: readonly AggregationIr[], context: Context): Doc {
  const group: Doc = doc(["_id", reference(pathOf(groupColumn, context))]);
  for (const aggregation of aggregations) {
    const output = outputName(aggregation);
    if (group.has(output)) {
      throw failure(`An aggregation resolves to the output name '${output}', which collides with another aggregation's output name or the grouped level's own bucket key: a $group stage is a document, so the later one would silently replace the earlier.`);
    }
    group.set(output, accumulator(aggregation, context));
  }
  return group;
}

function projection(fields: readonly string[], context: Context): Doc {
  const body: Doc = doc();
  for (const name of fields) {
    const path = pathOf(name, context);
    body.set(name, path === name ? 1 : reference(path));
  }
  body.set("_id", 0);
  return body;
}

function groupedTarget(sortField: string, plan: GroupingPlan & { groupColumn: string }, context: Context): { bucket: string; path: string; field: Field } {
  const matches = plan.aggregations.filter((aggregation) => columnId(aggregation) === sortField);
  if (matches.length > 1) throw failure(`Ambiguous $sort target for a grouped level: '${sortField}' matches ${matches.length} aggregations (${matches.map((a) => a.func).join(", ")}). Give each valueCol a distinct id.`);
  if (matches.length > 0 && sortField === plan.groupColumn) throw failure(`Ambiguous $sort target for a grouped level: '${sortField}' is this level's group column and the id of an aggregation. Give the aggregation a distinct id.`);
  const [first] = matches;
  if (first !== undefined) {
    const output = outputName(first);
    return { bucket: `__${output}NullBucket`, path: output, field: fieldOf(first.field, context) };
  }
  if (sortField === plan.groupColumn) return { bucket: GROUP_KEY_BUCKET, path: GROUP_KEY_PATH, field: fieldOf(sortField, context) };
  throw failure(`A grouped query can be ordered only by its group column ('${plan.groupColumn}') or by one of its aggregations, not by '${sortField}'.`);
}

function sortPlan(request: MongoRequest, plan: GroupingPlan | undefined, context: Context): SortKeyPlan[] {
  const items = (request.sort ?? []).map((item) => ({ field: item.field, direction: item.direction, nulls: item.nullsPosition }));
  const groupColumn = plan?.groupColumn;
  const level = plan !== undefined && groupColumn !== undefined ? { ...plan, groupColumn } : undefined;
  const keys = level === undefined ? effectiveSort(items, request.schema) : groupedSort(items, level.groupColumn, level.aggregations.map((aggregation) => columnId(aggregation)));
  const result: SortKeyPlan[] = [];
  for (const key of keys) {
    const target = level === undefined ? { bucket: `__${key.field}NullBucket`, path: pathOf(key.field, context), field: fieldOf(key.field, context) } : groupedTarget(key.field, level, context);
    const mode = orderingCaseSensitivity(target.field, level !== undefined, key.appended);
    recordCollationNeed(mode, context);
    if (mode === "sensitive") context.sink.exactStringSortKeys.push(key.field);
    const repeats = key.appended && result.some((earlier) => earlier.path === target.path);
    result.push({ bucket: target.bucket, path: target.path, direction: key.direction, nulls: key.nulls, ...(repeats ? { exactField: `__${key.field}ExactKey` } : {}) });
  }
  return result;
}

function claim(claimed: Map<string, string>, key: SortKeyPlan): void {
  const owner = claimed.get(key.bucket);
  if (owner === undefined) {
    claimed.set(key.bucket, key.path);
    return;
  }
  throw failure(
    owner === key.path
      ? `The sort names '${key.path}' twice outside SEM-6's exact tiebreaker (MDB-10): a $sort document holds a path once.`
      : `The sort keys '${key.path}' and '${owner}' both emulate null placement through the bucket field '${key.bucket}', which can hold only one of them; '${GROUP_KEY_BUCKET}' is reserved for a grouped level's own _id key, so rename the aggregation whose output name is 'group'.`,
  );
}

/** MDB-8 and MDB-10: the null-bucket `$addFields`, the `$sort`, and the `$unset` that removes the helper fields. */
function sortStages(stages: Doc[], keys: readonly SortKeyPlan[]): void {
  const buckets: Doc = doc();
  const sort: Doc = doc();
  const unset: string[] = [];
  const claimed = new Map<string, string>();
  for (const key of keys) {
    const exact = key.exactField;
    if (exact !== undefined) {
      if (claimed.has(exact)) throw failure(`The sort key '${key.path}' needs the exact-tiebreaker field '${exact}' more than once (MDB-10).`);
      claimed.set(exact, key.path);
      buckets.set(exact, doc(["$toHashedIndexKey", reference(key.path)]));
      sort.set(exact, key.direction === "asc" ? 1 : -1);
      unset.push(exact);
      continue;
    }
    claim(claimed, key);
    buckets.set(key.bucket, doc(["$cond", [isNull(reference(key.path)), 1, 0]]));
    sort.set(key.bucket, key.nulls === "last" ? 1 : -1);
    sort.set(key.path, key.direction === "asc" ? 1 : -1);
    unset.push(key.bucket);
  }
  stages.push(stage("$addFields", buckets), stage("$sort", sort), stage("$unset", unset.length === 1 ? unset[0]! : unset));
}

function compose(request: MongoRequest, context: Context): Doc[] {
  const plan = resolveGrouping(request.group, request.aggregations);
  const stages: Doc[] = [];
  const matched = match(request.filter, plan?.drillDown, context);
  if (matched !== undefined) stages.push(stage("$match", matched));
  if (plan?.groupColumn !== undefined) stages.push(stage("$group", groupStage(plan.groupColumn, plan.aggregations, context)));
  sortStages(stages, sortPlan(request, plan, context));
  if (request.page.mode === "range") stages.push(stage("$skip", request.page.startRow), stage("$limit", request.page.endRow - request.page.startRow));
  if (plan !== undefined && plan.groupColumn === undefined) stages.push(stage("$project", projection([...request.schema.fields.keys()], context)));
  else if (plan === undefined && request.projection !== undefined) stages.push(stage("$project", projection(request.projection, context)));
  return stages;
}

function assemble(stages: Doc[], sink: CollationSink, suppress: boolean): MongoQuery {
  const collation = sink.required && !suppress ? doc(["locale", "en"], ["strength", 2]) : undefined;
  return { pipeline: stages, ...(collation === undefined ? {} : { collation }) };
}

function pipelineOf(request: MongoRequest): MongoQuery {
  if (request.projection?.length === 0) throw failure("An export projection is empty: leave it out for the default.");
  if (request.projection !== undefined && request.group !== undefined) throw failure("A request carries both a group and an export projection: an export discards group state before it gets here.");
  const suppress = request.group !== undefined;
  const sink = new CollationSink();
  const stages = compose(request, { schema: request.schema, sink });
  if (!sink.required || suppress) return assemble(stages, sink, suppress);
  if (sink.exactStringSortKeys.length > 0) {
    throw failure(`The sort orders '${sink.exactStringSortKeys.join("', '")}', declared caseSensitivity: "sensitive", while another construct in the same request needs SEM-1's case-insensitive collation; MongoDB's collation is a query-level option with no per-stage form (MDB-9). Split the request, or declare the fields with one case sensitivity.`);
  }
  if (!sink.exactStringComparisons) return assemble(stages, sink, suppress);
  const exactSink = new CollationSink();
  return assemble(compose(request, { schema: request.schema, sink: exactSink, exactStringComparison: true }), exactSink, suppress);
}

function requirePositiveLimit(limit: number | undefined): void {
  if (limit !== undefined && limit <= 0) throw failure(`maxQueryTimeMs must be positive when set, not ${limit} (TL-4).`);
}

/** The page query. TL-3: an unpaginated request never carries the time limit. */
export function build(request: MongoRequest): MongoQuery {
  requirePositiveLimit(request.maxQueryTimeMs);
  const query = pipelineOf(request);
  return request.page.mode === "none" || request.maxQueryTimeMs === undefined ? query : { ...query, maxTimeMs: request.maxQueryTimeMs };
}

/** CNT-1 to CNT-8: the pipeline of the request without paging, projection and sort, ending in `$count`. */
export function buildCount(request: MongoRequest): MongoQuery {
  requirePositiveLimit(request.maxQueryTimeMs);
  const query = pipelineOf({ ...request, page: { mode: "none" }, projection: undefined, sort: undefined });
  const stages = query.pipeline.filter((item) => !COUNT_DROPPED.has([...item.keys()][0]!));
  stages.push(stage("$count", "count"));
  return { ...query, pipeline: stages, ...(request.maxQueryTimeMs === undefined ? {} : { maxTimeMs: request.maxQueryTimeMs }) };
}

export interface MongoSetValuesRequest {
  readonly schema: GridSchema;
  readonly colId: string;
  readonly filter?: FilterNodeIr | undefined;
  readonly rowLimit: number;
  readonly maxQueryTimeMs?: number | undefined;
}

/** GRP-6: the distinct values of one column, ordered by it, capped. */
export function buildSetValues(request: MongoSetValuesRequest): MongoQuery {
  requirePositiveLimit(request.maxQueryTimeMs);
  if (!Number.isInteger(request.rowLimit) || request.rowLimit <= 0) throw failure(`A set-values row limit must be positive, not ${request.rowLimit}.`);
  const sink = new CollationSink();
  const context: Context = { schema: request.schema, sink };
  const path = pathOf(request.colId, context);
  const stages: Doc[] = [];
  const matched = match(request.filter, undefined, context);
  if (matched !== undefined) stages.push(stage("$match", matched));
  stages.push(stage("$group", doc(["_id", reference(path)])));
  sortStages(stages, [{ bucket: GROUP_KEY_BUCKET, path: GROUP_KEY_PATH, direction: "asc", nulls: "last" }]);
  stages.push(stage("$limit", request.rowLimit));
  const query = assemble(stages, sink, true);
  return request.maxQueryTimeMs === undefined ? query : { ...query, maxTimeMs: request.maxQueryTimeMs };
}

/** The artifact: the bare pipeline, or `{pipeline, collation, maxTimeMS}` with the members in that order (MDB-7, TL-1). */
export function toArtifact(query: MongoQuery): Value {
  if (query.collation === undefined && query.maxTimeMs === undefined) return [...query.pipeline];
  const artifact: Doc = doc(["pipeline", [...query.pipeline]]);
  if (query.collation !== undefined) artifact.set("collation", query.collation);
  if (query.maxTimeMs !== undefined) artifact.set("maxTimeMS", query.maxTimeMs);
  return artifact;
}
