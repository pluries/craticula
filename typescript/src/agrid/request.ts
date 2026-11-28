import type { GroupSpecIr, Ir, PageIr, SortItemIr } from "../ir.js";
import type { GridSchema } from "../schema.js";
import { readFilterNode } from "./filter-node.js";
import { resolveZone } from "./dates.js";
import { mergeFilters, parseFilterModel, type DateContext } from "./filters.js";
import { AUTO_GROUP_COLUMN, parseGroups, resolveAutoColumn } from "./groups.js";
import { isRecord, malformed, unsupported, wholeNumber, type Obj } from "./values.js";
import { CompileError } from "../errors.js";

/** Harness and host settings that are not part of the wire request (`spec/conformance-runner.md` §3). */
export interface ParseOptions {
  /** PG-1: the rows of the page a request without a window gets. Default 100. */
  readonly defaultPageSize?: number;
  /** PG-3: whether `ignorePageLimit` may ask for every row. Default false. */
  readonly allowUnboundedRows?: boolean;
  /** The clock a date preset reads, injected by the host or the harness (`requestContext.now`). Read only when a preset appears. */
  readonly now?: () => Date;
  /** SEM-4: the zone used when the request names none. Default UTC. */
  readonly defaultZone?: string;
  /** The first day of the week for week presets, 0 = Sunday. Default 1 = Monday. */
  readonly firstDayOfWeek?: number;
}

export interface ExportSpecIr {
  readonly format: "csv" | "tsv";
  readonly scope: "all" | "page";
  /** EXP-1(b): the colIds to write, the exportable fields in schema order. */
  readonly columns: readonly string[];
}

export interface ParsedRequest {
  readonly ir: Ir;
  readonly export?: ExportSpecIr;
}

function isEmpty(value: unknown): boolean {
  return value === undefined || value === null || (Array.isArray(value) && value.length === 0) || (isRecord(value) && Object.keys(value).length === 0);
}

function readOptionalInt(root: Obj, name: string): number | null {
  const value = root[name];
  if (value === undefined || value === null) return null;
  const whole = wholeNumber(value);
  if (whole === undefined) throw malformed(`'${name}' must be a whole number or null.`);
  return whole;
}

function parseExport(root: Obj, schema: GridSchema): ExportSpecIr | undefined {
  const format = root["exportFormat"];
  const scope = root["exportScope"];
  const hasColumns = root["exportColumns"] !== undefined && root["exportColumns"] !== null;
  if (format === undefined || format === null) {
    if ((scope === undefined || scope === null) && !hasColumns) return undefined;
    throw malformed("'exportScope' and 'exportColumns' need an 'exportFormat' (\"csv\" or \"tsv\") on the same request.");
  }
  if (format !== "csv" && format !== "tsv") throw malformed("'exportFormat' must be \"csv\" or \"tsv\".");
  const resolvedScope = scope === undefined || scope === null ? "all" : scope;
  if (resolvedScope !== "all" && resolvedScope !== "page") throw malformed("'exportScope' must be \"all\" or \"page\".");
  if (hasColumns) throw unsupported("'exportColumns' names its own export columns.");
  const columns = [...schema.fields].filter(([, field]) => field.exportable).map(([colId]) => colId);
  return { format, scope: resolvedScope, columns };
}

function parseSort(root: Obj, group: GroupSpecIr | undefined): SortItemIr[] {
  const raw = root["sortModel"];
  if (raw === undefined || raw === null) return [];
  if (!Array.isArray(raw)) throw malformed("'sortModel' must be an array.");
  const entries = (raw as unknown[]).map((entry) => {
    if (!isRecord(entry)) throw malformed("A 'sortModel' entry must be an object.");
    const colId = entry["colId"];
    const direction = entry["sort"];
    if (typeof colId !== "string" || colId.length === 0) throw malformed("A 'sortModel' entry needs a string 'colId'.");
    if (direction !== "asc" && direction !== "desc") throw malformed(`The sortModel entry for '${colId}' needs 'sort' to be 'asc' or 'desc'.`);
    return { colId, direction: direction as "asc" | "desc" };
  });
  // AG Grid sends the auto column together with the sorts of the group columns it stands for: only the level on show is kept.
  const auto = entries.map((entry) => resolveAutoColumn(entry.colId, group));
  const target = auto.find((resolved) => resolved !== undefined)?.field ?? null;
  const covered = new Set(auto.some((resolved) => resolved !== undefined) ? (group?.groupCols ?? []).filter((col) => col !== target) : []);
  const items: SortItemIr[] = [];
  const seen = new Set<string>();
  entries.forEach(({ colId, direction }, i) => {
    const resolved = auto[i];
    const field = resolved === undefined ? colId : resolved.field;
    if (field === null || seen.has(field) || (resolved === undefined && covered.has(field))) return;
    seen.add(field);
    items.push({ field, direction, nullsPosition: direction === "asc" ? "last" : "first" });
  });
  return items;
}

function parsePage(root: Obj, exportSpec: ExportSpecIr | undefined, options: ParseOptions): PageIr {
  const startRow = readOptionalInt(root, "startRow");
  const endRow = readOptionalInt(root, "endRow");
  const ignore = root["ignorePageLimit"];
  if (ignore !== undefined && ignore !== null && typeof ignore !== "boolean") throw malformed("'ignorePageLimit' must be true or false.");
  if (ignore === true && options.allowUnboundedRows !== true) {
    throw new CompileError("InvalidRequest", "'ignorePageLimit' asks for every row, and this host has not allowed that.");
  }
  if ((startRow === null) !== (endRow === null)) {
    throw malformed("'startRow' and 'endRow' must both be present or both be null.");
  }
  let page: PageIr;
  if (startRow !== null && endRow !== null) {
    if (startRow < 0 || endRow <= startRow) throw malformed("The page window is empty or negative: it needs 0 <= startRow < endRow.");
    page = { mode: "range", startRow, endRow };
  } else if (ignore === true) {
    page = { mode: "none" };
  } else {
    const size = options.defaultPageSize ?? 100;
    if (!Number.isSafeInteger(size) || size <= 0) throw new RangeError("The default page size must be a positive integer.");
    page = { mode: "range", startRow: 0, endRow: size };
  }
  return exportSpec?.scope === "all" ? { mode: "none" } : page;
}

/** Reads an AG Grid server-side row request into the IR. Everything the parser cannot read yet is refused, never guessed. */
function dateContext(root: Obj, options: ParseOptions): DateContext {
  const context = root["requestContext"];
  let zone = options.defaultZone ?? "UTC";
  if (context !== undefined && context !== null) {
    if (!isRecord(context)) throw malformed("'requestContext' must be a JSON object or null.");
    const requested = context["zone"];
    if (requested !== undefined && requested !== null) {
      if (typeof requested !== "string") throw malformed("'requestContext.zone' must be a string IANA time zone id.");
      zone = requested;
    }
  }
  return { zone: resolveZone(zone), now: options.now ?? (() => new Date()), firstDayOfWeek: options.firstDayOfWeek ?? 1 };
}

export function parseRequest(value: unknown, schema: GridSchema, options: ParseOptions = {}): ParsedRequest {
  if (!isRecord(value)) throw malformed("The AG Grid request must be a JSON object.");
  if (value["setValuesRequest"] !== undefined) throw malformed("'setValuesRequest' is the set-filter-values envelope, not a row request.");
  if (value["pivotMode"] === true) throw malformed("'pivotMode: true' is not supported.");
  if (!isEmpty(value["pivotCols"])) throw malformed("A non-empty 'pivotCols' is not supported.");

  const custom = value["customFilters"];
  const filter = mergeFilters(parseFilterModel(value, schema, dateContext(value, options)), custom === undefined || custom === null ? undefined : readFilterNode(custom));
  const exportSpec = parseExport(value, schema);
  const { group, aggregations } = parseGroups(value);
  const sort = parseSort(value, group);
  const page = parsePage(value, exportSpec, options);
  const grouped = exportSpec === undefined ? { ...(group === undefined ? {} : { group }), ...(aggregations === undefined ? {} : { aggregations }) } : {};
  const ir: Ir = { ...(filter === undefined ? {} : { filter }), ...(sort.length > 0 ? { sort } : {}), ...grouped, page };
  return exportSpec === undefined ? { ir } : { ir, export: exportSpec };
}
