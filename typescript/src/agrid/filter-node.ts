import type { ComparisonIr, FilterNodeIr, TypedValueIr } from "../ir.js";
import { isRecord, malformed, numberText, type Obj } from "./values.js";

/**
 * Reads a host- or client-supplied filter node (`ir.schema.json` `filterNode`): the `customFilters` extension. The shape is checked
 * exactly as the schema states it; anything else is refused as a malformed request. Limits (depth, leaves, set sizes) and the
 * allowlist are separate stages.
 */
const UNARY = ["blank", "notBlank", "true", "false"];
const BINARY = ["eq", "neq", "gt", "gte", "lt", "lte", "contains", "notContains", "startsWith", "endsWith"];
const SET = ["in", "notIn"];
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;
const ZONE = /^[A-Za-z0-9_+-]+(\/[A-Za-z0-9_+-]+)*$/;
const DECIMAL = /^-?\d+(\.\d+)?$/;

function exactly(source: Obj, allowed: readonly string[], where: string): void {
  for (const key of Object.keys(source)) {
    if (!allowed.includes(key)) throw malformed(`${where} has an unknown member '${key}'.`);
  }
}

function fieldName(source: Obj, where: string): string {
  const field = source["field"];
  if (typeof field !== "string" || field.length === 0 || field.length > 256) throw malformed(`${where} needs a 'field' of 1 to 256 characters.`);
  return field;
}

export function readTypedValue(value: unknown, where: string): TypedValueIr {
  if (!isRecord(value)) throw malformed(`${where} must be a typed value object.`);
  const type = value["type"];
  const raw = value["value"];
  switch (type) {
    case "string":
      exactly(value, ["type", "value"], where);
      if (typeof raw !== "string" || raw.length > 8192) throw malformed(`${where}: a string value must be text of at most 8192 characters.`);
      return { type, value: raw };
    case "int64": {
      exactly(value, ["type", "value"], where);
      const text = numberText(raw);
      if (text === undefined || !/^-?\d+$/.test(text)) throw malformed(`${where}: an int64 value must be a whole number.`);
      return { type, value: Number(text) };
    }
    case "decimal":
      exactly(value, ["type", "value"], where);
      if (typeof raw !== "string" || !DECIMAL.test(raw)) throw malformed(`${where}: a decimal value must be text such as "19.99".`);
      return { type, value: raw };
    case "double": {
      exactly(value, ["type", "value"], where);
      const text = numberText(raw);
      if (text === undefined) throw malformed(`${where}: a double value must be a number.`);
      return { type, value: Number(text) };
    }
    case "boolean":
      exactly(value, ["type", "value"], where);
      if (typeof raw !== "boolean") throw malformed(`${where}: a boolean value must be true or false.`);
      return { type, value: raw };
    case "date":
      exactly(value, ["type", "value"], where);
      if (typeof raw !== "string" || !DATE.test(raw)) throw malformed(`${where}: a date value must be YYYY-MM-DD.`);
      return { type, value: raw };
    case "datetime": {
      exactly(value, ["type", "value", "zone"], where);
      const zone = value["zone"];
      if (typeof raw !== "string" || !DATETIME.test(raw)) throw malformed(`${where}: a datetime value must be an ISO-8601 instant.`);
      if (typeof zone !== "string" || zone.length === 0 || zone.length > 64 || !ZONE.test(zone)) throw malformed(`${where}: a datetime value needs a time zone id.`);
      return { type, value: raw, zone };
    }
    case "null":
      exactly(value, ["type"], where);
      return { type };
    default:
      throw malformed(`${where} has an unknown value type.`);
  }
}

function readComparison(source: Obj, where: string): ComparisonIr {
  const op = source["op"];
  if (typeof op !== "string") throw malformed(`${where} needs an 'op'.`);
  const field = fieldName(source, where);
  if (UNARY.includes(op)) {
    exactly(source, ["type", "field", "op"], where);
    return { type: "comparison", field, op };
  }
  if (BINARY.includes(op)) {
    exactly(source, ["type", "field", "op", "value"], where);
    return { type: "comparison", field, op, value: readTypedValue(source["value"], `${where}.value`) };
  }
  if (SET.includes(op)) {
    exactly(source, ["type", "field", "op", "values"], where);
    const values = source["values"];
    if (!Array.isArray(values)) throw malformed(`${where}.values must be an array.`);
    return { type: "comparison", field, op, values: (values as unknown[]).map((v, i) => readTypedValue(v, `${where}.values[${i}]`)) };
  }
  if (op === "inRange") {
    exactly(source, ["type", "field", "op", "from", "to", "fromInclusive", "toInclusive"], where);
    if (typeof source["fromInclusive"] !== "boolean" || typeof source["toInclusive"] !== "boolean") throw malformed(`${where} needs fromInclusive and toInclusive.`);
    return {
      type: "comparison",
      field,
      op,
      from: readTypedValue(source["from"], `${where}.from`),
      to: readTypedValue(source["to"], `${where}.to`),
      fromInclusive: source["fromInclusive"],
      toInclusive: source["toInclusive"],
    };
  }
  throw malformed(`${where} has an operator outside the closed set.`);
}

export function readFilterNode(value: unknown, where = "customFilters"): FilterNodeIr {
  if (!isRecord(value)) throw malformed(`${where} must be a filter node object.`);
  switch (value["type"]) {
    case "and":
    case "or": {
      exactly(value, ["type", "nodes"], where);
      const nodes = value["nodes"];
      if (!Array.isArray(nodes) || nodes.length === 0) throw malformed(`${where}.nodes must be a non-empty array.`);
      return { type: value["type"], nodes: (nodes as unknown[]).map((n, i) => readFilterNode(n, `${where}.nodes[${i}]`)) };
    }
    case "not":
      exactly(value, ["type", "node"], where);
      return { type: "not", node: readFilterNode(value["node"], `${where}.node`) };
    case "comparison":
      return readComparison(value, where);
    default:
      throw malformed(`${where} has an unknown node type.`);
  }
}
