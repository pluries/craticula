import { CompileError } from "./errors.js";

/** The case-insensitive collation of the PostgreSQL dialect (SEM-1), the same name the fixtures pin. */
export const CASE_INSENSITIVE_COLLATION = "craticula_ci";

/**
 * Quotes an identifier. The only function that puts a schema-declared name into SQL text: a double quote is doubled,
 * and a NUL is refused because PostgreSQL cannot hold one.
 */
export function quoteIdentifier(name: string): string {
  if (name.includes("\u0000")) {
    throw new CompileError("InvalidSchema", "An identifier cannot contain a NUL character.");
  }
  return `"${name.replaceAll('"', '""')}"`;
}

/** SEM-1 and SEM-3: collation (text only), direction, then an explicit null position, never the engine's default. */
export function renderSortKey(column: string, direction: "asc" | "desc", nulls: "first" | "last", insensitive: boolean): string {
  const collation = insensitive ? ` COLLATE ${CASE_INSENSITIVE_COLLATION}` : "";
  return `${column}${collation} ${direction === "asc" ? "ASC" : "DESC"} NULLS ${nulls === "first" ? "FIRST" : "LAST"}`;
}

/** The bound parameter bag: values are never spelled into the text, only their `$n` placeholder is. */
export class ParameterBag {
  readonly values: (string | number | boolean)[] = [];

  bind(value: string | number | boolean): string {
    this.values.push(value);
    return `$${this.values.length}`;
  }
}

/** `LIMIT $n OFFSET $m`, the limit bound first, as the fixtures pin. */
export function renderPaging(limit: number, offset: number, parameters: ParameterBag): string {
  const limitPlaceholder = parameters.bind(limit);
  const offsetPlaceholder = parameters.bind(offset);
  return `LIMIT ${limitPlaceholder} OFFSET ${offsetPlaceholder}`;
}
