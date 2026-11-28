import { CompileError } from "../errors.js";
import type { Anchor, Dialect } from "./dialect.js";
import { COMPARISON_SYMBOL } from "./dialect.js";
import { escapePattern } from "./escape.js";

const PATTERN_ESCAPE = "\\";

/** SQLite's GLOB has no escape clause: a wildcard is matched literally inside brackets. */
function escapeGlob(value: string): string {
  let escaped = "";
  for (const character of value) escaped += character === "*" || character === "?" || character === "[" ? `[${character}]` : character;
  return escaped;
}

function likePattern(anchor: Anchor, placeholder: string): string {
  if (anchor === "anywhere") return `'%' || ${placeholder} || '%'`;
  return anchor === "start" ? `${placeholder} || '%'` : `'%' || ${placeholder}`;
}

function globPattern(anchor: Anchor, placeholder: string): string {
  if (anchor === "anywhere") return `'*' || ${placeholder} || '*'`;
  return anchor === "start" ? `${placeholder} || '*'` : `'*' || ${placeholder}`;
}

/** SQLite: quoted identifiers, positional `?`, NOCASE on the value for a comparison and on the column elsewhere, GLOB for a case-sensitive match. */
export const sqlite: Dialect = {
  name: "sqlite",
  emptyStringIsNull: false,
  distinctValuesUseGroupBy: false,
  /** A datetime is TEXT here, compared character by character, so a bound carries the same three-digit fraction the host stores. */
  datetimeBoundsAreFixedWidth: true,

  quoteIdentifier(identifier: string): string {
    if (identifier.includes("\u0000")) throw new CompileError("InvalidSchema", "An identifier cannot contain a NUL character.");
    return `"${identifier.replaceAll('"', '""')}"`;
  },

  placeholder: (): string => "?",

  /** SEM-1: SQLite takes the left operand's collation if it has one, else the right's, so the value is collated and the column stays bare. */
  scalar(column, op, value, _type, mode, sink): string {
    const placeholder = sink.bind(value);
    return `${column} ${COMPARISON_SYMBOL[op]} ${mode === "insensitive" ? `${placeholder} COLLATE NOCASE` : placeholder}`;
  },

  substring(column, anchor, negated, value, mode, sink): string {
    if (mode !== "insensitive") {
      const placeholder = sink.bind(escapeGlob(value));
      return `${column} ${negated ? "NOT GLOB" : "GLOB"} ${globPattern(anchor, placeholder)}`;
    }
    const placeholder = sink.bind(escapePattern(value, PATTERN_ESCAPE));
    return `${column} ${negated ? "NOT LIKE" : "LIKE"} ${likePattern(anchor, placeholder)} ESCAPE '${PATTERN_ESCAPE}'`;
  },

  /** `x IN (...)` takes x's own collation, so it goes on the column here. */
  setMembership(column, negated, values, _type, mode, sink): string {
    const placeholders = values.map((value) => sink.bind(value));
    return `${mode === "insensitive" ? `${column} COLLATE NOCASE` : column} ${negated ? "NOT IN" : "IN"} (${placeholders.join(", ")})`;
  },

  sortKey: (column, direction, nulls, mode): string =>
    `${mode === "insensitive" ? `${column} COLLATE NOCASE` : column} ${direction === "asc" ? "ASC" : "DESC"} NULLS ${nulls === "first" ? "FIRST" : "LAST"}`,

  paging(offset, limit, sink): string {
    const limitPlaceholder = sink.bind(limit);
    return `LIMIT ${limitPlaceholder} OFFSET ${sink.bind(offset)}`;
  },

  rowLimit: (limit, sink): string => `LIMIT ${sink.bind(limit)}`,
};
