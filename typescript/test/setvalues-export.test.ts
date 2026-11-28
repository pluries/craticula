import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { parseRequest, parseSetValues } from "../src/agrid/request.js";
import { CompileError } from "../src/errors.js";
import { parseSchema } from "../src/schema.js";

// Feature 013, T010 (S2c-2): the set-values entry point (BM-3, GRP-6) and the exportColumns member (EXP-1(b), EXP-5).
const SCHEMA = parseSchema({
  mode: "strict",
  source: "sales",
  stableKey: "id",
  fields: {
    id: { type: "int64", physical: { sql: { column: "id" } } },
    region: { type: "string", label: "Region", physical: { sql: { column: "region" } } },
    amount: { type: "decimal", label: "Amount", format: { decimalSeparator: "," }, physical: { sql: { column: "amount" } } },
    secret: { type: "string", exportable: false, physical: { sql: { column: "secret" } } },
  },
});

function pairOf(action: () => unknown): [string | undefined, string | undefined] {
  try {
    action();
  } catch (error) {
    assert.ok(error instanceof CompileError, String(error));
    return [error.rejectedAt, error.reason];
  }
  return [undefined, undefined];
}

const bad: [string, string] = ["requestParsing", "malformed-request"];

describe("US2-AS5: set values", () => {
  const envelope = (extra: Record<string, unknown> = {}) => ({ setValuesRequest: { colId: "region", filterModel: {}, ...extra } });

  it("reads the column, the prefix and the limit, and parses the envelope's filter model untouched by the own-field rule", () => {
    const parsed = parseSetValues(envelope({ searchPrefix: "eu", limit: 20, filterModel: { region: { filterType: "text", type: "equals", filter: "EMEA" } } }), SCHEMA);
    assert.deepEqual(parsed.setValues, { colId: "region", searchPrefix: "eu", limit: 20 });
    assert.equal(parsed.nativeFilter?.type, "comparison");
  });

  it("omits an absent prefix and limit, accepts a null filter model, and carries custom filters", () => {
    const parsed = parseSetValues(envelope({ filterModel: null, customFilters: { type: "comparison", field: "id", op: "eq", value: { type: "int64", value: 1 } } }), SCHEMA);
    assert.deepEqual(parsed.setValues, { colId: "region" });
    assert.equal(parsed.nativeFilter, undefined);
    assert.equal(parsed.customFilters?.type, "comparison");
  });

  it("refuses a root that is not an object, a missing or non-object envelope, and a malformed envelope", () => {
    const cases: unknown[] = [
      [],
      {},
      { setValuesRequest: 3 },
      envelope({ colId: 5 }),
      { setValuesRequest: { filterModel: {} } },
      { setValuesRequest: { colId: "region" } },
      envelope({ filterModel: "x" }),
      envelope({ searchPrefix: 3 }),
      envelope({ limit: "ten" }),
    ];
    for (const value of cases) assert.deepEqual(pairOf(() => parseSetValues(value, SCHEMA)), bad, JSON.stringify(value));
  });

  it("is not a row request, and a row request is not a set-values request", () => {
    assert.deepEqual(pairOf(() => parseRequest(envelope(), SCHEMA, {})), bad);
    assert.deepEqual(pairOf(() => parseSetValues({ startRow: 0, endRow: 10 }, SCHEMA)), bad);
  });
});

describe("US2-AS5: export columns", () => {
  const base = { exportFormat: "csv", exportScope: "all", startRow: null, endRow: null };

  it("keeps the wire's own order, with the header from the wire, the schema label or the colId", () => {
    const parsed = parseRequest({ ...base, exportColumns: [{ colId: "amount", header: "Total" }, { colId: "region" }, { colId: "id" }] }, SCHEMA, {});
    assert.deepEqual(parsed.export?.columns, ["amount", "region", "id"]);
    assert.deepEqual(parsed.export?.columnSpecs, [
      { colId: "amount", header: "Total", format: { decimalSeparator: "," } },
      { colId: "region", header: "Region" },
      { colId: "id", header: "id" },
    ]);
  });

  it("the default projection carries labels and formats too", () => {
    const specs = parseRequest({ ...base }, SCHEMA, {}).export?.columnSpecs;
    assert.deepEqual(specs?.map((s) => [s.colId, s.header]), [["id", "id"], ["region", "Region"], ["amount", "Amount"]]);
  });

  it("refuses an empty list, a repeat, an unknown or non-exportable column, and entries of the wrong shape", () => {
    const cases: unknown[] = [[], [{ colId: "id" }, { colId: "id" }], [{ colId: "ghost" }], [{ colId: "secret" }], "id", [3], [{ header: "x" }]];
    for (const exportColumns of cases) assert.deepEqual(pairOf(() => parseRequest({ ...base, exportColumns }, SCHEMA, {})), bad, JSON.stringify(exportColumns));
  });
});
