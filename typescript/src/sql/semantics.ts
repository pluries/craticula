import type { CaseMode } from "./dialect.js";
import type { Field, FieldType } from "../schema.js";

export type CaseMechanism = "none" | "collation" | "patternMatch";
export interface CaseDecision {
  readonly mode: CaseMode;
  readonly mechanism: CaseMechanism;
}

const COLLATION_OPS = new Set(["eq", "neq", "gt", "gte", "lt", "lte", "in", "notIn"]);
const PATTERN_OPS = new Set(["contains", "notContains", "startsWith", "endsWith"]);

function modeOf(field: Field): CaseMode {
  if (field.type !== "string") return "notApplicable";
  return field.caseSensitive ? "sensitive" : "insensitive";
}

/** SEM-1: how a filter operator compares the field's text. One mechanism per operator family, collation or pattern match. */
export function caseSensitivity(field: Field, op: string): CaseDecision {
  const mode = modeOf(field);
  if (mode !== "insensitive") return { mode, mechanism: "none" };
  if (COLLATION_OPS.has(op)) return { mode, mechanism: "collation" };
  return { mode, mechanism: PATTERN_OPS.has(op) ? "patternMatch" : "none" };
}

/** SEM-1: the mode for an ORDER BY key and a group key. A grouped level and an appended tiebreaker are never folded. */
export function orderingCaseSensitivity(field: Field, grouped: boolean, appendedTiebreaker = false): CaseMode {
  if (grouped || appendedTiebreaker) return "notApplicable";
  return modeOf(field);
}

/** SEM-2: a negative operator keeps the rows where the column is NULL. */
export function isNullInclusive(op: string): boolean {
  return op === "neq" || op === "notContains" || op === "notIn";
}

/** SEM-2: `blank` on text means NULL or the empty string, on any other type NULL only. */
export function blankCondition(type: FieldType): "nullOnly" | "nullOrEmptyString" {
  return type === "string" ? "nullOrEmptyString" : "nullOnly";
}
