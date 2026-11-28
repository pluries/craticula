import { CompileError } from "../errors.js";
import type { TypedValueIr } from "../ir.js";
import { JsonNumber } from "../json.js";
import type { Field, FieldType } from "../schema.js";
import type { Value } from "../doc/ordered.js";
import { normalizeInstant } from "../sql/values.js";

/** An instant as UTC text: three fraction digits when the value is whole milliseconds, else up to 100 ns without trailing zeros. */
export function normalizeSearchInstant(value: string): string {
  return normalizeInstant(value, true, "none");
}

/** The explicit `format` a range query on a date-typed field carries (OSE-8). */
export function formatFor(type: FieldType): string | undefined {
  if (type === "date") return "strict_date";
  return type === "datetime" ? "strict_date_optional_time" : undefined;
}

/** A decimal's text as a JSON number literal. The IR's decimal pattern allows leading zeros, which JSON does not, and the body must stay valid JSON. */
function jsonNumber(text: string, fieldName: string): JsonNumber {
  const [integer = "", fraction] = text.replace(/^-/, "").split(".");
  const leadingZero = integer.length > 1 && integer.startsWith("0");
  if (integer.length === 0 || leadingZero || fraction === "") {
    throw new CompileError("InvalidRequest", `The decimal value on field '${fieldName}' is not a JSON number literal (a leading zero is not valid JSON).`);
  }
  return new JsonNumber(text);
}

/** A typed IR value as a JSON value of a search query; a decimal is a JSON number with the digits it was written with. */
export function encodeSearch(value: TypedValueIr, field: Field, fieldName: string): Value {
  if (value.type === "null") return null;
  if (value.type !== field.type) {
    throw new CompileError("InvalidRequest", `A '${value.type}' value cannot be embedded against field '${fieldName}', declared '${field.type}': the coercion stage runs before a compiler.`);
  }
  switch (value.type) {
    case "decimal":
      return jsonNumber(String(value.value), fieldName);
    case "datetime":
      return normalizeSearchInstant(value.value);
    case "int64":
      return typeof value.value === "number" || Number.isSafeInteger(Number(value.value)) ? Number(value.value) : new JsonNumber(value.value);
    default:
      return value.value;
  }
}
