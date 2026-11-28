import { parseRequest, parseSetValues, type ExportSpecIr, type ParseOptions } from "./agrid/request.js";
import { AUTO_GROUP_COLUMN } from "./agrid/groups.js";
import { isRecord } from "./agrid/values.js";
import { CompileError } from "./errors.js";
import type { Ir } from "./ir.js";
import { processRow, processSetValues } from "./pipeline.js";
import { build, buildCount, buildSetValues } from "./sql/builder.js";
import { postgres } from "./sql/postgres.js";
import { checkColumns, parseSchema, type GridSchema } from "./schema.js";

export interface PreparedRow {
  readonly schema: GridSchema;
  readonly ir: Ir;
  readonly export?: ExportSpecIr;
}

/**
 * The host's allowlist over every sort colId (`conformance-runner.md` §3) for a rejection request, read from the raw request before it
 * is parsed: an undeclared column is refused in every schema mode and in count mode, and an auto group column is not a schema field.
 * A compile request is not held to it: count mode ignores the sort (`count-mode/011`).
 */
function requireDeclaredSortColumns(schema: GridSchema, requestValue: unknown): void {
  const sortModel = isRecord(requestValue) ? requestValue["sortModel"] : undefined;
  if (!Array.isArray(sortModel)) return;
  for (const entry of sortModel as unknown[]) {
    const colId = isRecord(entry) ? entry["colId"] : undefined;
    if (typeof colId === "string" && !colId.startsWith(AUTO_GROUP_COLUMN) && !schema.fields.has(colId)) {
      throw new CompileError("UnknownField", `The sort column '${colId}' is not a declared field of the schema.`, { rejectedAt: "allowlist", reason: "unknown-field" });
    }
  }
}

/**
 * A row request through every stage before a compiler: the schema, the parse (with its parsing and coercion refusals), the allowlist over
 * the sort columns, then `processRow` (allowlist, limits, coercion). Count mode (CNT-8) ignores the sort and takes the unpaginated page.
 */
export function prepareRow(schemaValue: unknown, requestValue: unknown, options: ParseOptions = {}, countMode = false): PreparedRow {
  const schema = parseSchema(schemaValue);
  const parsed = parseRequest(requestValue, schema, options);
  // A grouped level sorts by its group column or an aggregate's id (GRP-4): the builder resolves those, so the schema check is for flat requests.
  if (!countMode && parsed.ir.group === undefined) checkColumns(schema, (parsed.ir.sort ?? []).map((item) => item.field), "sort");
  const staged: Ir = countMode ? { ...parsed.ir, page: { mode: "none" } } : parsed.ir;
  const ir = processRow(staged, schema);
  return parsed.export === undefined ? { schema, ir } : { schema, ir, export: parsed.export };
}

/** The same stages for any request, row or set-values, then the PostgreSQL builder as the C# driver does: it either returns or throws the refusal. */
export function checkRequest(schemaValue: unknown, requestValue: unknown, options: ParseOptions = {}, countMode = false): void {
  if (isRecord(requestValue) && requestValue["setValuesRequest"] !== undefined) {
    const prepared = prepareSetValues(schemaValue, requestValue, options);
    if (prepared !== undefined) buildSetValues({ schema: prepared.schema, colId: prepared.colId, filter: prepared.filter, rowLimit: prepared.rowLimit }, postgres);
    return;
  }
  requireDeclaredSortColumns(parseSchema(schemaValue), requestValue);
  const { schema, ir, export: exportSpec } = prepareRow(schemaValue, requestValue, options, countMode);
  const request = { schema, filter: ir.filter, sort: ir.sort, page: ir.page, projection: exportSpec?.columns, group: ir.group, aggregations: ir.aggregations };
  if (countMode) buildCount(request, postgres);
  else build(request, postgres);
}
export interface PreparedSetValues {
  readonly schema: GridSchema;
  readonly colId: string;
  readonly filter?: import("./ir.js").FilterNodeIr;
  readonly rowLimit: number;
}

/** A set-values request (BM-3) through the same stages, or undefined when the request is a row request. */
export function prepareSetValues(schemaValue: unknown, requestValue: unknown, options: ParseOptions = {}): PreparedSetValues | undefined {
  if (!isRecord(requestValue) || requestValue["setValuesRequest"] === undefined) return undefined;
  const schema = parseSchema(schemaValue);
  const parsed = parseSetValues(requestValue, schema, options);
  const { filter, rowLimit } = processSetValues(parsed, schema);
  return { schema, colId: parsed.setValues.colId, ...(filter === undefined ? {} : { filter }), rowLimit };
}
