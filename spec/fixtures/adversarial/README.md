# `adversarial/` — SEC-6 clean-rejection fixtures

Per `spec/fixtures/README.md`'s "Adversarial fixtures are a distinct shape" section: every case
in this category produces `expected/rejection.json` (validating against
`spec/fixtures/schemas/rejection.schema.json`) **instead of** any `expected/<backend>.artifact.json`
— no backend ever sees a compilable IR, because validation rejects the request before compilation
is reached.

Each fixture's `schema.json` is an ordinary, valid `GridSchema` (validates against
`spec/grid-schema.schema.json`); the adversarial part always lives in `agGridRequest.json`, never
in the schema. Most fixtures share the same base `GridSchema` (fields `id` int64, `name` string,
`amount` decimal, `quantity` int64, `price` double, `active` boolean, `createdDate` date,
`createdAt` datetime, `stableKey: "id"`, `mode: "strict"`) so the only thing that varies between
cases is the request shape.

**`source` (added #1638) is a convention here, not a derivation.** Every other category's `source`
was read back out of that fixture's own expected artifact's `FROM` clause — the authoritative
per-fixture answer. These 28 fixtures have no artifact to read (that is the point of the category),
so all 28 carry `source: "items"`, chosen to match their shared generic goods-shaped field set
(`name`/`price`/`quantity`/`amount`/`active`). Nothing in this category depends on the value: no
case here ever reaches a compiler, so no `FROM` clause is ever emitted. Keep new cases on the same
value unless one is deliberately testing something about `source` itself.

`rejectedAt` values follow the pinned validation order from
`docs/architecture/c4-components-core-ir.md`: **allowlist → resourceLimits → typeCoercion →
requestParsing**. Note `requestParsing` sits conceptually *before* allowlist in actual execution
(a request that doesn't even parse into a candidate IR shape never reaches the allowlist check) —
it is listed last among the enum's four values only because it is the catch-all for
malformed-wire-shape cases that never reach IR validation at all (see
`rejection.schema.json`'s own description of the field).

## Scoping note (read this before adding more cases)

"Injection attempts" here means **structural** injection via the wire payload shape itself — a
filter value sent as an object/array trying to smuggle extra operators, a colId that isn't even a
well-formed identifier, a JSON key collision. It does **not** mean "a normal string filter value
containing SQL metacharacters" (e.g. `filter: "'; DROP TABLE users; --"` sent as an ordinary
string to a text `equals` condition) — that is safely handled by parameterization and is not a
rejection case; such fixtures belong to the `operators/`/`dialect-parity/` categories' normal
safe-parameterization behavior, not here.

## Cases

| # | Slug | rejectedAt | reason | Requirement ids |
|---|---|---|---|---|
| 001 | `001-unknown-colid-filter-model` | `allowlist` | `unknown-field` | SC-1, SEC-1 |
| 002 | `002-unknown-colid-sort-model` | `allowlist` | `unknown-field` | SC-1, SEC-1, AR-9 |
| 003 | `003-unknown-colid-row-group` | `allowlist` | `unknown-field` | SC-1, SEC-1, AR-8 |
| 004 | `004-custom-filter-depth-9-one-beyond-boundary` | `resourceLimits` | `max-depth-exceeded` | SEC-3, AR-5, OQ-11 |
| 005 | `005-custom-filter-depth-20-deep-bomb` | `resourceLimits` | `max-depth-exceeded` | SEC-3, SEC-6, AR-5, OQ-11 |
| 006 | `006-and-node-65-leaves-single-node` | `resourceLimits` | `max-leaves-exceeded` | SEC-3, AR-5, OQ-11 |
| 007 | `007-nested-tree-wide-70-leaves-budget` | `resourceLimits` | `max-leaves-exceeded` | SEC-3, AR-5 |
| 008 | `008-set-filter-1001-values-one-beyond-boundary` | `resourceLimits` | `max-in-values-exceeded` | SEC-3, AR-6 |
| 009 | `009-custom-not-in-5000-values-deep-bomb` | `resourceLimits` | `max-in-values-exceeded` | SEC-3, AR-6, SEC-6, OQ-11 |
| 010 | `010-page-size-1001-rows-one-beyond-boundary` | `resourceLimits` | `max-page-size-exceeded` | SEC-3, AG-3 |
| 011 | `011-page-size-1000000-rows-deep-bomb` | `resourceLimits` | `max-page-size-exceeded` | SEC-3, AG-3, SEC-6 |
| 012 | `012-non-numeric-string-int64-field` | `typeCoercion` | `uncoercible-value` | SEM-5, AR-7 |
| 013 | `013-malformed-date-string-date-field` | `typeCoercion` | `uncoercible-value` | SEM-5, SEM-4, AR-7 |
| 014 | `014-boolean-like-value-int64-field` | `typeCoercion` | `uncoercible-value` | SEM-5, AR-7, AG-1 |
| 015 | `015-malformed-decimal-string-decimal-field` | `typeCoercion` | `uncoercible-value` | SEM-5, AR-7 |
| 016 | `016-unknown-operator-regex` | `requestParsing` | `unknown-operator` | AR-6, SEC-5, SEC-6 |
| 017 | `017-unknown-operator-typo-greaterthanorequalto` | `requestParsing` | `unknown-operator` | AR-6, SEC-6 |
| 018 | `018-filter-value-object-injection` | `requestParsing` | `malformed-request` | SEC-2, SEC-6, AR-7 |
| 019 | `019-colid-suspicious-characters` | `allowlist` | `unknown-field` | SC-1, SEC-1, SEC-6 |
| 020 | `020-filter-value-array-injection` | `requestParsing` | `malformed-request` | SEC-2, SEC-6, AR-6 |
| 021 | `021-duplicate-json-keys-deserializer-fuzz` | `requestParsing` | `malformed-request` | SEC-6, SEC-2 |
| 022 | `022-null-where-object-required-deserializer-fuzz` | `requestParsing` | `malformed-request` | SEC-6, AR-8 |
| 023 | `023-duplicate-aggregation-output-names` | `requestParsing` | `duplicate-output-name` | AGG-2, GRP-4, SEC-2, SEC-6, AR-8 |
| 024 | `024-filterable-false-in-filter-model` | `allowlist` | `field-not-filterable` | SC-1, SC-2, SEC-1 |
| 025 | `025-filterable-false-as-set-values-target` | `allowlist` | `field-not-filterable` | SC-1, SC-2, SEC-1, GRP-6 |
| 026 | `026-filterable-false-as-drilldown-key` | `allowlist` | `field-not-filterable` | SC-1, SC-2, SEC-1, GRP-1, GRP-2, GRP-5 |
| 027 | `027-zero-width-page-window` | `requestParsing` | `malformed-request` | AG-3, SEC-3, SEC-6 |
| 028 | `028-unknown-colid-sort-model-after-stable-key` | `allowlist` | `unknown-field` | SC-1, SEC-1, SEC-6, AR-9, SEM-6 |

## Breakdown by validation stage

- `allowlist`: 8 (001–003, 019, 024–026, 028)
- `resourceLimits`: 8 (004–011)
- `typeCoercion`: 4 (012–015)
- `requestParsing`: 8 (016–018, 020–023, 027)

**Total: 28 fixtures.**

## Notes on construction

- **Depth/leaf/in-values bombs (004–009)** mostly use the `customFilters` wire extension
  (OQ-11 — see `spec/fixtures/README.md`'s customFilters wire-shape note), because AG Grid's own
  `filterModel` is structurally shallow (a flat per-column map, at most two conditions per
  column) and cannot express a genuine depth/leaf bomb on its own. The exception is 008, which
  uses AG Grid's native `set` filter (mapped straight to an `in` IR comparison) since that alone
  is sufficient to exceed the max-in-values limit.
- **004/010 vs. 005/011/009** deliberately pair a "one beyond the boundary" case with a "deep
  bomb, far beyond the boundary" case for the same limit, per the task's request to pin the
  precise off-by-one separately from the general resource-exhaustion framing SEC-6 names.
- **007** specifically proves the max-leaves budget is tree-wide, not a per-node arity bound (35
  leaves in each of two `and` branches, 70 total) — see `spec/ir.schema.json`'s `andNode`/`orNode`
  descriptions for why no `maxItems` is placed on those arrays at the schema level.
- **021** is hand-authored as literal JSON text (not emitted by a serializer that would silently
  deduplicate the repeated key) specifically so the duplicate `"filter"` key survives into the
  fixture file.
- **019** deliberately shapes its colId to *look* like a SQL-injection payload
  (`"amount'); DROP TABLE users; --"`), but no spec document defines a colId shape check distinct
  from allowlist membership — the string is simply absent from `GridSchema.fields`, so this case
  is caught at the same `allowlist` stage as 001–003, not `requestParsing`. Its adversarial value
  is exactly that: an attacker gains nothing from the shape, because the allowlist rejects it
  before the shape could ever matter.
- **023** is the first case whose `reason` was added to `rejection.schema.json`'s enum by a later
  story (`duplicate-output-name`, #1886). It is also the first whose defect is invisible to every
  engine: `018`/`020` send a shape no parser can read, while this one compiles to a statement all
  five SQL dialects, MongoDB and Elasticsearch accept — and each of them then drops one of the two
  aggregates silently. Its `schema.json` is `003`'s with one edit, `amount` gaining `aggregatable`,
  so the request's only defect is the duplicated `ColumnVO.id` and not an SC-2 capability the field
  was never granted.
- **024/025** (#1872) added `field-not-filterable` to `rejection.schema.json`'s enum, deliberately
  distinct from `unknown-field`: both pairs' colId (`costBasis`) IS present in `GridSchema.fields` —
  the base schema plus one new field declared `filterable: false`, everything else identical to
  001–003's shared shape — so the rejection is a capability-flag failure (SC-2), not an allowlist
  membership failure (SC-1). `024` puts it in an ordinary `filterModel` condition (Strict rejects it,
  though — unlike 001–003/019 — Lenient would silently strip it instead, since it is still only a
  *condition*); `025` puts the same colId in `setValuesRequest.colId`, which no `GridSchemaMode` may
  drop, mirroring `003`'s own no-Lenient-carve-out for `rowGroupCols`.
- **026** (#1907, found by #1872's own code review) is a third `field-not-filterable` surface: its
  colId (`region`) is declared `groupable: true, filterable: false` — bucketing is allowed, but the
  request never sends a `filterModel` condition at all. Instead `rowGroupCols: [region]` +
  `groupKeys: ["West"]` drills into one specific value, which `DrillDownFilter.Synthesize` turns into
  a literal `region = 'West'` predicate — functionally a filter condition over a different wire
  channel. No `GridSchemaMode` may drop it, for the same reason `003`'s `rowGroupCols` cannot: only
  the CONSUMED prefix of `GroupCols` (i.e. columns with a corresponding `groupKeys` entry) is checked
  — a `GroupCols` entry with no key chosen yet is untouched, since plain bucketing across every value
  is exactly what `groupable: true` alone already permits.

## Execution-equality oracle (T-1b)

Out of scope: every case here is a rejection (`expected/rejection.json`, no compiled query), so none carries
`dataset.json` or `expectedRows.json` (XEQ-1).
