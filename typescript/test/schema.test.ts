import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { Ajv2020 } from "ajv/dist/2020.js";

import { CompileError } from "../src/errors.js";
import { checkColumns, parseSchema } from "../src/schema.js";

// Feature 013, T003. Scenarios US1-AS1 (all fixture schemas), US1-AS2 (invalid schemas), US1-AS3 and US1-AS4 (allowlist), US1-AS5 (prototype names).
const SPEC = fileURLToPath(new URL("../../../spec/", import.meta.url));

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8"));
}

const ajv = new Ajv2020({ strict: false, validateFormats: false, allErrors: true });
ajv.addSchema(readJson(`${SPEC}ir.schema.json`) as object);
const validate = ajv.compile(readJson(`${SPEC}grid-schema.schema.json`) as object);

function fixtureSchemas(): { name: string; path: string }[] {
  const root = `${SPEC}fixtures/`;
  const found: { name: string; path: string }[] = [];
  for (const category of readdirSync(root, { withFileTypes: true })) {
    if (!category.isDirectory() || category.name === "schemas") continue;
    for (const fixture of readdirSync(`${root}${category.name}`, { withFileTypes: true })) {
      if (fixture.isDirectory()) found.push({ name: `${category.name}/${fixture.name}`, path: `${root}${category.name}/${fixture.name}/schema.json` });
    }
  }
  return found;
}

function base(): Record<string, unknown> {
  return {
    mode: "strict",
    source: "items",
    stableKey: "id",
    fields: {
      id: { type: "int64", filterable: false, physical: { sql: { column: "id" } } },
      name: { type: "string", physical: { sql: { column: "name" } } },
    },
  };
}

function refusal(schema: unknown): string {
  try {
    parseSchema(schema);
  } catch (error) {
    assert.ok(error instanceof CompileError, `expected a CompileError, got ${String(error)}`);
    return error.message;
  }
  return "";
}

describe("US1-AS1: every fixture schema is accepted and valid under grid-schema.schema.json", () => {
  const all = fixtureSchemas();

  it("finds 284 schemas", () => {
    assert.equal(all.length, 284);
  });

  it("accepts each one and Ajv agrees", () => {
    const problems: string[] = [];
    for (const { name, path } of all) {
      const json = readJson(path);
      if (!validate(json)) problems.push(`${name}: ${ajv.errorsText(validate.errors)}`);
      try {
        parseSchema(json);
      } catch (error) {
        problems.push(`${name}: parseSchema refused it: ${String(error)}`);
      }
    }
    assert.deepEqual(problems, []);
  });
});

describe("US1-AS2: an invalid schema is refused with a named problem", () => {
  const cases: [string, (s: Record<string, unknown>) => void, RegExp][] = [
    ["an unknown mode", (s) => void (s["mode"] = "sloppy"), /mode/],
    ["a missing source", (s) => void delete s["source"], /source/],
    ["an empty source", (s) => void (s["source"] = ""), /source/],
    ["a stableKey that is not a field", (s) => void (s["stableKey"] = "nope"), /stableKey/],
    ["an unknown schema member", (s) => void (s["tenant"] = "x"), /tenant/],
    ["a field without a type", (s) => void delete (s["fields"] as Record<string, Record<string, unknown>>)["name"]!["type"], /type/],
    ["an unknown field member", (s) => void ((s["fields"] as Record<string, Record<string, unknown>>)["name"]!["indexed"] = true), /indexed/],
    ["an unknown physical backend", (s) => void ((s["fields"] as Record<string, Record<string, Record<string, unknown>>>)["name"]!["physical"]!["oracle"] = {}), /oracle/],
    ["a bad case sensitivity", (s) => void ((s["fields"] as Record<string, Record<string, unknown>>)["name"]!["text"] = { caseSensitivity: "maybe" }), /caseSensitivity/],
    ["an empty date pattern", (s) => void ((s["fields"] as Record<string, Record<string, unknown>>)["name"]!["format"] = { datePattern: "" }), /datePattern/],
    ["no fields", (s) => void (s["fields"] = {}), /fields/],
    ["a non-boolean filterable", (s) => void ((s["fields"] as Record<string, Record<string, unknown>>)["name"]!["filterable"] = "yes"), /filterable/],
    ["aggregatable that is not a list of functions", (s) => void ((s["fields"] as Record<string, Record<string, unknown>>)["name"]!["aggregatable"] = ["median"]), /aggregatable/],
  ];
  for (const [label, mutate, pattern] of cases) {
    it(`refuses ${label}`, () => {
      const schema = base();
      mutate(schema);
      assert.match(refusal(schema), pattern);
    });
  }

  it("refuses a schema that is not an object", () => {
    assert.match(refusal([]), /object/);
    assert.match(refusal("x"), /object/);
  });

  it("defaults the mode to strict", () => {
    const schema = base();
    delete schema["mode"];
    assert.equal(parseSchema(schema).mode, "strict");
  });
});

describe("US1-AS3 and US1-AS4: the allowlist", () => {
  const strict = parseSchema(base());
  const lenient = parseSchema({ ...base(), mode: "lenient" });

  function pair(action: () => unknown): [string | undefined, string | undefined] {
    try {
      action();
    } catch (error) {
      assert.ok(error instanceof CompileError);
      return [error.rejectedAt, error.reason];
    }
    return [undefined, undefined];
  }

  it("a strict schema refuses an undeclared column as allowlist / unknown-field", () => {
    assert.deepEqual(pair(() => checkColumns(strict, ["name", "secret"], "filter")), ["allowlist", "unknown-field"]);
  });

  it("a lenient schema strips the unlisted column and keeps the rest", () => {
    assert.deepEqual(checkColumns(lenient, ["name", "secret"], "filter"), ["name"]);
  });

  it("a field declared filterable: false is refused in a filter, a set-values target and a drill-down key", () => {
    for (const usage of ["filter", "setValues", "groupKey"] as const) {
      assert.deepEqual(pair(() => checkColumns(strict, ["id"], usage)), ["allowlist", "field-not-filterable"], usage);
    }
  });

  it("the same field is fine to sort by", () => {
    assert.deepEqual(checkColumns(strict, ["id"], "sort"), ["id"]);
  });

  it("a lenient schema also strips a filterable: false column from a filter", () => {
    assert.deepEqual(checkColumns(lenient, ["id", "name"], "filter"), ["name"]);
  });
});

describe("US1-AS5: prototype-like names are ordinary names", () => {
  const schema = parseSchema(base());

  it("are unknown when undeclared", () => {
    for (const name of ["__proto__", "constructor", "toString", "hasOwnProperty", "valueOf"]) {
      const [stage, reason] = (() => {
        try {
          checkColumns(schema, [name], "filter");
        } catch (error) {
          return error instanceof CompileError ? [error.rejectedAt, error.reason] : ["other", String(error)];
        }
        return [undefined, undefined];
      })();
      assert.deepEqual([stage, reason], ["allowlist", "unknown-field"], name);
    }
  });

  it("are declared like any other name when the schema declares them", () => {
    const declared = parseSchema({
      mode: "strict",
      source: "t",
      stableKey: "constructor",
      fields: JSON.parse('{"constructor":{"type":"int64","physical":{"sql":{"column":"c"}}},"__proto__":{"type":"string","physical":{"sql":{"column":"p"}}}}') as object,
    });
    assert.deepEqual(checkColumns(declared, ["constructor", "__proto__"], "sort"), ["constructor", "__proto__"]);
  });
});
