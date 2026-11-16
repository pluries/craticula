# count-mode

Fixtures for count mode (`semantics.md`, CNT-1..CNT-8). Each case is its own folder; `requestContext.compileMode: "count"` in its
`agGridRequest.json` selects the count entry point (`conformance-runner.md` §3). The expected files use the usual
`expected/<backend>.artifact.json` names, so the runner and the artifact schemas do not change.

| Case | Source fixture | Proves |
|---|---|---|
| `001-flat-no-filter-sort-ignored` | `dialect-parity/009` | CNT-2, CNT-3: no filter, the sort model is ignored |
| `002-flat-number-filter` | `dialect-parity/008` | CNT-4: number filter |
| `003-flat-set-filter` | `dialect-parity/016` | CNT-4: set filter |
| `004-flat-text-filter` | `dialect-parity/007` | CNT-4: text filter |
| `005-window-above-page-limit-ignored` | `dialect-parity/010`, `endRow` 100000 | CNT-3: a window above the page limit is ignored, not refused |
| `006-grouped-level` | `group-aggregation/001` | CNT-5: counts the groups |
| `007-grouped-level-filter-aggregate-sort` | `group-aggregation/020` | CNT-5: filter, aggregate and sort left out |
| `008-drill-down-leaf` | `group-aggregation/005` | CNT-4: the leaf under its group keys |
| `009-rejection-unknown-column` | `adversarial/001` | CNT-1: refused as the page is |

**How the expected files were made.** Each is the source fixture's page artifact for the same dialect with the `ORDER BY`, the
row window and the two paging parameters removed; a grouped level is wrapped as CNT-5 states. They were derived from the page
artifacts, which are pinned independently, and not from the count implementation. The five SQL dialects are present;
`mongo` and `search` expected files are added with their builders. No dataset files: the execution-tier proof that the count equals
the page total (SC-2) uses the datasets of the source fixtures.
