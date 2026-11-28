import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { parseRequest, parseSetValues } from "../src/agrid/request.js";
import { CompileError } from "../src/errors.js";
import type { FilterNodeIr, Ir } from "../src/ir.js";
import { createLimits } from "../src/limits.js";
import { processRow, processSetValues } from "../src/pipeline.js";
import { parseSchema } from "../src/schema.js";

// Feature 013, T020 (US3): the stages after parsing, in the order of spec/conformance-runner.md §3:
// the allowlist (SC-1, SC-2), the limits (SEC-3), the coercion (SEM-5). Static filter injection belongs to the compilers (feature 014).
function schemaOf(mode: "strict" | "lenient" = "strict") {
  return parseSchema({
    mode,
    source: "sales",
    stableKey: "id",
    fields: {
      id: { type: "int64", physical: { sql: { column: "id" } } },
      region: { type: "string", groupable: true, physical: { sql: { column: "region" } } },
      segment: { type: "string", groupable: true, filterable: false, physical: { sql: { column: "segment" } } },
      qty: { type: "int64", groupable: true, physical: { sql: { column: "qty" } } },
      price: { type: "decimal", aggregatable: ["sum"], physical: { sql: { column: "price" } } },
      ratio: { type: "double", physical: { sql: { column: "ratio" } } },
      active: { type: "boolean", physical: { sql: { column: "active" } } },
      day: { type: "date", physical: { sql: { column: "day" } } },
      at: { type: "datetime", physical: { sql: { column: "at" } } },
      flat: { type: "string", groupable: false, physical: { sql: { column: "flat" } } },
    },
  });
}

const eq = (field: string, value: unknown): FilterNodeIr => ({ type: "comparison", field, op: "eq", value: value as never });
const str = (value: string) => ({ type: "string", value }) as const;

function pairOf(action: () => unknown): [string | undefined, string | undefined] {
  try {
    action();
  } catch (error) {
    assert.ok(error instanceof CompileError, String(error));
    return [error.rejectedAt, error.reason];
  }
  return [undefined, undefined];
}

function row(extra: Record<string, unknown>, mode: "strict" | "lenient" = "strict") {
  const schema = schemaOf(mode);
  const { ir } = parseRequest({ startRow: 0, endRow: 100, ...extra }, schema, {});
  return { schema, ir };
}

function nested(depth: number, leaf: FilterNodeIr): FilterNodeIr {
  let node = leaf;
  for (let i = 1; i < depth; i++) node = { type: "and", nodes: [node] };
  return node;
}

describe("US3: the allowlist", () => {
  it("refuses an unknown filter column in a strict schema and strips it in a lenient one", () => {
    const request = { customFilters: { type: "and", nodes: [eq("ghost", str("x")), eq("region", str("EMEA"))] } };
    const strict = row(request);
    assert.deepEqual(pairOf(() => processRow(strict.ir, strict.schema)), ["allowlist", "unknown-field"]);
    const lenient = row(request, "lenient");
    assert.deepEqual(processRow(lenient.ir, lenient.schema).filter, eq("region", str("EMEA")));
  });

  it("refuses a column declared filterable: false as field-not-filterable", () => {
    const { ir, schema } = row({ customFilters: eq("segment", str("x")) });
    assert.deepEqual(pairOf(() => processRow(ir, schema)), ["allowlist", "field-not-filterable"]);
  });

  it("refuses a group column that is unknown or not groupable, as unknown-field", () => {
    for (const col of ["ghost", "flat"]) {
      const { ir, schema } = row({ rowGroupCols: [{ id: col, displayName: col }] });
      assert.deepEqual(pairOf(() => processRow(ir, schema)), ["allowlist", "unknown-field"], col);
    }
  });

  it("refuses an aggregation on an unknown field or outside the field's declared functions", () => {
    for (const valueCols of [[{ id: "ghost", displayName: "g", aggFunc: "sum" }], [{ id: "price", displayName: "p", aggFunc: "avg" }]]) {
      const { ir, schema } = row({ valueCols });
      assert.deepEqual(pairOf(() => processRow(ir, schema)), ["allowlist", "unknown-field"], JSON.stringify(valueCols));
    }
  });

  it("holds a consumed drill-down key to the filterable flag, and leaves an unconsumed group column alone", () => {
    const cols = [{ id: "segment", displayName: "s" }, { id: "region", displayName: "r" }];
    const consumed = row({ rowGroupCols: cols, groupKeys: [str("x")] });
    assert.deepEqual(pairOf(() => processRow(consumed.ir, consumed.schema)), ["allowlist", "field-not-filterable"]);
    const unconsumed = row({ rowGroupCols: cols });
    assert.doesNotThrow(() => processRow(unconsumed.ir, unconsumed.schema));
  });

  it("holds a set-values target to the allowlist in every mode", () => {
    const schema = schemaOf("lenient");
    for (const [colId, reason] of [["ghost", "unknown-field"], ["segment", "field-not-filterable"]] as const) {
      const parsed = parseSetValues({ setValuesRequest: { colId, filterModel: {} } }, schema);
      assert.deepEqual(pairOf(() => processSetValues(parsed, schema)), ["allowlist", reason], colId);
    }
  });
});

describe("US3: the limits", () => {
  const leaf = eq("region", str("x"));

  it("accepts a filter tree of depth 8 and refuses depth 9", () => {
    const ok = row({ customFilters: nested(8, leaf) });
    assert.doesNotThrow(() => processRow(ok.ir, ok.schema));
    const over = row({ customFilters: nested(9, leaf) });
    assert.deepEqual(pairOf(() => processRow(over.ir, over.schema)), ["resourceLimits", "max-depth-exceeded"]);
  });

  it("accepts 64 leaves and refuses 65", () => {
    const wide = (n: number): FilterNodeIr => ({ type: "or", nodes: Array.from({ length: n }, () => leaf) });
    const ok = row({ customFilters: wide(64) });
    assert.doesNotThrow(() => processRow(ok.ir, ok.schema));
    const over = row({ customFilters: wide(65) });
    assert.deepEqual(pairOf(() => processRow(over.ir, over.schema)), ["resourceLimits", "max-leaves-exceeded"]);
  });

  it("accepts 1000 values in a set condition and refuses 1001", () => {
    const set = (n: number): FilterNodeIr => ({ type: "comparison", field: "region", op: "in", values: Array.from({ length: n }, (_, i) => str(`v${i}`)) });
    const ok = row({ customFilters: set(1000) });
    assert.doesNotThrow(() => processRow(ok.ir, ok.schema));
    const over = row({ customFilters: set(1001) });
    assert.deepEqual(pairOf(() => processRow(over.ir, over.schema)), ["resourceLimits", "max-in-values-exceeded"]);
  });

  it("accepts a page of 1000 rows and refuses 1001, but not an unpaginated export", () => {
    const ok = row({ startRow: 0, endRow: 1000 });
    assert.doesNotThrow(() => processRow(ok.ir, ok.schema));
    const over = row({ startRow: 0, endRow: 1001 });
    assert.deepEqual(pairOf(() => processRow(over.ir, over.schema)), ["resourceLimits", "max-page-size-exceeded"]);
    const exported = row({ startRow: 0, endRow: 5000, exportFormat: "csv", exportScope: "all" });
    assert.doesNotThrow(() => processRow(exported.ir, exported.schema));
  });

  it("counts the consumed group keys against the budget together with the filter", () => {
    const fifty: FilterNodeIr = { type: "or", nodes: Array.from({ length: 64 }, () => leaf) };
    const { ir, schema } = row({ rowGroupCols: [{ id: "region", displayName: "r" }], groupKeys: [str("EMEA")], customFilters: fifty });
    assert.deepEqual(pairOf(() => processRow(ir, schema)), ["resourceLimits", "max-leaves-exceeded"]);
  });

  it("takes the host's own limits, which can be raised or lowered but never switched off", () => {
    const { ir, schema } = row({ customFilters: nested(3, leaf) });
    assert.deepEqual(pairOf(() => processRow(ir, schema, createLimits({ maxDepth: 2 }))), ["resourceLimits", "max-depth-exceeded"]);
    assert.doesNotThrow(() => processRow(ir, schema, createLimits({ maxDepth: 3 })));
    assert.throws(() => createLimits({ maxDepth: 0 }), RangeError);
  });
});

describe("US3: the coercion", () => {
  const coerced = (field: string, text: string) => {
    const { ir, schema } = row({ customFilters: eq(field, str(text)) });
    return processRow(ir, schema).filter;
  };

  it("types a string value by the field's declared type", () => {
    assert.deepEqual(coerced("qty", "12"), eq("qty", { type: "int64", value: 12 }));
    assert.deepEqual(coerced("price", "19.99"), eq("price", { type: "decimal", value: "19.99" }));
    assert.deepEqual(coerced("ratio", "0.5"), eq("ratio", { type: "double", value: 0.5 }));
    assert.deepEqual(coerced("active", "true"), eq("active", { type: "boolean", value: true }));
    assert.deepEqual(coerced("day", "2026-02-03"), eq("day", { type: "date", value: "2026-02-03" }));
    assert.deepEqual(coerced("at", "2026-02-03T04:05:06Z"), eq("at", { type: "datetime", value: "2026-02-03T04:05:06Z", zone: "UTC" }));
  });

  it("refuses what the declared type cannot hold, as typeCoercion / uncoercible-value", () => {
    const bad: [string, string][] = [["qty", "abc"], ["qty", "1.5"], ["qty", "99999999999999999999"], ["price", "1e3"], ["ratio", "NaN"], ["ratio", "1e400"], ["active", "yes"], ["day", "2026-13-40"], ["at", "yesterday"]];
    for (const [field, text] of bad) {
      const { ir, schema } = row({ customFilters: eq(field, str(text)) });
      assert.deepEqual(pairOf(() => processRow(ir, schema)), ["typeCoercion", "uncoercible-value"], `${field} ${text}`);
    }
  });

  it("never turns a typed value into a string, and keeps a null", () => {
    const { ir, schema } = row({ customFilters: eq("region", { type: "int64", value: 5 }) });
    assert.deepEqual(pairOf(() => processRow(ir, schema)), ["typeCoercion", "uncoercible-value"]);
    const nulls = row({ customFilters: eq("qty", { type: "null" }) });
    assert.deepEqual(processRow(nulls.ir, nulls.schema).filter, eq("qty", { type: "null" }));
  });

  it("holds a group key to its column's declared type", () => {
    const { ir, schema } = row({ rowGroupCols: [{ id: "qty", displayName: "q" }], groupKeys: [str("12")] });
    assert.deepEqual(pairOf(() => processRow(ir, schema)), ["typeCoercion", "uncoercible-value"]);
  });
});

describe("US3: the stage order", () => {
  it("reports the allowlist before the limits, and the limits before the coercion", () => {
    const wide: FilterNodeIr = { type: "or", nodes: [...Array.from({ length: 70 }, () => eq("region", str("x"))), eq("ghost", str("x"))] };
    const first = row({ customFilters: wide });
    assert.deepEqual(pairOf(() => processRow(first.ir, first.schema)), ["allowlist", "unknown-field"]);
    const second = row({ customFilters: { type: "or", nodes: [...Array.from({ length: 70 }, () => eq("region", str("x"))), eq("qty", str("abc"))] } });
    assert.deepEqual(pairOf(() => processRow(second.ir, second.schema)), ["resourceLimits", "max-leaves-exceeded"]);
  });
});

describe("US3: set values", () => {
  const schema = schemaOf();
  const parse = (envelope: Record<string, unknown>) => parseSetValues({ setValuesRequest: { colId: "region", filterModel: {}, ...envelope } }, schema);

  it("drops the target column's own conditions, keeps the others and adds the prefix as startsWith", () => {
    const parsed = parse({
      searchPrefix: "eu",
      filterModel: { region: { filterType: "text", type: "equals", filter: "EMEA" }, qty: { filterType: "number", type: "equals", filter: 3 } },
    });
    const { filter } = processSetValues(parsed, schema);
    assert.deepEqual(filter, {
      type: "and",
      nodes: [eq("qty", { type: "int64", value: 3 }), { type: "comparison", field: "region", op: "startsWith", value: str("eu") }],
    });
  });

  it("has no filter when nothing is left", () => {
    assert.equal(processSetValues(parse({ filterModel: { region: { filterType: "text", type: "equals", filter: "EMEA" } } }), schema).filter, undefined);
  });

  it("refuses a prefix on a column that is not text", () => {
    const parsed = parseSetValues({ setValuesRequest: { colId: "qty", filterModel: {}, searchPrefix: "1" } }, schema);
    assert.deepEqual(pairOf(() => processSetValues(parsed, schema)), ["typeCoercion", "uncoercible-value"]);
  });

  it("clamps the cap: the smaller of the request or the default, and the maximum", () => {
    assert.equal(processSetValues(parse({}), schema).rowLimit, 1000);
    assert.equal(processSetValues(parse({ limit: 50 }), schema).rowLimit, 50);
    assert.equal(processSetValues(parse({ limit: 50000 }), schema).rowLimit, 10000);
    assert.equal(processSetValues(parse({ limit: 50000 }), schema, createLimits({ maxSetValuesResults: 20 })).rowLimit, 20);
  });
});

describe("US3: the IR is returned with the coerced filter and nothing else changed", () => {
  it("keeps sort, page, group and aggregations", () => {
    const { ir, schema } = row({ sortModel: [{ colId: "id", sort: "asc" }], rowGroupCols: [{ id: "region", displayName: "r" }], valueCols: [{ id: "price", displayName: "p", aggFunc: "sum" }] });
    const out: Ir = processRow(ir, schema);
    assert.deepEqual({ ...out }, { ...ir });
  });
});
