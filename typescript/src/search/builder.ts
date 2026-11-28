import { CompileError } from "../errors.js";
import type { AggregationIr, ComparisonIr, FilterNodeIr, GroupSpecIr, PageIr, SortItemIr } from "../ir.js";
import type { Field, GridSchema } from "../schema.js";
import { effectiveSort, groupedSort } from "../sort.js";
import { doc, type Doc, type Value } from "../doc/ordered.js";
import { columnId, outputName, resolveGrouping } from "../sql/grouping.js";
import { blankCondition, caseSensitivity, isNullInclusive, orderingCaseSensitivity, type CaseMechanism } from "../sql/semantics.js";
import type { CaseMode } from "../sql/dialect.js";
import { escapeSearchRegex, escapeWildcard } from "./escape.js";
import { encodeSearch, formatFor } from "./json.js";

export interface SearchRequest {
  readonly schema: GridSchema;
  readonly filter?: FilterNodeIr | undefined;
  readonly sort?: readonly SortItemIr[] | undefined;
  readonly page: PageIr;
  readonly group?: GroupSpecIr | undefined;
  readonly aggregations?: readonly AggregationIr[] | undefined;
  readonly maxQueryTimeMs?: number | undefined;
}

export interface SearchQuery {
  readonly query?: Doc;
  readonly sort?: readonly Value[];
  readonly from?: number;
  readonly size?: number;
  readonly aggs?: Doc;
  readonly timeoutMs?: number;
}

interface Target {
  readonly config: Field;
  readonly raw: string;
  readonly keyword: string;
  readonly normalized: string | undefined;
}

interface Context {
  readonly schema: GridSchema;
  readonly groupKeyMatch?: boolean;
}

function failure(message: string): CompileError {
  return new CompileError("InvalidRequest", message);
}

/** SC-4, OSE-6: the three search names of a field. Only these, from the schema, ever become a key. */
function resolve(name: string, context: Context): Target {
  const config = context.schema.fields.get(name);
  if (config === undefined) throw failure(`Field '${name}' is not declared in the GridSchema: the allowlist runs before a compiler.`);
  const raw = config.search?.field ?? name;
  return { config, raw, keyword: config.search?.keywordSubField ?? raw, normalized: config.search?.normalizedSubField };
}

const mustNot = (clause: Value): Doc => doc(["bool", doc(["must_not", clause])]);
const exists = (raw: string): Doc => doc(["exists", doc(["field", raw])]);
const should = (clauses: Value[]): Doc => doc(["bool", doc(["should", clauses], ["minimum_should_match", 1])]);
const termOf = (key: string, body: Value): Doc => doc(["term", doc([key, body])]);

function fieldsIn(node: FilterNodeIr, into: Set<string> = new Set()): Set<string> {
  if (node.type === "comparison") into.add(node.field);
  else if (node.type === "not") fieldsIn(node.node, into);
  else node.nodes.forEach((child) => fieldsIn(child, into));
  return into;
}

function requireValue(node: ComparisonIr): NonNullable<ComparisonIr["value"]> {
  if (node.value === undefined) throw failure(`Operator '${node.op}' on field '${node.field}' requires 'value'.`);
  return node.value;
}

function resolveMode(target: Target, fieldName: string, op: string, family: CaseMechanism, context: Context): CaseMode {
  if (context.groupKeyMatch === true) return orderingCaseSensitivity(target.config, true);
  const decision = caseSensitivity(target.config, op);
  if (decision.mode === "insensitive" && decision.mechanism !== family) {
    throw failure(`Operator '${op}' on field '${fieldName}' resolves to the '${decision.mechanism}' case-insensitivity mechanism, but is rendered through the '${family}' family: SEM-1 requires one mechanism per field.`);
  }
  return decision.mode;
}

function blank(target: Target): Doc {
  if (blankCondition(target.config.type) === "nullOrEmptyString") return should([mustNot(exists(target.raw)), termOf(target.keyword, doc(["value", ""]))]);
  return mustNot(exists(target.raw));
}

function nullInclusive(affirmative: Doc, op: string, target: Target): Doc {
  return isNullInclusive(op) ? should([mustNot(affirmative), mustNot(exists(target.raw))]) : affirmative;
}

function term(target: Target, fieldName: string, op: string, value: NonNullable<ComparisonIr["value"]>, context: Context): Doc {
  const mode = resolveMode(target, fieldName, op, "collation", context);
  const encoded = encodeSearch(value, target.config, fieldName);
  if (target.config.type !== "string") return termOf(target.raw, encoded);
  const body: Doc = doc(["value", encoded]);
  if (mode === "insensitive") body.set("case_insensitive", true);
  return termOf(target.keyword, body);
}

function setCondition(target: Target, node: ComparisonIr, context: Context): Doc {
  const mode = resolveMode(target, node.field, node.op, "collation", context);
  const values = node.values;
  if (values === undefined) throw failure(`Operator '${node.op}' on field '${node.field}' requires 'values'.`);
  const isText = target.config.type === "string";
  if (isText && mode === "insensitive") {
    return should(values.map((value) => termOf(target.keyword, doc(["value", encodeSearch(value, target.config, node.field)], ["case_insensitive", true]))));
  }
  return doc(["terms", doc([isText ? target.keyword : target.raw, values.map((value) => encodeSearch(value, target.config, node.field))])]);
}

/** OSE-6, SEM-1: the name a range or a sort addresses. A case-insensitive text field must have paid for a normalised sub-field. */
function orderingTarget(target: Target, mode: CaseMode, fieldName: string, construct: string): string {
  if (target.config.type !== "string") return target.raw;
  if (mode !== "insensitive") return target.keyword;
  if (target.normalized === undefined) {
    throw failure(`Field '${fieldName}' is a case-insensitive string and this ${construct} orders by it, but the schema declares no 'physical.search.normalizedSubField': a range query has no case-insensitive parameter in the pinned subset, so case-insensitive ordering is an index-time cost this field has not paid. Declare the sub-field, or declare the field caseSensitivity: "sensitive".`);
  }
  return target.normalized;
}

function rangeCondition(target: Target, node: ComparisonIr, context: Context): Doc {
  const body: Doc = doc();
  let mechanismOp = node.op;
  if (node.op === "inRange") {
    if (node.from === undefined || node.to === undefined || node.fromInclusive === undefined || node.toInclusive === undefined) {
      throw failure(`Operator 'inRange' on field '${node.field}' requires 'from', 'to', 'fromInclusive' and 'toInclusive'.`);
    }
    const lower = node.fromInclusive ? "gte" : "gt";
    const upper = node.toInclusive ? "lte" : "lt";
    body.set(lower, encodeSearch(node.from, target.config, node.field));
    body.set(upper, encodeSearch(node.to, target.config, node.field));
    mechanismOp = lower;
  } else {
    body.set(node.op, encodeSearch(requireValue(node), target.config, node.field));
  }
  const mode = resolveMode(target, node.field, mechanismOp, "collation", context);
  const format = formatFor(target.config.type);
  if (format !== undefined) body.set("format", format);
  return doc(["range", doc([orderingTarget(target, mode, node.field, "range query"), body])]);
}

function wildcardOf(op: string, escaped: string): string {
  if (op === "startsWith") return `${escaped}*`;
  return op === "endsWith" ? `*${escaped}` : `*${escaped}*`;
}

function substringCondition(target: Target, node: ComparisonIr, context: Context): Doc {
  if (target.config.type !== "string") throw failure(`Field '${node.field}' is declared '${target.config.type}', but '${node.op}' is a substring match and needs a string field.`);
  const mode = resolveMode(target, node.field, node.op, "patternMatch", context);
  const value = requireValue(node);
  if (value.type !== "string") throw failure(`Operator '${node.op}' on field '${node.field}' needs a string value: the coercion stage runs before a compiler.`);
  if (target.config.searchMode === "analyzed" && (node.op === "contains" || node.op === "notContains")) {
    if (mode !== "insensitive") {
      throw failure(`Field '${node.field}' declares searchMode 'analyzed' and caseSensitivity 'sensitive', and '${node.op}' has no rendering that satisfies both: a match is resolved by the field's own analyzer, which lowercases (SEM-1). Declare searchMode 'substring' or caseSensitivity 'insensitive'.`);
    }
    return doc(["match", doc([target.raw, doc(["query", value.value], ["operator", "and"])])]);
  }
  const escaped = escapeWildcard(value.value);
  const pattern = wildcardOf(node.op, escaped);
  const body: Doc = doc(["value", pattern]);
  if (mode === "insensitive") body.set("case_insensitive", true);
  return doc(["wildcard", doc([target.keyword, body])]);
}

function comparison(node: ComparisonIr, context: Context): Doc {
  const target = resolve(node.field, context);
  switch (node.op) {
    case "blank":
      return blank(target);
    case "notBlank":
      return mustNot(blank(target));
    case "true":
      return term(target, node.field, "eq", { type: "boolean", value: true }, context);
    case "false":
      return term(target, node.field, "eq", { type: "boolean", value: false }, context);
    case "eq":
      if (node.value?.type === "null") return mustNot(exists(target.raw));
      return nullInclusive(term(target, node.field, node.op, requireValue(node), context), node.op, target);
    case "neq":
      return nullInclusive(term(target, node.field, node.op, requireValue(node), context), node.op, target);
    case "gt":
    case "gte":
    case "lt":
    case "lte":
    case "inRange":
      return rangeCondition(target, node, context);
    case "contains":
    case "notContains":
    case "startsWith":
    case "endsWith":
      return nullInclusive(substringCondition(target, node, context), node.op, target);
    case "in":
    case "notIn":
      if (node.values?.length === 0) return doc([node.op === "notIn" ? "match_all" : "match_none", doc()]);
      return nullInclusive(setCondition(target, node, context), node.op, target);
    default:
      throw failure(`Unknown comparison operator '${node.op}'.`);
  }
}

function node(filter: FilterNodeIr, context: Context): Doc {
  switch (filter.type) {
    case "and":
      return doc(["bool", doc(["must", filter.nodes.map((child) => node(child, context))])]);
    case "or":
      return should(filter.nodes.map((child) => node(child, context)));
    case "not": {
      const clauses: Value[] = [doc(["bool", doc(["must_not", [node(filter.node, context)]])])];
      for (const name of fieldsIn(filter.node)) clauses.push(mustNot(exists(resolve(name, context).raw)));
      return should(clauses);
    }
    default:
      return comparison(filter, context);
  }
}

/** OSE-3: an ordinary row query is the bare tree; a bucket request wraps its conjuncts in `bool.filter`. */
function renderQuery(filter: FilterNodeIr | undefined, drillDown: FilterNodeIr | undefined, protocol: boolean, context: Context): Doc | undefined {
  if (!protocol) return filter === undefined ? undefined : node(filter, context);
  const clauses: Value[] = [];
  const conjuncts = (tree: FilterNodeIr, inner: Context) => (tree.type === "and" ? tree.nodes.forEach((child) => clauses.push(node(child, inner))) : clauses.push(node(tree, inner)));
  if (drillDown !== undefined) conjuncts(drillDown, { ...context, groupKeyMatch: true });
  if (filter !== undefined) conjuncts(filter, context);
  return clauses.length === 0 ? undefined : doc(["bool", doc(["filter", clauses])]);
}

function sortClauses(request: SearchRequest, context: Context): Value[] {
  const items = (request.sort ?? []).map((item) => ({ field: item.field, direction: item.direction, nulls: item.nullsPosition }));
  return effectiveSort(items, request.schema).map((key) => {
    const target = resolve(key.field, context);
    const mode = orderingCaseSensitivity(target.config, false, key.appended);
    return doc([orderingTarget(target, mode, key.field, "sort key"), doc(["order", key.direction], ["missing", key.nulls === "last" ? "_last" : "_first"])]);
  });
}

function requireOutputName(aggregation: AggregationIr): string {
  const name = outputName(aggregation);
  const legal = name.length > 0 && !/^\d/.test(name) && [...name].every((c) => /\w/.test(c));
  if (aggregation.alias === undefined && !legal) {
    throw failure(`The default output name '${name}' for the '${aggregation.func}' of '${aggregation.field}' is not a legal aggregation name: send an explicit alias (AG Grid's ColumnVO.id) for this column.`);
  }
  return name;
}

function requireAggregationName(colId: string, role: string): string {
  if ([...colId].some((c) => c === "[" || c === "]" || c === ">")) {
    throw failure(`The column '${colId}' names ${role}'s aggregation, but '[', ']' and '>' are reserved by the buckets_path syntax and both engines reject an aggregation name containing them.`);
  }
  return colId;
}

const AGGREGATION: Readonly<Record<AggregationIr["func"], string>> = { sum: "sum", min: "min", max: "max", avg: "avg", count: "value_count" };

function metrics(aggregations: readonly AggregationIr[], context: Context): Doc {
  const aggs: Doc = doc();
  for (const aggregation of aggregations) {
    const output = requireOutputName(aggregation);
    if (aggs.has(output)) throw failure(`Two aggregations resolve to the output name '${output}': an aggregation container is a JSON object, so the second would silently replace the first.`);
    aggs.set(output, doc([AGGREGATION[aggregation.func], doc(["field", resolve(aggregation.field, context).raw])]));
  }
  return aggs;
}

function groupFieldTarget(groupColumn: string, context: Context): string {
  const target = resolve(groupColumn, context);
  return target.config.type === "string" ? target.keyword : target.raw;
}

function bucketOrder(groupColumn: string, aggregations: readonly AggregationIr[], request: SearchRequest): "asc" | "desc" {
  const items = (request.sort ?? []).map((item) => ({ field: item.field, direction: item.direction, nulls: item.nullsPosition }));
  const keys = groupedSort(items, groupColumn, aggregations.map((aggregation) => columnId(aggregation)));
  for (const key of keys) {
    if (key.field === groupColumn) continue;
    if (aggregations.some((a) => columnId(a) === key.field)) {
      throw failure(`The grouped level on '${groupColumn}' is ordered by the aggregate '${key.field}', which a composite aggregation cannot express (OSE-11(c)): a bucket_sort would only reorder one page of group-key order.`);
    }
    throw failure(`A grouped query can be ordered only by its group column ('${groupColumn}'), but the request sorts on '${key.field}'.`);
  }
  if (keys.length !== 1) throw failure(`The grouped level on '${groupColumn}' resolves to ${keys.length} ordering keys on that one column: a composite source carries a single order.`);
  return keys[0]!.direction;
}

function bucketWindow(page: PageIr): number {
  if (page.mode === "none") throw failure("A grouped level was asked for an unpaginated page, but a composite aggregation always returns at most `size` buckets.");
  if (page.startRow !== 0) {
    throw failure(`A grouped level was asked for rows ${page.startRow}..${page.endRow}, but a composite aggregation has no offset: it pages forward with an after key that the execution adapter carries.`);
  }
  return page.endRow - page.startRow;
}

function groupedAggregations(groupColumn: string, aggregations: readonly AggregationIr[], request: SearchRequest, context: Context): Doc {
  const direction = bucketOrder(groupColumn, aggregations, request);
  const source: Doc = doc(["field", groupFieldTarget(groupColumn, context)], ["missing_bucket", true]);
  if (direction === "desc") source.set("order", "desc");
  const level: Doc = doc(["composite", doc(["size", bucketWindow(request.page)], ["sources", [doc([groupColumn, doc(["terms", source])])]])]);
  const children = metrics(aggregations, context);
  if (children.size > 0) level.set("aggs", children);
  return doc([requireAggregationName(groupColumn, "the grouped level"), level]);
}

function bodyOf(request: SearchRequest): SearchQuery {
  const context: Context = { schema: request.schema };
  const plan = resolveGrouping(request.group, request.aggregations);
  const query = renderQuery(request.filter, plan?.drillDown, plan !== undefined, context);
  if (plan?.groupColumn !== undefined) return { ...(query === undefined ? {} : { query }), size: 0, aggs: groupedAggregations(plan.groupColumn, plan.aggregations, request, context) };
  const window = request.page.mode === "range" ? { from: request.page.startRow, size: request.page.endRow - request.page.startRow } : {};
  return { query: query ?? doc(["match_all", doc()]), sort: sortClauses(request, context), ...window };
}

function requirePositiveLimit(limit: number | undefined): void {
  if (limit !== undefined && limit <= 0) throw failure(`maxQueryTimeMs must be positive when set, not ${limit} (TL-4).`);
}

/** The page query. TL-3: an unpaginated request never carries the time limit. */
export function build(request: SearchRequest): SearchQuery {
  requirePositiveLimit(request.maxQueryTimeMs);
  const body = bodyOf(request);
  return request.page.mode === "none" || request.maxQueryTimeMs === undefined ? body : { ...body, timeoutMs: request.maxQueryTimeMs };
}

/** CNT-1 to CNT-8: size zero and no sort; at a grouped level, a cardinality and a missing count over the group field. */
export function buildCount(request: SearchRequest): SearchQuery {
  requirePositiveLimit(request.maxQueryTimeMs);
  const body = bodyOf({ ...request, page: { mode: "range", startRow: 0, endRow: 1 }, sort: undefined });
  const counted: SearchQuery = { ...(body.query === undefined ? {} : { query: body.query }), size: 0, ...(request.maxQueryTimeMs === undefined ? {} : { timeoutMs: request.maxQueryTimeMs }) };
  const plan = resolveGrouping(request.group, request.aggregations);
  if (plan?.groupColumn === undefined) return counted;
  const field = groupFieldTarget(plan.groupColumn, { schema: request.schema });
  return { ...counted, aggs: doc(["bucket_count", doc(["cardinality", doc(["field", field])])], ["missing_group_values", doc(["missing", doc(["field", field])])]) };
}

export interface SearchSetValuesRequest {
  readonly schema: GridSchema;
  readonly colId: string;
  readonly filter?: FilterNodeIr | undefined;
  readonly searchPrefix?: string | undefined;
  readonly rowLimit: number;
  readonly maxQueryTimeMs?: number | undefined;
}

function samePredicate(candidate: FilterNodeIr, colId: string, prefix: string): boolean {
  return candidate.type === "comparison" && candidate.field === colId && candidate.op === "startsWith" && candidate.value?.type === "string" && candidate.value.value === prefix;
}

/** GRP-6(c): the prefix predicate is the terms aggregation's `include`, so the first copy of it is removed from the filter. */
function removeFirst(tree: FilterNodeIr | undefined, colId: string, prefix: string, removed: { done: boolean }): FilterNodeIr | undefined {
  if (tree === undefined) return undefined;
  if (tree.type === "comparison") {
    if (!removed.done && samePredicate(tree, colId, prefix)) {
      removed.done = true;
      return undefined;
    }
    return tree;
  }
  if (tree.type === "not") {
    const inner = removeFirst(tree.node, colId, prefix, removed);
    return inner === undefined ? undefined : { type: "not", node: inner };
  }
  const kept = tree.nodes.map((child) => removeFirst(child, colId, prefix, removed)).filter((child): child is FilterNodeIr => child !== undefined);
  if (kept.length === 0) return undefined;
  return kept.length === 1 ? kept[0] : { type: tree.type, nodes: kept };
}

/** GRP-6: a `terms` aggregation over the column's keyword, ordered by key, capped, with the search prefix as its `include`. */
export function buildSetValues(request: SearchSetValuesRequest): SearchQuery {
  requirePositiveLimit(request.maxQueryTimeMs);
  if (!Number.isInteger(request.rowLimit) || request.rowLimit <= 0) throw failure(`A set-values row limit must be positive, not ${request.rowLimit}.`);
  const context: Context = { schema: request.schema };
  const target = resolve(request.colId, context);
  if (target.config.type !== "string") {
    throw failure(`Set-filter values are resolved for field '${request.colId}', declared '${target.config.type}': a terms aggregation's include is a term-level regex, so this path is for a string column only.`);
  }
  const terms: Doc = doc(["field", target.keyword], ["size", request.rowLimit]);
  let filter = request.filter;
  if (request.searchPrefix !== undefined) {
    terms.set("include", `${escapeSearchRegex(request.searchPrefix)}.*`);
    const removed = { done: false };
    filter = removeFirst(request.filter, request.colId, request.searchPrefix, removed);
    if (!removed.done) throw failure(`The search prefix on '${request.colId}' compiles to the terms aggregation's include, so its predicate must appear in the filter the pipeline produced: pass that filter unmodified.`);
  }
  terms.set("order", doc(["_key", "asc"]));
  const query = renderQuery(filter, undefined, true, context);
  const body: SearchQuery = { ...(query === undefined ? {} : { query }), size: 0, aggs: doc([requireAggregationName(request.colId, "the distinct-values"), doc(["terms", terms])]) };
  return request.maxQueryTimeMs === undefined ? body : { ...body, timeoutMs: request.maxQueryTimeMs };
}

/** The artifact body, members in the C# order (query, sort, from, size, aggs, timeout); the engines compare them as unordered maps (OSE-0). */
export function toArtifact(query: SearchQuery): Value {
  const artifact: Doc = doc();
  if (query.query !== undefined) artifact.set("query", query.query);
  if (query.sort !== undefined) artifact.set("sort", [...query.sort]);
  if (query.from !== undefined) artifact.set("from", query.from);
  if (query.size !== undefined) artifact.set("size", query.size);
  if (query.aggs !== undefined) artifact.set("aggs", query.aggs);
  if (query.timeoutMs !== undefined) artifact.set("timeout", `${query.timeoutMs}ms`);
  return artifact;
}
