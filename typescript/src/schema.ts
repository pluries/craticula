import { CompileError } from "./errors.js";

const FIELD_TYPES = ["string", "int64", "decimal", "double", "boolean", "date", "datetime"] as const;
export type FieldType = (typeof FIELD_TYPES)[number];

export interface Field {
  readonly type: FieldType;
  readonly sortable: boolean;
  readonly exportable: boolean;
  /** The physical column (`physical.sql.column`), the only text of a schema that reaches the SQL. */
  readonly column: string;
  /** SC-3: a text field declared case-sensitive. Anything else that is text folds case (SEM-1). */
  readonly caseSensitive: boolean;
}

export interface GridSchema {
  readonly source: string;
  readonly stableKey: string;
  /** Declared fields, in schema order, keyed by colId. A Map, so a colId such as `__proto__` is just an unknown key. */
  readonly fields: ReadonlyMap<string, Field>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(value: unknown, what: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new CompileError("InvalidSchema", `${what} must be a non-empty string.`);
  }
  return value;
}

function parseField(colId: string, value: unknown): Field {
  if (!isRecord(value)) {
    throw new CompileError("InvalidSchema", `Field '${colId}' must be an object.`);
  }
  const type = value["type"];
  if (typeof type !== "string" || !(FIELD_TYPES as readonly string[]).includes(type)) {
    throw new CompileError("InvalidSchema", `Field '${colId}' has no declared type from ${FIELD_TYPES.join(", ")}.`);
  }
  const physical = value["physical"];
  const sql = isRecord(physical) ? physical["sql"] : undefined;
  if (!isRecord(sql)) {
    throw new CompileError("InvalidSchema", `Field '${colId}' has no physical.sql mapping.`);
  }
  if ("qualifiedColumn" in sql || "expression" in sql) {
    throw new CompileError("Unsupported", `Field '${colId}' maps to a qualified column or an expression; this driver reads plain columns only.`);
  }
  const text = value["text"];
  return {
    type: type as FieldType,
    sortable: value["sortable"] !== false,
    exportable: value["exportable"] !== false,
    column: requireString(sql["column"], `Field '${colId}' physical.sql.column`),
    caseSensitive: isRecord(text) && text["caseSensitivity"] === "sensitive",
  };
}

/** Reads the parts of a GridSchema (`spec/grid-schema.schema.json`) this skeleton compiles with. */
export function parseSchema(value: unknown): GridSchema {
  if (!isRecord(value)) {
    throw new CompileError("InvalidSchema", "The schema must be a JSON object.");
  }
  const source = requireString(value["source"], "The schema's source");
  const stableKey = requireString(value["stableKey"], "The schema's stableKey");
  const rawFields = value["fields"];
  if (!isRecord(rawFields)) {
    throw new CompileError("InvalidSchema", "The schema's fields must be an object.");
  }
  const fields = new Map<string, Field>();
  for (const [colId, raw] of Object.entries(rawFields)) {
    fields.set(colId, parseField(colId, raw));
  }
  if (!fields.has(stableKey)) {
    throw new CompileError("InvalidSchema", `The stableKey '${stableKey}' is not a declared field.`);
  }
  return { source, stableKey, fields };
}
