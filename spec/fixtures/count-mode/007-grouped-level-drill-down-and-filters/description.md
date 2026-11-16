# 007-grouped-level-drill-down-and-filters

Count mode (CNT-1..CNT-8): grouped level under group keys, with row filters and an aggregate left out (CNT-5).

Request and schema are those of `group-aggregation/023-grouped-drill-down-with-active-row-filter` with `requestContext.compileMode: "count"`; the expected artifacts are that fixture's page artifacts without the `ORDER BY`, the row window and the two paging params (hand-checked, see the category README).
