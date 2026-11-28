import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { parseRequest, parseSetValues } from "../src/agrid/request.js";
import { CompileError } from "../src/errors.js";
import { processRow } from "../src/pipeline.js";
import { parseSchema } from "../src/schema.js";
import { prepareRow } from "../src/stages.js";

// Feature 013, review round (autopilot): behaviours where the first port diverged from the C# reference.
const base = {
  source: "t",
  stableKey: "id",
  fields: {
    id: { type: "int64", physical: { sql: { column: "id" } } },
    region: { type: "string", groupable: true, physical: { sql: { column: "region" } } },
    segment: { type: "string", groupable: true, physical: { sql: { column: "segment" } } },
    qty: { type: "int64", physical: { sql: { column: "qty" } } },
    ratio: { type: "double", physical: { sql: { column: "ratio" } } },
    ok: { type: "boolean", physical: { sql: { column: "ok" } } },
    day: { type: "date", physical: { sql: { column: "day" } } },
    at: { type: "datetime", physical: { sql: { column: "at" } } },
  },
};
const strict = parseSchema({ mode: "strict", ...base });
const col = (id: string, field = id) => ({ id, displayName: id, field });
const str = (value: string) => ({ type: "string", value });
const eq = (field: string, value: string) => ({ type: "comparison", field, op: "eq", value: str(value) });

function pairOf(action: () => unknown): [string | undefined, string | undefined] {
  try {
    action();
  } catch (error) {
    assert.ok(error instanceof CompileError, String(error));
    return [error.rejectedAt, error.reason];
  }
  return [undefined, undefined];
}

const parse = (extra: Record<string, unknown>) => parseRequest({ startRow: 0, endRow: 10, ...extra }, strict, {});

describe("the sort allowlist reads the raw request, in every mode", () => {
  const sortModel = [{ colId: "ghost", sort: "asc" }];

  it("refuses an undeclared sort column in a lenient schema and in count mode, and before the window is checked", () => {
    const lenient = { mode: "lenient", ...base };
    for (const [request, countMode] of [[{ startRow: 0, endRow: 10, sortModel }, false], [{ startRow: 0, endRow: 10, sortModel }, true], [{ startRow: 10, endRow: 5, sortModel }, false]] as const) {
      assert.deepEqual(pairOf(() => prepareRow(lenient, request, {}, countMode)), ["allowlist", "unknown-field"], JSON.stringify(request));
    }
  });
});

describe("the auto group column in a sort follows AG-6", () => {
  const rows = [col("regionCol", "region"), col("segment")];
  const sorted = (extra: Record<string, unknown>) => (parse({ rowGroupCols: rows, ...extra }).ir.sort ?? []).map((item) => `${item.field} ${item.direction}`);

  it("couples only what comes after the display column", () => {
    assert.deepEqual(sorted({ groupKeys: [str("EMEA")], sortModel: [{ colId: "region", sort: "asc" }, { colId: "ag-Grid-AutoColumn", sort: "desc" }] }), ["region asc", "segment desc"]);
  });

  it("keeps a sort the client sent on its own at a leaf, where the auto column is dropped", () => {
    const leaf = { rowGroupCols: [col("region")], groupKeys: [str("EMEA")], sortModel: [{ colId: "region", sort: "asc" }, { colId: "ag-Grid-AutoColumn", sort: "desc" }, { colId: "id", sort: "asc" }] };
    assert.deepEqual((parse(leaf).ir.sort ?? []).map((item) => item.field), ["region", "id"]);
  });

  it("resolves a suffixed auto column by the column's id, and couples only that one field", () => {
    assert.deepEqual(sorted({ sortModel: [{ colId: "ag-Grid-AutoColumn-regionCol", sort: "asc" }, { colId: "segment", sort: "asc" }] }), ["region asc", "segment asc"]);
    assert.deepEqual(sorted({ sortModel: [{ colId: "ag-Grid-AutoColumn-region", sort: "asc" }] }), ["ag-Grid-AutoColumn-region asc"]);
  });
});

describe("wire integers fit an Int32, as in the C# parser", () => {
  it("refuses a window or a limit above 2147483647", () => {
    assert.deepEqual(pairOf(() => parse({ startRow: 2147483648, endRow: 2147483700 })), ["requestParsing", "malformed-request"]);
    assert.deepEqual(pairOf(() => parseSetValues({ setValuesRequest: { colId: "region", filterModel: {}, limit: 3000000000 } }, strict)), ["requestParsing", "malformed-request"]);
    assert.doesNotThrow(() => parse({ startRow: 0, endRow: 2147483647, exportFormat: "csv", exportScope: "all" }));
  });
});

describe("an export discards group state before the group checks", () => {
  it("accepts duplicate output names, a bad alias and too many group keys on an export", () => {
    const request = {
      exportFormat: "csv",
      rowGroupCols: [col("region")],
      groupKeys: [str("a"), str("b")],
      valueCols: [{ id: "bad alias", displayName: "x", field: "qty", aggFunc: "sum" }, { id: "bad alias", displayName: "y", field: "id", aggFunc: "sum" }],
    };
    assert.doesNotThrow(() => parse(request));
    const ir = parse(request).ir;
    assert.equal("group" in ir || "aggregations" in ir, false);
  });

  it("still refuses group keys without group columns and an unknown function", () => {
    assert.deepEqual(pairOf(() => parse({ exportFormat: "csv", groupKeys: [str("a")] })), ["requestParsing", "malformed-request"]);
    assert.deepEqual(pairOf(() => parse({ exportFormat: "csv", valueCols: [{ id: "qty", displayName: "q", aggFunc: "median" }] })), ["requestParsing", "unknown-operator"]);
  });

  it("refuses an export when no field is exportable", () => {
    const none = parseSchema({ mode: "strict", ...base, fields: { id: { type: "int64", exportable: false, physical: { sql: { column: "id" } } } } });
    assert.deepEqual(pairOf(() => parseRequest({ exportFormat: "csv" }, none, {})), ["requestParsing", "malformed-request"]);
  });
});

describe("coercion trims what .NET trims and reads every calendar year", () => {
  const coerce = (field: string, text: string) => processRow(parse({ customFilters: eq(field, text) }).ir, strict).filter;
  const refused = (field: string, text: string) => pairOf(() => coerce(field, text));

  it("refuses the extra Unicode spaces JavaScript's trim would strip from a number", () => {
    assert.deepEqual(refused("qty", " 12"), ["typeCoercion", "uncoercible-value"]);
    assert.deepEqual(refused("ratio", "1.5　"), ["typeCoercion", "uncoercible-value"]);
    assert.deepEqual(refused("ok", "﻿true"), ["typeCoercion", "uncoercible-value"]);
    assert.doesNotThrow(() => coerce("qty", " 12\t"));
    assert.doesNotThrow(() => coerce("ok", "true\u0000"));
  });

  it("accepts a date and a datetime in the years 0001 to 0099", () => {
    assert.doesNotThrow(() => coerce("day", "0050-06-15"));
    assert.doesNotThrow(() => coerce("at", "0050-06-15T00:00:00Z"));
    assert.deepEqual(refused("day", "0050-02-30"), ["typeCoercion", "uncoercible-value"]);
  });
});

describe("set values envelope checks and the wire shapes C# ignores", () => {
  it("refuses a blank or oversized colId and an oversized prefix at parsing", () => {
    for (const envelope of [{ colId: "" }, { colId: "c".repeat(257) }, { colId: "region", searchPrefix: "p".repeat(8193) }]) {
      assert.deepEqual(pairOf(() => parseSetValues({ setValuesRequest: { filterModel: {}, ...envelope } }, strict)), ["requestParsing", "malformed-request"], JSON.stringify(envelope).slice(0, 40));
    }
  });

  it("ignores a pivotCols that is not an array and a ColumnVO field that is not a string", () => {
    assert.doesNotThrow(() => parse({ pivotCols: "x" }));
    assert.doesNotThrow(() => parse({ pivotCols: { a: 1 } }));
    assert.deepEqual(parse({ rowGroupCols: [{ id: "region", field: 5 }] }).ir.group?.groupCols, ["region"]);
  });
});
