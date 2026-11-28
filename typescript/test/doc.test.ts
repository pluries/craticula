import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { doc, writeJson } from "../src/doc/ordered.js";
import { JsonNumber } from "../src/json.js";

// Feature 015, T001 (US1-AS1): the ordered document the MongoDB artifact is built on, and its writer.
describe("the ordered document and its writer", () => {
  it("keeps the insertion order of integer-like keys, which a plain object would list first", () => {
    const value = doc(["b", 1], ["10", 2], ["a", 3], ["2", 4]);
    assert.equal(writeJson(value), '{"b":1,"10":2,"a":3,"2":4}');
    assert.equal(JSON.stringify({ b: 1, 10: 2, a: 3, 2: 4 }), '{"2":4,"10":2,"b":1,"a":3}', "the problem this type exists to avoid");
  });

  it("writes nested documents, arrays, null, booleans and escaped strings compactly", () => {
    const value = doc(["x", [1, "q\"\\\n", null, true]], ["y", doc(["z", []])]);
    assert.equal(writeJson(value), '{"x":[1,"q\\"\\\\\\n",null,true],"y":{"z":[]}}');
  });

  it("writes a JsonNumber with the digits it carries", () => {
    assert.equal(writeJson(doc(["n", new JsonNumber("9007199254740993")])), '{"n":9007199254740993}');
  });

  it("writes a bare array and a scalar", () => {
    assert.equal(writeJson([doc(["a", 1]), doc(["b", 2])]), '[{"a":1},{"b":2}]');
    assert.equal(writeJson("text"), '"text"');
  });

  it("refuses a number that is not finite", () => {
    assert.throws(() => writeJson(Number.NaN), RangeError);
    assert.throws(() => writeJson(Number.POSITIVE_INFINITY), RangeError);
  });
});

describe("numbers are written as .NET writes them, because the runner compares their text", () => {
  it("uses scientific notation below 1E-4 and from 1E+17, with an upper-case E, a sign and two exponent digits at least", () => {
    assert.equal(writeJson(1e21), "1E+21");
    assert.equal(writeJson(1e19), "1E+19");
    assert.equal(writeJson(4.9e-324), "5E-324");
    assert.equal(writeJson(1e-5), "1E-05");
    assert.equal(writeJson(1.5e-7), "1.5E-07");
    assert.equal(writeJson(1.2345678901234568e17), "1.2345678901234568E+17");
  });

  it("keeps fixed notation in between, negative zero and plain integers", () => {
    assert.equal(writeJson(1e16), "10000000000000000");
    assert.equal(writeJson(0.0001), "0.0001");
    assert.equal(writeJson(123456.789), "123456.789");
    assert.equal(writeJson(100), "100");
    assert.equal(writeJson(-0), "-0");
    assert.equal(writeJson(0), "0");
  });
});
