import { CompileError } from "../errors.js";
import type { FilterNodeIr, TypedValueIr } from "../ir.js";
import type { GridSchema } from "../schema.js";
import { isIsoInstant, localDateTimeToInstant, parseWireDate, resolvePreset } from "./dates.js";
import { isRecord, malformed, numberText, requiredString, unknownOperator, type Obj } from "./values.js";

/** What date resolution needs from the request and the host: the zone (never the machine's), a clock read only for a preset, the week start. */
export interface DateContext {
  readonly zone: string;
  readonly now: () => Date;
  readonly firstDayOfWeek: number;
}

type Node = FilterNodeIr;

function combine(nodes: readonly Node[], isAnd: boolean, where: string): Node {
  if (nodes.length === 0) throw malformed(`${where}: a combined filter has no conditions.`);
  if (nodes.length === 1) return nodes[0]!;
  return { type: isAnd ? "and" : "or", nodes };
}

const TEXT: Readonly<Record<string, string>> = { equals: "eq", notEqual: "neq", contains: "contains", notContains: "notContains", startsWith: "startsWith", endsWith: "endsWith", blank: "blank", notBlank: "notBlank" };
const NUMBER: Readonly<Record<string, string>> = { equals: "eq", notEqual: "neq", lessThan: "lt", lessThanOrEqual: "lte", greaterThan: "gt", greaterThanOrEqual: "gte", blank: "blank", notBlank: "notBlank" };

function textCondition(field: string, condition: Obj): Node {
  const type = requiredString(condition, "type", field);
  const op = Object.hasOwn(TEXT, type) ? TEXT[type]! : undefined;
  if (op === undefined) throw unknownOperator(`Column '${field}': 'text' filterType does not recognize condition type '${type}'.`);
  if (op === "blank" || op === "notBlank") return { type: "comparison", field, op };
  const filter = condition["filter"];
  if (typeof filter !== "string") throw malformed(`Column '${field}' ('text' filter): expected a string 'filter' value.`);
  return { type: "comparison", field, op, value: { type: "string", value: filter } };
}

function numberCondition(field: string, condition: Obj): Node {
  const type = requiredString(condition, "type", field);
  if (type === "inRange") throw unknownOperator(`Column '${field}': native 'inRange' carries no boundary-inclusivity flags; use the 'customFilters' extension instead.`);
  const op = Object.hasOwn(NUMBER, type) ? NUMBER[type]! : undefined;
  if (op === undefined) throw unknownOperator(`Column '${field}': 'number' filterType does not recognize condition type '${type}'.`);
  if (op === "blank" || op === "notBlank") return { type: "comparison", field, op };
  const filter = condition["filter"];
  const text = typeof filter === "string" ? filter : numberText(filter);
  if (text === undefined) throw malformed(`Column '${field}' ('number' filter): expected a numeric or string 'filter' value.`);
  return { type: "comparison", field, op, value: { type: "string", value: text } };
}

const DATE_OPS: Readonly<Record<string, string>> = { equals: "eq", notEqual: "neq", lessThan: "lt", lessThanOrEqual: "lte", greaterThan: "gt", greaterThanOrEqual: "gte", blank: "blank", notBlank: "notBlank" };

/** AG Grid's wire date text as the typed value the field's declared type calls for (SEM-4). */
function wireDateValue(field: string, property: string, raw: string, schema: GridSchema, ctx: DateContext): TypedValueIr {
  const type = schema.fields.get(field)?.type;
  if (type !== "date" && type !== "datetime") return { type: "string", value: raw };
  const parsed = parseWireDate(raw);
  if (parsed === undefined) {
    throw new CompileError("InvalidRequest", `Column '${field}': '${property}' value '${raw}' is not one of AG Grid's date-filter wire formats ('YYYY-MM-DD' or 'YYYY-MM-DD hh:mm:ss').`, {
      rejectedAt: "typeCoercion",
      reason: "uncoercible-value",
    });
  }
  if (type === "datetime") return { type: "datetime", value: localDateTimeToInstant(`${parsed.date} ${parsed.time ?? "00:00:00"}`, ctx.zone), zone: ctx.zone };
  if (parsed.time !== undefined && parsed.time !== "00:00:00") {
    throw malformed(`Column '${field}' is declared 'date', but '${property}' carries a non-midnight time ('${raw}'); declare the field 'datetime' if the time matters.`);
  }
  return { type: "date", value: parsed.date };
}

function presetNode(field: string, name: string, schema: GridSchema, ctx: DateContext): Node | undefined {
  const range = resolvePreset(name, ctx.now(), ctx.zone, ctx.firstDayOfWeek);
  if (range === undefined) return undefined;
  const type = schema.fields.get(field)?.type;
  if (type !== "date" && type !== "datetime") {
    throw malformed(`Column '${field}': the date preset '${name}' targets a field that is not declared as a date or datetime in the schema.`);
  }
  const bound = (day: string): TypedValueIr => (type === "date" ? { type: "date", value: day } : { type: "datetime", value: localDateTimeToInstant(`${day} 00:00:00`, ctx.zone), zone: ctx.zone });
  return { type: "comparison", field, op: "inRange", from: bound(range.from), to: bound(range.to), fromInclusive: true, toInclusive: false };
}

function dateCondition(field: string, condition: Obj, schema: GridSchema, ctx: DateContext): Node {
  const type = requiredString(condition, "type", field);
  if (type === "inRange") throw unknownOperator(`Column '${field}': native 'inRange' carries no boundary-inclusivity flags; use the 'customFilters' extension instead.`);
  const preset = presetNode(field, type, schema, ctx);
  if (preset !== undefined) return preset;
  const op = Object.hasOwn(DATE_OPS, type) ? DATE_OPS[type]! : undefined;
  if (op === undefined) throw unknownOperator(`Column '${field}': 'date' filterType does not recognize condition type '${type}'.`);
  if (op === "blank" || op === "notBlank") return { type: "comparison", field, op };
  const raw = condition["dateFrom"];
  if (typeof raw !== "string") throw malformed(`Column '${field}' ('date' filter): expected a string 'dateFrom' value.`);
  return { type: "comparison", field, op, value: wireDateValue(field, "dateFrom", raw, schema, ctx) };
}

function setCondition(field: string, condition: Obj, schema: GridSchema, ctx: DateContext): Node {
  const values = condition["values"];
  if (values === undefined || values === null) throw malformed(`Column '${field}': a 'set' filter requires a non-null 'values' array.`);
  if (!Array.isArray(values)) throw malformed(`Column '${field}': a 'set' filter's 'values' must be an array.`);
  const declared = schema.fields.get(field)?.type;
  const typed = (values as unknown[]).map((element): TypedValueIr => {
    if (typeof element !== "string") throw malformed(`Column '${field}': a 'set' filter's 'values' entry must be a string.`);
    if (declared === "datetime" && isIsoInstant(element)) return { type: "string", value: element };
    return wireDateValue(field, "values", element, schema, ctx);
  });
  if (typed.length === 1 && declared === "boolean") {
    const only = (typed[0] as { value: string }).value;
    if (only === "true" || only === "false") return { type: "comparison", field, op: only };
  }
  return { type: "comparison", field, op: "in", values: typed };
}

function singleCondition(field: string, condition: unknown, schema: GridSchema, ctx: DateContext): Node {
  if (!isRecord(condition)) throw malformed(`Column '${field}': a condition must be an object.`);
  const filterType = requiredString(condition, "filterType", field);
  switch (filterType) {
    case "text":
      return textCondition(field, condition);
    case "number":
      return numberCondition(field, condition);
    case "set":
      return setCondition(field, condition, schema, ctx);
    case "date":
      return dateCondition(field, condition, schema, ctx);
    default:
      throw unknownOperator(`Column '${field}': unrecognized filterType '${filterType}'.`);
  }
}

function combineByOperator(field: string, entry: Obj, nodes: readonly Node[]): Node {
  const operator = requiredString(entry, "operator", field);
  if (operator !== "AND" && operator !== "OR") throw malformed(`Column '${field}': combined filter has an unrecognized 'operator' value '${operator}' (expected 'AND' or 'OR').`);
  return combine(nodes, operator === "AND", field);
}

function conditionOrCombined(field: string, entry: Obj, schema: GridSchema, ctx: DateContext): Node {
  if (entry["conditions"] !== undefined) {
    const conditions = entry["conditions"];
    if (!Array.isArray(conditions)) throw malformed(`Column '${field}': 'conditions' must be an array.`);
    return combineByOperator(field, entry, (conditions as unknown[]).map((c) => singleCondition(field, c, schema, ctx)));
  }
  if (entry["condition1"] !== undefined) {
    if (entry["condition2"] === undefined) throw malformed(`Column '${field}': legacy combined form has 'condition1' but is missing 'condition2'.`);
    return combineByOperator(field, entry, [singleCondition(field, entry["condition1"], schema, ctx), singleCondition(field, entry["condition2"], schema, ctx)]);
  }
  return singleCondition(field, entry, schema, ctx);
}

function columnEntry(field: string, entry: Obj, schema: GridSchema, ctx: DateContext): Node | undefined {
  if (requiredString(entry, "filterType", field) !== "multi") return conditionOrCombined(field, entry, schema, ctx);
  const models = entry["filterModels"];
  if (!Array.isArray(models)) throw malformed(`Column '${field}': 'multi' filterType requires a 'filterModels' array.`);
  const nodes: Node[] = [];
  for (const model of models as unknown[]) {
    if (model === null) continue;
    if (!isRecord(model)) throw malformed(`Column '${field}': a 'multi' filterModels entry must be an object or null.`);
    nodes.push(conditionOrCombined(field, model, schema, ctx));
  }
  return nodes.length === 0 ? undefined : combine(nodes, true, field);
}

/** The AG Grid `filterModel` as a filter tree: one node per column, ANDed in the order of the model. */
export function parseFilterModel(root: Obj, schema: GridSchema, ctx: DateContext): Node | undefined {
  const model = root["filterModel"];
  if (model === undefined || model === null) return undefined;
  if (!isRecord(model)) throw malformed("'filterModel' must be a JSON object or null.");
  const nodes: Node[] = [];
  for (const [field, entry] of Object.entries(model)) {
    if (!isRecord(entry)) throw malformed(`filterModel['${field}'] must be a JSON object.`);
    const node = columnEntry(field, entry, schema, ctx);
    if (node !== undefined) nodes.push(node);
  }
  return nodes.length === 0 ? undefined : combine(nodes, true, "filterModel");
}

/** FilterTreeMerge: the native filter, then the custom filter, ANDed. */
export function mergeFilters(native: Node | undefined, custom: Node | undefined): Node | undefined {
  if (native === undefined) return custom;
  if (custom === undefined) return native;
  return { type: "and", nodes: [native, custom] };
}
