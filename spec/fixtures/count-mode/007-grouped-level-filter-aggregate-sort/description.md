# 007-grouped-level-filter-aggregate-sort

Count mode (CNT-1..CNT-8): grouped level with a filter, an aggregate and a sort (CNT-5).

Request and schema are those of `group-aggregation/020-grouped-query-with-filter-and-sort` with `requestContext.compileMode: "count"`; the expected artifacts are that fixture's page artifacts without the `ORDER BY`, the row window and the two paging params (hand-checked, see the category README).
