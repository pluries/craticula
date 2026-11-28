import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { CompileError } from "../src/errors.js";
import { JsonNumber } from "../src/json.js";
import { parseSchema } from "../src/schema.js";
import { escapePattern, escapePatternWithBracket } from "../src/sql/escape.js";
import { ParameterBag } from "../src/sql/params.js";
import { postgres } from "../src/sql/postgres.js";
import { blankCondition, caseSensitivity, isNullInclusive } from "../src/sql/semantics.js";
import { encodeValue, normalizeInstant } from "../src/sql/values.js";

// Feature 014, T001 (US1-AS2, US1-AS3): the pieces under the builder.
const schema = parseSchema({
  mode: "strict",
  source: "t",
  stableKey: "id",
  fields: {
    id: { type: "int64", physical: { sql: { column: "id" } } },
    name: { type: "string", physical: { sql: { column: "name" } } },
    code: { type: "string", text: { caseSensitivity: "sensitive" }, physical: { sql: { column: "code" } } },
    price: { type: "decimal", physical: { sql: { column: "price" } } },
    day: { type: "date", physical: { sql: { column: "day" } } },
    at: { type: "datetime", physical: { sql: { column: "at" } } },
  },
});
const field = (name: string) => schema.fields.get(name)!;

describe("pattern escaping (SEM-7, SQL-5)", () => {
  it("escapes the escape character, percent and underscore", () => {
    assert.equal(escapePattern("a%b_c\\d", "\\"), "a\\%b\\_c\\\\d");
    assert.equal(escapePattern("plain", "\\"), "plain");
  });

  it("escapes a left bracket as well where the engine reads one", () => {
    assert.equal(escapePatternWithBracket("[x]%", "\\"), "\\[x]\\%");
  });
});

describe("semantics (SEM-1, SEM-2)", () => {
  it("text is case-insensitive unless declared sensitive, with the mechanism of the operator family", () => {
    assert.deepEqual(caseSensitivity(field("name"), "eq"), { mode: "insensitive", mechanism: "collation" });
    assert.deepEqual(caseSensitivity(field("name"), "in"), { mode: "insensitive", mechanism: "collation" });
    assert.deepEqual(caseSensitivity(field("name"), "contains"), { mode: "insensitive", mechanism: "patternMatch" });
    assert.deepEqual(caseSensitivity(field("code"), "eq"), { mode: "sensitive", mechanism: "none" });
    assert.deepEqual(caseSensitivity(field("id"), "eq"), { mode: "notApplicable", mechanism: "none" });
  });

  it("negative operators include null rows, positive ones do not", () => {
    for (const op of ["neq", "notContains", "notIn"]) assert.equal(isNullInclusive(op), true, op);
    for (const op of ["eq", "gt", "contains", "in", "blank"]) assert.equal(isNullInclusive(op), false, op);
  });

  it("blank is null or empty for text and null only for the rest", () => {
    assert.equal(blankCondition("string"), "nullOrEmptyString");
    assert.equal(blankCondition("int64"), "nullOnly");
  });
});

describe("value encoding and instants (AR-7, SEM-4)", () => {
  it("passes strings, decimals as text, booleans and null through", () => {
    assert.equal(encodeValue({ type: "string", value: "x" }, field("name"), postgres), "x");
    assert.equal(encodeValue({ type: "decimal", value: "19.90" }, field("price"), postgres), "19.90");
    assert.equal(encodeValue({ type: "null" }, field("name"), postgres), null);
  });

  it("keeps the digits of an int64 beyond 2^53 and uses a number otherwise", () => {
    assert.equal(encodeValue({ type: "int64", value: 12 }, field("id"), postgres), 12);
    const big = encodeValue({ type: "int64", value: "9007199254740993" }, field("id"), postgres);
    assert.ok(big instanceof JsonNumber);
    assert.equal(big.text, "9007199254740993");
  });

  it("refuses a value whose type is not the field's", () => {
    assert.throws(() => encodeValue({ type: "string", value: "1" }, field("id"), postgres), CompileError);
  });

  it("normalises an instant to UTC, trimming the fraction", () => {
    assert.equal(normalizeInstant("2026-01-02T03:04:05+02:00", false, "none"), "2026-01-02T01:04:05Z");
    assert.equal(normalizeInstant("2026-01-02T03:04:05.1230000Z", false, "none"), "2026-01-02T03:04:05.123Z");
    assert.equal(normalizeInstant("2026-01-02T03:04:05.1234567Z", false, "none"), "2026-01-02T03:04:05.1234567Z");
  });

  it("fixed-width engines print milliseconds and round a bound toward the side that keeps the rows", () => {
    assert.equal(normalizeInstant("2026-01-02T03:04:05Z", true, "none"), "2026-01-02T03:04:05.000Z");
    assert.equal(normalizeInstant("2026-01-02T03:04:05.1239Z", true, "floor"), "2026-01-02T03:04:05.123Z");
    assert.equal(normalizeInstant("2026-01-02T03:04:05.1239Z", true, "ceiling"), "2026-01-02T03:04:05.124Z");
  });
});

describe("the parameter bag", () => {
  it("numbers placeholders in binding order for the dialect", () => {
    const bag = new ParameterBag(postgres);
    assert.equal(bag.bind("a"), "$1");
    assert.equal(bag.bind(7), "$2");
    assert.deepEqual(bag.values, ["a", 7]);
  });
});

describe("the PostgreSQL dialect (SQL-1, SQL-4, SQL-5, SQL-8)", () => {
  it("quotes an identifier by doubling the quote and refuses a NUL", () => {
    assert.equal(postgres.quoteIdentifier('we"ird'), '"we""ird"');
    assert.throws(() => postgres.quoteIdentifier("a\u0000b"), CompileError);
  });

  it("renders a scalar comparison with the collation on the column and a cast for decimal, date and datetime", () => {
    const bag = new ParameterBag(postgres);
    assert.equal(postgres.scalar('"name"', "eq", "x", "string", "insensitive", bag), '"name" COLLATE craticula_ci = $1');
    assert.equal(postgres.scalar('"price"', "gt", "1.5", "decimal", "notApplicable", bag), '"price" > $2::numeric');
    assert.equal(postgres.scalar('"day"', "lte", "2026-01-01", "date", "notApplicable", bag), '"day" <= $3::date');
    assert.equal(postgres.scalar('"at"', "lt", "2026-01-01T00:00:00Z", "datetime", "notApplicable", bag), '"at" < $4::timestamptz');
  });

  it("renders the substring family with ILIKE or LIKE and an escaped parameter", () => {
    const bag = new ParameterBag(postgres);
    assert.equal(postgres.substring('"name"', "anywhere", false, "a%", "insensitive", bag), `"name" ILIKE '%' || $1 || '%' ESCAPE '\\'`);
    assert.deepEqual(bag.values, ["a\\%"]);
    assert.equal(postgres.substring('"code"', "start", true, "a", "sensitive", bag), `"code" NOT LIKE $2 || '%' ESCAPE '\\'`);
    assert.equal(postgres.substring('"code"', "end", false, "a", "sensitive", bag), `"code" LIKE '%' || $3 ESCAPE '\\'`);
  });

  it("renders set membership as one array parameter", () => {
    const bag = new ParameterBag(postgres);
    assert.equal(postgres.setMembership('"id"', false, [1, 2], "int64", "notApplicable", bag), '"id" = ANY($1)');
    assert.equal(postgres.setMembership('"price"', true, ["1", "2"], "decimal", "notApplicable", bag), '"price" <> ALL($2::numeric[])');
    assert.deepEqual(bag.values, [[1, 2], ["1", "2"]]);
  });

  it("renders sort keys, paging and the row cap", () => {
    const bag = new ParameterBag(postgres);
    assert.equal(postgres.sortKey('"name"', "asc", "last", "insensitive"), '"name" COLLATE craticula_ci ASC NULLS LAST');
    assert.equal(postgres.sortKey('"id"', "desc", "first", "notApplicable"), '"id" DESC NULLS FIRST');
    assert.equal(postgres.paging(20, 10, bag), "LIMIT $1 OFFSET $2");
    assert.deepEqual(bag.values, [10, 20]);
    assert.equal(postgres.rowLimit(5, bag), "LIMIT $3");
  });
});
