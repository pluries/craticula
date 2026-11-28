import type { ParseOptions } from "./agrid/request.js";
import { compile } from "./compile.js";
import { doc, type Value } from "./doc/ordered.js";
import { compileMongo } from "./mongo/compile.js";
import { compileSearch } from "./search/compile.js";
import type { Artifact } from "./sql/builder.js";
import { DIALECTS } from "./sql/dialects.js";

export interface CompileOptions extends ParseOptions {
  /** TL-1 to TL-4: the host's maximum query time in milliseconds, carried by the document compilers. Never read from a wire request. */
  readonly maxQueryTimeMs?: number;
}

/** A backend: the schema and request values in, the artifact as an ordered value out. */
export type Backend = (schemaValue: unknown, requestValue: unknown, options: CompileOptions, countMode: boolean) => Value;

function sqlArtifact(artifact: Artifact): Value {
  return doc(["dialect", artifact.dialect], ["sql", artifact.sql], ["params", artifact.params]);
}

/** The backends this port compiles, in the order the driver declares them: the C# driver's order. */
export const BACKENDS: ReadonlyMap<string, Backend> = new Map<string, Backend>([
  ...[...DIALECTS].map(([name, dialect]): [string, Backend] => [name, (schemaValue, requestValue, options, countMode) => sqlArtifact(compile(schemaValue, requestValue, options, countMode, dialect))]),
  ["mongo", compileMongo],
  ["search", compileSearch],
]);
