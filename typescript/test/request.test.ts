import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { Ajv2020 } from "ajv/dist/2020.js";

import { CompileError } from "../src/errors.js";
import { readJson } from "../src/json.js";
import { checkColumns, parseSchema } from "../src/schema.js";
import { parseRequest, type ParseOptions } from "../src/agrid/request.js";

// Feature 013, T010 (first part, S2a): the non-filter half of the request parser. Scenarios US2-AS1 and US2-AS2 for the requests that
// carry no filter, group or aggregation yet, US2-AS5 (paging and export), US2-AS6 (determinism), and the refusals US3 relies on.
const SPEC = fileURLToPath(new URL("../../../spec/", import.meta.url));

const ajv = new Ajv2020({ strict: false, validateFormats: false, allErrors: true });
ajv.addSchema(JSON.parse(readFileSync(`${SPEC}ir.schema.json`, "utf8")) as object);
const validateIr = ajv.compile({ $ref: "https://schemas.pluries.dev/craticula/v1/ir.schema.json" });

function load(path: string): unknown {
  return readJson(readFileSync(path, "utf8"));
}

const SCHEMA = parseSchema({
  mode: "strict",
  source: "items",
  stableKey: "id",
  fields: {
    id: { type: "int64", physical: { sql: { column: "id" } } },
    name: { type: "string", physical: { sql: { column: "name" } } },
    secret: { type: "string", exportable: false, physical: { sql: { column: "secret" } } },
  },
});

function request(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { startRow: 0, endRow: 100, rowGroupCols: [], valueCols: [], pivotCols: [], pivotMode: false, groupKeys: [], filterModel: null, sortModel: [], ...extra };
}

function parse(extra: Record<string, unknown>, options: ParseOptions = {}) {
  return parseRequest(request(extra), SCHEMA, options);
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

function isEmpty(value: unknown): boolean {
  return value === undefined || value === null || (Array.isArray(value) && value.length === 0) || (typeof value === "object" && !Array.isArray(value) && Object.keys(value as object).length === 0);
}

/** The fixtures this slice can parse: a request with no filter, group, aggregation, pivot, set values, export columns or context, no auto-group sort column, and no rejection oracle. */
function usableFixtures(root: string): string[] {
  const usable: string[] = [];
  for (const category of readdirSync(root, { withFileTypes: true })) {
    if (!category.isDirectory() || category.name === "schemas") continue;
    for (const fixture of readdirSync(`${root}${category.name}`, { withFileTypes: true })) {
      if (!fixture.isDirectory()) continue;
      const dir = `${root}${category.name}/${fixture.name}/`;
      let req: Record<string, unknown>;
      try {
        req = load(`${dir}agGridRequest.json`) as Record<string, unknown>;
      } catch {
        continue; // a request the strict reader refuses (adversarial/021's duplicate keys) is a rejection case, not an acceptance case
      }
      const sortIds = ((req["sortModel"] as { colId: string }[] | null | undefined) ?? []).map((s) => s.colId);
      const plain =
        ["filterModel", "customFilters", "rowGroupCols", "valueCols", "pivotCols", "groupKeys", "setValuesRequest", "exportColumns", "requestContext"].every((m) => isEmpty(req[m])) &&
        req["pivotMode"] !== true &&
        !sortIds.some((id) => id.startsWith("ag-Grid-AutoColumn"));
      const rejection = readdirSync(`${dir}expected`).includes("rejection.json");
      if (plain && !rejection) usable.push(`${category.name}/${fixture.name}`);
    }
  }
  return usable;
}

describe("US2-AS1 and US2-AS2: every request without filter, group or aggregation parses and its IR is valid", () => {
  const root = `${SPEC}fixtures/`;
  const usable = usableFixtures(root);

  it("finds at least the 17 sort-paging requests", () => {
    assert.ok(usable.filter((name) => name.startsWith("sort-paging/")).length >= 17, `found ${usable.length}`);
  });

  it("parses each and the IR validates against ir.schema.json", () => {
    const problems: string[] = [];
    for (const name of usable) {
      const dir = `${root}${name}/`;
      try {
        const schema = parseSchema(load(`${dir}schema.json`));
        const parsed = parseRequest(load(`${dir}agGridRequest.json`), schema, {});
        if (!validateIr(parsed.ir)) problems.push(`${name}: ${ajv.errorsText(validateIr.errors)}`);
      } catch (error) {
        problems.push(`${name}: ${String(error)}`);
      }
    }
    assert.deepEqual(problems, []);
  });
});

describe("US2-AS5: paging and export", () => {
  it("carries a row window as a range page", () => {
    assert.deepEqual(parse({ startRow: 20, endRow: 40 }).ir.page, { mode: "range", startRow: 20, endRow: 40 });
  });

  it("gives a request without a window the default page, 100 rows or the host's default page size", () => {
    assert.deepEqual(parse({ startRow: null, endRow: null }).ir.page, { mode: "range", startRow: 0, endRow: 100 });
    assert.deepEqual(parse({ startRow: undefined, endRow: undefined }, { defaultPageSize: 25 }).ir.page, { mode: "range", startRow: 0, endRow: 25 });
  });

  it("refuses a window with only one end, as a parsing rejection", () => {
    assert.deepEqual(pairOf(() => parse({ startRow: 0, endRow: null })), ["requestParsing", "malformed-request"]);
    assert.deepEqual(pairOf(() => parse({ startRow: null, endRow: 10 })), ["requestParsing", "malformed-request"]);
  });

  it("refuses a window that is not made of whole numbers", () => {
    assert.deepEqual(pairOf(() => parse({ startRow: "0", endRow: 10 })), ["requestParsing", "malformed-request"]);
    assert.deepEqual(pairOf(() => parse({ startRow: 0.5, endRow: 10 })), ["requestParsing", "malformed-request"]);
  });

  it("allows an unbounded page only when the host has allowed it", () => {
    assert.throws(() => parse({ startRow: null, endRow: null, ignorePageLimit: true }), CompileError);
    assert.deepEqual(parse({ startRow: null, endRow: null, ignorePageLimit: true }, { allowUnboundedRows: true }).ir.page, { mode: "none" });
  });

  it("an export of everything is the unpaginated page, whatever the window says", () => {
    const parsed = parse({ exportFormat: "csv", exportScope: "all", startRow: 0, endRow: 50 });
    assert.deepEqual(parsed.ir.page, { mode: "none" });
    assert.equal(parsed.export?.format, "csv");
    assert.equal(parsed.export?.scope, "all");
  });

  it("an export of the page keeps the window", () => {
    assert.deepEqual(parse({ exportFormat: "tsv", exportScope: "page", startRow: 10, endRow: 20 }).ir.page, { mode: "range", startRow: 10, endRow: 20 });
  });

  it("an export's default columns are the exportable fields in schema order", () => {
    assert.deepEqual(parse({ exportFormat: "csv" }).export?.columns, ["id", "name"]);
  });

  it("refuses an export scope without a format, and an unknown format or scope", () => {
    assert.deepEqual(pairOf(() => parse({ exportScope: "all" })), ["requestParsing", "malformed-request"]);
    assert.deepEqual(pairOf(() => parse({ exportFormat: "xlsx" })), ["requestParsing", "malformed-request"]);
    assert.deepEqual(pairOf(() => parse({ exportFormat: "csv", exportScope: "some" })), ["requestParsing", "malformed-request"]);
  });
});

describe("the sort model", () => {
  it("applies SEM-3's default null position to each key", () => {
    const sort = parse({
      sortModel: [
        { colId: "name", sort: "asc" },
        { colId: "id", sort: "desc" },
      ],
    }).ir.sort;
    assert.deepEqual(sort, [
      { field: "name", direction: "asc", nullsPosition: "last" },
      { field: "id", direction: "desc", nullsPosition: "first" },
    ]);
  });

  it("is absent from the IR when the request sorts by nothing", () => {
    assert.equal("sort" in parse({ sortModel: [] }).ir, false);
    assert.equal("sort" in parse({ sortModel: null }).ir, false);
  });

  it("refuses a sortModel that is not an array, an entry that is not an object, and a direction that is not asc or desc", () => {
    const bad: Record<string, unknown>[] = [{ sortModel: {} }, { sortModel: [1] }, { sortModel: [{ colId: "id", sort: "up" }] }, { sortModel: [{ sort: "asc" }] }, { sortModel: [{ colId: 5, sort: "asc" }] }];
    for (const extra of bad) {
      assert.deepEqual(pairOf(() => parse(extra)), ["requestParsing", "malformed-request"], JSON.stringify(extra));
    }
  });

  it("keeps a sort column the schema does not declare: the allowlist is the host's stage, and count mode ignores sort altogether", () => {
    const parsed = parse({ sortModel: [{ colId: "id", sort: "asc" }, { colId: "ghost", sort: "asc" }] });
    assert.deepEqual(parsed.ir.sort?.map((item) => item.field), ["id", "ghost"]);
    for (const sortModel of [[{ colId: "ghost", sort: "asc" }], [{ colId: "id", sort: "asc" }, { colId: "ghost", sort: "asc" }]]) {
      const fields = (parse({ sortModel }).ir.sort ?? []).map((item) => item.field);
      assert.deepEqual(pairOf(() => checkColumns(SCHEMA, fields, "sort")), ["allowlist", "unknown-field"]);
    }
  });
});

describe("US2-AS6: parsing is deterministic and reads no clock", () => {
  it("gives equal results for the same request", () => {
    const a = parse({ sortModel: [{ colId: "name", sort: "desc" }], startRow: 5, endRow: 15 });
    const b = parse({ sortModel: [{ colId: "name", sort: "desc" }], startRow: 5, endRow: 15 });
    assert.equal(JSON.stringify(a), JSON.stringify(b));
  });
});

describe("what the parser does not read is refused, not guessed", () => {
  it("refuses pivoting and a set-values envelope", () => {
    const cases: Record<string, unknown>[] = [
      { pivotMode: true },
      { pivotCols: [{ id: "name" }] },
      { setValuesRequest: { colId: "name" } },
    ];
    for (const extra of cases) {
      assert.throws(() => parse(extra), CompileError, JSON.stringify(extra));
    }
  });

  it("refuses a request that is not an object", () => {
    assert.throws(() => parseRequest([], SCHEMA, {}), CompileError);
    assert.deepEqual(pairOf(() => parseRequest("x", SCHEMA, {})), ["requestParsing", "malformed-request"]);
  });
});
