# `query-time-limit/`: the optional server-side time limit (TL-1..TL-5)

Spec: the addendum "query time limit" in `../../semantics.md`. The harness sets the limit from `requestContext.maxQueryTimeMs`
(`../../conformance-runner.md` §3); a production parser never reads it.

| Case | Proves |
|---|---|
| `001-rows-limit-set` | a row request: Mongo wrapper with `maxTimeMS`, Search `timeout`, PostgreSQL unchanged (TL-1, TL-2) |
| `002-set-values-limit-set` | the same two members on a set-values request |
| `003-export-no-limit` | an export artifact is unchanged even with a limit set (TL-3) |
| `004-no-limit` | control: no limit, today's artifact (TL-3) |
| `005-limit-wrapper-with-collation` | the limit joins a `{ pipeline, collation }` wrapper, in the order `pipeline`, `collation`, `maxTimeMS` (TL-1) |
| `006-limit-in-request` | adversarial: a top-level `maxQueryTimeMs` on the request is ignored; the artifact equals 004's (TL-4) |

The row count is compiled by the execution adapters at run time and the harness has no entry point for it: it is proved in
the adapter tests, not here.
