# 008-drill-down-leaf

Count mode (CNT-1..CNT-8): drill-down leaf: a flat count under the group keys (CNT-4).

Request and schema are those of `group-aggregation/005-leaf-query-two-group-cols-fully-consumed` with `requestContext.compileMode: "count"`; the expected artifacts are that fixture's page artifacts without the `ORDER BY`, the row window and the two paging params (hand-checked, see the category README).
