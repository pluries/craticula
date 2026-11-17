# 001-flat-no-filter-sort-ignored

Count mode (CNT-1..CNT-8): flat: no filter; the sort model is ignored (CNT-2, CNT-3).

Request and schema are those of `dialect-parity/009-parity-sem3-null-order-asc` with `requestContext.compileMode: "count"`; the expected artifacts are that fixture's page artifacts without the `ORDER BY`, the row window and the two paging params (hand-checked, see the category README).
