/** OSE-12: every ASCII character outside letters and digits is backslash-escaped in a term-level regular expression. */
export function escapeSearchRegex(value: string): string {
  let escaped = "";
  for (const character of value) {
    const code = (character.codePointAt(0) ?? 0);
    const alphanumeric = (code >= 48 && code <= 57) || (code >= 65 && code <= 90) || (code >= 97 && code <= 122);
    escaped += code <= 0x7f && !alphanumeric ? `\\${character}` : character;
  }
  return escaped;
}

/** SEM-7: `\\`, `*` and `?` are the wildcard query's special characters. */
export function escapeWildcard(value: string): string {
  let escaped = "";
  for (const character of value) escaped += character === "\\" || character === "*" || character === "?" ? `\\${character}` : character;
  return escaped;
}
