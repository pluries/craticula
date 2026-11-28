import { parseRequest, parseSetValues, type ExportSpecIr, type ParseOptions } from "./agrid/request.js";
import { isRecord } from "./agrid/values.js";
import type { Ir } from "./ir.js";
import { processRow, processSetValues } from "./pipeline.js";
import { checkColumns, parseSchema, type GridSchema } from "./schema.js";

export interface PreparedRow {
  readonly schema: GridSchema;
  readonly ir: Ir;
  readonly export?: ExportSpecIr;
}

/**
 * A row request through every stage before a compiler: the schema, the parse (with its parsing and coercion refusals), the allowlist over
 * the sort columns, then `processRow` (allowlist, limits, coercion). Count mode (CNT-8) ignores the sort and takes the unpaginated page.
 */
export function prepareRow(schemaValue: unknown, requestValue: unknown, options: ParseOptions = {}, countMode = false): PreparedRow {
  const schema = parseSchema(schemaValue);
  const parsed = parseRequest(requestValue, schema, options);
  if (!countMode) checkColumns(schema, (parsed.ir.sort ?? []).map((item) => item.field), "sort");
  const staged: Ir = countMode ? { ...parsed.ir, page: { mode: "none" } } : parsed.ir;
  const ir = processRow(staged, schema);
  return parsed.export === undefined ? { schema, ir } : { schema, ir, export: parsed.export };
}

/** The same stages for any request, row or set-values, answering nothing: it either returns or throws the refusal. */
export function checkRequest(schemaValue: unknown, requestValue: unknown, options: ParseOptions = {}, countMode = false): void {
  if (isRecord(requestValue) && requestValue["setValuesRequest"] !== undefined) {
    const schema = parseSchema(schemaValue);
    processSetValues(parseSetValues(requestValue, schema, options), schema);
    return;
  }
  prepareRow(schemaValue, requestValue, options, countMode);
}
