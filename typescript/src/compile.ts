import type { ParseOptions } from "./agrid/request.js";
import { CompileError } from "./errors.js";
import { build, buildCount, buildSetValues, type Artifact } from "./sql/builder.js";
import type { Dialect } from "./sql/dialect.js";
import { postgres } from "./sql/postgres.js";
import { prepareRow, prepareSetValues } from "./stages.js";

export type { Artifact };

/**
 * Compiles an AG Grid request against a GridSchema to a query for the dialect (PostgreSQL by default) with bound parameters: the stages of feature 013, then the SQL
 * builder. A request with a top-level `setValuesRequest` is the distinct-values query (BM-3); `countMode` is the count entry point (CNT-8).
 */
export function compile(schemaValue: unknown, requestValue: unknown, options: ParseOptions = {}, countMode = false, dialect: Dialect = postgres): Artifact {
  const set = prepareSetValues(schemaValue, requestValue, options);
  if (set !== undefined && countMode) throw new CompileError("Unsupported", "Count mode counts the rows of a row request; a set-values request has no count.");
  if (set !== undefined) return buildSetValues({ schema: set.schema, colId: set.colId, filter: set.filter, rowLimit: set.rowLimit }, dialect);
  const { schema, ir, export: exportSpec } = prepareRow(schemaValue, requestValue, options, countMode);
  const request = { schema, filter: ir.filter, sort: ir.sort, page: ir.page, projection: exportSpec?.columns, group: ir.group, aggregations: ir.aggregations };
  return countMode ? buildCount(request, dialect) : build(request, dialect);
}
