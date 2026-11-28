import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { isIsoInstant, localDateTimeToInstant, parseWireDate, resolvePreset, resolveZone } from "../src/agrid/dates.js";
import { parseRequest } from "../src/agrid/request.js";
import { CompileError } from "../src/errors.js";
import { readJson } from "../src/json.js";
import { parseSchema } from "../src/schema.js";

// Feature 013, T010 (third part, S2b-2): date conditions, presets and zones. Scenario US2-AS4 (SEM-4 resolution without the host's zone,
// a daylight-saving boundary), US2-AS3 (the date filter shapes) and US3-AS5 (an unparseable date text is a coercion rejection).
const SPEC = fileURLToPath(new URL("../../../spec/", import.meta.url));

const PRESETS: Record<string, Record<string, [string, string]>> = {
  "2026-08-12T14:37:00Z": {
    today: ["2026-08-12", "2026-08-13"], yesterday: ["2026-08-11", "2026-08-12"], tomorrow: ["2026-08-13", "2026-08-14"],
    thisWeek: ["2026-08-10", "2026-08-17"], lastWeek: ["2026-08-03", "2026-08-10"], nextWeek: ["2026-08-17", "2026-08-24"],
    thisMonth: ["2026-08-01", "2026-09-01"], lastMonth: ["2026-07-01", "2026-08-01"], nextMonth: ["2026-09-01", "2026-10-01"],
    thisQuarter: ["2026-07-01", "2026-10-01"], lastQuarter: ["2026-04-01", "2026-07-01"], nextQuarter: ["2026-10-01", "2027-01-01"],
    thisYear: ["2026-01-01", "2027-01-01"], lastYear: ["2025-01-01", "2026-01-01"], nextYear: ["2027-01-01", "2028-01-01"],
    yearToDate: ["2026-01-01", "2026-08-13"], last7Days: ["2026-08-05", "2026-08-13"], last30Days: ["2026-07-13", "2026-08-13"],
    last90Days: ["2026-05-14", "2026-08-13"], last6Months: ["2026-02-12", "2026-08-13"], last12Months: ["2025-08-12", "2026-08-13"],
    last24Months: ["2024-08-12", "2026-08-13"],
  },
  "2026-08-31T10:00:00Z": {
    thisWeek: ["2026-08-31", "2026-09-07"], last6Months: ["2026-02-28", "2026-09-01"], last90Days: ["2026-06-02", "2026-09-01"], yearToDate: ["2026-01-01", "2026-09-01"],
  },
  "2024-03-31T10:00:00Z": {
    lastMonth: ["2024-02-01", "2024-03-01"], thisQuarter: ["2024-01-01", "2024-04-01"], lastQuarter: ["2023-10-01", "2024-01-01"], last6Months: ["2023-09-30", "2024-04-01"],
    last24Months: ["2022-03-31", "2024-04-01"],
  },
};

describe("US2-AS4: the 22 presets resolve to the half-open ranges SEM-4 prescribes", () => {
  for (const [now, table] of Object.entries(PRESETS)) {
    for (const [preset, [from, to]] of Object.entries(table)) {
      it(`${preset} at ${now} in UTC`, () => {
        assert.deepEqual(resolvePreset(preset, new Date(now), "UTC"), { from, to });
      });
    }
  }

  it("a day starts in the request's zone, not in UTC", () => {
    assert.deepEqual(resolvePreset("today", new Date("2026-08-16T23:30:00Z"), "Europe/Paris"), { from: "2026-08-17", to: "2026-08-18" });
    assert.deepEqual(resolvePreset("thisWeek", new Date("2026-08-16T23:30:00Z"), "Europe/Paris"), { from: "2026-08-17", to: "2026-08-24" });
  });

  it("the first day of the week is configurable", () => {
    assert.deepEqual(resolvePreset("thisWeek", new Date("2026-08-12T14:37:00Z"), "UTC", 0), { from: "2026-08-09", to: "2026-08-16" });
  });

  it("is undefined for a name that is not a preset", () => {
    assert.equal(resolvePreset("equals", new Date("2026-08-12T00:00:00Z"), "UTC"), undefined);
  });

  it("does not depend on the host's time zone", () => {
    const before = process.env["TZ"];
    process.env["TZ"] = "Pacific/Kiritimati";
    try {
      assert.deepEqual(resolvePreset("today", new Date("2026-08-12T14:37:00Z"), "UTC"), { from: "2026-08-12", to: "2026-08-13" });
    } finally {
      if (before === undefined) delete process.env["TZ"];
      else process.env["TZ"] = before;
    }
  });
});

describe("US2-AS4: a local wall-clock time becomes an instant, across a daylight-saving boundary", () => {
  it("an ordinary time", () => {
    assert.equal(localDateTimeToInstant("2026-01-15 10:30:00", "Europe/Paris"), "2026-01-15T09:30:00Z");
    assert.equal(localDateTimeToInstant("2026-08-15 10:30:00", "Europe/Paris"), "2026-08-15T08:30:00Z");
    assert.equal(localDateTimeToInstant("2026-08-15 10:30:00", "UTC"), "2026-08-15T10:30:00Z");
  });

  it("the start of the day across spring forward (Paris, 2026-03-29)", () => {
    assert.equal(localDateTimeToInstant("2026-03-29 00:00:00", "Europe/Paris"), "2026-03-28T23:00:00Z");
    assert.equal(localDateTimeToInstant("2026-03-30 00:00:00", "Europe/Paris"), "2026-03-29T22:00:00Z");
  });

  it("an ambiguous time (fall back, Paris, 2026-10-25 02:30) takes the later offset, so the earlier instant", () => {
    assert.equal(localDateTimeToInstant("2026-10-25 02:30:00", "Europe/Paris"), "2026-10-25T00:30:00Z");
  });

  it("a time that does not exist (spring forward, Paris, 2026-03-29 02:30) takes the standard offset", () => {
    assert.equal(localDateTimeToInstant("2026-03-29 02:30:00", "Europe/Paris"), "2026-03-29T01:30:00Z");
  });
});

describe("zones", () => {
  it("accepts IANA ids", () => {
    for (const id of ["UTC", "Europe/Paris", "America/Argentina/Buenos_Aires", "Etc/GMT+1"]) {
      assert.equal(resolveZone(id), id);
    }
  });

  it("refuses an id that names no zone, an artifact that is not a zone, and an id of the wrong shape", () => {
    for (const id of ["Mars/Olympus_Mons", "localtime", "Localtime", "Factory", "posixrules", "../etc/passwd", "Europe//Paris", "", "a b"]) {
      assert.throws(() => resolveZone(id), (error: unknown) => error instanceof CompileError && error.rejectedAt === "requestParsing" && error.reason === "malformed-request", id);
    }
  });
});

describe("AG Grid wire dates and instants", () => {
  it("reads YYYY-MM-DD and YYYY-MM-DD hh:mm:ss as calendar-valid text only", () => {
    assert.deepEqual(parseWireDate("2026-01-15"), { date: "2026-01-15", time: undefined });
    assert.deepEqual(parseWireDate("2026-01-15 10:30:00"), { date: "2026-01-15", time: "10:30:00" });
    for (const bad of ["2026-13-45", "2026-02-30", "15/01/2026", "2026-1-5", "2026-01-15T10:30:00", "2026-01-15 24:00:00", "2026-01-15 10:30", "", "not a date"]) {
      assert.equal(parseWireDate(bad), undefined, bad);
    }
  });

  it("is an ISO instant when it has a date, a time and Z or an offset, and is a real instant", () => {
    for (const ok of ["2026-01-01T00:00:00Z", "2026-01-01T00:00:00.001Z", "2026-01-01T09:30:00-05:00", "2026-06-15T12:30:00+14:00"]) {
      assert.equal(isIsoInstant(ok), true, ok);
    }
    for (const bad of ["2026-01-01 00:00:00", "2026-01-01", "2026-01-01T00:00:00", "2026-13-01T00:00:00Z", "2026-01-01T24:00:00Z", "2026-01-01T00:00:60Z", "2026-01-01T00:00:00+15:00", "not a date"]) {
      assert.equal(isIsoInstant(bad), false, bad);
    }
  });
});

const SCHEMA = parseSchema({
  mode: "strict",
  source: "t",
  stableKey: "id",
  fields: {
    id: { type: "int64", physical: { sql: { column: "id" } } },
    born: { type: "date", physical: { sql: { column: "born" } } },
    seen: { type: "datetime", physical: { sql: { column: "seen" } } },
    name: { type: "string", physical: { sql: { column: "name" } } },
  },
});
const NOW = { now: () => new Date("2026-08-12T14:37:00Z") };

function filterOf(model: unknown, requestContext?: unknown) {
  const request: Record<string, unknown> = { startRow: 0, endRow: 10, filterModel: model };
  if (requestContext !== undefined) request["requestContext"] = requestContext;
  return (parseRequest(request, SCHEMA, NOW).ir as { filter?: unknown }).filter;
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

describe("US2-AS3: date conditions", () => {
  it("a date field takes a date value from either wire format", () => {
    const expected = { type: "comparison", field: "born", op: "gt", value: { type: "date", value: "2026-01-15" } };
    assert.deepEqual(filterOf({ born: { filterType: "date", type: "greaterThan", dateFrom: "2026-01-15 00:00:00" } }), expected);
    assert.deepEqual(filterOf({ born: { filterType: "date", type: "greaterThan", dateFrom: "2026-01-15" } }), expected);
  });

  it("a datetime field takes the instant of the wall-clock time in the request's zone", () => {
    assert.deepEqual(filterOf({ seen: { filterType: "date", type: "equals", dateFrom: "2026-01-15 10:30:00" } }, { zone: "Europe/Paris" }), {
      type: "comparison", field: "seen", op: "eq", value: { type: "datetime", value: "2026-01-15T09:30:00Z", zone: "Europe/Paris" },
    });
    assert.deepEqual(filterOf({ seen: { filterType: "date", type: "lessThan", dateFrom: "2026-01-15 10:30:00" } }), {
      type: "comparison", field: "seen", op: "lt", value: { type: "datetime", value: "2026-01-15T10:30:00Z", zone: "UTC" },
    });
  });

  it("blank and notBlank carry no value", () => {
    assert.deepEqual(filterOf({ born: { filterType: "date", type: "blank" } }), { type: "comparison", field: "born", op: "blank" });
  });

  it("a preset is an inRange comparison with an inclusive start and an exclusive end, typed by the field", () => {
    assert.deepEqual(filterOf({ born: { filterType: "date", type: "thisMonth" } }), {
      type: "comparison", field: "born", op: "inRange", from: { type: "date", value: "2026-08-01" }, to: { type: "date", value: "2026-09-01" }, fromInclusive: true, toInclusive: false,
    });
    assert.deepEqual(filterOf({ seen: { filterType: "date", type: "today" } }, { zone: "Europe/Paris" }), {
      type: "comparison", field: "seen", op: "inRange", from: { type: "datetime", value: "2026-08-11T22:00:00Z", zone: "Europe/Paris" },
      to: { type: "datetime", value: "2026-08-12T22:00:00Z", zone: "Europe/Paris" }, fromInclusive: true, toInclusive: false,
    });
  });

  it("a set filter over a date column resolves each value; over a datetime column a ready instant stays as written", () => {
    assert.deepEqual(filterOf({ born: { filterType: "set", values: ["2026-01-15", "2026-02-01 00:00:00"] } }), {
      type: "comparison", field: "born", op: "in", values: [{ type: "date", value: "2026-01-15" }, { type: "date", value: "2026-02-01" }],
    });
    assert.deepEqual(filterOf({ seen: { filterType: "set", values: ["2026-01-15T10:30:00Z", "2026-01-16 00:00:00"] } }), {
      type: "comparison", field: "seen", op: "in", values: [{ type: "string", value: "2026-01-15T10:30:00Z" }, { type: "datetime", value: "2026-01-16T00:00:00Z", zone: "UTC" }],
    });
  });

  it("a date text outside the wire formats is a coercion rejection; a time on a date field and a native inRange are not accepted", () => {
    assert.deepEqual(pairOf(() => filterOf({ born: { filterType: "date", type: "equals", dateFrom: "2026-13-45" } })), ["typeCoercion", "uncoercible-value"]);
    assert.deepEqual(pairOf(() => filterOf({ born: { filterType: "date", type: "equals", dateFrom: "2026-01-15 10:30:00" } })), ["requestParsing", "malformed-request"]);
    assert.deepEqual(pairOf(() => filterOf({ born: { filterType: "date", type: "inRange", dateFrom: "2026-01-01", dateTo: "2026-02-01" } })), ["requestParsing", "unknown-operator"]);
    assert.deepEqual(pairOf(() => filterOf({ born: { filterType: "date", type: "sometime", dateFrom: "2026-01-01" } })), ["requestParsing", "unknown-operator"]);
    assert.deepEqual(pairOf(() => filterOf({ born: { filterType: "date", type: "equals" } })), ["requestParsing", "malformed-request"]);
    assert.deepEqual(pairOf(() => filterOf({ born: { filterType: "date", type: "equals", dateFrom: 20260115 } })), ["requestParsing", "malformed-request"]);
  });

  it("a preset on a column that is not a date, or not declared, is refused", () => {
    assert.deepEqual(pairOf(() => filterOf({ name: { filterType: "date", type: "today" } })), ["requestParsing", "malformed-request"]);
    assert.deepEqual(pairOf(() => filterOf({ ghost: { filterType: "date", type: "today" } })), ["requestParsing", "malformed-request"]);
  });

  it("a date condition on a text column keeps the text", () => {
    assert.deepEqual(filterOf({ name: { filterType: "date", type: "equals", dateFrom: "2026-01-15" } }), { type: "comparison", field: "name", op: "eq", value: { type: "string", value: "2026-01-15" } });
  });
});

describe("the request context's zone", () => {
  it("refuses a zone that is not a string, a context that is not an object, and an unresolvable or artifact zone", () => {
    const base = { born: { filterType: "date", type: "today" } };
    for (const context of [{ zone: 5 }, "UTC", { zone: "Mars/Olympus_Mons" }, { zone: "localtime" }]) {
      assert.deepEqual(pairOf(() => filterOf(base, context)), ["requestParsing", "malformed-request"], JSON.stringify(context));
    }
  });

  it("ignores harness members it does not read, such as now", () => {
    assert.doesNotThrow(() => filterOf(null, { now: "2026-08-12T14:37:00Z", maxQueryTimeMs: 2000 }));
  });
});

describe("the date-presets fixtures agree with the bounds the expected PostgreSQL artifacts bind", () => {
  const dir = `${SPEC}fixtures/date-presets/`;
  const checked: string[] = [];

  it("resolves the first two parameters of each single-range preset fixture", () => {
    const problems: string[] = [];
    for (const name of readdirSync(dir).sort().filter((entry) => /^\d{3}-/.test(entry))) {
      const folder = `${dir}${name}/`;
      if (readdirSync(`${folder}expected`).includes("rejection.json")) continue;
      const request = readJson(readFileSync(`${folder}agGridRequest.json`, "utf8"), { numbers: "text" }) as Record<string, unknown>;
      const context = request["requestContext"] as Record<string, unknown>;
      const schema = parseSchema(readJson(readFileSync(`${folder}schema.json`, "utf8")));
      const parsed = parseRequest(request, schema, { now: () => new Date(String(context["now"])) });
      const filter = (parsed.ir as { filter?: { type: string; op?: string; from?: { value: string }; to?: { value: string } } }).filter;
      if (filter?.type !== "comparison" || filter.op !== "inRange") continue;
      const expected = JSON.parse(readFileSync(`${folder}expected/postgres.artifact.json`, "utf8")) as { params: unknown[] };
      checked.push(name);
      if (filter.from?.value !== expected.params[0] || filter.to?.value !== expected.params[1]) {
        problems.push(`${name}: got ${filter.from?.value}..${filter.to?.value}, the artifact binds ${String(expected.params[0])}..${String(expected.params[1])}`);
      }
    }
    assert.deepEqual(problems, []);
    assert.ok(checked.length >= 20, `only ${checked.length} preset fixtures were compared`);
  });
});
