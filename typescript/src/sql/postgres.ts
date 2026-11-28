import { CompileError } from "../errors.js";
import type { Anchor, CaseMode, Dialect, Param, ParamSink, ScalarOp } from "./dialect.js";
import { COMPARISON_SYMBOL } from "./dialect.js";
import { escapePattern } from "./escape.js";
import type { FieldType } from "../schema.js";

/** SEM-1: the case-insensitive collation of the PostgreSQL dialect, the name the fixtures pin. */
export const CASE_INSENSITIVE_COLLATION = "craticula_ci";
const PATTERN_ESCAPE = "\\";

function collated(column: string, mode: CaseMode): string {
  return mode === "insensitive" ? `${column} COLLATE ${CASE_INSENSITIVE_COLLATION}` : column;
}

/** SQL-8: decimal, date and datetime values travel as text, and PostgreSQL has no `numeric = text`, so the placeholder is cast. */
const CAST: Readonly<Partial<Record<FieldType, string>>> = { decimal: "numeric", date: "date", datetime: "timestamptz" };

function castSuffix(type: FieldType, array: boolean): string {
  const cast = CAST[type];
  if (cast === undefined) return "";
  return array ? `::${cast}[]` : `::${cast}`;
}

function likePattern(anchor: Anchor, placeholder: string): string {
  if (anchor === "anywhere") return `'%' || ${placeholder} || '%'`;
  return anchor === "start" ? `${placeholder} || '%'` : `'%' || ${placeholder}`;
}

export const postgres: Dialect = {
  name: "postgres",
  emptyStringIsNull: false,
  distinctValuesUseGroupBy: false,
  datetimeBoundsAreFixedWidth: false,

  quoteIdentifier(identifier: string): string {
    if (identifier.includes("\u0000")) throw new CompileError("InvalidSchema", "An identifier cannot contain a NUL character.");
    return `"${identifier.replaceAll('"', '""')}"`;
  },

  placeholder: (ordinal: number): string => `$${ordinal + 1}`,

  scalar(column: string, op: ScalarOp, value: Param, type: FieldType, mode: CaseMode, sink: ParamSink): string {
    return `${collated(column, mode)} ${COMPARISON_SYMBOL[op]} ${sink.bind(value)}${castSuffix(type, false)}`;
  },

  substring(column, anchor, negated, value, mode, sink): string {
    const operator = `${negated ? "NOT " : ""}${mode === "insensitive" ? "ILIKE" : "LIKE"}`;
    const placeholder = sink.bind(escapePattern(value, PATTERN_ESCAPE));
    return `${column} ${operator} ${likePattern(anchor, placeholder)} ESCAPE '${PATTERN_ESCAPE}'`;
  },

  /** SQL-4: one array parameter, so the number of placeholders never depends on the number of values. */
  setMembership(column, negated, values, type, mode, sink): string {
    const placeholder = `${sink.bind(values)}${castSuffix(type, true)}`;
    return negated ? `${collated(column, mode)} <> ALL(${placeholder})` : `${collated(column, mode)} = ANY(${placeholder})`;
  },

  sortKey(column, direction, nulls, mode): string {
    return `${collated(column, mode)} ${direction === "asc" ? "ASC" : "DESC"} NULLS ${nulls === "first" ? "FIRST" : "LAST"}`;
  },

  /** The limit is bound first, as the fixtures pin. */
  paging(offset, limit, sink): string {
    const limitPlaceholder = sink.bind(limit);
    return `LIMIT ${limitPlaceholder} OFFSET ${sink.bind(offset)}`;
  },

  rowLimit: (limit, sink): string => `LIMIT ${sink.bind(limit)}`,
};
