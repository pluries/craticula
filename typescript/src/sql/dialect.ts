import type { JsonNumber } from "../json.js";
import type { FieldType } from "../schema.js";

export type DialectName = "postgres" | "mssql" | "mysql" | "oracle" | "sqlite";

/** A bound value. An array is one array parameter (PostgreSQL set membership); a JsonNumber keeps the digits of an integer beyond 2^53. */
export type Param = string | number | boolean | null | JsonNumber | readonly Param[];

export type ScalarOp = "eq" | "neq" | "gt" | "gte" | "lt" | "lte";
export type Anchor = "anywhere" | "start" | "end";
/** SEM-1: whether a text comparison folds case, is exact, or does not apply (not text). */
export type CaseMode = "notApplicable" | "insensitive" | "sensitive";

/** The only way a value reaches a query: the sink hands back the placeholder to write into the text. */
export interface ParamSink {
  bind(value: Param): string;
}

/** What differs between engines (SQL-1 to SQL-8). The builder holds everything else. */
export interface Dialect {
  readonly name: DialectName;
  /** SQL-7: the engine treats the empty string as NULL. */
  readonly emptyStringIsNull: boolean;
  /** GRP-6(f): the distinct-values query groups instead of using DISTINCT. */
  readonly distinctValuesUseGroupBy: boolean;
  /** Instants are bound with exactly three fractional digits. */
  readonly datetimeBoundsAreFixedWidth: boolean;
  quoteIdentifier(identifier: string): string;
  /** The placeholder of the parameter at a zero-based position. */
  placeholder(ordinal: number): string;
  scalar(column: string, op: ScalarOp, value: Param, type: FieldType, mode: CaseMode, sink: ParamSink): string;
  substring(column: string, anchor: Anchor, negated: boolean, value: string, mode: CaseMode, sink: ParamSink): string;
  setMembership(column: string, negated: boolean, values: readonly Param[], type: FieldType, mode: CaseMode, sink: ParamSink): string;
  sortKey(column: string, direction: "asc" | "desc", nulls: "first" | "last", mode: CaseMode): string;
  paging(offset: number, limit: number, sink: ParamSink): string;
  rowLimit(limit: number, sink: ParamSink): string;
}

export const COMPARISON_SYMBOL: Readonly<Record<ScalarOp, string>> = { eq: "=", neq: "<>", gt: ">", gte: ">=", lt: "<", lte: "<=" };
