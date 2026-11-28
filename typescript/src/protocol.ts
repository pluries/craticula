import { isIsoInstant } from "./agrid/dates.js";
import { isRecord, wholeNumber } from "./agrid/values.js";
import { BACKENDS, type CompileOptions } from "./backends.js";
import { doc, writeJson } from "./doc/ordered.js";
import { CompileError } from "./errors.js";
import { JsonError, readJson } from "./json.js";
import { checkRequest } from "./stages.js";

/** The spec version this driver targets (`spec/VERSION`); a test keeps the two equal. */
export const SPEC_VERSION = "1.0.0";
export const MIN_NODE_MAJOR = 22;

export function assertSupportedNode(version: string): void {
  const major = Number.parseInt(version.split(".")[0] ?? "", 10);
  if (!Number.isInteger(major) || major < MIN_NODE_MAJOR) {
    throw new Error(`The Craticula TypeScript driver needs Node ${MIN_NODE_MAJOR} or newer; this is Node ${version}.`);
  }
}

/** The first line a driver prints (`spec/conformance-runner.md` §2.1). */
export function helloLine(): string {
  return JSON.stringify({ hello: { impl: "typescript", specVersion: SPEC_VERSION, backends: [...BACKENDS.keys()], capabilities: ["rejection"] } });
}

export type Outcome = { readonly answer: string } | { readonly unanswerable: string };

function errorLine(id: string, kind: string, message: string, rejection?: { readonly rejectedAt?: string | undefined; readonly reason?: string | undefined }): Outcome {
  const error: Record<string, string> = { kind, message };
  if (rejection?.rejectedAt !== undefined && rejection.reason !== undefined) {
    error["rejectedAt"] = rejection.rejectedAt;
    error["reason"] = rejection.reason;
  }
  return { answer: JSON.stringify({ id, error }) };
}

const NO_ID = "it is not a JSON object with a readable string 'id'";
const LEADING_SCAN = 2048;
const MAX_ID_LITERAL = 514;

function skipSpace(text: string, from: number): number {
  let at = from;
  while (at < text.length && " \t\n\r".includes(text.charAt(at))) at += 1;
  return at;
}

/** The end (exclusive) of the string literal that opens at `from`, or -1 when it is not one, runs past `limit` characters or holds a raw control character. */
function endOfString(text: string, from: number, limit: number): number {
  if (text.charAt(from) !== '"') return -1;
  for (let at = from + 1; at < text.length && at - from < limit; at += 1) {
    const c = text.charAt(at);
    if (c === '"') return at + 1;
    if (c === "\\") at += 1;
    else if (c < " ") return -1;
  }
  return -1;
}

/** Reads `"<name>":"<string>"` at `from`: the decoded string and the position after it. */
function member(text: string, from: number, name: string, limit: number): { value: string; end: number } | undefined {
  const key = `"${name}"`;
  if (!text.startsWith(key, from)) return undefined;
  const colon = skipSpace(text, from + key.length);
  if (text.charAt(colon) !== ":") return undefined;
  const start = skipSpace(text, colon + 1);
  const end = endOfString(text, start, limit);
  if (end < 0) return undefined;
  try {
    return { value: JSON.parse(text.slice(start, end)) as string, end };
  } catch {
    return undefined;
  }
}

/** The id (and kind) of a line the strict reader refused, when the line opens with them as the runner writes it (§2.2). */
function recoverLeading(line: string): { id: string; kind: string | undefined } | undefined {
  const text = line.slice(0, LEADING_SCAN);
  const open = skipSpace(text, 0);
  if (text.charAt(open) !== "{") return undefined;
  const id = member(text, skipSpace(text, open + 1), "id", MAX_ID_LITERAL);
  if (id === undefined) return undefined;
  const comma = skipSpace(text, id.end);
  const kind = text.charAt(comma) === "," ? member(text, skipSpace(text, comma + 1), "kind", 18) : undefined;
  return { id: id.value, kind: kind?.value };
}

const MALFORMED = { rejectedAt: "requestParsing", reason: "malformed-request" } as const;

/** The harness members of `requestContext` (§3) as parse options. They are read here, in the driver, and never by the library from a wire request. */
function harnessOf(request: unknown): { options: CompileOptions; countMode: boolean } {
  const context = isRecord(request) ? request["requestContext"] : undefined;
  if (context === undefined || context === null) return { options: {}, countMode: false };
  if (!isRecord(context)) throw new CompileError("InvalidRequest", "'requestContext' must be a JSON object or null.", MALFORMED);
  const options: { -readonly [K in keyof CompileOptions]: CompileOptions[K] } = {};
  const now = context["now"];
  if (now !== undefined && now !== null) {
    const instant = typeof now === "string" && isIsoInstant(now) ? new Date(now) : undefined;
    if (instant === undefined) throw new CompileError("InvalidRequest", "'requestContext.now' must be an ISO-8601 instant.", MALFORMED);
    options.now = () => instant;
  }
  const size = context["defaultPageSize"];
  if (size !== undefined && size !== null) {
    const whole = wholeNumber(size);
    if (whole === undefined || whole <= 0) throw new CompileError("InvalidRequest", "'requestContext.defaultPageSize' must be a positive whole number.", MALFORMED);
    options.defaultPageSize = whole;
  }
  if (context["allowUnboundedRows"] === true) options.allowUnboundedRows = true;
  const limit = context["maxQueryTimeMs"];
  if (limit !== undefined && limit !== null) {
    const whole = wholeNumber(limit);
    if (whole === undefined || whole < 1 || whole > 2_147_483_647) throw new CompileError("InvalidRequest", "'requestContext.maxQueryTimeMs' must be a whole number from 1 to 2147483647 (TL-4).", MALFORMED);
    options.maxQueryTimeMs = whole;
  }
  const mode = context["compileMode"];
  if (mode !== undefined && mode !== null && mode !== "count") throw new CompileError("InvalidRequest", `'requestContext.compileMode' ${JSON.stringify(mode)} is not supported.`, MALFORMED);
  return { options, countMode: mode === "count" };
}

/** One request line to one protocol line, or the reason the line cannot be answered because it has no id to echo (§2.4). */
export function answerFor(line: string): Outcome {
  let request: unknown;
  try {
    request = readJson(line, { numbers: "text" });
  } catch (error) {
    if (!(error instanceof JsonError)) throw error;
    const leading = recoverLeading(line);
    if (leading === undefined) return { unanswerable: `it is not JSON, or the strict reader refused it and it opens with no id (${error.message})` };
    return errorLine(leading.id, "InvalidRequest", `The request line was refused: ${error.message}.`, leading.kind === "rejection" ? MALFORMED : undefined);
  }
  if (!isRecord(request)) return { unanswerable: NO_ID };
  const id = request["id"];
  if (typeof id !== "string") return { unanswerable: NO_ID };

  const kind = request["kind"];
  if (kind !== undefined && kind !== "compile" && kind !== "rejection") {
    return errorLine(id, "Unsupported", `The request kind ${JSON.stringify(kind)} is not supported by this driver.`);
  }
  const backend = request["backend"];
  const compileFor = typeof backend === "string" ? BACKENDS.get(backend) : undefined;
  if (kind !== "rejection" && compileFor === undefined) {
    return errorLine(id, "Unsupported", `The backend '${String(backend).slice(0, 64)}' is not one this driver declares (${[...BACKENDS.keys()].join(", ")}).`);
  }
  try {
    const { options, countMode } = harnessOf(request["agGridRequest"]);
    if (kind === "rejection") {
      checkRequest(request["schema"], request["agGridRequest"], options, countMode);
      return { answer: JSON.stringify({ id, artifact: { accepted: true } }) };
    }
    return { answer: writeJson(doc(["id", id], ["artifact", compileFor!(request["schema"], request["agGridRequest"], options, countMode)])) };
  } catch (error) {
    if (error instanceof CompileError) {
      return errorLine(id, error.kind, error.message, kind === "rejection" ? error : undefined);
    }
    return errorLine(id, error instanceof Error ? error.name : "Error", error instanceof Error ? error.message : String(error));
  }
}
