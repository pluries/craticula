import { compile } from "./compile.js";
import { CompileError } from "./errors.js";

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
  return JSON.stringify({ hello: { impl: "typescript", specVersion: SPEC_VERSION, backends: ["postgres"] } });
}

export type Outcome = { readonly answer: string } | { readonly unanswerable: string };

function errorLine(id: string, kind: string, message: string): Outcome {
  return { answer: JSON.stringify({ id, error: { kind, message } }) };
}

/** One request line to one protocol line, or the reason the line cannot be answered because it has no id to echo (§2.4). */
export function answerFor(line: string): Outcome {
  let request: unknown;
  try {
    request = JSON.parse(line);
  } catch (error) {
    return { unanswerable: `it is not JSON (${error instanceof Error ? error.message : String(error)})` };
  }
  if (typeof request !== "object" || request === null || Array.isArray(request)) {
    return { unanswerable: "it is not a JSON object with a readable string 'id'" };
  }
  const fields = request as Record<string, unknown>;
  const id = fields["id"];
  if (typeof id !== "string") {
    return { unanswerable: "it is not a JSON object with a readable string 'id'" };
  }

  const kind = fields["kind"];
  if (kind !== undefined && kind !== "compile") {
    return errorLine(id, "Unsupported", `The request kind ${JSON.stringify(kind)} is not supported by this driver.`);
  }
  if (fields["backend"] !== "postgres") {
    return errorLine(id, "Unsupported", `The backend '${String(fields["backend"])}' is not one this driver declares (postgres).`);
  }
  try {
    return { answer: JSON.stringify({ id, artifact: compile(fields["schema"], fields["agGridRequest"]) }) };
  } catch (error) {
    if (error instanceof CompileError) {
      return errorLine(id, error.kind, error.message);
    }
    return errorLine(id, error instanceof Error ? error.name : "Error", error instanceof Error ? error.message : String(error));
  }
}
