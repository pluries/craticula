import { CompileError } from "../errors.js";
import type { Anchor, CaseMode, Dialect, Param } from "./dialect.js";
import { COMPARISON_SYMBOL } from "./dialect.js";
import { escapePattern } from "./escape.js";

const PATTERN_ESCAPE = "\\";

function collation(mode: CaseMode): string {
  switch (mode) {
    case "insensitive":
      return " COLLATE BINARY_CI";
    case "sensitive":
      return " COLLATE BINARY";
    default:
      return "";
  }
}

/**
 * SQL-7: Oracle stores a zero-length string as NULL, so binding one compiles to a comparison against NULL, which is UNKNOWN for every
 * row. The statement would be valid and silently wrong, so this dialect refuses it; `blank` and `notBlank` ask the question properly.
 */
function rejectEmpty(value: Param | undefined, construct: string): void {
  if (value === "") {
    throw new CompileError("InvalidRequest", `Oracle stores a zero-length string as NULL, so an empty value in ${construct} would silently match the wrong rows. Use the 'blank' or 'notBlank' operator instead.`);
  }
}

function likePattern(anchor: Anchor, placeholder: string): string {
  if (anchor === "anywhere") return `'%' || ${placeholder} || '%'`;
  return anchor === "start" ? `${placeholder} || '%'` : `'%' || ${placeholder}`;
}

/** Oracle: quoted identifiers, `:pN`, COLLATE BINARY_CI on the column, `||`, OFFSET/FETCH, native null position. */
export const oracle: Dialect = {
  name: "oracle",
  emptyStringIsNull: true,
  distinctValuesUseGroupBy: false,
  datetimeBoundsAreFixedWidth: false,

  quoteIdentifier(identifier: string): string {
    if (identifier.includes("\u0000")) throw new CompileError("InvalidSchema", "An identifier cannot contain a NUL character.");
    return `"${identifier.replaceAll('"', '""')}"`;
  },

  placeholder: (ordinal: number): string => `:p${ordinal + 1}`,

  scalar(column, op, value, _type, mode, sink): string {
    rejectEmpty(value, "a scalar comparison");
    return `${column}${collation(mode)} ${COMPARISON_SYMBOL[op]} ${sink.bind(value)}`;
  },

  substring(column, anchor, negated, value, mode, sink): string {
    rejectEmpty(value, "a substring match");
    const placeholder = sink.bind(escapePattern(value, PATTERN_ESCAPE));
    return `${column}${collation(mode)} ${negated ? "NOT LIKE" : "LIKE"} ${likePattern(anchor, placeholder)} ESCAPE '${PATTERN_ESCAPE}'`;
  },

  /** One empty member poisons a NOT IN list, so every member is checked before any is bound. */
  setMembership(column, negated, values, _type, mode, sink): string {
    for (const member of values) rejectEmpty(member, "a set membership list");
    const placeholders = values.map((value) => sink.bind(value));
    return `${column}${collation(mode)} ${negated ? "NOT IN" : "IN"} (${placeholders.join(", ")})`;
  },

  sortKey: (column, direction, nulls, mode): string => `${column}${collation(mode)} ${direction === "asc" ? "ASC" : "DESC"} NULLS ${nulls === "first" ? "FIRST" : "LAST"}`,

  /** The offset is bound first: the row-limiting clause spells it before the row count. */
  paging(offset, limit, sink): string {
    const offsetPlaceholder = sink.bind(offset);
    return `OFFSET ${offsetPlaceholder} ROWS FETCH NEXT ${sink.bind(limit)} ROWS ONLY`;
  },

  rowLimit: (limit, sink): string => `FETCH FIRST ${sink.bind(limit)} ROWS ONLY`,
};
