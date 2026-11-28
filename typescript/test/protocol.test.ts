import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { assertSupportedNode } from "../src/protocol.js";

// Scenarios US2-AS1 (hello), US2-AS2 (artifact answer), US2-AS3 (error answers), US2-AS4 (hostile colId), US2-AS5 (exit codes), US2-AS6 (stdout).
const DRIVER = fileURLToPath(new URL("../src/driver.js", import.meta.url));
const FIXTURES = fileURLToPath(new URL("../../../spec/fixtures/sort-paging/", import.meta.url));
const SPEC_VERSION = readFileSync(fileURLToPath(new URL("../../../spec/VERSION", import.meta.url)), "utf8").trim();

function readJson(path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
}

function request(id: string, name = "002-single-key-int64-asc-nulls-last-default", extra: Record<string, unknown> = {}): string {
  const dir = `${FIXTURES}${name}/`;
  return JSON.stringify({ id, backend: "postgres", schema: readJson(`${dir}schema.json`), agGridRequest: readJson(`${dir}agGridRequest.json`), ...extra });
}

function run(lines: string[]): { status: number | null; stdout: string[]; stderr: string } {
  const result = spawnSync(process.execPath, [DRIVER], { input: lines.join("\n") + (lines.length > 0 ? "\n" : ""), encoding: "utf8" });
  return { status: result.status, stdout: result.stdout.split("\n").filter((line) => line.length > 0), stderr: result.stderr };
}

function parse(line: string | undefined): Record<string, unknown> {
  assert.ok(line, "a line was expected");
  return JSON.parse(line) as Record<string, unknown>;
}

describe("US2-AS1: the hello", () => {
  it("is the first line and declares impl, the spec version, the five SQL dialects and the rejection capability", () => {
    const { stdout } = run([]);
    const hello = parse(stdout[0])["hello"] as Record<string, unknown>;
    assert.equal(hello["impl"], "typescript");
    assert.equal(hello["specVersion"], SPEC_VERSION);
    assert.deepEqual(hello["backends"], ["postgres", "mssql", "mysql", "oracle", "sqlite"]);
    assert.deepEqual(hello["capabilities"], ["rejection"]);
  });
});

describe("US2-AS2 and US2-AS6: an artifact answer, protocol lines only", () => {
  it("answers one compact line per request with the same id", () => {
    const { stdout, status } = run([request("sort-paging/002#postgres")]);
    assert.equal(status, 0);
    assert.equal(stdout.length, 2);
    const answer = parse(stdout[1]);
    assert.equal(answer["id"], "sort-paging/002#postgres");
    const artifact = answer["artifact"] as Record<string, unknown>;
    assert.equal(artifact["dialect"], "postgres");
    assert.deepEqual(artifact["params"], [100, 0]);
    assert.equal(stdout[1], JSON.stringify(answer));
    assert.match(stdout[1]!, /"params":\[100,0\]/);
  });

  it("writes nothing but JSON objects on stdout", () => {
    const { stdout } = run([request("a"), request("b", "011-page-range-with-tiebreaker")]);
    for (const line of stdout) {
      assert.equal(typeof parse(line), "object");
    }
  });
});

describe("US2-AS3: unsupported requests get an error answer and the driver keeps running", () => {
  const cases: [string, string][] = [
    ["another backend", request("x1", undefined, { backend: "mongo" })],
    ["a writer request", request("x3", undefined, { kind: "writer" })],
    ["an unknown kind", request("x4", undefined, { kind: "teleport" })],
  ];

  for (const [label, line] of cases) {
    it(`answers ${label} with an error and then answers the next request`, () => {
      const id = String(parse(line)["id"]);
      const { stdout, status } = run([line, request("after")]);
      assert.equal(status, 0);
      const first = parse(stdout[1]);
      assert.equal(first["id"], id);
      assert.equal("artifact" in first, false);
      const error = first["error"] as Record<string, unknown>;
      assert.equal(typeof error["kind"], "string");
      assert.equal(typeof error["message"], "string");
      assert.ok("artifact" in parse(stdout[2]), "the driver went on");
    });
  }

  it("answers a request whose schema is not an object with an error", () => {
    const { stdout } = run([JSON.stringify({ id: "bad", backend: "postgres", schema: 7, agGridRequest: {} })]);
    assert.ok("error" in parse(stdout[1]));
  });
});

describe("US2-AS4: a hostile sort column gets an error and no artifact", () => {
  it("refuses x\"; DROP TABLE t; --", () => {
    const dir = `${FIXTURES}002-single-key-int64-asc-nulls-last-default/`;
    const agGridRequest = { ...readJson(`${dir}agGridRequest.json`), sortModel: [{ colId: 'x"; DROP TABLE t; --', sort: "asc" }] };
    const line = JSON.stringify({ id: "evil", backend: "postgres", schema: readJson(`${dir}schema.json`), agGridRequest });
    const { stdout } = run([line]);
    const answer = parse(stdout[1]);
    assert.equal("artifact" in answer, false);
    assert.equal((answer["error"] as Record<string, unknown>)["kind"], "UnknownField");
    assert.equal(stdout[1]!.includes("DROP"), true, "the message may quote the input; it is never SQL");
  });
});

describe("US2-AS5: exit codes", () => {
  it("exits 0 when stdin closes", () => {
    assert.equal(run([]).status, 0);
  });

  it("exits non-zero and says why on stderr for a line with no readable id", () => {
    const { status, stderr } = run(["{\"backend\":\"postgres\"}"]);
    assert.notEqual(status, 0);
    assert.match(stderr, /cannot be answered/);
  });

  it("exits non-zero for a line that is not JSON", () => {
    const { status, stderr } = run(["not json"]);
    assert.notEqual(status, 0);
    assert.match(stderr, /not JSON/);
  });
});

describe("a Node older than the minimum is refused with a clear message", () => {
  it("accepts 22.0.0 and 24.1.0, refuses 20.11.0", () => {
    assert.doesNotThrow(() => assertSupportedNode("22.0.0"));
    assert.doesNotThrow(() => assertSupportedNode("24.1.0"));
    assert.throws(() => assertSupportedNode("20.11.0"), /Node 22 or newer/);
  });
});
