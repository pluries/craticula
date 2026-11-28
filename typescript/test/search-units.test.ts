import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { BACKENDS } from "../src/backends.js";
import { writeJson } from "../src/doc/ordered.js";
import { CompileError } from "../src/errors.js";
import { escapeSearchRegex, escapeWildcard } from "../src/search/escape.js";
import { formatFor, normalizeSearchInstant } from "../src/search/json.js";

// Feature 015, T020 and T030 (US2-AS2 to US2-AS4, US3-AS1, US3-AS2): the rules of the search compiler beyond the fixtures.
const search = BACKENDS.get("search")!;
const field = (extra: Record<string, unknown>, name: string) => ({
  type: "string",
  physical: { search: { field: name, keywordSubField: `${name}.keyword`, normalizedSubField: `${name}.normalized` } },
  ...extra,
});
const schemaValue = {
  mode: "strict",
  source: "items",
  stableKey: "id",
  fields: {
    id: { type: "int64", physical: { search: { field: "id" } } },
    name: field({ groupable: true }, "name"),
    bare: { type: "string", physical: { search: { field: "bare", keywordSubField: "bare.keyword" } } },
    note: field({ text: { caseSensitivity: "sensitive", searchMode: "analyzed" } }, "note"),
    amount: { type: "decimal", aggregatable: ["sum"], physical: { search: { field: "amount" } } },
  },
};
const ask = (extra: Record<string, unknown>, options = {}, countMode = false) => writeJson(search(schemaValue, { startRow: 0, endRow: 10, ...extra }, options, countMode));
const filter = (fieldName: string, op: string, value: unknown) => ({ customFilters: { type: "comparison", field: fieldName, op, value } });
const text = (value: string) => ({ type: "string", value });

describe("escaping (MDB-11 analogue OSE-12, SEM-7)", () => {
  it("escapes the ASCII characters of a term-level regular expression and leaves letters, digits and non-ASCII", () => {
    assert.equal(escapeSearchRegex("a.b*c"), "a\\.b\\*c");
    assert.equal(escapeSearchRegex("Zz09 café"), "Zz09\\ café");
  });

  it("escapes the wildcard characters only", () => {
    assert.equal(escapeWildcard("a*b?c\\d.e"), "a\\*b\\?c\\\\d.e");
  });
});

describe("value forms", () => {
  it("prints instants with three fraction digits for whole milliseconds and the date formats of OSE-8", () => {
    assert.equal(normalizeSearchInstant("2026-01-02T03:04:05Z"), "2026-01-02T03:04:05.000Z");
    assert.equal(normalizeSearchInstant("2026-01-02T03:04:05.1234567Z"), "2026-01-02T03:04:05.1234567Z");
    assert.equal(formatFor("date"), "strict_date");
    assert.equal(formatFor("datetime"), "strict_date_optional_time");
    assert.equal(formatFor("string"), undefined);
  });

  it("writes a decimal as a JSON number with its digits", () => {
    const body = ask(filter("amount", "gt", { type: "decimal", value: "19.90" }));
    assert.match(body, /"gt":19\.90/);
  });
});

describe("US2-AS2: a value is a JSON value, never a key or a script", () => {
  it("keeps an operator-shaped or script-shaped text as a string value", () => {
    const body = ask(filter("name", "eq", text('{"script":"x"}')));
    assert.match(body, /"value":"\{\\"script\\":\\"x\\"\}"/);
    assert.ok(!body.includes('"script":"x"') || body.includes('\\"script\\"'));
  });
});

describe("US2-AS4: what the pinned subset cannot express is refused", () => {
  it("refuses a case-insensitive range or sort on a field with no normalised sub-field", () => {
    assert.throws(() => ask(filter("bare", "gt", text("a"))), CompileError);
    assert.throws(() => ask({ sortModel: [{ colId: "bare", sort: "asc" }] }), CompileError);
  });

  it("refuses an analysed, case-sensitive contains, which no rendering satisfies", () => {
    assert.throws(() => ask(filter("note", "contains", text("x"))), CompileError);
  });

  it("refuses a grouped level ordered by an aggregate and one asked for a second block", () => {
    const grouped = { rowGroupCols: [{ id: "name", displayName: "n" }], valueCols: [{ id: "total", displayName: "t", field: "amount", aggFunc: "sum" }] };
    assert.throws(() => ask({ ...grouped, sortModel: [{ colId: "total", sort: "desc" }] }), CompileError);
    assert.throws(() => ask({ ...grouped, startRow: 100, endRow: 200 }), CompileError);
  });

  it("refuses an aggregation or column name that the buckets_path syntax reserves", () => {
    assert.throws(() => ask({ rowGroupCols: [{ id: "name", displayName: "n" }], valueCols: [{ id: "a>b", displayName: "t", field: "amount", aggFunc: "sum" }] }), CompileError);
  });
});

describe("US3-AS2, US3-AS3: the time limit", () => {
  it("carries timeout as text for a page and a count, and not for an unpaginated request", () => {
    assert.match(ask({}, { maxQueryTimeMs: 2000 }), /"timeout":"2000ms"/);
    assert.match(ask({}, { maxQueryTimeMs: 2000 }, true), /"timeout":"2000ms"/);
    assert.ok(!ask({ startRow: null, endRow: null, ignorePageLimit: true }, { maxQueryTimeMs: 2000, allowUnboundedRows: true }).includes("timeout"));
    assert.ok(!ask({}).includes("timeout"));
  });
});

describe("US2-AS3: count mode", () => {
  it("has no sort, no from and a size of zero", () => {
    const body = ask({}, {}, true);
    assert.match(body, /"size":0/);
    assert.ok(!body.includes('"sort"') && !body.includes('"from"'));
  });
});
