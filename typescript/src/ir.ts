/**
 * The IR (`spec/ir.schema.json`), the vendor-neutral request every compiler reads. Only the parts the parser produces so far are typed
 * here; the filter tree, grouping and aggregations arrive with the next slice of feature 013.
 */
export interface SortItemIr {
  readonly field: string;
  readonly direction: "asc" | "desc";
  readonly nullsPosition: "first" | "last";
}

export type PageIr = { readonly mode: "range"; readonly startRow: number; readonly endRow: number } | { readonly mode: "none" };

export interface Ir {
  readonly sort?: readonly SortItemIr[];
  readonly page: PageIr;
}
