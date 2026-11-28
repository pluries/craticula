import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { createLimits, DEFAULT_LIMITS } from "../src/limits.js";

// Feature 013, T002. Scenario US3-AS4 (SEC-3: every limit configurable, none can be switched off) and FR-008.

describe("the SEC-3 resource limits", () => {
  it("have the spec's defaults", () => {
    assert.deepEqual(DEFAULT_LIMITS, {
      maxDepth: 8,
      maxLeaves: 64,
      maxInValues: 1000,
      maxPageSize: 1000,
      maxSetValuesResults: 10000,
      defaultSetValuesResults: 1000,
    });
  });

  it("can be raised or lowered by the host", () => {
    const limits = createLimits({ maxDepth: 12, maxPageSize: 50 });
    assert.equal(limits.maxDepth, 12);
    assert.equal(limits.maxPageSize, 50);
    assert.equal(limits.maxLeaves, 64);
  });

  it("refuse a value that is not a positive integer, at start", () => {
    for (const bad of [0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, "8" as unknown as number, null as unknown as number]) {
      assert.throws(() => createLimits({ maxLeaves: bad }), RangeError, String(bad));
    }
    assert.throws(() => createLimits({ maxQueryTimeMs: 0 }), RangeError);
  });

  it("refuse an unknown option, so a typo cannot silently keep a default", () => {
    assert.throws(() => createLimits({ maxDepht: 3 } as never), RangeError);
  });

  it("are frozen", () => {
    const limits = createLimits();
    assert.throws(() => {
      (limits as { maxDepth: number }).maxDepth = 1000;
    }, TypeError);
  });

  it("leave the defaults untouched after an override", () => {
    createLimits({ maxDepth: 99 });
    assert.equal(DEFAULT_LIMITS.maxDepth, 8);
  });
});
