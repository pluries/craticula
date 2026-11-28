/**
 * The IR (`spec/ir.schema.json`), the vendor-neutral request every compiler reads. Only the parts the parser produces so far are typed
 * here; grouping and aggregations arrive with a later slice of feature 013.
 */
export interface SortItemIr {
  readonly field: string;
  readonly direction: "asc" | "desc";
  readonly nullsPosition: "first" | "last";
}

export type PageIr = { readonly mode: "range"; readonly startRow: number; readonly endRow: number } | { readonly mode: "none" };

export type TypedValueIr =
  | { readonly type: "string"; readonly value: string }
  | { readonly type: "int64" | "decimal"; readonly value: string | number }
  | { readonly type: "double"; readonly value: number }
  | { readonly type: "boolean"; readonly value: boolean }
  | { readonly type: "date"; readonly value: string }
  | { readonly type: "datetime"; readonly value: string; readonly zone: string }
  | { readonly type: "null" };

export interface ComparisonIr {
  readonly type: "comparison";
  readonly field: string;
  readonly op: string;
  readonly value?: TypedValueIr;
  readonly values?: readonly TypedValueIr[];
  readonly from?: TypedValueIr;
  readonly to?: TypedValueIr;
  readonly fromInclusive?: boolean;
  readonly toInclusive?: boolean;
}

export type FilterNodeIr =
  | { readonly type: "and" | "or"; readonly nodes: readonly FilterNodeIr[] }
  | { readonly type: "not"; readonly node: FilterNodeIr }
  | ComparisonIr;

export interface Ir {
  readonly filter?: FilterNodeIr;
  readonly sort?: readonly SortItemIr[];
  readonly page: PageIr;
}
