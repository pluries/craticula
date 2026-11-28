import type { ParseOptions } from "./agrid/request.js";
import { build, type Artifact } from "./sql/builder.js";
import { postgres } from "./sql/postgres.js";
import { prepareRow } from "./stages.js";

export type { Artifact };

/** Compiles an AG Grid request against a GridSchema to a PostgreSQL query with bound parameters: the stages of feature 013, then the SQL builder. */
export function compile(schemaValue: unknown, requestValue: unknown, options: ParseOptions = {}): Artifact {
  const { schema, ir, export: exportSpec } = prepareRow(schemaValue, requestValue, options);
  return build({ schema, filter: ir.filter, sort: ir.sort, page: ir.page, projection: exportSpec?.columns, group: ir.group, aggregations: ir.aggregations }, postgres);
}
