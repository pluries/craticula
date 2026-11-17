# 004-flat-text-filter

Count mode (CNT-1..CNT-8): flat: text contains filter (CNT-4).

Request and schema are those of `dialect-parity/007-parity-sem1-case-insensitive-contains` with `requestContext.compileMode: "count"`; the expected artifacts are that fixture's page artifacts without the `ORDER BY`, the row window and the two paging params (hand-checked, see the category README).
