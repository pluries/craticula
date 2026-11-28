import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { Ajv2020 } from "ajv/dist/2020.js";

import { parseRequest } from "../src/agrid/request.js";
import { CompileError } from "../src/errors.js";
import { readJson } from "../src/json.js";
import { parseSchema } from "../src/schema.js";

// Feature 013, T010 (fourth part, S2c-1): grouping, group keys, aggregation, the auto group column in a sort, and the export carve-out.
// Scenarios US2-AS5 (grouping, group keys, aggregations with aliases), US2-AS1 and US2-AS2 (every such fixture parses and validates).
const SPEC = fileURLToPath(new URL("../../../spec/", import.meta.url));

const ajv = new Ajv2020({ strict: false, validateFormats: false, allErrors: true });
ajv.addSchema(JSON.parse(readFileSync(`${SPEC}ir.schema.json`, "utf8")) as object);
const validateIr = ajv.compile({ $ref: "https://schemas.pluries.dev/craticula/v1/ir.schema.json" });

const SCHEMA = parseSchema({
  mode: "strict",
  source: "sales",
  stableKey: "id",
  fields: {
    id: { type: "int64", physical: { sql: { column: "id" } } },
    region: { type: "string", groupable: true, physical: { sql: { column: "region" } } },
    segment: { type: "string", groupable: true, physical: { sql: { column: "segment" } } },
    product: { type: "string", groupable: true, physical: { sql: { column: "product" } } },
    amount: { type: "decimal", aggregatable: ["sum", "avg", "min", "max", "count"], physical: { sql: { column: "amount" } } },
  },
});

const col = (id: string, extra: Record<string, unknown> = {}) => ({ id, displayName: id, field: id, ...extra });
const str = (value: string) => ({ type: "string", value });

function parse(extra: Record<string, unknown>) {
  return parseRequest({ startRow: 0, endRow: 100, filterModel: null, ...extra }, SCHEMA, {});
}

function pairOf(action: () => unknown): [string | undefined, string | undefined] {
  try {
    action();
  } catch (error) {
    assert.ok(error instanceof CompileError, String(error));
    return [error.rejectedAt, error.reason];
  }
  return [undefined, undefined];
}

describe("US2-AS5: grouping and group keys", () => {
  it("carries the group columns and the keys already drilled into", () => {
    const ir = parse({ rowGroupCols: [col("region"), col("segment")], groupKeys: [str("EMEA")] }).ir as { group?: unknown };
    assert.deepEqual(ir.group, { groupCols: ["region", "segment"], groupKeys: [str("EMEA")] });
  });

  it("uses the id when a column carries no field", () => {
    const ir = parse({ rowGroupCols: [{ id: "region", displayName: "Region" }] }).ir as { group?: { groupCols: string[] } };
    assert.deepEqual(ir.group?.groupCols, ["region"]);
  });

  it("has no group when there are no group columns", () => {
    assert.equal("group" in parse({ rowGroupCols: [] }).ir, false);
    assert.equal("group" in parse({}).ir, false);
  });

  it("refuses group keys without a group column, and keys or columns of the wrong shape", () => {
    const bad: Record<string, unknown>[] = [
      { groupKeys: [str("EMEA")] },
      { rowGroupCols: {} },
      { rowGroupCols: [7] },
      { rowGroupCols: [{ displayName: "x" }] },
      { rowGroupCols: [col("region")], groupKeys: "EMEA" },
      { rowGroupCols: [col("region")], groupKeys: ["EMEA"] },
      { rowGroupCols: [col("region")], groupKeys: [{ type: "blob", value: "x" }] },
    ];
    for (const extra of bad) {
      assert.deepEqual(pairOf(() => parse(extra)), ["requestParsing", "malformed-request"], JSON.stringify(extra));
    }
  });

  it("an export discards group state and aggregations (EXP-1's carve-out)", () => {
    const ir = parse({ rowGroupCols: [col("region")], valueCols: [col("amount", { aggFunc: "sum" })], groupKeys: [], exportFormat: "csv", exportScope: "all" }).ir;
    assert.equal("group" in ir, false);
    assert.equal("aggregations" in ir, false);
  });
});

describe("US2-AS5: aggregations", () => {
  it("reads the function, and an alias only when the column id differs from its field", () => {
    const ir = parse({ rowGroupCols: [col("region")], valueCols: [col("amount", { aggFunc: "sum" }), { id: "avgAmount", displayName: "x", field: "amount", aggFunc: "avg" }] }).ir as { aggregations?: unknown };
    assert.deepEqual(ir.aggregations, [
      { field: "amount", func: "sum" },
      { field: "amount", func: "avg", alias: "avgAmount" },
    ]);
  });

  it("knows the five functions of the closed set", () => {
    for (const func of ["sum", "min", "max", "avg", "count"]) {
      const ir = parse({ valueCols: [col("amount", { aggFunc: func })] }).ir as { aggregations?: { func: string }[] };
      assert.equal(ir.aggregations?.[0]?.func, func);
    }
  });

  it("refuses a missing function as malformed and an unknown one as unknown-operator", () => {
    assert.deepEqual(pairOf(() => parse({ valueCols: [col("amount")] })), ["requestParsing", "malformed-request"]);
    assert.deepEqual(pairOf(() => parse({ valueCols: [col("amount", { aggFunc: "median" })] })), ["requestParsing", "unknown-operator"]);
  });

  it("refuses two aggregations that resolve to one output name", () => {
    assert.deepEqual(
      pairOf(() => parse({ valueCols: [{ id: "total", displayName: "a", field: "amount", aggFunc: "sum" }, { id: "total", displayName: "b", field: "id", aggFunc: "sum" }] })),
      ["requestParsing", "duplicate-output-name"],
    );
    assert.deepEqual(
      pairOf(() => parse({ valueCols: [col("amount", { aggFunc: "sum" }), { id: "amount_sum", displayName: "b", field: "id", aggFunc: "sum" }] })),
      ["requestParsing", "duplicate-output-name"],
    );
  });

  it("allows sum and avg of one field without aliases: their default names differ", () => {
    assert.doesNotThrow(() => parse({ valueCols: [col("amount", { aggFunc: "sum" }), col("amount", { aggFunc: "avg" })] }));
  });

  it("refuses an alias outside the identifier pattern and a field name that is too long", () => {
    assert.deepEqual(pairOf(() => parse({ valueCols: [{ id: "1bad", displayName: "x", field: "amount", aggFunc: "sum" }] })), ["requestParsing", "malformed-request"]);
    assert.deepEqual(pairOf(() => parse({ valueCols: [{ id: "a b", displayName: "x", field: "amount", aggFunc: "sum" }] })), ["requestParsing", "malformed-request"]);
    assert.deepEqual(pairOf(() => parse({ valueCols: [{ id: "x", displayName: "x", field: "f".repeat(257), aggFunc: "sum" }] })), ["requestParsing", "malformed-request"]);
  });
});

describe("the auto group column in a sort", () => {
  const rows = [col("region"), col("segment"), col("product")];

  function sortOf(extra: Record<string, unknown>): { field: string; direction: string }[] {
    return (parse(extra).ir.sort ?? []).map(({ field, direction }) => ({ field, direction }));
  }

  it("names the group column of the level being shown and drops the sorts the auto column stands for", () => {
    const sort = sortOf({
      rowGroupCols: rows,
      groupKeys: [str("EMEA")],
      sortModel: [{ colId: "ag-Grid-AutoColumn", sort: "desc" }, { colId: "region", sort: "desc" }, { colId: "segment", sort: "desc" }, { colId: "product", sort: "desc" }],
    });
    assert.deepEqual(sort, [{ field: "segment", direction: "desc" }]);
  });

  it("an auto column of a given source names that group column", () => {
    const sort = sortOf({ rowGroupCols: rows, sortModel: [{ colId: "ag-Grid-AutoColumn-segment", sort: "asc" }] });
    assert.deepEqual(sort, [{ field: "segment", direction: "asc" }]);
  });

  it("an auto column with an unknown source stays as written, to fail as the unknown column it is", () => {
    assert.deepEqual(sortOf({ rowGroupCols: rows, sortModel: [{ colId: "ag-Grid-AutoColumn-ghost", sort: "asc" }] }), [{ field: "ag-Grid-AutoColumn-ghost", direction: "asc" }]);
  });

  it("an auto column on a request with no grouping stays as written", () => {
    assert.deepEqual(sortOf({ sortModel: [{ colId: "ag-Grid-AutoColumn", sort: "asc" }] }), [{ field: "ag-Grid-AutoColumn", direction: "asc" }]);
  });

  it("an auto column at a leaf level, where no group column is left, is dropped", () => {
    assert.deepEqual(
      sortOf({ rowGroupCols: [col("region")], groupKeys: [str("EMEA")], sortModel: [{ colId: "ag-Grid-AutoColumn", sort: "asc" }, { colId: "amount", sort: "desc" }] }),
      [{ field: "amount", direction: "desc" }],
    );
  });

  it("a sort on a column the same auto column already named is not repeated", () => {
    assert.deepEqual(
      sortOf({ rowGroupCols: rows, sortModel: [{ colId: "region", sort: "asc" }, { colId: "ag-Grid-AutoColumn-region", sort: "desc" }] }),
      [{ field: "region", direction: "asc" }],
    );
  });
});

describe("US2-AS1 and US2-AS2: every request fixture except set-values and export columns parses and its IR is valid", () => {
  const root = `${SPEC}fixtures/`;

  it("parses each, none refused as unsupported, each IR valid", () => {
    const problems: string[] = [];
    let parsed = 0;
    for (const category of readdirSync(root, { withFileTypes: true })) {
      if (!category.isDirectory() || category.name === "schemas") continue;
      for (const fixture of readdirSync(`${root}${category.name}`, { withFileTypes: true })) {
        if (!fixture.isDirectory()) continue;
        const dir = `${root}${category.name}/${fixture.name}/`;
        if (readdirSync(`${dir}expected`).includes("rejection.json")) continue;
        const name = `${category.name}/${fixture.name}`;
        try {
          const schema = parseSchema(readJson(readFileSync(`${dir}schema.json`, "utf8")));
          const request = readJson(readFileSync(`${dir}agGridRequest.json`, "utf8"), { numbers: "text" }) as Record<string, unknown>;
          if (request["setValuesRequest"] !== undefined || (request["exportColumns"] !== undefined && request["exportColumns"] !== null)) continue;
          const context = (request["requestContext"] ?? {}) as Record<string, unknown>;
          const result = parseRequest(request, schema, {
            allowUnboundedRows: context["allowUnboundedRows"] === true,
            ...(typeof context["now"] === "string" ? { now: () => new Date(context["now"] as string) } : {}),
          });
          parsed += 1;
          if (!validateIr(result.ir)) problems.push(`${name}: ${ajv.errorsText(validateIr.errors)}`);
        } catch (error) {
          problems.push(`${name}: ${String(error)}`);
        }
      }
    }
    assert.deepEqual(problems, []);
    assert.ok(parsed >= 200, `only ${parsed} fixture requests parsed`);
  });
});
