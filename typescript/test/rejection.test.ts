import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { JsonError, readJson } from "../src/json.js";

// Feature 013, T020 (US3): the rejection kind and capability, and hostile lines (spec/conformance-runner.md §2.2, §2.4, §3, §4.1).
const DRIVER = fileURLToPath(new URL("../src/driver.js", import.meta.url));
const FIXTURES = fileURLToPath(new URL("../../../spec/fixtures/", import.meta.url));

type Reply = Record<string, unknown>;

function run(lines: string[]): { status: number | null; replies: Reply[]; stderr: string } {
  const result = spawnSync(process.execPath, [DRIVER], { input: lines.join("\n") + "\n", encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  const replies = result.stdout.split("\n").filter((line) => line.length > 0).map((line) => JSON.parse(line) as Reply);
  return { status: result.status, replies, stderr: result.stderr };
}

/** The line the runner writes: members in the runner's order, the request text unchanged (duplicate keys survive). */
function line(id: string, kind: string | undefined, dir: string, extra = ""): string {
  const compact = (name: string) => readFileSync(`${dir}${name}`, "utf8").replace(/\r?\n/g, " ");
  const head = kind === undefined ? `"id":${JSON.stringify(id)}` : `"id":${JSON.stringify(id)},"kind":${JSON.stringify(kind)}`;
  return `{${head},${extra}"schema":${compact("schema.json")},"agGridRequest":${compact("agGridRequest.json")}}`;
}

function rejectionFixtures(): { name: string; dir: string; pair: { rejectedAt: string; reason: string } }[] {
  const found: { name: string; dir: string; pair: { rejectedAt: string; reason: string } }[] = [];
  for (const category of readdirSync(FIXTURES, { withFileTypes: true })) {
    if (!category.isDirectory() || category.name === "schemas") continue;
    for (const fixture of readdirSync(`${FIXTURES}${category.name}`, { withFileTypes: true })) {
      const dir = `${FIXTURES}${category.name}/${fixture.name}/`;
      if (fixture.isDirectory() && readdirSync(`${dir}expected`).includes("rejection.json")) {
        found.push({ name: `${category.name}/${fixture.name}`, dir, pair: JSON.parse(readFileSync(`${dir}expected/rejection.json`, "utf8")) as { rejectedAt: string; reason: string } });
      }
    }
  }
  return found;
}

describe("US3: the hello declares the rejection capability", () => {
  it("lists rejection and no writer", () => {
    const hello = run([]).replies[0]!["hello"] as Reply;
    assert.deepEqual(hello["capabilities"], ["rejection"]);
  });
});

describe("US3-AS1: every shared rejection fixture is refused at its own stage for its own reason", () => {
  const fixtures = rejectionFixtures();

  it("finds the 33 fixtures", () => {
    assert.equal(fixtures.length, 33);
  });

  it("answers each with the expected rejectedAt and reason", () => {
    const { replies, status } = run(fixtures.map((f) => line(`${f.name}#rejection`, "rejection", f.dir)));
    assert.equal(status, 0);
    const problems: string[] = [];
    fixtures.forEach((f, i) => {
      const reply = replies[i + 1];
      const error = (reply?.["error"] ?? {}) as Reply;
      if (reply?.["id"] !== `${f.name}#rejection` || error["rejectedAt"] !== f.pair.rejectedAt || error["reason"] !== f.pair.reason) {
        problems.push(`${f.name}: expected ${f.pair.rejectedAt}/${f.pair.reason}, got ${JSON.stringify(reply).slice(0, 200)}`);
      }
    });
    assert.deepEqual(problems, []);
  });

  it("answers a request that is accepted with an artifact, which the runner fails", () => {
    const { replies } = run([line("sort-paging/001#rejection", "rejection", `${FIXTURES}sort-paging/001-single-key-string-asc-nulls-last-default/`)]);
    assert.ok("artifact" in replies[1]!, JSON.stringify(replies[1]));
  });
});

describe("US3-AS2: harness inputs reach the parser and the limits are the defaults", () => {
  const dir = `${FIXTURES}sort-paging/001-single-key-string-asc-nulls-last-default/`;
  const schema = readFileSync(`${dir}schema.json`, "utf8").replace(/\r?\n/g, " ");
  const request = (context: string, window = '"startRow":null,"endRow":null') =>
    `{"id":"a#postgres","backend":"postgres","schema":${schema},"agGridRequest":{${window},"sortModel":[],"requestContext":${context}}}`;

  it("takes the default page size from requestContext", () => {
    const artifact = run([request('{"defaultPageSize":25}')]).replies[1]!["artifact"] as Reply;
    assert.deepEqual(artifact["params"], [25, 0]);
  });

  it("takes the unbounded-rows switch from requestContext, and refuses ignorePageLimit without it", () => {
    const window = '"startRow":null,"endRow":null,"ignorePageLimit":true';
    assert.ok("error" in run([request("{}", window)]).replies[1]!);
    const artifact = run([request('{"allowUnboundedRows":true}', window)]).replies[1]!["artifact"] as Reply;
    assert.doesNotMatch(String(artifact["sql"]), /LIMIT/);
  });

  it("refuses a page above the limit with the limits stage on a rejection request", () => {
    const text = readFileSync(`${dir}agGridRequest.json`, "utf8").replace(/"endRow":\s*[0-9]+/, '"endRow": 5000');
    const raw = `{"id":"x#rejection","kind":"rejection","schema":${readFileSync(`${dir}schema.json`, "utf8").replace(/\r?\n/g, " ")},"agGridRequest":${text.replace(/\r?\n/g, " ")}}`;
    const error = run([raw]).replies[1]!["error"] as Reply;
    assert.deepEqual([error["rejectedAt"], error["reason"]], ["resourceLimits", "max-page-size-exceeded"]);
  });
});

describe("US3-AS3: hostile lines are answered or refused, never crash the driver", () => {
  const dir = `${FIXTURES}sort-paging/001-single-key-string-asc-nulls-last-default/`;

  it("answers an oversized line by id, as a malformed request on a rejection request", () => {
    const padding = "x".repeat(5 * 1024 * 1024);
    const raw = `{"id":"big#rejection","kind":"rejection","schema":{},"agGridRequest":{"pad":"${padding}"}}`;
    const { replies, status } = run([raw]);
    assert.equal(status, 0);
    const error = replies[1]!["error"] as Reply;
    assert.equal(replies[1]!["id"], "big#rejection");
    assert.deepEqual([error["rejectedAt"], error["reason"]], ["requestParsing", "malformed-request"]);
  });

  it("answers a nesting bomb by id", () => {
    const bomb = "[".repeat(100000) + "]".repeat(100000);
    const { replies, status } = run([`{"id":"deep#rejection","kind":"rejection","schema":{},"agGridRequest":${bomb}}`]);
    assert.equal(status, 0);
    assert.equal(replies[1]!["id"], "deep#rejection");
    assert.ok("error" in replies[1]!);
  });

  it("answers a duplicate-key line on a compile request with a plain error", () => {
    const { replies } = run([`{"id":"dup#postgres","backend":"postgres","backend":"mongo","schema":{},"agGridRequest":{}}`]);
    assert.equal(replies[1]!["id"], "dup#postgres");
    assert.ok("error" in replies[1]!);
  });

  it("still refuses a line with no readable id, with exit status 1", () => {
    const { status, replies, stderr } = run([`{"kind":"rejection","id":"a","id":"b"`]);
    assert.equal(status, 1);
    assert.equal(replies.length, 1);
    assert.match(stderr, /cannot be answered/);
  });

  it("keeps the number text of a request", () => {
    const text = `{"id":"n#rejection","kind":"rejection","schema":${readFileSync(`${dir}schema.json`, "utf8").replace(/\r?\n/g, " ")},"agGridRequest":{"startRow":0,"endRow":100.0,"sortModel":[]}}`;
    const error = run([text]).replies[1]!["error"] as Reply;
    assert.deepEqual([error["rejectedAt"], error["reason"]], ["requestParsing", "malformed-request"]);
  });
});

describe("the JSON reader's recovery mode", () => {
  it("refuses a duplicate key by default and reads the last when asked, for recovering an id", () => {
    assert.throws(() => readJson('{"id":"a","id":"b"}'), (error: unknown) => error instanceof JsonError && error.kind === "duplicate-key");
    assert.deepEqual({ ...(readJson('{"id":"a","id":"b"}', { duplicateKeys: "last" }) as object) }, { id: "b" });
  });
});
