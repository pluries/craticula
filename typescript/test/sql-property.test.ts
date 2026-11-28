import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { compile } from "../src/compile.js";
import { CompileError } from "../src/errors.js";
import { DIALECTS } from "../src/sql/dialects.js";

// Feature 014, T030 (SC-003, US1-AS2): over generated requests, no request value ever appears in the SQL text of any dialect; it is in the params.
const schema = {
  mode: "strict",
  source: "sales",
  stableKey: "id",
  fields: {
    id: { type: "int64", physical: { sql: { column: "id" } } },
    name: { type: "string", groupable: true, physical: { sql: { column: "name" } } },
    note: { type: "string", text: { caseSensitivity: "sensitive" }, groupable: true, physical: { sql: { column: "note" } } },
    amount: { type: "decimal", aggregatable: ["sum", "avg", "count"], physical: { sql: { column: "amount" } } },
  },
};

/** A small deterministic generator (mulberry32), so a failure is reproducible from the seed in the message. */
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

const HOSTILE = ["'", '"', "; DROP TABLE sales; --", "%", "_", "\\", "[x]", "`", "$1", ":p1", "@p1", "?", "||", "/*", "NULL"];
const STRING_OPS = ["eq", "neq", "contains", "notContains", "startsWith", "endsWith", "gt", "lte"];

describe("SC-003: no request value in the SQL text of any dialect", () => {
  it("holds for 400 generated requests on every dialect", () => {
    const failures: string[] = [];
    let compiled = 0;
    for (let seed = 1; seed <= 400; seed += 1) {
      const next = generator(seed);
      const pick = <T>(items: readonly T[]): T => items[Math.floor(next() * items.length)]!;
      const marker = `ZQ${seed}X`;
      const text = () => `${marker}${pick(HOSTILE)}${pick(HOSTILE)}`;
      const leaf = (): Record<string, unknown> => {
        if (next() < 0.25) {
          const count = 1 + Math.floor(next() * 4);
          return { type: "comparison", field: pick(["name", "note"]), op: pick(["in", "notIn"]), values: Array.from({ length: count }, () => ({ type: "string", value: text() })) };
        }
        return { type: "comparison", field: pick(["name", "note"]), op: pick(STRING_OPS), value: { type: "string", value: text() } };
      };
      const node = (depth: number): Record<string, unknown> => {
        if (depth === 0 || next() < 0.4) return leaf();
        const kind = pick(["and", "or", "not"]);
        return kind === "not" ? { type: "not", node: node(depth - 1) } : { type: kind, nodes: [node(depth - 1), node(depth - 1)] };
      };
      const grouped = next() < 0.3;
      const request: Record<string, unknown> = {
        startRow: 0,
        endRow: 1 + Math.floor(next() * 100),
        customFilters: node(2),
        sortModel: [{ colId: pick(["id", "name", "note"]), sort: pick(["asc", "desc"]) }],
        ...(grouped ? { rowGroupCols: [{ id: "name", displayName: "n" }], groupKeys: [], valueCols: [{ id: "amount", displayName: "a", aggFunc: pick(["sum", "avg", "count"]) }], sortModel: [{ colId: "name", sort: "asc" }] } : {}),
      };
      for (const [name, dialect] of DIALECTS) {
        for (const countMode of [false, true]) {
          try {
            const { sql, params } = compile(schema, request, {}, countMode, dialect);
            compiled += 1;
            const bound = JSON.stringify(params);
            if (sql.includes(marker)) failures.push(`seed ${seed} ${name}: the value is in the sql: ${sql}`);
            else if (!bound.includes(marker)) failures.push(`seed ${seed} ${name}: the value is in neither sql nor params`);
          } catch (error) {
            if (!(error instanceof CompileError)) failures.push(`seed ${seed} ${name}: ${String(error)}`);
          }
        }
      }
    }
    assert.deepEqual(failures, []);
    assert.ok(compiled >= 3900, `only ${compiled} of 4000 compiled`);
  });
});
