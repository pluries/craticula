import { CompileError } from "../errors.js";
import type { Anchor, CaseMode, Dialect } from "./dialect.js";
import { COMPARISON_SYMBOL } from "./dialect.js";
import { escapePatternWithBracket } from "./escape.js";

const PATTERN_ESCAPE = "\\";

function collation(mode: CaseMode): string {
  switch (mode) {
    case "insensitive":
      return " COLLATE Latin1_General_CI_AS";
    case "sensitive":
      return " COLLATE Latin1_General_CS_AS";
    default:
      return "";
  }
}

function likePattern(anchor: Anchor, placeholder: string): string {
  if (anchor === "anywhere") return `'%' + ${placeholder} + '%'`;
  return anchor === "start" ? `${placeholder} + '%'` : `'%' + ${placeholder}`;
}

/** SQL Server (T-SQL): bracket quoting, `@pN`, a collation on the column both ways, `+` concatenation, OFFSET/FETCH, a bucket key for null position. */
export const mssql: Dialect = {
  name: "mssql",
  emptyStringIsNull: false,
  distinctValuesUseGroupBy: true,
  datetimeBoundsAreFixedWidth: false,

  quoteIdentifier(identifier: string): string {
    if (identifier.includes("\u0000")) throw new CompileError("InvalidSchema", "An identifier cannot contain a NUL character.");
    return `[${identifier.replaceAll("]", "]]")}]`;
  },

  placeholder: (ordinal: number): string => `@p${ordinal + 1}`,

  scalar: (column, op, value, _type, mode, sink): string => `${column}${collation(mode)} ${COMPARISON_SYMBOL[op]} ${sink.bind(value)}`,

  substring(column, anchor, negated, value, mode, sink): string {
    const placeholder = sink.bind(escapePatternWithBracket(value, PATTERN_ESCAPE));
    return `${column}${collation(mode)} ${negated ? "NOT LIKE" : "LIKE"} ${likePattern(anchor, placeholder)} ESCAPE '${PATTERN_ESCAPE}'`;
  },

  setMembership(column, negated, values, _type, mode, sink): string {
    const placeholders = values.map((value) => sink.bind(value));
    return `${column}${collation(mode)} ${negated ? "NOT IN" : "IN"} (${placeholders.join(", ")})`;
  },

  /** SEM-3: T-SQL has no NULLS FIRST or LAST, so a leading key buckets the nulls. A case-sensitive key collates inside the bucket test too. */
  sortKey(column, direction, nulls, mode): string {
    const bucket = nulls === "first" ? "DESC" : "ASC";
    const tested = mode === "sensitive" ? `${column}${collation(mode)}` : column;
    return `CASE WHEN ${tested} IS NULL THEN 1 ELSE 0 END ${bucket}, ${column}${collation(mode)} ${direction === "asc" ? "ASC" : "DESC"}`;
  },

  /** The offset is bound first: OFFSET/FETCH spells it before the row count. */
  paging(offset, limit, sink): string {
    const offsetPlaceholder = sink.bind(offset);
    return `OFFSET ${offsetPlaceholder} ROWS FETCH NEXT ${sink.bind(limit)} ROWS ONLY`;
  },

  /** FETCH is illegal without an OFFSET on this engine, so the cap spells a literal zero. */
  rowLimit: (limit, sink): string => `OFFSET 0 ROWS FETCH NEXT ${sink.bind(limit)} ROWS ONLY`,
};
