import type { Dialect, Param, ParamSink } from "./dialect.js";

/** The ordered bound values of one query. The placeholder is the dialect's, numbered by binding order. */
export class ParameterBag implements ParamSink {
  readonly values: Param[] = [];

  constructor(private readonly dialect: Dialect) {}

  bind(value: Param): string {
    const ordinal = this.values.length;
    this.values.push(value);
    return this.dialect.placeholder(ordinal);
  }
}
