import { CompileError } from "../errors.js";
import type { Anchor, Dialect } from "./dialect.js";
import { COMPARISON_SYMBOL } from "./dialect.js";
import { escapePattern } from "./escape.js";

const PATTERN_ESCAPE = "\\";
/** The escape clause as MySQL reads its string literal: two backslashes spell one. */
const PATTERN_ESCAPE_LITERAL = "\\\\";

function likePattern(anchor: Anchor, placeholder: string): string {
  if (anchor === "anywhere") return `CONCAT('%', ${placeholder}, '%')`;
  return anchor === "start" ? `CONCAT(${placeholder}, '%')` : `CONCAT('%', ${placeholder})`;
}

/** MySQL: backtick quoting, positional `?`, the column's own (case-insensitive) collation, CONCAT, LIMIT/OFFSET, ISNULL for null position. */
export const mysql: Dialect = {
  name: "mysql",
  emptyStringIsNull: false,
  distinctValuesUseGroupBy: false,
  datetimeBoundsAreFixedWidth: false,

  quoteIdentifier(identifier: string): string {
    if (identifier.includes("\u0000")) throw new CompileError("InvalidSchema", "An identifier cannot contain a NUL character.");
    return `\`${identifier.replaceAll("`", "``")}\``;
  },

  placeholder: (): string => "?",

  scalar: (column, op, value, _type, _mode, sink): string => `${column} ${COMPARISON_SYMBOL[op]} ${sink.bind(value)}`,

  substring(column, anchor, negated, value, _mode, sink): string {
    const placeholder = sink.bind(escapePattern(value, PATTERN_ESCAPE));
    return `${column} ${negated ? "NOT LIKE" : "LIKE"} ${likePattern(anchor, placeholder)} ESCAPE '${PATTERN_ESCAPE_LITERAL}'`;
  },

  setMembership(column, negated, values, _type, _mode, sink): string {
    const placeholders = values.map((value) => sink.bind(value));
    return `${column} ${negated ? "NOT IN" : "IN"} (${placeholders.join(", ")})`;
  },

  /** SEM-3: no NULLS FIRST or LAST, so ISNULL buckets the nulls ahead of the key. */
  sortKey: (column, direction, nulls): string => `ISNULL(${column}) ${nulls === "first" ? "DESC" : "ASC"}, ${column} ${direction === "asc" ? "ASC" : "DESC"}`,

  paging(offset, limit, sink): string {
    const limitPlaceholder = sink.bind(limit);
    return `LIMIT ${limitPlaceholder} OFFSET ${sink.bind(offset)}`;
  },

  rowLimit: (limit, sink): string => `LIMIT ${sink.bind(limit)}`,
};
