import { JsonNumber } from "../json.js";

/**
 * An ordered document: a JSON object whose key order is part of the artifact (MDB-7). A plain JavaScript object lists integer-like
 * keys first whatever the insertion order, so a document that can hold a schema name as a key is a `Map`, written by `writeJson`.
 */
export type Doc = Map<string, Value>;
export type Value = string | number | boolean | null | JsonNumber | readonly Value[] | Doc;

export function doc(...entries: [string, Value][]): Doc {
  return new Map(entries);
}

/**
 * A double as .NET writes it, because the runner compares numbers by their text: shortest round-trip digits, fixed notation from 1E-4 up to
 * 1E+17 (exclusive), otherwise scientific with an upper-case `E`, a sign and at least two exponent digits (`1E+19`, `1E-05`, `5E-324`); `-0` stays `-0`.
 */
function formatNumber(value: number): string {
  if (!Number.isFinite(value)) throw new RangeError("A JSON number must be finite.");
  if (value === 0) return Object.is(value, -0) ? "-0" : "0";
  const [mantissa = "", exponentText = "0"] = value.toExponential().split("e");
  const exponent = Number(exponentText);
  if (exponent >= -4 && exponent < 17) return String(value);
  const digits = String(Math.abs(exponent)).padStart(2, "0");
  return `${mantissa}E${exponent < 0 ? "-" : "+"}${digits}`;
}

function writeEntry(key: string, item: Value): string {
  return `${JSON.stringify(key)}:${writeJson(item)}`;
}

/** Compact JSON text of a value: a Map keeps its insertion order, a JsonNumber its digits, and a number is written as .NET writes it. */
export function writeJson(value: Value): string {
  if (value === null || typeof value === "boolean" || typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number") return formatNumber(value);
  if (value instanceof JsonNumber) return value.text;
  if (value instanceof Map) {
    const entries = [...value].map(([key, item]) => writeEntry(key, item));
    return `{${entries.join(",")}}`;
  }
  return `[${(value as readonly Value[]).map(writeJson).join(",")}]`;
}
