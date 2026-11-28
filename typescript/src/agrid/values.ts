import { CompileError } from "../errors.js";
import { JsonNumber } from "../json.js";

export type Obj = Record<string, unknown>;

export function isRecord(value: unknown): value is Obj {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function malformed(message: string): CompileError {
  return new CompileError("InvalidRequest", message, { rejectedAt: "requestParsing", reason: "malformed-request" });
}

export function unknownOperator(message: string): CompileError {
  return new CompileError("InvalidRequest", message, { rejectedAt: "requestParsing", reason: "unknown-operator" });
}

export function unsupported(message: string): CompileError {
  return new CompileError("Unsupported", `${message} The TypeScript request parser does not read it yet.`);
}

/** The text of a number as written (a JsonNumber keeps it; a native number prints its shortest form), or undefined for anything else. */
export function numberText(value: unknown): string | undefined {
  if (value instanceof JsonNumber) return value.text;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return undefined;
}

/** A whole number from a JsonNumber or a native number, or undefined. */
export function wholeNumber(value: unknown): number | undefined {
  const text = numberText(value);
  if (text === undefined || !/^-?[0-9]+$/.test(text)) return undefined;
  const parsed = Number(text);
  return Number.isSafeInteger(parsed) ? parsed : undefined;
}

export function requiredString(source: Obj, name: string, where: string): string {
  const value = source[name];
  if (typeof value !== "string") throw malformed(`${where}: expected a string '${name}' property.`);
  return value;
}
