import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { compile } from "../src/compile.js";
import { CompileError } from "../src/errors.js";
import { parseSchema } from "../src/schema.js";
import { DIALECTS } from "../src/sql/dialects.js";
import { checkRequest } from "../src/stages.js";

// Feature 014, review round (autopilot): behaviour the fixtures do not reach, found by comparing with the C# compiler.
const schemaValue = {
  mode: "strict",
  source: "t",
  stableKey: "id",
  fields: {
    id: { type: "int64", groupable: true, physical: { sql: { column: "id" } } },
    name: { type: "string", groupable: true, physical: { sql: { column: "name" } } },
    amount: { type: "decimal", aggregatable: ["sum", "avg"], physical: { sql: { column: "amount" } } },
    at: { type: "datetime", physical: { sql: { column: "at" } } },
  },
};
const ask = (extra: Record<string, unknown>, dialect = "postgres") => compile(schemaValue, { startRow: 0, endRow: 10, ...extra }, {}, false, DIALECTS.get(dialect as never));
const custom = (value: unknown, op = "gt") => ({ customFilters: { type: "comparison", field: "at", op, value } });
const pair = (action: () => unknown): [string | undefined, string | undefined] => {
  try {
    action();
  } catch (error) {
    assert.ok(error instanceof CompileError, String(error));
    return [error.rejectedAt, error.reason];
  }
  return [undefined, undefined];
};

describe("datetimes in the years 0001 to 0099", () => {
  it("bind the year they were given, not 19xx", () => {
    const wire = ask({ filterModel: { at: { filterType: "date", type: "greaterThan", dateFrom: "0050-06-01 00:00:00" } } });
    assert.ok(wire.params.includes("0050-06-01T00:00:00Z"), JSON.stringify(wire.params));
  });
});

describe("datetime values the typed way", () => {
  it("round a fraction longer than seven digits half up, carrying into the next second", () => {
    assert.ok(ask(custom({ type: "datetime", value: "2020-01-01T00:00:00.12345678Z", zone: "UTC" })).params.includes("2020-01-01T00:00:00.1234568Z"));
    assert.ok(ask(custom({ type: "datetime", value: "2020-01-01T00:00:00.99999999Z", zone: "UTC" })).params.includes("2020-01-01T00:00:01Z"));
  });

  it("refuse an instant whose UTC time falls outside the years 0001 to 9999", () => {
    for (const value of ["9999-12-31T23:30:00-01:00", "0001-01-01T00:00:00+01:00"]) {
      assert.throws(() => ask(custom({ type: "datetime", value, zone: "UTC" })), CompileError, value);
    }
  });
});

describe("typed values the IR schema bounds", () => {
  it("refuses an int64 beyond 64 bits and a decimal beyond 128 characters as malformed", () => {
    assert.deepEqual(pair(() => ask({ customFilters: { type: "comparison", field: "id", op: "eq", value: { type: "int64", value: 18446744073709551616n.toString() } } })), ["requestParsing", "malformed-request"]);
    assert.deepEqual(pair(() => ask({ customFilters: { type: "comparison", field: "amount", op: "eq", value: { type: "decimal", value: "1".repeat(129) } } })), ["requestParsing", "malformed-request"]);
  });
});

describe("a grouped level sorts by an aggregate's id", () => {
  it("accepts an alias that differs from its field in a strict schema", () => {
    const artifact = ask({ rowGroupCols: [{ id: "name", displayName: "n" }], valueCols: [{ id: "total", displayName: "t", field: "amount", aggFunc: "sum" }], sortModel: [{ colId: "total", sort: "desc" }] });
    assert.match(artifact.sql, /ORDER BY COALESCE\(SUM\("amount"\), 0\) DESC NULLS FIRST/);
  });
});

describe("the rejection path compiles as the C# driver does", () => {
  it("refuses an output name that collides with the group column, as duplicate-output-name", () => {
    const request = { startRow: 0, endRow: 10, rowGroupCols: [{ id: "name", displayName: "n" }], valueCols: [{ id: "name", displayName: "x", field: "amount", aggFunc: "sum" }] };
    assert.deepEqual(pair(() => checkRequest(schemaValue, request)), ["requestParsing", "duplicate-output-name"]);
  });

  it("does not answer a set-values request in count mode", () => {
    const request = { setValuesRequest: { colId: "name", filterModel: {} } };
    assert.throws(() => compile(schemaValue, request, {}, true), CompileError);
  });
});

describe("the schema's static filter is read with the schema", () => {
  it("refuses a malformed one as an invalid schema, before any request is looked at", () => {
    const broken = { ...schemaValue, staticFilter: { type: "comparison", field: "id", op: "eq" } };
    assert.throws(() => parseSchema(broken), (error: unknown) => error instanceof CompileError && error.kind === "InvalidSchema");
  });
});
