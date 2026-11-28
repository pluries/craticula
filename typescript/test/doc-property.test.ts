import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { BACKENDS } from "../src/backends.js";
import { writeJson } from "../src/doc/ordered.js";
import { CompileError } from "../src/errors.js";

// Feature 015, T051 (SC-003, US1-AS2, US2-AS2): over generated requests with operator-, script- and pattern-shaped values, a value appears in the
// MongoDB and search artifacts only as a value, never as a key, and no server-side script operator is ever written.
const schema = {
  mode: "strict",
  source: "sales",
  stableKey: "id",
  fields: {
    id: { type: "int64", physical: { mongo: { path: "id" }, search: { field: "id" } } },
    name: { type: "string", groupable: true, physical: { mongo: { path: "name" }, search: { field: "name", keywordSubField: "name.keyword", normalizedSubField: "name.normalized" } } },
    note: { type: "string", text: { caseSensitivity: "sensitive" }, groupable: true, physical: { mongo: { path: "note" }, search: { field: "note", keywordSubField: "note.keyword" } } },
    amount: { type: "decimal", aggregatable: ["sum", "avg", "count"], physical: { mongo: { path: "amount" }, search: { field: "amount" } } },
  },
};

function generator(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const HOSTILE = ['{"$ne":null}', '{"$gt":""}', "$where", "$function", '{"script":{"source":"1"}}', "${jndi:x}", "<script>", "^(a+)+$", ".*", "\\", "*", "?", "$", "'", '"'];
const OPS = ["eq", "neq", "contains", "notContains", "startsWith", "endsWith", "gt", "lte"];
const FORBIDDEN = ["$where", "$function", "$accumulator", "$out", "$merge", "script", "script_score", "scripted_metric", "script_fields"];

function keysOf(value: unknown, into: string[] = []): string[] {
  if (Array.isArray(value)) value.forEach((item) => keysOf(item, into));
  else if (value !== null && typeof value === "object") {
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      into.push(key);
      keysOf(item, into);
    }
  }
  return into;
}

describe("SC-003: a value is never a key and a script operator is never written", () => {
  it("holds for 300 generated requests on both document backends", () => {
    const failures: string[] = [];
    let compiled = 0;
    for (let seed = 1; seed <= 300; seed += 1) {
      const next = generator(seed);
      const pick = <T>(items: readonly T[]): T => items[Math.floor(next() * items.length)]!;
      const marker = `ZQ${seed}X`;
      const text = () => `${marker}${pick(HOSTILE)}${pick(HOSTILE)}`;
      const leaf = (): Record<string, unknown> =>
        next() < 0.25
          ? { type: "comparison", field: pick(["name", "note"]), op: pick(["in", "notIn"]), values: [{ type: "string", value: text() }, { type: "string", value: text() }] }
          : { type: "comparison", field: pick(["name", "note"]), op: pick(OPS), value: { type: "string", value: text() } };
      const request = { startRow: 0, endRow: 1 + Math.floor(next() * 50), customFilters: leaf(), sortModel: [{ colId: pick(["id", "name"]), sort: pick(["asc", "desc"]) }] };
      for (const name of ["mongo", "search"]) {
        for (const countMode of [false, true]) {
          try {
            const artifact = writeJson(BACKENDS.get(name)!(schema, request, {}, countMode));
            compiled += 1;
            const parsed: unknown = JSON.parse(artifact);
            const keys = keysOf(parsed);
            if (keys.some((key) => key.includes(marker))) failures.push(`seed ${seed} ${name}: a value is a key`);
            if (keys.some((key) => FORBIDDEN.includes(key))) failures.push(`seed ${seed} ${name}: a script or write operator`);
            if (!artifact.includes(marker)) failures.push(`seed ${seed} ${name}: the value is missing`);
          } catch (error) {
            if (!(error instanceof CompileError)) failures.push(`seed ${seed} ${name}: ${String(error)}`);
          }
        }
      }
    }
    assert.deepEqual(failures, []);
    assert.ok(compiled >= 1100, `only ${compiled} of 1200 compiled`);
  });
});
