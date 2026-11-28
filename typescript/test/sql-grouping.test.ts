import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { compile } from "../src/compile.js";
import { CompileError } from "../src/errors.js";
import { buildCount, buildSetValues } from "../src/sql/builder.js";
import { postgres } from "../src/sql/postgres.js";
import { parseSchema } from "../src/schema.js";

// Feature 014, T010 (US3, US1-AS4, US1-AS5): the rules of grouping, count mode and set values that the fixtures do not all reach.
const schemaValue = {
  mode: "strict",
  source: "sales",
  stableKey: "id",
  fields: {
    id: { type: "int64", physical: { sql: { column: "id" } } },
    region: { type: "string", groupable: true, physical: { sql: { column: "region" } } },
    amount: { type: "decimal", aggregatable: ["sum", "avg", "count"], physical: { sql: { column: "amount" } } },
  },
};
const schema = parseSchema(schemaValue);
const region = { id: "region", displayName: "Region" };
const request = (extra: Record<string, unknown>) => ({ startRow: 0, endRow: 10, rowGroupCols: [region], ...extra });
const pairOf = (action: () => unknown): string => {
  try {
    action();
  } catch (error) {
    assert.ok(error instanceof CompileError, String(error));
    return error.message;
  }
  return "";
};

describe("US3-AS2: aggregation output", () => {
  it("projects the group column under its own name, then each aggregate under its output name, with sum coalesced", () => {
    const artifact = compile(schemaValue, request({ valueCols: [{ id: "amount", displayName: "A", aggFunc: "sum" }, { id: "avgAmount", displayName: "B", field: "amount", aggFunc: "avg" }] }));
    assert.match(artifact.sql, /^SELECT "region" AS "region", COALESCE\(SUM\("amount"\), 0\) AS "amount_sum", AVG\("amount"\) AS "avgAmount" FROM "sales" GROUP BY "region" ORDER BY /);
  });

  it("refuses an output name that collides with the group column", () => {
    const message = pairOf(() => compile(schemaValue, request({ valueCols: [{ id: "region", displayName: "A", field: "amount", aggFunc: "sum" }] })));
    assert.match(message, /collides with this grouped level's own group column/);
  });
});

describe("US3-AS4: sorting a grouped level", () => {
  const sum = { id: "amount", displayName: "A", aggFunc: "sum" };

  it("orders by an aggregate through its call and appends the group column as the tiebreaker, without a collation", () => {
    const artifact = compile(schemaValue, request({ valueCols: [sum], sortModel: [{ colId: "amount", sort: "desc" }] }));
    assert.match(artifact.sql, /ORDER BY COALESCE\(SUM\("amount"\), 0\) DESC NULLS FIRST, "region" ASC NULLS LAST LIMIT/);
  });

  it("refuses a sort that names neither the group column nor an aggregate of the level", () => {
    assert.match(pairOf(() => compile(schemaValue, request({ valueCols: [sum], sortModel: [{ colId: "id", sort: "asc" }] }))), /ordered only by its group column/);
  });

  it("refuses a sort key that two aggregations both answer to", () => {
    const twice = [sum, { id: "amount", displayName: "B", field: "amount", aggFunc: "avg" }];
    assert.match(pairOf(() => compile(schemaValue, request({ valueCols: twice, sortModel: [{ colId: "amount", sort: "asc" }] }))), /Ambiguous ORDER BY target/);
  });
});

describe("US1-AS4: count mode", () => {
  it("counts the groups of a grouped level through a derived table, and rows otherwise", () => {
    const grouped = buildCount({ schema, page: { mode: "none" }, group: { groupCols: ["region"], groupKeys: [] } }, postgres);
    assert.equal(grouped.sql, 'SELECT COUNT(*) FROM (SELECT "region" FROM "sales" GROUP BY "region") craticula_count');
    const flat = buildCount({ schema, page: { mode: "none" } }, postgres);
    assert.equal(flat.sql, 'SELECT COUNT(*) FROM "sales"');
  });
});

describe("US1-AS5: set values", () => {
  it("selects the distinct values of the column in order with the cap bound, and nothing else", () => {
    const artifact = buildSetValues({ schema, colId: "region", rowLimit: 25 }, postgres);
    assert.equal(artifact.sql, 'SELECT DISTINCT "region" FROM "sales" ORDER BY "region" ASC NULLS LAST LIMIT $1');
    assert.deepEqual(artifact.params, [25]);
  });

  it("refuses a cap that is not positive", () => {
    assert.throws(() => buildSetValues({ schema, colId: "region", rowLimit: 0 }, postgres), CompileError);
  });
});
