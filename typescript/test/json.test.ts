import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { JsonError, JsonNumber, readJson } from "../src/json.js";

// Feature 013, T001. Scenarios US3-AS7 (a hostile or oversized document is refused, never read without bound) and the spec's edge cases:
// duplicate keys, number text, lone surrogates, prototype-like keys.

function kindOf(action: () => unknown): string | undefined {
  try {
    action();
  } catch (error) {
    return error instanceof JsonError ? error.kind : `other:${String(error)}`;
  }
  return undefined;
}

describe("the strict JSON reader", () => {
  it("reads ordinary documents", () => {
    const value = readJson('{"a":[1,2,{"b":"x"}],"c":null,"d":true}') as Record<string, unknown>;
    assert.equal(JSON.stringify(value["a"]), '[1,2,{"b":"x"}]');
    assert.equal(value["c"], null);
    assert.equal(value["d"], true);
  });

  it("builds objects without a prototype", () => {
    const value = readJson('{"a":1}') as object;
    assert.equal(Object.getPrototypeOf(value), null);
  });

  it("keeps __proto__ as an ordinary key and pollutes nothing", () => {
    const value = readJson('{"__proto__":{"polluted":true},"constructor":1}') as Record<string, unknown>;
    assert.deepEqual(Object.keys(value), ["__proto__", "constructor"]);
    assert.equal(({} as Record<string, unknown>)["polluted"], undefined);
  });

  it("refuses a duplicate key, at the root and nested", () => {
    assert.equal(kindOf(() => readJson('{"a":1,"a":2}')), "duplicate-key");
    assert.equal(kindOf(() => readJson('{"x":{"a":1,"b":2,"a":3}}')), "duplicate-key");
    assert.equal(kindOf(() => readJson('[{"a":1},{"a":1}]')), undefined, "the same key in two objects is not a duplicate");
  });

  it("refuses syntax errors, NaN and Infinity", () => {
    for (const text of ["", "{", '{"a":1,}', "[1,]", "NaN", "[Infinity]", "{'a':1}", '{"a":01}', "1 2", '{"a" 1}']) {
      assert.equal(kindOf(() => readJson(text)), "syntax", text);
    }
  });

  it("refuses a lone surrogate and accepts a valid pair", () => {
    assert.equal(kindOf(() => readJson('"\\ud800"')), "surrogate");
    assert.equal(kindOf(() => readJson('"\\udc00x"')), "surrogate");
    assert.equal(readJson('"\\ud83d\\ude00"'), "😀");
  });

  it("bounds the nesting depth: 64 levels pass, 65 are refused", () => {
    const nested = (levels: number): string => "[".repeat(levels) + "]".repeat(levels);
    assert.doesNotThrow(() => readJson(nested(64)));
    assert.equal(kindOf(() => readJson(nested(65))), "depth");
    assert.equal(kindOf(() => readJson(nested(200_000))), "depth", "a depth bomb never reaches the stack limit");
    assert.equal(kindOf(() => readJson(nested(3), { maxDepth: 2 })), "depth");
  });

  it("bounds the length", () => {
    assert.equal(kindOf(() => readJson('"' + "a".repeat(100) + '"', { maxLength: 50 })), "too-long");
  });

  it("returns native numbers by default", () => {
    assert.equal(readJson("[1.0]") instanceof Array, true);
    assert.deepEqual(readJson("[1.0, 2e2, -0.5]"), [1, 200, -0.5]);
  });

  it("keeps the text of every number when asked", () => {
    const value = readJson("[1.0, 2e2, 9007199254740993, 0.10]", { numbers: "text" }) as JsonNumber[];
    assert.deepEqual(value.map((n) => n.text), ["1.0", "2e2", "9007199254740993", "0.10"]);
    assert.ok(value.every((n) => n instanceof JsonNumber));
    assert.equal(value[0]!.value, 1);
  });
});
