import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { JsonNumber, readJson, type JsonValue } from "../src/json.js";
import { answerFor } from "../src/protocol.js";

// Feature 014, T002 (US1-AS1, US1-AS2, US1-AS7): the PostgreSQL artifacts of every fixture the current slice compiles, through the
// driver's own request path, compared as the runner compares them: sql character for character, params element by element, numbers by text.
const FIXTURES = fileURLToPath(new URL("../../../spec/fixtures/", import.meta.url));

function plain(value: JsonValue): unknown {
  if (value instanceof JsonNumber) return `number:${value.text}`;
  if (Array.isArray(value)) return value.map(plain);
  if (value !== null && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, plain(item)]));
  return value;
}

function compact(path: string): string {
  return readFileSync(path, "utf8").replace(/\r?\n/g, " ");
}

function lineFor(id: string, dir: string, backend: string): string {
  return `{"id":${JSON.stringify(id)},"backend":${JSON.stringify(backend)},"schema":${compact(`${dir}schema.json`)},"agGridRequest":${compact(`${dir}agGridRequest.json`)}}`;
}

interface Case {
  readonly name: string;
  readonly dir: string;
}

/** Every fixture with a PostgreSQL artifact: filters, sorting and paging, grouping, aggregation, count mode, set values, export. */
function postgresCases(): Case[] {
  const found: Case[] = [];
  for (const category of readdirSync(FIXTURES, { withFileTypes: true })) {
    if (!category.isDirectory() || category.name === "schemas") continue;
    for (const fixture of readdirSync(`${FIXTURES}${category.name}`, { withFileTypes: true })) {
      const dir = `${FIXTURES}${category.name}/${fixture.name}/`;
      if (!fixture.isDirectory() || !readdirSync(`${dir}expected`).includes("postgres.artifact.json")) continue;
      found.push({ name: `${category.name}/${fixture.name}`, dir });
    }
  }
  return found;
}

describe("US1-AS1, US1-AS4, US1-AS5, US3: the PostgreSQL artifact of every fixture", () => {
  const cases = postgresCases();

  it("finds the 246 cases", () => {
    assert.equal(cases.length, 246);
  });

  it("compiles each to the expected sql and params", () => {
    const problems: string[] = [];
    for (const { name, dir } of cases) {
      const outcome = answerFor(lineFor(`${name}#postgres`, dir, "postgres"));
      if (!("answer" in outcome)) {
        problems.push(`${name}: unanswerable`);
        continue;
      }
      const reply = readJson(outcome.answer, { numbers: "text" }) as Record<string, JsonValue>;
      const expected = readJson(readFileSync(`${dir}expected/postgres.artifact.json`, "utf8"), { numbers: "text" }) as Record<string, JsonValue>;
      if (reply["artifact"] === undefined) {
        problems.push(`${name}: ${JSON.stringify(reply["error"]).slice(0, 160)}`);
        continue;
      }
      try {
        assert.deepEqual(plain(reply["artifact"]), plain(expected));
      } catch {
        const got = reply["artifact"] as Record<string, JsonValue>;
        problems.push(`${name}: expected ${String(expected["sql"])} ${JSON.stringify(plain(expected["params"] as JsonValue))} got ${String(got["sql"])} ${JSON.stringify(plain(got["params"] as JsonValue))}`);
      }
    }
    assert.deepEqual(problems, []);
  });
});

describe("US1-AS2, US1-AS3, US1-AS7: values are parameters, names come from the schema, the output follows the request", () => {
  const dir = `${FIXTURES}operators/001-eq-string/`;
  const schema = compact(`${dir}schema.json`);
  const reply = (filterModel: string, extra = "") =>
    readJson(
      (answerFor(`{"id":"h","backend":"postgres","schema":${schema},"agGridRequest":{"startRow":0,"endRow":10,"filterModel":${filterModel},"sortModel":[]${extra}}}`) as { answer: string }).answer,
      { numbers: "text" },
    ) as Record<string, JsonValue>;
  const filter = (op: string, value: string) => `{"status":{"filterType":"text","type":"${op}","filter":${JSON.stringify(value)}}}`;
  const sqlOf = (r: Record<string, JsonValue>) => String((r["artifact"] as Record<string, JsonValue>)["sql"]);
  const paramsOf = (r: Record<string, JsonValue>) => plain((r["artifact"] as Record<string, JsonValue>)["params"] as JsonValue) as unknown[];

  it("binds a hostile value and never spells it into the sql", () => {
    for (const hostile of ["'; DROP TABLE items; --", "\" OR 1=1 --", "$1; SELECT 1", "x'||(SELECT 1)||'"]) {
      const r = reply(filter("equals", hostile));
      assert.ok(r["artifact"] !== undefined, JSON.stringify(r["error"]));
      assert.ok(!sqlOf(r).includes(hostile), hostile);
      assert.ok(paramsOf(r).includes(hostile), hostile);
    }
  });

  it("escapes pattern characters of a substring value in the parameter, not the sql", () => {
    const r = reply(filter("contains", "50%_\\"));
    assert.ok(paramsOf(r).includes("50\\%\\_\\\\"), JSON.stringify(paramsOf(r)));
  });

  it("changes the sql when the operator changes and the params when the value changes", () => {
    const eq = reply(filter("equals", "a"));
    const neq = reply(filter("notEqual", "a"));
    const other = reply(filter("equals", "b"));
    assert.notEqual(sqlOf(eq), sqlOf(neq));
    assert.equal(sqlOf(eq), sqlOf(other));
    assert.notDeepEqual(paramsOf(eq), paramsOf(other));
  });

  it("refuses a column that is a hostile name before any sql is built", () => {
    const r = reply(`{"status\\"; DROP TABLE x; --":{"filterType":"text","type":"equals","filter":"a"}}`);
    assert.equal(r["artifact"], undefined);
    assert.ok(r["error"] !== undefined);
  });
});

describe("US1-AS6: the schema's static filter is injected and a request cannot remove it", () => {
  const base = JSON.parse(readFileSync(`${FIXTURES}operators/001-eq-string/schema.json`, "utf8")) as Record<string, unknown>;
  const withStatic = JSON.stringify({ ...base, staticFilter: { type: "comparison", field: "status", op: "neq", value: { type: "string", value: "deleted" } } });
  const ask = (filterModel: string) =>
    readJson(
      (answerFor(`{"id":"s","backend":"postgres","schema":${withStatic},"agGridRequest":{"startRow":0,"endRow":10,"filterModel":${filterModel},"sortModel":[]}}`) as { answer: string }).answer,
      { numbers: "text" },
    ) as Record<string, JsonValue>;

  it("adds the static condition alone when the request has no filter", () => {
    const sql = String(((ask("null")["artifact"]) as Record<string, JsonValue>)["sql"]);
    assert.match(sql, /WHERE \(?"status" COLLATE craticula_ci <> \$1 OR "status" IS NULL\)?/);
  });

  it("ands it with the request's filter, whatever the filter says", () => {
    const sql = String(((ask(`{"status":{"filterType":"text","type":"equals","filter":"deleted"}}`)["artifact"]) as Record<string, JsonValue>)["sql"]);
    assert.match(sql, / AND \(/);
    assert.match(sql, /<> \$/);
  });
});

describe("US1-AS2: an integer beyond 2^53 keeps its digits through the driver's output", () => {
  it("writes the digits of a large int64 filter value into the artifact's params", () => {
    const dir = `${FIXTURES}operators/003-eq-int64/`;
    const raw = `{"id":"big","backend":"postgres","schema":${compact(`${dir}schema.json`)},"agGridRequest":{"startRow":0,"endRow":10,"sortModel":[],"customFilters":{"type":"comparison","field":"age","op":"eq","value":{"type":"int64","value":9007199254740993}}}}`;
    const outcome = answerFor(raw);
    assert.ok("answer" in outcome);
    assert.match(outcome.answer, /"params":\[9007199254740993,10,0\]/);
  });
});
