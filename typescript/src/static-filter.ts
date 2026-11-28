import { readFilterNode } from "./agrid/filter-node.js";
import type { FilterNodeIr } from "./ir.js";
import type { GridSchema } from "./schema.js";

/** SC-5: the schema's static filter, ANDed with the request's filter after the request's own stages. A request cannot remove it. */
export function injectStaticFilter(filter: FilterNodeIr | undefined, schema: GridSchema): FilterNodeIr | undefined {
  if (schema.staticFilter === undefined || schema.staticFilter === null) return filter;
  const fixed = readFilterNode(schema.staticFilter);
  return filter === undefined ? fixed : { type: "and", nodes: [filter, fixed] };
}
