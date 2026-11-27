import { CompileError } from "./errors.js";
import { ParameterBag, quoteIdentifier, renderPaging, renderSortKey } from "./postgres.js";
import { parseSchema, type GridSchema } from "./schema.js";
import { defaultNulls, effectiveSort, type SortItem } from "./sort.js";

export interface Artifact {
  readonly dialect: "postgres";
  readonly sql: string;
  readonly params: (string | number | boolean)[];
}

/** PG-1: the page a row request gets when it sends no window. */
const DEFAULT_PAGE_SIZE = 100;
/** SEC-3: the largest page a request may ask for. */
const MAX_PAGE_SIZE = 1000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isEmpty(value: unknown): boolean {
  return value === undefined || value === null || (Array.isArray(value) && value.length === 0) || (isRecord(value) && Object.keys(value).length === 0);
}

function refuseUnsupported(request: Record<string, unknown>): void {
  const unsupported: [string, string][] = [
    ["filterModel", "filters"],
    ["customFilters", "custom filters"],
    ["rowGroupCols", "grouping"],
    ["valueCols", "aggregation"],
    ["pivotCols", "pivoting"],
    ["groupKeys", "group drill-down"],
    ["setValuesRequest", "set-values requests"],
    ["requestContext", "request context"],
  ];
  for (const [member, what] of unsupported) {
    if (!isEmpty(request[member])) {
      throw new CompileError("Unsupported", `This driver compiles sorting and paging only; ${what} (${member}) are not supported.`);
    }
  }
  if (request["pivotMode"] === true) {
    throw new CompileError("Unsupported", "This driver compiles sorting and paging only; pivot mode is not supported.");
  }
}

function readSort(request: Record<string, unknown>, schema: GridSchema): SortItem[] {
  const raw = request["sortModel"];
  if (raw === undefined || raw === null) {
    return [];
  }
  if (!Array.isArray(raw)) {
    throw new CompileError("InvalidRequest", "sortModel must be an array.");
  }
  return raw.map((entry: unknown): SortItem => {
    if (!isRecord(entry) || typeof entry["colId"] !== "string") {
      throw new CompileError("InvalidRequest", "Each sortModel entry must be an object with a string colId.");
    }
    const direction = entry["sort"];
    if (direction !== "asc" && direction !== "desc") {
      throw new CompileError("InvalidRequest", "A sortModel entry's sort must be 'asc' or 'desc'.");
    }
    const colId = entry["colId"];
    const field = schema.fields.get(colId);
    if (field === undefined || !field.sortable) {
      throw new CompileError("UnknownField", `The sort column '${colId}' is not a declared, sortable field of the schema.`);
    }
    return { field: colId, direction, nulls: defaultNulls(direction) };
  });
}

function readWindow(request: Record<string, unknown>): { limit: number; offset: number } {
  const start = request["startRow"];
  const end = request["endRow"];
  if ((start === undefined || start === null) && (end === undefined || end === null)) {
    return { limit: DEFAULT_PAGE_SIZE, offset: 0 };
  }
  if (typeof start !== "number" || typeof end !== "number" || !Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 0 || end <= start) {
    throw new CompileError("InvalidRequest", "startRow and endRow must be whole numbers with 0 <= startRow < endRow.");
  }
  const limit = end - start;
  if (limit > MAX_PAGE_SIZE) {
    throw new CompileError("LimitExceeded", `A page of ${limit} rows is above the limit of ${MAX_PAGE_SIZE}.`);
  }
  return { limit, offset: start };
}

/** EXP-1(b), the default projection: the exportable fields in schema order, aliased to their colId where the column differs. */
function exportProjection(schema: GridSchema): string {
  const columns = [...schema.fields].filter(([, field]) => field.exportable).map(([colId, field]) => {
    const column = quoteIdentifier(field.column);
    return field.column === colId ? column : `${column} AS ${quoteIdentifier(colId)}`;
  });
  if (columns.length === 0) {
    throw new CompileError("InvalidSchema", "The schema declares no exportable field.");
  }
  return columns.join(", ");
}

/** Compiles a sort-and-page AG Grid request against a GridSchema to a PostgreSQL query with bound parameters. */
export function compile(schemaValue: unknown, requestValue: unknown): Artifact {
  const schema = parseSchema(schemaValue);
  if (!isRecord(requestValue)) {
    throw new CompileError("InvalidRequest", "The request must be a JSON object.");
  }
  refuseUnsupported(requestValue);

  const isExport = requestValue["exportFormat"] !== undefined && requestValue["exportFormat"] !== null;
  if (isExport && !isEmpty(requestValue["exportColumns"])) {
    throw new CompileError("Unsupported", "This driver exports the default column list only; exportColumns is not supported.");
  }
  const exportScope = requestValue["exportScope"];
  if (isExport && exportScope !== "all" && exportScope !== "page") {
    throw new CompileError("InvalidRequest", "An export request needs exportScope 'all' or 'page'.");
  }

  const sort = effectiveSort(readSort(requestValue, schema), schema).map((key) => {
    const field = schema.fields.get(key.field)!;
    const insensitive = !key.appended && field.type === "string" && !field.caseSensitive;
    return renderSortKey(quoteIdentifier(field.column), key.direction, key.nulls, insensitive);
  });

  const parameters = new ParameterBag();
  let sql = `SELECT ${isExport ? exportProjection(schema) : "*"} FROM ${quoteIdentifier(schema.source)} ORDER BY ${sort.join(", ")}`;
  if (!(isExport && exportScope === "all")) {
    const window = readWindow(requestValue);
    sql += ` ${renderPaging(window.limit, window.offset, parameters)}`;
  }
  return { dialect: "postgres", sql, params: parameters.values };
}
