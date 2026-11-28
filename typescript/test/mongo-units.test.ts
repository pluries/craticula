import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { writeJson } from "../src/doc/ordered.js";
import { CompileError } from "../src/errors.js";
import { escapeRegex } from "../src/mongo/regex.js";
import { encodeEjson, normalizeEjsonInstant } from "../src/mongo/ejson.js";
import { parseSchema } from "../src/schema.js";
import { BACKENDS } from "../src/backends.js";

// Feature 015, T001 and T010 (US1-AS2 to US1-AS4, US3-AS1): the pieces under the MongoDB builder.
const schemaValue = {
  mode: "strict",
  source: "sales",
  stableKey: "id",
  fields: {
    id: { type: "int64", physical: { mongo: { path: "id" } } },
    name: { type: "string", groupable: true, physical: { mongo: { path: "name" } } },
    note: { type: "string", text: { caseSensitivity: "sensitive" }, groupable: true, physical: { mongo: { path: "note" } } },
    amount: { type: "decimal", aggregatable: ["sum", "avg", "count"], physical: { mongo: { path: "amount" } } },
    at: { type: "datetime", physical: { mongo: { path: "at" } } },
  },
};
const schema = parseSchema(schemaValue);
const mongo = BACKENDS.get("mongo")!;
const ask = (extra: Record<string, unknown>, countMode = false) => writeJson(mongo(schemaValue, { startRow: 0, endRow: 10, ...extra }, {}, countMode));

describe("MDB-11: regular-expression escaping", () => {
  it("escapes every ASCII character outside letters and digits and leaves the rest", () => {
    assert.equal(escapeRegex("a.b*c$"), "a\\.b\\*c\\$");
    assert.equal(escapeRegex("Zz09"), "Zz09");
    assert.equal(escapeRegex("café 中"), "café\\ 中");
    assert.equal(escapeRegex("^(a|b)+$"), "\\^\\(a\\|b\\)\\+\\$");
  });
});

describe("extended JSON values (AR-7, SEM-4)", () => {
  const field = (name: string) => schema.fields.get(name)!;

  it("wraps a decimal and a datetime, and passes the rest as data", () => {
    assert.equal(writeJson(encodeEjson({ type: "decimal", value: "19.90" }, field("amount"), "amount")), '{"$numberDecimal":"19.90"}');
    assert.equal(writeJson(encodeEjson({ type: "datetime", value: "2026-01-02T03:04:05+02:00", zone: "UTC" }, field("at"), "at")), '{"$date":"2026-01-02T01:04:05Z"}');
    assert.equal(encodeEjson({ type: "string", value: "{\"$ne\":null}" }, field("name"), "name"), '{"$ne":null}');
    assert.equal(encodeEjson({ type: "null" }, field("name"), "name"), null);
  });

  it("trims a fraction to ticks and refuses a value of the wrong type", () => {
    assert.equal(normalizeEjsonInstant("2026-01-02T03:04:05.1230000Z"), "2026-01-02T03:04:05.123Z");
    assert.throws(() => encodeEjson({ type: "string", value: "1" }, field("id"), "id"), CompileError);
  });
});

describe("US1-AS2: a value is data, never an operator", () => {
  it("keeps an operator-shaped string as a string member", () => {
    const text = ask({ customFilters: { type: "comparison", field: "name", op: "eq", value: { type: "string", value: "{\"$ne\":null}" } } });
    assert.match(text, /"name":\{"\$eq":"\{\\"\$ne\\":null\}"\}/);
  });
});

describe("US1-AS3: MDB-10 collisions", () => {
  it("refuses an aggregate whose output name is group, since the group key claims that bucket", () => {
    const request = { rowGroupCols: [{ id: "name", displayName: "n" }], valueCols: [{ id: "group", displayName: "g", field: "amount", aggFunc: "sum" }], sortModel: [{ colId: "group", sort: "asc" }] };
    assert.throws(() => mongo(schemaValue, { startRow: 0, endRow: 10, ...request }, {}, false), CompileError);
  });
});

describe("US1-AS4: count mode", () => {
  it("drops the paging, projection and sort stages and counts", () => {
    const text = ask({ customFilters: { type: "comparison", field: "name", op: "eq", value: { type: "string", value: "a" } } }, true);
    assert.ok(text.endsWith('{"$count":"count"}]') || text.includes('"$count":"count"'), text);
    assert.ok(!text.includes("$sort") && !text.includes("$skip") && !text.includes("$limit"), text);
  });
});
