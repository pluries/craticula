/** SEM-7: escapes the escape character, `%` and `_` in a value used inside a LIKE pattern. */
export function escapePattern(value: string, escapeCharacter: string): string {
  let escaped = "";
  for (const character of value) {
    if (character === escapeCharacter || character === "%" || character === "_") escaped += escapeCharacter;
    escaped += character;
  }
  return escaped;
}

/** SQL-5: as `escapePattern`, and a left bracket too, for an engine whose LIKE reads `[...]` as a character class. */
export function escapePatternWithBracket(value: string, escapeCharacter: string): string {
  return escapePattern(value, escapeCharacter).replaceAll("[", `${escapeCharacter}[`);
}
