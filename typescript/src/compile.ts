import type { ParseOptions } from "./agrid/request.js";
import { build, buildCount, buildSetValues, type Artifact } from "./sql/builder.js";
import { postgres } from "./sql/postgres.js";
import { prepareRow, prepareSetValues } from "./stages.js";

export type { Artifact };

/**
 * Compiles an AG Grid request against a GridSchema to a PostgreSQL query with bound parameters: the stages of feature 013, then the SQL
 * builder. A request with a top-level `setValuesRequest` is the distinct-values query (BM-3); `countMode` is the count entry point (CNT-8).
 */
export function compile(schemaValue: unknown, requestValue: unknown, options: ParseOptions = {}, countMode = false): Artifact {
  const set = prepareSetValues(schemaValue, requestValue, options);
  if (set !== undefined) return buildSetValues({ schema: set.schema, colId: set.colId, filter: set.filter, rowLimit: set.rowLimit }, postgres);
  const { schema, ir, export: exportSpec } = prepareRow(schemaValue, requestValue, options, countMode);
  const request = { schema, filter: ir.filter, sort: ir.sort, page: ir.page, projection: exportSpec?.columns, group: ir.group, aggregations: ir.aggregations };
  return countMode ? buildCount(request, postgres) : build(request, postgres);
}
