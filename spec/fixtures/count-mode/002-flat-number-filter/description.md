# 002-flat-number-filter

Count mode (CNT-1..CNT-8): flat: number filter (CNT-4).

Request and schema are those of `dialect-parity/008-parity-sem2-neq-includes-nulls` with `requestContext.compileMode: "count"`; the expected artifacts are that fixture's page artifacts without the `ORDER BY`, the row window and the two paging params (hand-checked, see the category README).
