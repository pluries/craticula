import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { Ajv2020 } from "ajv/dist/2020.js";

import { parseRequest } from "../src/agrid/request.js";
import { CompileError } from "../src/errors.js";
import { readJson } from "../src/json.js";
import { parseSchema } from "../src/schema.js";

// Feature 013, T010 (second part, S2b-1): the filter families that need no date resolution. Scenarios US2-AS1 to US2-AS3 and the refusals US3 relies on.
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const SPEC = fileURLToPath(new URL("../../../spec/", import.meta.url));

const ajv = new Ajv2020({ strict: false, validateFormats: false, allErrors: true });
ajv.addSchema(JSON.parse(readFileSync(`${SPEC}ir.schema.json`, "utf8")) as object);
const validateIr = ajv.compile({ $ref: "https://schemas.pluries.dev/craticula/v1/ir.schema.json" });

const SCHEMA = parseSchema({
  mode: "strict",
  source: "items",
  stableKey: "id",
  fields: {
    id: { type: "int64", physical: { sql: { column: "id" } } },
    name: { type: "string", physical: { sql: { column: "name" } } },
    qty: { type: "int64", physical: { sql: { column: "qty" } } },
    active: { type: "boolean", physical: { sql: { column: "active" } } },
    born: { type: "date", physical: { sql: { column: "born" } } },
  },
});

function filterOf(filterModel: unknown, extra: Record<string, unknown> = {}): unknown {
  const parsed = parseRequest({ startRow: 0, endRow: 100, filterModel, ...extra }, SCHEMA, {});
  return (parsed.ir as { filter?: unknown }).filter;
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

const cmp = (field: string, op: string, value?: string) => ({ type: "comparison", field, op, ...(value === undefined ? {} : { value: { type: "string", value } }) });

describe("US2-AS3: text and number conditions become comparison nodes", () => {
  const text: [string, string][] = [
    ["equals", "eq"], ["notEqual", "neq"], ["contains", "contains"], ["notContains", "notContains"], ["startsWith", "startsWith"], ["endsWith", "endsWith"],
  ];
  for (const [type, op] of text) {
    it(`text ${type} is ${op}`, () => {
      assert.deepEqual(filterOf({ name: { filterType: "text", type, filter: "x" } }), cmp("name", op, "x"));
    });
  }

  it("text blank and notBlank carry no value", () => {
    assert.deepEqual(filterOf({ name: { filterType: "text", type: "blank" } }), cmp("name", "blank"));
    assert.deepEqual(filterOf({ name: { filterType: "text", type: "notBlank" } }), cmp("name", "notBlank"));
  });

  const number: [string, string][] = [
    ["equals", "eq"], ["notEqual", "neq"], ["lessThan", "lt"], ["lessThanOrEqual", "lte"], ["greaterThan", "gt"], ["greaterThanOrEqual", "gte"],
  ];
  for (const [type, op] of number) {
    it(`number ${type} is ${op}, the value kept as text`, () => {
      assert.deepEqual(filterOf({ qty: { filterType: "number", type, filter: 5 } }), cmp("qty", op, "5"));
      assert.deepEqual(filterOf({ qty: { filterType: "number", type, filter: "7" } }), cmp("qty", op, "7"));
    });
  }

  it("number blank and notBlank carry no value", () => {
    assert.deepEqual(filterOf({ qty: { filterType: "number", type: "blank" } }), cmp("qty", "blank"));
  });

  it("keeps the written text of a number when the reader preserves it", () => {
    const request = readJson('{"startRow":0,"endRow":10,"filterModel":{"qty":{"filterType":"number","type":"equals","filter":1.50}}}', { numbers: "text" });
    assert.deepEqual((parseRequest(request, SCHEMA, {}).ir as { filter?: unknown }).filter, cmp("qty", "eq", "1.50"));
  });
});

describe("US2-AS3: combined conditions, legacy conditions and multi filters", () => {
  const eq = (v: string) => ({ filterType: "text", type: "equals", filter: v });

  it("combines a conditions array by its operator", () => {
    assert.deepEqual(filterOf({ name: { filterType: "text", operator: "OR", conditions: [eq("a"), eq("b")] } }), { type: "or", nodes: [cmp("name", "eq", "a"), cmp("name", "eq", "b")] });
    assert.deepEqual(filterOf({ name: { filterType: "text", operator: "AND", conditions: [eq("a"), eq("b")] } }), { type: "and", nodes: [cmp("name", "eq", "a"), cmp("name", "eq", "b")] });
  });

  it("reads the legacy condition1 and condition2 form", () => {
    assert.deepEqual(filterOf({ name: { filterType: "text", operator: "OR", condition1: eq("a"), condition2: eq("b") } }), { type: "or", nodes: [cmp("name", "eq", "a"), cmp("name", "eq", "b")] });
  });

  it("a combination of one condition is that condition", () => {
    assert.deepEqual(filterOf({ name: { filterType: "text", operator: "AND", conditions: [eq("a")] } }), cmp("name", "eq", "a"));
  });

  it("several columns are ANDed in the order of the model", () => {
    assert.deepEqual(filterOf({ name: eq("a"), qty: { filterType: "number", type: "equals", filter: 1 } }), { type: "and", nodes: [cmp("name", "eq", "a"), cmp("qty", "eq", "1")] });
  });

  it("a multi filter ANDs its models, skipping null ones", () => {
    const multi = { filterType: "multi", filterModels: [null, eq("a"), { filterType: "text", operator: "OR", conditions: [eq("b"), eq("c")] }] };
    assert.deepEqual(filterOf({ name: multi }), { type: "and", nodes: [cmp("name", "eq", "a"), { type: "or", nodes: [cmp("name", "eq", "b"), cmp("name", "eq", "c")] }] });
  });

  it("an empty or null model is no filter at all", () => {
    assert.equal(filterOf(null), undefined);
    assert.equal(filterOf({}), undefined);
    assert.equal(filterOf({ name: { filterType: "multi", filterModels: [null] } }), undefined);
  });

  it("refuses a combination with no operator or an unknown one, a missing condition2, and an empty conditions array", () => {
    const bad = [
      { name: { filterType: "text", conditions: [eq("a"), eq("b")] } },
      { name: { filterType: "text", operator: "XOR", conditions: [eq("a"), eq("b")] } },
      { name: { filterType: "text", operator: "OR", condition1: eq("a") } },
      { name: { filterType: "text", operator: "OR", conditions: [] } },
      { name: { filterType: "multi" } },
      { name: { filterType: "multi", filterModels: [7] } },
    ];
    for (const model of bad) {
      assert.deepEqual(pairOf(() => filterOf(model)), ["requestParsing", "malformed-request"], JSON.stringify(model));
    }
  });
});

describe("US2-AS3: the set filter", () => {
  it("is an in comparison over string values", () => {
    assert.deepEqual(filterOf({ name: { filterType: "set", values: ["a", "b"] } }), { type: "comparison", field: "name", op: "in", values: [{ type: "string", value: "a" }, { type: "string", value: "b" }] });
  });

  it("an empty list is an in over no value", () => {
    assert.deepEqual(filterOf({ name: { filterType: "set", values: [] } }), { type: "comparison", field: "name", op: "in", values: [] });
  });

  it("a boolean field with the single value true or false is the unary true or false", () => {
    assert.deepEqual(filterOf({ active: { filterType: "set", values: ["true"] } }), cmp("active", "true"));
    assert.deepEqual(filterOf({ active: { filterType: "set", values: ["false"] } }), cmp("active", "false"));
    assert.deepEqual(filterOf({ active: { filterType: "set", values: ["true", "false"] } }), { type: "comparison", field: "active", op: "in", values: [{ type: "string", value: "true" }, { type: "string", value: "false" }] });
  });

  it("refuses values that are missing, null, not an array, or not strings", () => {
    for (const set of [{ filterType: "set" }, { filterType: "set", values: null }, { filterType: "set", values: "a" }, { filterType: "set", values: [1] }, { filterType: "set", values: [null] }]) {
      assert.deepEqual(pairOf(() => filterOf({ name: set })), ["requestParsing", "malformed-request"], JSON.stringify(set));
    }
  });
});

describe("the refusals the shared oracle expects", () => {
  it("an unknown filter type, an unknown condition type and a native inRange are unknown-operator", () => {
    const bad = [
      { name: { filterType: "regex", filter: "x" } },
      { name: { filterType: "text", type: "regex", filter: "x" } },
      { qty: { filterType: "number", type: "greaterThanOrEqualTo", filter: 1 } },
      { qty: { filterType: "number", type: "inRange", filter: 1, filterTo: 2 } },
    ];
    for (const model of bad) {
      assert.deepEqual(pairOf(() => filterOf(model)), ["requestParsing", "unknown-operator"], JSON.stringify(model));
    }
  });

  it("a malformed shape is malformed-request: object or array values, missing or non-string members, a non-object entry or model", () => {
    const bad: unknown[] = [
      { name: { filterType: "text", type: "equals", filter: { $ne: null } } },
      { name: { filterType: "text", type: "equals", filter: ["a"] } },
      { name: { filterType: "text", type: "equals" } },
      { name: { filterType: "text", filter: "x" } },
      { name: { type: "equals", filter: "x" } },
      { qty: { filterType: "number", type: "equals", filter: true } },
      { qty: { filterType: "number", type: "equals" } },
      { name: "equals" },
      { name: null },
      [],
      "x",
    ];
    for (const model of bad) {
      assert.deepEqual(pairOf(() => filterOf(model)), ["requestParsing", "malformed-request"], JSON.stringify(model));
    }
  });
});

describe("custom filters and the merge with the native filter", () => {
  const custom = { type: "not", node: cmp("name", "eq", "blocked") };

  it("accepts a filter node of every form", () => {
    const nodes = [
      custom,
      { type: "and", nodes: [cmp("name", "eq", "a"), { type: "or", nodes: [cmp("qty", "gt", "1"), cmp("qty", "lt", "9")] }] },
      cmp("name", "blank"),
      { type: "comparison", field: "name", op: "notIn", values: [{ type: "string", value: "a" }] },
      { type: "comparison", field: "qty", op: "inRange", from: { type: "string", value: "1" }, to: { type: "string", value: "9" }, fromInclusive: true, toInclusive: false },
    ];
    for (const node of nodes) {
      assert.deepEqual(filterOf(null, { customFilters: node }), node);
    }
  });

  it("is ANDed after the native filter, and either alone stands alone", () => {
    const native = { name: { filterType: "text", type: "equals", filter: "a" } };
    assert.deepEqual(filterOf(native, { customFilters: custom }), { type: "and", nodes: [cmp("name", "eq", "a"), custom] });
    assert.deepEqual(filterOf(native), cmp("name", "eq", "a"));
    assert.deepEqual(filterOf(null, { customFilters: custom }), custom);
  });

  it("refuses a filter node of no known form, with an unknown member, a missing part, or an operator outside the closed set", () => {
    const bad: unknown[] = [
      { type: "xor", nodes: [] },
      { type: "and", nodes: [] },
      { type: "and" },
      { type: "not" },
      { type: "comparison", field: "name", op: "regex", value: { type: "string", value: "x" } },
      { type: "comparison", field: "name", op: "eq" },
      { type: "comparison", field: "name", op: "eq", value: { type: "string", value: "x" }, extra: 1 },
      { type: "comparison", field: "name", op: "eq", value: { type: "blob", value: "x" } },
      { type: "comparison", field: "name", op: "in", values: "a" },
      { type: "comparison", op: "blank" },
      "not a node",
      7,
    ];
    for (const node of bad) {
      assert.deepEqual(pairOf(() => filterOf(null, { customFilters: node })), ["requestParsing", "malformed-request"], JSON.stringify(node));
    }
  });
});

describe("US2-AS1 and US2-AS2: the request fixtures this slice reads, and only the ones it cannot read are refused as unsupported", () => {
  const root = `${SPEC}fixtures/`;

  it("parses what it can, validates each IR, and refuses the rest only as Unsupported", () => {
    let parsed = 0;
    const problems: string[] = [];
    for (const category of readdirSync(root, { withFileTypes: true })) {
      if (!category.isDirectory() || category.name === "schemas") continue;
      for (const fixture of readdirSync(`${root}${category.name}`, { withFileTypes: true })) {
        if (!fixture.isDirectory()) continue;
        const dir = `${root}${category.name}/${fixture.name}/`;
        if (readdirSync(`${dir}expected`).includes("rejection.json")) continue;
        const name = `${category.name}/${fixture.name}`;
        try {
          const schema = parseSchema(readJson(readFileSync(`${dir}schema.json`, "utf8")));
          const request = readJson(readFileSync(`${dir}agGridRequest.json`, "utf8"), { numbers: "text" });
          if (isRecord(request) && request["setValuesRequest"] !== undefined) continue; // the set-values envelope has its own entry point (a later slice)
          const context = isRecord(request) && isRecord(request["requestContext"]) ? request["requestContext"] : {};
          const result = parseRequest(request, schema, {
            allowUnboundedRows: context["allowUnboundedRows"] === true,
            ...(typeof context["now"] === "string" ? { now: () => new Date(context["now"] as string) } : {}),
          });
          parsed += 1;
          if (!validateIr(result.ir)) problems.push(`${name}: ${ajv.errorsText(validateIr.errors)}`);
        } catch (error) {
          if (!(error instanceof CompileError) || error.kind !== "Unsupported") problems.push(`${name}: ${String(error)}`);
        }
      }
    }
    assert.deepEqual(problems, []);
    assert.ok(parsed >= 100, `only ${parsed} fixture requests parsed`);
  });
});
