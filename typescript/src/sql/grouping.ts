import { CompileError } from "../errors.js";
import type { AggregationIr, FilterNodeIr, GroupSpecIr } from "../ir.js";

export interface GroupingPlan {
  /** The group column of the level on show; absent at the leaf, where every group column is consumed. */
  readonly groupColumn?: string;
  readonly drillDown?: FilterNodeIr;
  readonly aggregations: readonly AggregationIr[];
}

/** AGG-2: the name an aggregate is projected under. */
export function outputName(aggregation: AggregationIr): string {
  return aggregation.alias ?? `${aggregation.field}_${aggregation.func}`;
}

/** AGG-2's ColumnVO.id: what a sort key names when it means this aggregate. */
export function columnId(aggregation: AggregationIr): string {
  return aggregation.alias ?? aggregation.field;
}

/** GRP-5: each consumed group key as an equality condition on its group column, ANDed. */
export function drillDownOf(group: GroupSpecIr | undefined): FilterNodeIr | undefined {
  const predicates: FilterNodeIr[] = (group?.groupKeys ?? []).map((value, i) => ({ type: "comparison", field: group!.groupCols[i]!, op: "eq", value }));
  if (predicates.length === 0) return undefined;
  return predicates.length === 1 ? predicates[0] : { type: "and", nodes: predicates };
}

/** GRP-1 to GRP-3: the level on show, its drill-down and its aggregates. Undefined when the request is not grouped. */
export function resolveGrouping(group: GroupSpecIr | undefined, aggregations: readonly AggregationIr[] | undefined): GroupingPlan | undefined {
  if (group === undefined) return undefined;
  const groupColumn = group.groupKeys.length < group.groupCols.length ? group.groupCols[group.groupKeys.length] : undefined;
  const resolved = aggregations ?? [];
  if (groupColumn !== undefined) {
    const colliding = resolved.map((aggregation, i) => (outputName(aggregation) === groupColumn ? i : -1)).filter((i) => i >= 0);
    if (colliding.length > 0) {
      throw new CompileError(
        "InvalidRequest",
        `aggregations[${colliding.join(", ")}] resolve to the output name '${groupColumn}', which collides with this grouped level's own group column (GRP-3 projects it under that name). Give the valueCol an id (alias) that differs from it.`,
      );
    }
  }
  const drillDown = drillDownOf(group);
  return { ...(groupColumn === undefined ? {} : { groupColumn }), ...(drillDown === undefined ? {} : { drillDown }), aggregations: resolved };
}
