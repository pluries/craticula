/**
 * A strict JSON reader for request and schema text. `JSON.parse` is not enough here: it hides a duplicate key (the last wins), it
 * loses the text of a number (`1.0` becomes `1`), it accepts a lone surrogate, and it builds objects whose prototype a key such as
 * `__proto__` can reach. This reader refuses the first and the third, keeps the second when asked, bounds the nesting depth and the
 * length, and builds objects without a prototype.
 */
export type JsonErrorKind = "syntax" | "duplicate-key" | "depth" | "surrogate" | "too-long";

export class JsonError extends Error {
  readonly kind: JsonErrorKind;

  constructor(kind: JsonErrorKind, message: string) {
    super(message);
    this.name = "JsonError";
    this.kind = kind;
  }
}

/** A number kept as written: `1.0`, `2e2` and `9007199254740993` are three different texts. */
export class JsonNumber {
  readonly text: string;
  readonly value: number;

  constructor(text: string) {
    this.text = text;
    this.value = Number(text);
  }
}

export type JsonValue = string | number | boolean | null | JsonNumber | JsonValue[] | { [key: string]: JsonValue };

export interface ReadOptions {
  /** The deepest nesting accepted. Default 64, the C# parser's own bound. */
  readonly maxDepth?: number;
  /** The longest text accepted, in UTF-16 code units. Default 4 MiB. */
  readonly maxLength?: number;
  /** `native` (default) returns numbers; `text` returns a JsonNumber that keeps the written text. */
  readonly numbers?: "native" | "text";
  /** `refuse` (default) rejects a repeated key; `last` keeps the last one. Only for recovering the id of a line that is refused anyway. */
  readonly duplicateKeys?: "refuse" | "last";
}

const NUMBER = /-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/y;
const LONE_SURROGATE = /[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/;
const ESCAPES: Readonly<Record<string, string>> = { '"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" };

class Reader {
  private position = 0;
  private depth = 0;

  constructor(
    private readonly text: string,
    private readonly maxDepth: number,
    private readonly keepNumberText: boolean,
    private readonly allowDuplicates: boolean,
  ) {}

  read(): JsonValue {
    this.skipWhitespace();
    const value = this.value();
    this.skipWhitespace();
    if (this.position < this.text.length) {
      throw this.fail("unexpected content after the document");
    }
    return value;
  }

  private fail(message: string): JsonError {
    return new JsonError("syntax", `${message} at position ${this.position}`);
  }

  private skipWhitespace(): void {
    while (this.position < this.text.length && " \t\n\r".includes(this.text.charAt(this.position))) {
      this.position += 1;
    }
  }

  private value(): JsonValue {
    const c = this.text.charAt(this.position);
    if (c === "{") return this.object();
    if (c === "[") return this.array();
    if (c === '"') return this.string();
    if (c === "-" || (c >= "0" && c <= "9")) return this.number();
    for (const [literal, value] of [["true", true], ["false", false], ["null", null]] as const) {
      if (this.text.startsWith(literal, this.position)) {
        this.position += literal.length;
        return value;
      }
    }
    throw this.fail("expected a JSON value");
  }

  private enter(): void {
    this.depth += 1;
    if (this.depth > this.maxDepth) {
      throw new JsonError("depth", `the document is nested deeper than ${this.maxDepth} levels`);
    }
  }

  private object(): JsonValue {
    this.enter();
    this.position += 1;
    const result: { [key: string]: JsonValue } = Object.create(null) as { [key: string]: JsonValue };
    this.skipWhitespace();
    if (this.text.charAt(this.position) === "}") {
      this.position += 1;
      this.depth -= 1;
      return result;
    }
    for (;;) {
      this.skipWhitespace();
      if (this.text.charAt(this.position) !== '"') throw this.fail("expected a string key");
      const key = this.string();
      if (!this.allowDuplicates && Object.hasOwn(result, key)) {
        throw new JsonError("duplicate-key", `the key ${JSON.stringify(key)} appears twice in one object`);
      }
      this.skipWhitespace();
      if (this.text.charAt(this.position) !== ":") throw this.fail("expected ':'");
      this.position += 1;
      this.skipWhitespace();
      Object.defineProperty(result, key, { value: this.value(), enumerable: true, writable: true, configurable: true });
      this.skipWhitespace();
      const next = this.text.charAt(this.position);
      this.position += 1;
      if (next === "}") break;
      if (next !== ",") {
        this.position -= 1;
        throw this.fail("expected ',' or '}'");
      }
    }
    this.depth -= 1;
    return result;
  }

  private array(): JsonValue {
    this.enter();
    this.position += 1;
    const result: JsonValue[] = [];
    this.skipWhitespace();
    if (this.text.charAt(this.position) === "]") {
      this.position += 1;
      this.depth -= 1;
      return result;
    }
    for (;;) {
      this.skipWhitespace();
      result.push(this.value());
      this.skipWhitespace();
      const next = this.text.charAt(this.position);
      this.position += 1;
      if (next === "]") break;
      if (next !== ",") {
        this.position -= 1;
        throw this.fail("expected ',' or ']'");
      }
    }
    this.depth -= 1;
    return result;
  }

  private number(): JsonValue {
    NUMBER.lastIndex = this.position;
    const match = NUMBER.exec(this.text);
    if (match === null) throw this.fail("malformed number");
    this.position += match[0].length;
    return this.keepNumberText ? new JsonNumber(match[0]) : Number(match[0]);
  }

  private string(): string {
    this.position += 1;
    let out = "";
    for (;;) {
      if (this.position >= this.text.length) throw this.fail("unterminated string");
      const c = this.text.charAt(this.position);
      this.position += 1;
      if (c === '"') break;
      if (c < " ") throw this.fail("a control character in a string");
      if (c !== "\\") {
        out += c;
        continue;
      }
      const escape = this.text.charAt(this.position);
      this.position += 1;
      if (escape === "u") {
        const hex = this.text.slice(this.position, this.position + 4);
        if (!/^[0-9a-fA-F]{4}$/.test(hex)) throw this.fail("a malformed \\u escape");
        out += String.fromCharCode(Number.parseInt(hex, 16));
        this.position += 4;
      } else if (Object.hasOwn(ESCAPES, escape)) {
        out += ESCAPES[escape];
      } else {
        throw this.fail("an unknown escape");
      }
    }
    if (LONE_SURROGATE.test(out)) {
      throw new JsonError("surrogate", "a string holds a lone surrogate");
    }
    return out;
  }
}

/** Reads one JSON document, strictly. Throws a JsonError; never anything else. */
export function readJson(text: string, options: ReadOptions = {}): JsonValue {
  const maxLength = options.maxLength ?? 4_194_304;
  if (text.length > maxLength) {
    throw new JsonError("too-long", `the document is longer than ${maxLength} characters`);
  }
  return new Reader(text, options.maxDepth ?? 64, options.numbers === "text", options.duplicateKeys === "last").read();
}
