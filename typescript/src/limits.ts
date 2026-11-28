/** SEC-3's resource limits. Every limit is configurable and none can be switched off: a value that is not a positive integer is refused. */
export interface Limits {
  readonly maxDepth: number;
  readonly maxLeaves: number;
  readonly maxInValues: number;
  readonly maxPageSize: number;
  readonly maxSetValuesResults: number;
  readonly defaultSetValuesResults: number;
  readonly maxQueryTimeMs?: number;
}

export type LimitsInput = Partial<Limits>;

export const DEFAULT_LIMITS: Readonly<Limits> = Object.freeze({
  maxDepth: 8,
  maxLeaves: 64,
  maxInValues: 1000,
  maxPageSize: 1000,
  maxSetValuesResults: 10000,
  defaultSetValuesResults: 1000,
});

const KNOWN = new Set<string>([...Object.keys(DEFAULT_LIMITS), "maxQueryTimeMs"]);

/** The host's limits: the defaults, with any override that is a positive integer. Refuses anything else, at start. */
export function createLimits(overrides: LimitsInput = {}): Readonly<Limits> {
  const merged: Record<string, number> = { ...DEFAULT_LIMITS };
  for (const [name, value] of Object.entries(overrides)) {
    if (!KNOWN.has(name)) {
      throw new RangeError(`Unknown limit '${name}'.`);
    }
    if (typeof value !== "number" || !Number.isSafeInteger(value) || value <= 0) {
      throw new RangeError(`The limit '${name}' must be a positive integer (SEC-3: a limit can be changed but not switched off), not ${String(value)}.`);
    }
    merged[name] = value;
  }
  return Object.freeze(merged as unknown as Limits);
}
