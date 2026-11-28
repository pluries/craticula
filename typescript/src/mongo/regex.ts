/** MDB-11: every ASCII character outside `[A-Za-z0-9]` is backslash-escaped; a non-ASCII character is left alone. */
export function escapeRegex(value: string): string {
  let escaped = "";
  for (const character of value) {
    const code = character.charCodeAt(0);
    const plain = code >= 0x80 || (code >= 48 && code <= 57) || (code >= 65 && code <= 90) || (code >= 97 && code <= 122);
    escaped += plain ? character : `\\${character}`;
  }
  return escaped;
}
