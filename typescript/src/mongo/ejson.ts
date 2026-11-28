import { CompileError } from "../errors.js";
import type { TypedValueIr } from "../ir.js";
import { JsonNumber } from "../json.js";
import type { Field } from "../schema.js";
import { doc, type Value } from "../doc/ordered.js";
import { normalizeInstant } from "../sql/values.js";

/** An ISO-8601 instant as UTC text without trailing zeros of the fraction (up to 100 ns). */
export function normalizeEjsonInstant(value: string): string {
  return normalizeInstant(value, false, "none");
}

/** A typed IR value as a MongoDB extended-JSON value: a decimal and a datetime are wrapped, the rest is data. */
export function encodeEjson(value: TypedValueIr, field: Field, fieldName: string): Value {
  if (value.type === "null") return null;
  if (value.type !== field.type) {
    throw new CompileError("InvalidRequest", `A '${value.type}' value cannot be embedded against field '${fieldName}', declared '${field.type}': the coercion stage runs before a compiler.`);
  }
  switch (value.type) {
    case "decimal":
      return doc(["$numberDecimal", value.value]);
    case "datetime":
      return doc(["$date", normalizeEjsonInstant(value.value)]);
    case "int64":
      return typeof value.value === "number" || Number.isSafeInteger(Number(value.value)) ? Number(value.value) : new JsonNumber(value.value);
    default:
      return value.value;
  }
}
