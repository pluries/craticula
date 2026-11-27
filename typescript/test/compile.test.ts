import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { compile } from "../src/compile.js";
import { CompileError } from "../src/errors.js";
import { quoteIdentifier } from "../src/postgres.js";

// Scenarios US3-AS3 (the 17 sort-paging artifacts), US3-AS4 (a mutation changes the answer), US2-AS4 (hostile identifiers).
const FIXTURES = fileURLToPath(new URL("../../../spec/fixtures/sort-paging/", import.meta.url));

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8"));
}

function fixture(name: string): { schema: unknown; request: Record<string, unknown>; expected: { sql: string; params: unknown[] } } {
  const dir = `${FIXTURES}${name}/`;
  return {
    schema: readJson(`${dir}schema.json`),
    request: readJson(`${dir}agGridRequest.json`) as Record<string, unknown>,
    expected: readJson(`${dir}expected/postgres.artifact.json`) as { sql: string; params: unknown[] },
  };
}

const cases = readdirSync(FIXTURES).filter((name) => /^\d{3}-/.test(name)).sort();

describe("US3-AS3: the sort-paging family compiles to the expected PostgreSQL artifact", () => {
  it("finds the 17 cases", () => {
    assert.equal(cases.length, 17);
  });

  for (const name of cases) {
    it(name, () => {
      const { schema, request, expected } = fixture(name);
      const actual = compile(schema, request);
      assert.equal(actual.dialect, "postgres");
      assert.equal(actual.sql, expected.sql);
      assert.deepEqual(actual.params, expected.params);
    });
  }
});

describe("US3-AS4: the driver compiles the request, it does not look the answer up", () => {
  it("a flipped sort direction changes the ORDER BY where the request says so", () => {
    const { schema, request } = fixture("002-single-key-int64-asc-nulls-last-default");
    const flipped = structuredClone(request);
    (flipped["sortModel"] as { sort: string }[])[0]!.sort = "desc";
    const original = compile(schema, request).sql;
    const mutated = compile(schema, flipped).sql;
    assert.notEqual(mutated, original);
    assert.match(mutated, /ORDER BY "age" DESC NULLS FIRST, "id" ASC NULLS LAST/);
  });

  it("a different row window changes only the bound parameters", () => {
    const { schema, request } = fixture("011-page-range-with-tiebreaker");
    const moved = structuredClone(request);
    moved["startRow"] = 40;
    moved["endRow"] = 70;
    const a = compile(schema, request);
    const b = compile(schema, moved);
    assert.equal(a.sql, b.sql);
    assert.deepEqual(b.params, [30, 40]);
  });
});

describe("US2-AS4: no request text reaches the SQL except as a parameter or a declared identifier", () => {
  const { schema, request } = fixture("002-single-key-int64-asc-nulls-last-default");

  for (const hostile of ['x"; DROP TABLE t; --', "id; DELETE FROM items", "age\u0000", "ID", "__proto__", "constructor"]) {
    it(`refuses the sort column ${JSON.stringify(hostile)}`, () => {
      const bad = structuredClone(request);
      bad["sortModel"] = [{ colId: hostile, sort: "asc" }];
      assert.throws(() => compile(schema, bad), (error: unknown) => error instanceof CompileError && error.kind === "UnknownField");
    });
  }

  it("quotes an identifier by doubling the quote and refuses a NUL", () => {
    assert.equal(quoteIdentifier('a"b'), '"a""b"');
    assert.throws(() => quoteIdentifier("a\u0000b"), CompileError);
  });

  it("refuses a direction that is not asc or desc", () => {
    const bad = structuredClone(request);
    bad["sortModel"] = [{ colId: "age", sort: "asc; DROP" }];
    assert.throws(() => compile(schema, bad), CompileError);
  });
});

describe("US2-AS3: what the skeleton does not support is refused, not guessed", () => {
  const { schema, request } = fixture("001-single-key-string-asc-nulls-last-default");

  it("refuses a filter model", () => {
    const filtered = { ...request, filterModel: { last_name: { filterType: "text", type: "equals", filter: "x" } } };
    assert.throws(() => compile(schema, filtered), (error: unknown) => error instanceof CompileError && error.kind === "Unsupported");
  });

  it("refuses grouping", () => {
    const grouped = { ...request, rowGroupCols: [{ id: "department", displayName: "Department", field: "department" }] };
    assert.throws(() => compile(schema, grouped), (error: unknown) => error instanceof CompileError && error.kind === "Unsupported");
  });

  it("refuses a request that is not an object", () => {
    assert.throws(() => compile(schema, [] as unknown as Record<string, unknown>), CompileError);
  });
});
