import type { FilterNodeIr } from "../ir.js";
import type { GridSchema } from "../schema.js";
import { isRecord, malformed, numberText, requiredString, unknownOperator, unsupported, type Obj } from "./values.js";

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

function setCondition(field: string, condition: Obj, schema: GridSchema): Node {
  const values = condition["values"];
  if (values === undefined || values === null) throw malformed(`Column '${field}': a 'set' filter requires a non-null 'values' array.`);
  if (!Array.isArray(values)) throw malformed(`Column '${field}': a 'set' filter's 'values' must be an array.`);
  const typed = (values as unknown[]).map((element) => {
    if (typeof element !== "string") throw malformed(`Column '${field}': a 'set' filter's 'values' entry must be a string.`);
    return { type: "string" as const, value: element };
  });
  const declared = schema.fields.get(field)?.type;
  if (declared === "date" || declared === "datetime") throw unsupported(`A set filter over the ${declared} column '${field}' resolves date text.`);
  if (typed.length === 1 && declared === "boolean") {
    const only = typed[0]!.value;
    if (only === "true" || only === "false") return { type: "comparison", field, op: only };
  }
  return { type: "comparison", field, op: "in", values: typed };
}

function singleCondition(field: string, condition: unknown, schema: GridSchema): Node {
  if (!isRecord(condition)) throw malformed(`Column '${field}': a condition must be an object.`);
  const filterType = requiredString(condition, "filterType", field);
  switch (filterType) {
    case "text":
      return textCondition(field, condition);
    case "number":
      return numberCondition(field, condition);
    case "set":
      return setCondition(field, condition, schema);
    case "date":
      throw unsupported(`A date condition on column '${field}'.`);
    default:
      throw unknownOperator(`Column '${field}': unrecognized filterType '${filterType}'.`);
  }
}

function combineByOperator(field: string, entry: Obj, nodes: readonly Node[]): Node {
  const operator = requiredString(entry, "operator", field);
  if (operator !== "AND" && operator !== "OR") throw malformed(`Column '${field}': combined filter has an unrecognized 'operator' value '${operator}' (expected 'AND' or 'OR').`);
  return combine(nodes, operator === "AND", field);
}

function conditionOrCombined(field: string, entry: Obj, schema: GridSchema): Node {
  if (entry["conditions"] !== undefined) {
    const conditions = entry["conditions"];
    if (!Array.isArray(conditions)) throw malformed(`Column '${field}': 'conditions' must be an array.`);
    return combineByOperator(field, entry, (conditions as unknown[]).map((c) => singleCondition(field, c, schema)));
  }
  if (entry["condition1"] !== undefined) {
    if (entry["condition2"] === undefined) throw malformed(`Column '${field}': legacy combined form has 'condition1' but is missing 'condition2'.`);
    return combineByOperator(field, entry, [singleCondition(field, entry["condition1"], schema), singleCondition(field, entry["condition2"], schema)]);
  }
  return singleCondition(field, entry, schema);
}

function columnEntry(field: string, entry: Obj, schema: GridSchema): Node | undefined {
  if (requiredString(entry, "filterType", field) !== "multi") return conditionOrCombined(field, entry, schema);
  const models = entry["filterModels"];
  if (!Array.isArray(models)) throw malformed(`Column '${field}': 'multi' filterType requires a 'filterModels' array.`);
  const nodes: Node[] = [];
  for (const model of models as unknown[]) {
    if (model === null) continue;
    if (!isRecord(model)) throw malformed(`Column '${field}': a 'multi' filterModels entry must be an object or null.`);
    nodes.push(conditionOrCombined(field, model, schema));
  }
  return nodes.length === 0 ? undefined : combine(nodes, true, field);
}

/** The AG Grid `filterModel` as a filter tree: one node per column, ANDed in the order of the model. */
export function parseFilterModel(root: Obj, schema: GridSchema): Node | undefined {
  const model = root["filterModel"];
  if (model === undefined || model === null) return undefined;
  if (!isRecord(model)) throw malformed("'filterModel' must be a JSON object or null.");
  const nodes: Node[] = [];
  for (const [field, entry] of Object.entries(model)) {
    if (!isRecord(entry)) throw malformed(`filterModel['${field}'] must be a JSON object.`);
    const node = columnEntry(field, entry, schema);
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
