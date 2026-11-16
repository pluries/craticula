# 006-grouped-level

Count mode (CNT-1..CNT-8): grouped level: counts the groups (CNT-5).

Request and schema are those of `group-aggregation/001-group-top-level-no-keys-consumed` with `requestContext.compileMode: "count"`; the expected artifacts are that fixture's page artifacts without the `ORDER BY`, the row window and the two paging params (hand-checked, see the category README).
