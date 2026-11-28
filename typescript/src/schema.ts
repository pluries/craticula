import { CompileError } from "./errors.js";

const FIELD_TYPES = ["string", "int64", "decimal", "double", "boolean", "date", "datetime"] as const;
export type FieldType = (typeof FIELD_TYPES)[number];
const AGGREGATIONS = ["sum", "min", "max", "avg", "count"] as const;

export interface SqlMapping {
  readonly kind: "column" | "qualifiedColumn" | "expression";
  readonly text: string;
}

export interface Field {
  readonly type: FieldType;
  readonly filterable: boolean;
  readonly sortable: boolean;
  readonly groupable: boolean;
  readonly aggregatable: readonly string[];
  readonly exportable: boolean;
  readonly label?: string;
  readonly format?: { readonly datePattern?: string; readonly decimalSeparator?: string };
  /** SC-3: a text field declared case-sensitive. Anything else that is text folds case (SEM-1). */
  readonly caseSensitive: boolean;
  readonly searchMode: "substring" | "analyzed";
  /** The SQL mapping, the only text of a schema that reaches SQL. Absent when the field has no SQL mapping. */
  readonly sql?: SqlMapping;
  readonly mongoPath?: string;
  readonly search?: { readonly field: string; readonly keywordSubField?: string; readonly normalizedSubField?: string };
}

export interface GridSchema {
  readonly mode: "strict" | "lenient";
  readonly source: string;
  readonly stableKey: string;
  /** Declared fields, in schema order, keyed by colId. A Map, so a colId such as `__proto__` is just a name. */
  readonly fields: ReadonlyMap<string, Field>;
  /** SC-5: the host's static filter, an IR filter node, validated when it is injected. */
  readonly staticFilter?: unknown;
}

type Obj = Record<string, unknown>;

function isRecord(value: unknown): value is Obj {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function invalid(message: string): CompileError {
  return new CompileError("InvalidSchema", message);
}

function only(value: Obj, allowed: readonly string[], where: string): void {
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) {
      throw invalid(`${where} has an unknown member '${key}'.`);
    }
  }
}

function text(value: unknown, where: string, maxLength?: number): string {
  if (typeof value !== "string" || value.length === 0 || (maxLength !== undefined && value.length > maxLength)) {
    throw invalid(`${where} must be a non-empty string${maxLength === undefined ? "" : ` of at most ${maxLength} characters`}.`);
  }
  return value;
}

function flag(value: unknown, fallback: boolean, where: string): boolean {
  if (value === undefined) return fallback;
  if (typeof value !== "boolean") throw invalid(`${where} must be true or false.`);
  return value;
}

function parseSql(value: unknown, colId: string): SqlMapping {
  const where = `Field '${colId}' physical.sql`;
  if (!isRecord(value)) throw invalid(`${where} must be an object.`);
  const keys = Object.keys(value);
  const kind = keys.length === 1 ? keys[0] : undefined;
  if (kind !== "column" && kind !== "qualifiedColumn" && kind !== "expression") {
    throw invalid(`${where} must hold exactly one of column, qualifiedColumn or expression.`);
  }
  return { kind, text: text(value[kind], `${where}.${kind}`) };
}

function parsePhysical(value: unknown, colId: string): Pick<Field, "sql" | "mongoPath" | "search"> {
  if (value === undefined) return {};
  const where = `Field '${colId}' physical`;
  if (!isRecord(value)) throw invalid(`${where} must be an object.`);
  only(value, ["sql", "mongo", "search"], where);
  const out: { sql?: SqlMapping; mongoPath?: string; search?: NonNullable<Field["search"]> } = {};
  if (value["sql"] !== undefined) out.sql = parseSql(value["sql"], colId);
  const mongo = value["mongo"];
  if (mongo !== undefined) {
    if (!isRecord(mongo)) throw invalid(`${where}.mongo must be an object.`);
    only(mongo, ["path"], `${where}.mongo`);
    out.mongoPath = text(mongo["path"], `${where}.mongo.path`);
  }
  const search = value["search"];
  if (search !== undefined) {
    if (!isRecord(search)) throw invalid(`${where}.search must be an object.`);
    only(search, ["field", "keywordSubField", "normalizedSubField"], `${where}.search`);
    const mapped: { field: string; keywordSubField?: string; normalizedSubField?: string } = { field: text(search["field"], `${where}.search.field`) };
    if (search["keywordSubField"] !== undefined) mapped.keywordSubField = text(search["keywordSubField"], `${where}.search.keywordSubField`);
    if (search["normalizedSubField"] !== undefined) mapped.normalizedSubField = text(search["normalizedSubField"], `${where}.search.normalizedSubField`);
    out.search = mapped;
  }
  return out;
}

function parseField(colId: string, value: unknown): Field {
  const where = `Field '${colId}'`;
  if (!isRecord(value)) throw invalid(`${where} must be an object.`);
  only(value, ["type", "filterable", "sortable", "groupable", "aggregatable", "physical", "text", "exportable", "label", "format"], where);

  const type = value["type"];
  if (typeof type !== "string" || !(FIELD_TYPES as readonly string[]).includes(type)) {
    throw invalid(`${where} has no declared type from ${FIELD_TYPES.join(", ")}.`);
  }

  const aggregatable = value["aggregatable"] ?? [];
  if (!Array.isArray(aggregatable) || new Set(aggregatable).size !== aggregatable.length || !aggregatable.every((a) => (AGGREGATIONS as readonly unknown[]).includes(a))) {
    throw invalid(`${where} aggregatable must be a list of distinct functions from ${AGGREGATIONS.join(", ")}.`);
  }

  let caseSensitive = false;
  let searchMode: "substring" | "analyzed" = "substring";
  const textOptions = value["text"];
  if (textOptions !== undefined) {
    if (!isRecord(textOptions)) throw invalid(`${where} text must be an object.`);
    only(textOptions, ["caseSensitivity", "searchMode"], `${where} text`);
    const sensitivity = textOptions["caseSensitivity"];
    if (sensitivity !== undefined && sensitivity !== "insensitive" && sensitivity !== "sensitive") {
      throw invalid(`${where} text.caseSensitivity must be 'insensitive' or 'sensitive'.`);
    }
    caseSensitive = sensitivity === "sensitive";
    const mode = textOptions["searchMode"];
    if (mode !== undefined && mode !== "substring" && mode !== "analyzed") {
      throw invalid(`${where} text.searchMode must be 'substring' or 'analyzed'.`);
    }
    searchMode = mode ?? "substring";
  }

  let format: Field["format"];
  const formatOptions = value["format"];
  if (formatOptions !== undefined) {
    if (!isRecord(formatOptions)) throw invalid(`${where} format must be an object.`);
    only(formatOptions, ["datePattern", "decimalSeparator"], `${where} format`);
    const parsed: { datePattern?: string; decimalSeparator?: string } = {};
    if (formatOptions["datePattern"] !== undefined) parsed.datePattern = text(formatOptions["datePattern"], `${where} format.datePattern`);
    if (formatOptions["decimalSeparator"] !== undefined) parsed.decimalSeparator = text(formatOptions["decimalSeparator"], `${where} format.decimalSeparator`, 1);
    format = parsed;
  }

  return {
    type: type as FieldType,
    filterable: flag(value["filterable"], true, `${where} filterable`),
    sortable: flag(value["sortable"], true, `${where} sortable`),
    groupable: flag(value["groupable"], false, `${where} groupable`),
    aggregatable: aggregatable as string[],
    exportable: flag(value["exportable"], true, `${where} exportable`),
    ...(value["label"] === undefined ? {} : { label: text(value["label"], `${where} label`) }),
    ...(format === undefined ? {} : { format }),
    caseSensitive,
    searchMode,
    ...parsePhysical(value["physical"], colId),
  };
}

/** Reads and validates a GridSchema (`spec/grid-schema.schema.json`, SC-1 to SC-5). Throws a CompileError naming the problem. */
export function parseSchema(value: unknown): GridSchema {
  if (!isRecord(value)) throw invalid("The schema must be a JSON object.");
  only(value, ["mode", "source", "stableKey", "fields", "staticFilter"], "The schema");

  const mode = value["mode"] ?? "strict";
  if (mode !== "strict" && mode !== "lenient") throw invalid("The schema's mode must be 'strict' or 'lenient'.");
  const source = text(value["source"], "The schema's source");
  const stableKey = text(value["stableKey"], "The schema's stableKey");

  const rawFields = value["fields"];
  if (!isRecord(rawFields) || Object.keys(rawFields).length === 0) throw invalid("The schema's fields must be an object with at least one field.");
  const fields = new Map<string, Field>();
  for (const [colId, raw] of Object.entries(rawFields)) {
    fields.set(colId, parseField(colId, raw));
  }
  if (!fields.has(stableKey)) throw invalid(`The stableKey '${stableKey}' is not a declared field.`);

  return { mode, source, stableKey, fields, ...(value["staticFilter"] === undefined ? {} : { staticFilter: value["staticFilter"] }) };
}

export type ColumnUse = "filter" | "setValues" | "groupKey" | "sort" | "group" | "any";

/**
 * SC-1 and SC-2, the allowlist. Every column a request names is checked against the schema: an undeclared column, and a field declared
 * `filterable: false` when it is used to filter, as a set-values target or as a drill-down key, is refused in `strict` mode as
 * `allowlist` (`unknown-field`, `field-not-filterable`) and stripped from the list in `lenient` mode. A sort column that is
 * undeclared or not sortable is refused as unknown. Returns the columns that remain.
 */
export function checkColumns(schema: GridSchema, columns: readonly string[], use: ColumnUse): string[] {
  const kept: string[] = [];
  for (const column of columns) {
    const field = schema.fields.get(column);
    const needsFilterable = use === "filter" || use === "setValues" || use === "groupKey";
    let refusal: { reason: "unknown-field" | "field-not-filterable"; message: string } | undefined;
    if (field === undefined) {
      refusal = { reason: "unknown-field", message: `The column '${column}' is not a declared field of the schema.` };
    } else if (needsFilterable && !field.filterable) {
      refusal = { reason: "field-not-filterable", message: `The column '${column}' is declared filterable: false and cannot be used here.` };
    } else if (use === "sort" && !field.sortable) {
      refusal = { reason: "unknown-field", message: `The sort column '${column}' is declared sortable: false.` };
    }
    if (refusal === undefined) {
      kept.push(column);
    } else if (schema.mode === "strict") {
      throw new CompileError("UnknownField", refusal.message, { rejectedAt: "allowlist", reason: refusal.reason });
    }
  }
  return kept;
}
