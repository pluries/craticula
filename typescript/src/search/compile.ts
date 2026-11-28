import { CompileError } from "../errors.js";
import type { CompileOptions } from "../backends.js";
import type { Value } from "../doc/ordered.js";
import { prepareRow, prepareSetValues } from "../stages.js";
import { build, buildCount, buildSetValues, toArtifact } from "./builder.js";

/** An AG Grid request against a GridSchema to an OpenSearch or Elasticsearch body (one shared DSL subset, OSE-14), as an ordered artifact. */
export function compileSearch(schemaValue: unknown, requestValue: unknown, options: CompileOptions, countMode: boolean): Value {
  const set = prepareSetValues(schemaValue, requestValue, options);
  if (set !== undefined && countMode) throw new CompileError("Unsupported", "Count mode counts the rows of a row request; a set-values request has no count.");
  if (set !== undefined) {
    return toArtifact(buildSetValues({ schema: set.schema, colId: set.colId, filter: set.filter, searchPrefix: set.searchPrefix, rowLimit: set.rowLimit, maxQueryTimeMs: options.maxQueryTimeMs }));
  }
  const { schema, ir } = prepareRow(schemaValue, requestValue, options, countMode);
  const request = { schema, filter: ir.filter, sort: ir.sort, page: ir.page, group: ir.group, aggregations: ir.aggregations, maxQueryTimeMs: options.maxQueryTimeMs };
  return toArtifact(countMode ? buildCount(request) : build(request));
}
