# 005-window-above-page-limit-ignored

Count mode (CNT-1..CNT-8): flat: sort and an endRow above the maximum page size; the window is ignored and not rejected (CNT-3).

Request and schema are those of `dialect-parity/010-parity-sem3-null-order-desc` with `requestContext.compileMode: "count"`; the expected artifacts are that fixture's page artifacts without the `ORDER BY`, the row window and the two paging params (hand-checked, see the category README).
