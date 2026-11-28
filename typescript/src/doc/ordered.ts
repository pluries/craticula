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

/** Compact JSON text of a value: a Map keeps its insertion order, a JsonNumber its digits, and a number must be finite. */
export function writeJson(value: Value): string {
  if (value === null || typeof value === "boolean" || typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new RangeError("A JSON number must be finite.");
    return JSON.stringify(value);
  }
  if (value instanceof JsonNumber) return value.text;
  if (value instanceof Map) return `{${[...value].map(([key, item]) => `${JSON.stringify(key)}:${writeJson(item)}`).join(",")}}`;
  return `[${(value as readonly Value[]).map(writeJson).join(",")}]`;
}
