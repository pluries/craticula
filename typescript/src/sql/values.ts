import { parseIsoInstant, utcMs } from "../agrid/dates.js";
import { CompileError } from "../errors.js";
import type { TypedValueIr } from "../ir.js";
import { JsonNumber } from "../json.js";
import type { Field } from "../schema.js";
import type { Dialect, Param } from "./dialect.js";

/** Which way a datetime bound is rounded on an engine that stores milliseconds: toward the side that keeps the rows the exact bound keeps. */
export type Rounding = "none" | "floor" | "ceiling";

const TICKS_PER_SECOND = 10_000_000n;
const TICKS_PER_MILLISECOND = 10_000n;

function floorDiv(a: bigint, b: bigint): bigint {
  const quotient = a / b;
  return a % b !== 0n && a < 0n !== b < 0n ? quotient - 1n : quotient;
}

/** An ISO-8601 instant as UTC text: no fraction when it is whole seconds, else the fraction without trailing zeros (up to 100 ns); `fixedWidth` prints milliseconds. */
export function normalizeInstant(value: string, fixedWidth: boolean, rounding: Rounding): string {
  const instant = parseIsoInstant(value);
  if (instant === undefined) {
    throw new CompileError("InvalidRequest", `The datetime value '${value.slice(0, 64)}' is not an ISO-8601 instant.`);
  }
  const seconds = BigInt(utcMs(instant.year, instant.month - 1, instant.day, instant.hour, instant.minute, instant.second) / 1000 - instant.offsetMinutes * 60);
  // .NET reads up to 7 fraction digits as ticks and rounds a longer fraction half up, which can carry into the next second.
  const roundUp = instant.fraction.length > 7 && Number(instant.fraction.charAt(7)) >= 5 ? 1n : 0n;
  let ticks = seconds * TICKS_PER_SECOND + BigInt(instant.fraction.slice(0, 7).padEnd(7, "0")) + roundUp;

  const subMillisecond = ((ticks % TICKS_PER_MILLISECOND) + TICKS_PER_MILLISECOND) % TICKS_PER_MILLISECOND;
  if (fixedWidth && rounding !== "none" && subMillisecond !== 0n) {
    const floor = ticks - subMillisecond;
    ticks = rounding === "floor" ? floor : floor + TICKS_PER_MILLISECOND;
  }

  const wholeSeconds = floorDiv(ticks, TICKS_PER_SECOND);
  if (wholeSeconds >= BigInt(utcMs(10_000, 0) / 1000)) throw new CompileError("InvalidRequest", `The datetime value '${value.slice(0, 64)}' rounds past the last representable instant.`);
  const fractionTicks = ticks - wholeSeconds * TICKS_PER_SECOND;
  const stamp = new Date(Number(wholeSeconds) * 1000).toISOString().slice(0, 19);
  if (fixedWidth && fractionTicks % TICKS_PER_MILLISECOND === 0n) {
    return `${stamp}.${String(fractionTicks / TICKS_PER_MILLISECOND).padStart(3, "0")}Z`;
  }
  if (fractionTicks === 0n) return `${stamp}Z`;
  let digits = fractionTicks.toString().padStart(7, "0");
  while (digits.endsWith("0")) digits = digits.slice(0, -1);
  return `${stamp}.${digits}Z`;
}

function mismatch(value: TypedValueIr, field: Field): CompileError {
  return new CompileError("InvalidRequest", `A '${value.type}' value cannot be bound against a field declared '${field.type}': the coercion stage runs before a compiler.`);
}

/** A typed IR value as the value a driver binds. The type must be the field's own, or null. */
export function encodeValue(value: TypedValueIr, field: Field, dialect: Dialect, rounding: Rounding = "none"): Param {
  if (value.type === "null") return null;
  if (value.type !== field.type) throw mismatch(value, field);
  switch (value.type) {
    case "int64": {
      if (typeof value.value === "number") return value.value;
      const parsed = Number(value.value);
      return Number.isSafeInteger(parsed) ? parsed : new JsonNumber(value.value);
    }
    case "datetime":
      return normalizeInstant(value.value, dialect.datetimeBoundsAreFixedWidth, rounding);
    default:
      return value.value;
  }
}
