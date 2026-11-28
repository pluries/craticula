import { parseRequest, type ParseOptions } from "./agrid/request.js";
import { CompileError } from "./errors.js";
import { DEFAULT_LIMITS } from "./limits.js";
import { ParameterBag, quoteIdentifier, renderPaging, renderSortKey } from "./postgres.js";
import { checkColumns, parseSchema, type Field, type GridSchema } from "./schema.js";
import { effectiveSort } from "./sort.js";

export interface Artifact {
  readonly dialect: "postgres";
  readonly sql: string;
  readonly params: (string | number | boolean)[];
}

/** The plain SQL column of a field: the only mapping this skeleton compiles. */
function columnOf(colId: string, field: Field): string {
  if (field.sql === undefined) {
    throw new CompileError("Unsupported", `Field '${colId}' has no SQL mapping.`);
  }
  if (field.sql.kind !== "column") {
    throw new CompileError("Unsupported", `Field '${colId}' maps to a qualified column or an expression; this driver reads plain columns only.`);
  }
  return field.sql.text;
}

/** EXP-1(b): the export projection, each exportable column aliased to its colId where the physical column differs. */
function exportProjection(schema: GridSchema, columns: readonly string[]): string {
  const rendered = columns.map((colId) => {
    const field = schema.fields.get(colId)!;
    const physical = columnOf(colId, field);
    const column = quoteIdentifier(physical);
    return physical === colId ? column : `${column} AS ${quoteIdentifier(colId)}`;
  });
  if (rendered.length === 0) {
    throw new CompileError("InvalidSchema", "The schema declares no exportable field.");
  }
  return rendered.join(", ");
}

/** Compiles a sort-and-page AG Grid request against a GridSchema to a PostgreSQL query with bound parameters. */
export function compile(schemaValue: unknown, requestValue: unknown, options: ParseOptions = {}): Artifact {
  const schema = parseSchema(schemaValue);
  const { ir, export: exportSpec } = parseRequest(requestValue, schema, options);
  // The host's allowlist over every sort column (`conformance-runner.md` §3): the parser keeps them as the request names them.
  checkColumns(schema, (ir.sort ?? []).map((item) => item.field), "sort");
  if (ir.group !== undefined || ir.aggregations !== undefined) {
    throw new CompileError("Unsupported", "This driver compiles sorting and paging only; grouping and aggregation are parsed but not rendered to SQL yet.");
  }
  if (ir.filter !== undefined) {
    throw new CompileError("Unsupported", "This driver compiles sorting and paging only; a filter is parsed but not rendered to SQL yet.");
  }

  const sort = effectiveSort((ir.sort ?? []).map((item) => ({ field: item.field, direction: item.direction, nulls: item.nullsPosition })), schema).map((key) => {
    const field = schema.fields.get(key.field)!;
    const insensitive = !key.appended && field.type === "string" && !field.caseSensitive;
    return renderSortKey(quoteIdentifier(columnOf(key.field, field)), key.direction, key.nulls, insensitive);
  });

  const parameters = new ParameterBag();
  const projection = exportSpec === undefined ? "*" : exportProjection(schema, exportSpec.columns);
  let sql = `SELECT ${projection} FROM ${quoteIdentifier(schema.source)} ORDER BY ${sort.join(", ")}`;
  if (ir.page.mode === "range") {
    const limit = ir.page.endRow - ir.page.startRow;
    if (limit > DEFAULT_LIMITS.maxPageSize) {
      throw new CompileError("LimitExceeded", `A page of ${limit} rows is above the limit of ${DEFAULT_LIMITS.maxPageSize}.`, {
        rejectedAt: "resourceLimits",
        reason: "max-page-size-exceeded",
      });
    }
    sql += ` ${renderPaging(limit, ir.page.startRow, parameters)}`;
  }
  return { dialect: "postgres", sql, params: parameters.values };
}
