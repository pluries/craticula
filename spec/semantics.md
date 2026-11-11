# `spec/semantics.md` — Semantics specification (SEM-1..SEM-8)

Normative per **AR-1** (the maintainers' private TRD, §7): this document, not any single
compiler, is where these behaviors are decided (SEM-1..SEM-7 from the TRD, SEM-8 added in #2455). A backend compiler that disagrees with a rule
below has a bug, not an alternative opinion. Every rule here is the target of conformance fixtures
(`spec/fixtures/`, TRD T-1) authored in a later work item (#1630) — this document states the rule
and gives **illustrative** examples; it does not itself constitute the enforceable test suite.

Each section follows the same shape: the rule, why it exists (the naive alternative it rules out —
see TRD §1's problem statement for the catalogue of ways this translation is usually done badly),
one worked example per backend family showing the *same logical outcome* reached through different
backend-native mechanisms, an explicit "must NOT" list, and cross-links to the IR shapes in
[`ir.schema.json`](./ir.schema.json) that the rule constrains.

All SQL/Mongo/OpenSearch examples in the SEM-1..SEM-7 sections below are illustrative snippets to
convey intent, not the literal compiler output for any one dialect. The literal rendering — identifier
quoting, parenthesisation, which operator carries a negation, how a set is parameterized — is pinned
separately in **three addenda** at the end of this document, all of which *are* normative and *are*
byte-for-byte what the `spec/fixtures/` artifacts contain: **"Addendum — canonical SQL rendering"**
(SQL-0..SQL-8) for the Postgres reference arm and its four sibling dialects, **"Addendum —
canonical MongoDB rendering"** (MDB-1..MDB-12) for the `mongo.artifact.json` arm, and **"Addendum —
canonical OpenSearch/Elasticsearch rendering"** (OSE-0..OSE-14) for the `search.artifact.json` arm. A
Mongo or OpenSearch snippet below is illustrative in exactly the way a SQL one is; where the two
disagree — SEM-1's implicit `{name: "Smith"}` against MDB-1's explicit `$eq`, or its bare
`{"term": {"name.keyword": …}}` shorthand against OSE-1's — the addendum is what a compiler follows.

---

## SEM-1. Case sensitivity

**Rule.** Every operator in `$defs/binaryOperator` (`eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `contains`,
`notContains`, `startsWith`, `endsWith`) and `$defs/setOperator` (`in`, `notIn`), when applied to a
`stringValue`, is **case-insensitive by default** — including the four ordering comparisons
(`gt`/`gte`/`lt`/`lte`), which fold case in their lexicographic comparison exactly as the
equality/substring operators fold case in theirs: case sensitivity is a per-field property (SC-3),
not a per-operator one, and — the scope of "not a per-operator one" pinned explicitly here — **not
a per-context one either**: the identical mechanism governs an `eq`/`in` comparison and an
`ORDER BY`/`$sort`/`sort` on that field. Per-field, a schema author may opt a field into
case-sensitive comparison instead. Whichever mode is active, the compiler MUST reach it through an
index-friendly, backend-native mechanism — and, critically, **the same class of mechanism (collation
vs. pattern-match) MUST be used consistently across every context on that field**, never one
mechanism for filtering and a different one for sorting.

**The one carve-out, and it is not a per-context exception smuggled back in: grouping (GRP-2).**
This rule governs how a field's *values* are compared. It does **not** govern *bucket identity*, a
question it never asks and which BM-2's protocol answers separately: inside a grouping request the
`GROUP BY` key, the `groupSpec.groupKeys` drill-down match and the `ORDER BY` are all **exact**,
because they have to agree with one another or a child level stops summing to its parent's
aggregate — and because collating a `GROUP BY` key produces a statement the engines reject outright.
That is a per-*statement* rule, not a per-construct one, so it cannot reintroduce the mix this
section forbids; a user's own filter predicate inside that same grouped request is still governed
here, in full. **BM-3's distinct-values query answers to the same carve-out** (GRP-6): its
`SELECT DISTINCT` column and that column's `ORDER BY` are exact, because a distinct set is a set of
buckets and its entries are handed back to the grid to be matched exactly — while the set filter's
own search prefix over that very same column is a filter, and so is still governed here. See the
grouping addendum (GRP-2, GRP-6) for the whole argument, the accepted divergence on engines whose
default collation folds case, and why an earlier draft of this section — which read the drill-down
match as an ordinary comparison — was wrong on this one point.

**Two distinct mechanisms, not one — pick per shape, not per whim.** This document previously left
it ambiguous whether Postgres case-insensitive *equality* (`eq`/`in`/`notIn`, and by extension sort)
should reuse `ILIKE` (the *substring* mechanism, §SEM-7's territory) or use a
collation (the *exact-comparison* mechanism, as SQL Server/MySQL already do below). Reusing `ILIKE`
for exact match turns out to be a trap: `ILIKE`'s pattern-language treats a literal `%`/`_` in the
*value* as a wildcard, so an exact-match operator silently becomes a widened pattern match unless
every value is escaped — and MongoDB's `$eq`/`$in` set-membership forms have no `ESCAPE`-clause
equivalent at all, making that escaping structurally inapplicable to some backends' idiomatic forms.
The rule, pinned: **`eq`/`neq`/`gt`/`gte`/`lt`/`lte`/`in`/`notIn`, plus sorting on
a case-insensitive field, use a case-insensitive COLLATION** (an equality/ordering mechanism, no
pattern language, nothing to escape). **`contains`/`notContains`/`startsWith`/`endsWith` use `ILIKE`
or the backend's substring mechanism** (SEM-7 covers `contains` specifically) — a pattern-match
mechanism is appropriate there because the operator itself is a pattern match; the value's own `%`/
`_` are escaped there because the position is a pattern, not because the CI requirement demands it.

> **This paragraph says *which mechanism* when one is used at all; it does not say one always is.**
> An earlier draft ended both sentences above with "plus sort **and group-key matching**", which
> #1640 made wrong and #1640's own review found still standing here — in the very sentence this
> section labels *the rule, pinned* — after the carve-out had been written into the intro and the
> Must-NOTs. A `groupSpec.groupKeys` drill-down match, a `GROUP BY` key and a **grouped level's**
> `ORDER BY` use **no** case-folding mechanism at all (GRP-2) — as do BM-3's `SELECT DISTINCT` key
> and its `ORDER BY` (GRP-6). A port implementing SEM-1 from the pinned sentence alone would emit the
> collation and fail `group-aggregation/002` (and `016`).

**Rationale.** AG Grid's in-memory (client-side) row model filters text case-insensitively by
default. If the SSRM compiler defaults to case-sensitive comparison instead, the exact same filter
typed into the exact same grid produces different rows depending on which row model happens to be
active — a correctness regression that looks like a backend bug but is really a default mismatch.
The "obvious" fix — wrap the column in `lower()`/`LOWER()` on both sides — reintroduces a different
failure: on most SQL engines a bare function wrapper on the indexed column makes the predicate
non-sargable, silently turning an indexed lookup into a full scan the moment a table grows past a
trivial size. This is exactly the class of "broken null/case semantics" bug the TRD's problem
statement (§1) calls out as endemic to hand-rolled OData/dynamic-LINQ translations. The rule exists
so every dialect gets case-insensitivity *and* keeps its index.

**Worked example, exact-match family** — `eq` on `name`, case-insensitive, matching `"Smith"`:

- **PostgreSQL** — a case-insensitive **collation** on the comparison, never `ILIKE` (see the
  mechanism note above). This project's fixtures and reference docs pin one canonical, explicitly
  host-created ICU collation name for this purpose — `craticula_ci` — rather than each host
  inventing its own name:
  ```sql
  -- One-time host DDL, documented in the per-backend index-guidance page (PERF-4):
  -- CREATE COLLATION craticula_ci (provider = icu, locale = 'und-u-ks-level2', deterministic = false);
  WHERE name COLLATE craticula_ci = :v
  ```
- **SQL Server / MySQL** — unchanged from before: a case-insensitive collation on the column (or
  applied inline), so the engine's own comparison semantics do the folding and a plain B-tree index
  remains usable:
  ```sql
  -- SQL Server: column declared/queried with a CI collation
  WHERE name COLLATE Latin1_General_CI_AS = @v
  -- MySQL: column already uses a _ci collation (e.g. utf8mb4_0900_ai_ci)
  WHERE name = :v
  ```
- **MongoDB** — a query-level collation with `strength: 2` makes `$eq`/`$in`/`$gt`/`$lt`/`$sort`
  compare case-insensitively (and can still use a supporting index), which is the mechanism this
  document means wherever it says "the collation option for CI" (e.g. TRD §5's Mongo row):
  ```json
  db.items.find(
    { name: "Smith" },
    { collation: { locale: "en", strength: 2 } }
  )
  ```
- **OpenSearch / Elasticsearch** — a term-level query's `case_insensitive` parameter (available on
  `term`, `wildcard`, `prefix`, and `regexp` since 7.10 — **not** `range`; ordering comparisons on
  ES/OpenSearch are covered separately below) against a `keyword` field:
  ```json
  { "term": { "name.keyword": { "value": "Smith", "case_insensitive": true } } }
  ```

**Worked example, substring family** — `contains` on `name`, case-insensitive, matching
`"Bob Smith"` against pattern `"smith"` — this is the pattern-match mechanism, distinct from the
exact-match family above:

- **PostgreSQL** — `ILIKE`, backed by a `pg_trgm` GIN index (PERF-4 index guidance) rather than a
  functional index on `lower(name)`:
  ```sql
  WHERE name ILIKE '%' || :pattern || '%' ESCAPE '\'
  ```
- **MongoDB** — no collation-compatible substring operator exists; `contains` necessarily compiles
  to `$regex` with the `"i"` option, which is *not* index-friendly the way the collation/`pg_trgm`
  forms above are — SEM-7 covers this mechanism (and its escaping requirements) in full.
- **OpenSearch / Elasticsearch** — `wildcard`/`case_insensitive` against the `keyword` sub-field, no
  separate analyzed sub-field or runtime lowercasing required (SEM-7 governs the substring mechanics
  themselves):
  ```json
  { "wildcard": { "name.keyword": { "value": "*smith*", "case_insensitive": true } } }
  ```

**Ordering comparisons (`gt`/`gte`/`lt`/`lte`) on OpenSearch/Elasticsearch — the one real gap.**
Unlike `term`/`wildcard`, a `range` query has no `case_insensitive` parameter in the pinned 7.10-era
subset, and there is no query-time equivalent. The compiler targets a schema-declared **normalized
sub-field** (`SC-3`'s `search.normalizedSubField` — a `keyword` sub-field maintained via an
ICU-folding normalizer *at index time*, distinct from the plain `.keyword` exact-match sub-field
`search.keywordSubField` used by `term`/`in`/`notIn` above) instead of the raw field:
```json
// filtering `name > "Smith"` on a case-insensitive field:
{ "range": { "name.normalized": { "gt": "Smith" } } }
```
A field that needs case-insensitive ordering on ES/OpenSearch MUST declare
`search.normalizedSubField`; a field that only needs case-insensitive equality/substring ops does
not need one. This is a genuine index-time cost (SC-3, PERF-4), not a query-time toggle — document it
per field, never assume it exists.

**The compared VALUE is bound as typed — the sub-field is the mechanism, not a licence to fold the
value too.** The snippet above binds `"Smith"`, unchanged, exactly as the collation arms bind it. A
normalizer is applied at search time as well as at index time for a term-level query (which `range`
is), so pre-folding is redundant; worse, it is unknowable — the schema declares the sub-field's
*name* and nothing about what its normalizer does, and an ICU-folding one folds diacritics and width
as well as case, so a compiler lowering `"ÉCOLE"` to `"école"` would miss every document the
normalizer had reduced to `"ecole"`. "Lowercase" is also not one operation across the four language
ports G4 requires to agree. See **OSE-6**, and `spec/fixtures/dialect-parity/015`, whose Search arm
pinned the folded value until #1644 compiled it.

**Must NOT.**
- Must NOT wrap the column/field in a bare `lower()`/`LOWER()`/`toLowerCase` when the dialect offers
  an index-friendly alternative (`ILIKE`, a CI collation, `case_insensitive` query option) — reserve
  the bare wrapper for the rare dialect that truly has nothing better, and document that exception
  per dialect (PERF-4).
- Must NOT default to case-sensitive comparison "because SQL's default collation is case-sensitive
  on this engine" — the IR-level default is case-insensitive regardless of any one engine's own
  default; per-field case sensitivity is an explicit schema opt-in (SC-3), never an accidental
  inheritance from the underlying engine.
- Must NOT apply case-folding inconsistently between the comparison and any related `ORDER BY`/sort
  on the same field — case sensitivity is a per-field property, not a per-operator *or per-context*
  one. (A `groupSpec.groupKeys` drill-down match is the documented carve-out: it is exact, together
  with the `GROUP BY` and `ORDER BY` of the same statement — GRP-2, not this rule. So is BM-3's
  `SELECT DISTINCT` key with its own `ORDER BY` — GRP-6, and note that a set filter's search prefix
  over that same column IS governed here, which is why one such statement legitimately spells two
  mechanisms.)
- Must NOT use `ILIKE`/pattern-match as the mechanism for `eq`/`neq`/`in`/`notIn`/ordering/sort —
  that mechanism is a collation. Reserve `ILIKE`/pattern-match for
  `contains`/`notContains`/`startsWith`/`endsWith`, where the operator itself is a pattern match.
- Must NOT assume an ES/OpenSearch `range` query can be made case-insensitive at query time — it
  cannot in the pinned 7.10-era subset; case-insensitive ordering requires a schema-declared
  `search.normalizedSubField`, index-time cost included.

**Cross-links.** `$defs/binaryOperator`, `$defs/setOperator`, `$defs/stringValue`.

---

## SEM-2. Null handling

**Rule.** The unary operators `blank`/`notBlank` (`$defs/unaryOperator`) resolve as: `blank` ⇔
`IS NULL OR = ''` for text fields, `IS NULL` for every other type; `notBlank` is `blank`'s exact
Boolean negation (never a separately-derived condition that could disagree with it at the edges).
*(The text arm is per-engine as well as per-type: on a backend whose empty string **is** NULL —
Oracle among the SQL dialects — it collapses to `IS NULL`, and emitting the `= ''` disjunct there
makes `notBlank` match nothing at all. The negation rule above is unaffected. See **SQL-7** in the
canonical-SQL-rendering addendum for the truth table and the reason it is a correctness rule.)*
Negative binary/set operators — `neq`, `notContains`, `notIn` — MUST include NULL-valued rows in
their match set. A negative comparison compiles as, e.g., `col <> :v OR col IS NULL`, never a bare
`col <> :v`. **The same null-inclusive rule applies to a tree-level `$defs/notNode` wrapping any
child** (`Not(Comparison(...))`, `Not(And(...))`, `Not(Or(...))`, arbitrarily nested) — not just the
negative *operators* above. AG Grid's client-side row model has no tree-level NOT construct to take
as a reference point, but its own rationale extends cleanly: a NOT that excludes a NULL/missing row
just because SQL's three-valued logic happens to do so is the identical bug this rule exists to
prevent, one syntax level up. Concretely, `Not(Comparison(field, contains, X))` on SQL compiles as
`(NOT (col ILIKE '%'||:v||'%') OR col IS NULL)` — the `OR col IS NULL` is mandatory on the *outside*
of the `NOT`, exactly mirroring `neq`'s own compiled shape — and **the same fan-out is
emitted by every backend at every `notNode`, at every nesting depth, whatever the child is**: one
"this field is null/missing" disjunct per distinct field referenced in the negated subtree, in
first-appearance order, outside the negation. `Not(And(Or(Not(eq status X))))` therefore carries the
disjunct at *both* `not` nodes. Mongo's `$nor` and ES's `must_not` are *not* a substitute: they
include a null document only when the child does not match it, and a child such as `neq`, `blank`
or an inner `not`, or an `or` whose other field matches, does match one — the null row would then
be dropped by exactly the bug this rule exists to prevent. The disjunct is `{field: null}` on
MongoDB and `must_not: exists` on the raw field on OpenSearch/Elasticsearch (MDB-2, OSE-2).

**Rationale.** AG Grid's in-memory row model filters with plain JavaScript equality, where a missing
or `null` cell value is simply "not equal" to any concrete filter value — so `neq` in the client-side
row model always includes rows with a null/missing value for that column. SQL's three-valued logic
does the opposite by default: `NULL <> 'Alice'` evaluates to `NULL` (neither true nor false), so a
bare `WHERE name <> 'Alice'` **silently excludes** every NULL row from the result — the naive,
"obviously correct" translation is actually the wrong answer, and it disagrees with what the same
filter would have shown against the same dataset in the client-side row model. This divergence is
exactly the "broken null semantics" the TRD's problem statement (§1) flags as one of the two most
common ways this translation goes wrong (case sensitivity being the other, SEM-1). Pinning the answer
— NULLs match negative operators — makes every backend agree with each other and with AG Grid's own
non-SSRM behavior.

**Worked example** — `neq: "Alice"` against a `name` field where some rows have `name IS NULL`:

- **SQL** — the explicit `OR IS NULL` is mandatory precisely because bare `<>` drops NULLs (the
  enclosing parentheses are not optional either — see SQL-2 in the canonical-rendering addendum):
  ```sql
  WHERE (name <> :v OR name IS NULL)
  ```
- **MongoDB** — `{ field: { $ne: value } }` already matches documents where the field is null or
  entirely missing (MongoDB's `$ne` treats a missing field as not-equal), so the naive single-clause
  form happens to be correct in the plain query language. The compiler nonetheless emits the
  explicit composed form below, for two reasons: it keeps the compiled shape parallel to the SQL and
  ES forms (useful for the fixture suite comparing structure across backends), and it stays correct
  inside an `$expr`/aggregation-expression context (e.g. when combined with a `$strcasecmp` for
  case-insensitive comparison, SEM-1), where relying on the query-language `$ne`'s implicit
  missing-field handling is not an option because the predicate is no longer a plain query-language
  clause:
  ```json
  { "$or": [ { "name": { "$ne": "Alice" } }, { "name": null } ] }
  ```
- **OpenSearch / Elasticsearch** — a `bool` query composing a negated `term` with an explicit
  "field does not exist" clause via `should`/`must_not`:
  ```json
  {
    "bool": {
      "should": [
        { "bool": { "must_not": { "term": { "name.keyword": "Alice" } } } },
        { "bool": { "must_not": { "exists": { "field": "name" } } } }
      ],
      "minimum_should_match": 1
    }
  }
  ```
  Note that the first `should` clause alone already covers the missing-field case for a `term` query
  (a `must_not` around a query that can't match a missing field is itself true for that document),
  so the second clause is belt-and-suspenders here — kept explicit because that implicit behavior is
  a property of the `term` query type specifically and is not guaranteed to hold for every query type
  a future operator might compile to (e.g. `range`), so the compiler does not lean on it silently.

**Must NOT.**
- SQL: must NOT emit a bare `<>`/`NOT IN (...)` for a negative operator, **or a bare `NOT (...)` for
  a tree-level `notNode`**, without the accompanying `OR col IS NULL` on the outside — three-valued
  logic drops NULLs from a bare comparison or a bare `NOT`, which is the exact bug this rule exists
  to prevent. `NOT (col ILIKE ...)` and `col <> ...` fail identically and need the identical fix.
- MongoDB: must NOT add a defensive `{ field: { $ne: null } }` guard "to be safe" or "for parity with
  SQL" — that guard would *exclude* null-valued documents from a negative comparison, which is the
  opposite of this rule and a Mongo-specific regression introduced by SQL-shaped intuition.
- Must NOT derive `notBlank` independently from `blank` (e.g. hand-writing `IS NOT NULL AND <> ''`
  separately from `blank`'s own `IS NULL OR = ''`) — always negate the compiled `blank` condition so
  the two can never drift apart. This holds unchanged under SQL-7: an engine that collapses the text
  arm negates *its own* collapsed text, so the two operators stay in step there too.
- Must NOT apply the text-specific `= ''` clause of `blank`/`notBlank` to non-text field types — nor
  to a text field on an engine where `''` is NULL (**SQL-7**), where it is not merely redundant but
  turns `notBlank` into a predicate no row satisfies.

**Cross-links.** `$defs/unaryOperator` (`blank`, `notBlank`), `$defs/binaryOperator` (`neq`),
`$defs/setOperator` (`notIn`), `$defs/nullValue`, SQL-2 and **SQL-7** (the compiled shapes of
`blank`/`notBlank`, per construct and per engine).

---

## SEM-3. Null ordering

**Rule.** Every `sortItem` in the IR carries an explicit `nullsPosition` (`first` or `last`),
independent of `sortDirection` — the IR never leaves null placement to be inferred from direction,
and the compiler MUST honor `nullsPosition` literally rather than deriving it itself. Compilers emit
native `NULLS LAST`/`NULLS FIRST` syntax where the dialect supports it, or an equivalent emulation
where it doesn't.

**The adapter's default (pinned).** AG Grid's `sortModel` carries no null-position signal at all —
it is purely `{ colId, sort }`. Since `$defs/sortItem` requires `nullsPosition` on every sort key,
the adapter must produce one on every sort key the grid sends, and it does so with a single, fixed
rule: **`nullsPosition: "last"` on `asc`, `nullsPosition: "first"` on `desc`.** This is the one
direction→position mapping this document pins — not because compilers are allowed to derive it
themselves (they are not; see "must NOT" below), but because the *adapter* has to choose something
deterministic when the wire protocol gives it nothing, and an arbitrary-but-consistent choice here is
what makes G3/G4 achievable: every port's adapter applies the identical mapping, so every port's
compiler receives the identical `nullsPosition` for the identical `sortModel`, and none of them ever
compute it themselves.

**Rationale.** Database engines disagree about where NULLs sort by default: PostgreSQL and Oracle
treat NULL as the "largest" value (NULLS LAST on ASC, NULLS FIRST on DESC, by default), while MySQL
and SQLite treat NULL as the "smallest" value (NULLS FIRST on ASC by default) — and some engines'
defaults are additionally subject to session/locale settings. If a compiler just emits `ORDER BY col
ASC` and trusts the engine's default, the exact same IR produces a different row order depending on
which SQL dialect executes it — a direct violation of G3/G4 (identical semantics across backends and
language ports). Worse, it means results are technically legal-but-unpredictable per the SQL standard
even on a single engine whose defaults change across a major version. Pinning `nullsPosition`
explicitly in the IR, and pinning *what value the adapter writes there* in this document rather than
leaving four ports to invent their own default — removes the ambiguity at the one place (the adapter,
resolving AG Grid's request into IR) that should own the decision, and happens to match the
PostgreSQL/Oracle default exactly (a coincidence of this particular choice, not a requirement that
compilers rely on it — see "must NOT" below).

**Worked example** — sort `amount ASC`, `nullsPosition: "last"`:

- **PostgreSQL / Oracle / SQL:2003-compliant dialects** — native syntax:
  ```sql
  ORDER BY amount ASC NULLS LAST
  ```
- **MySQL** — no native `NULLS LAST` syntax; emulated with an `ISNULL(col)` prefix key (returns `1`
  for NULL, `0` otherwise), so ordering ascending by that key pushes NULLs after every non-null row,
  with the real column kept as the secondary key so non-null rows still sort correctly among
  themselves:
  ```sql
  ORDER BY ISNULL(amount) ASC, amount ASC
  ```
- **MongoDB** — no native "nulls last" `$sort` behavior (BSON has its own type-ordering rules where
  null sorts before numbers); emulated with a synthetic null-bucket field added upstream in the
  pipeline, then sorted on the bucket first — and **removed afterward**, since the bucket is a
  compiler-internal emulation detail, not part of the row shape the grid should ever see:
  ```json
  [
    { "$addFields": { "__amountNullBucket": { "$cond": [{ "$eq": ["$amount", null] }, 1, 0] } } },
    { "$sort": { "__amountNullBucket": 1, "amount": 1 } },
    { "$unset": "__amountNullBucket" }
  ]
  ```
  The `$unset` MUST appear after every `$sort` stage that used a bucket, before the pipeline's final
  `$skip`/`$limit`/`$group` — a result row carrying `__amountNullBucket` alongside the real fields is
  a shape divergence from the Postgres/Search results for the identical IR, on top of leaking an
  implementation detail. If multiple sort keys each need a bucket, unset all of them in one stage
  (`{ "$unset": ["__amountNullBucket", "__lastNameNullBucket"] }`).
- **OpenSearch / Elasticsearch** — the sort clause's native `missing` parameter:
  ```json
  { "sort": [ { "amount": { "order": "asc", "missing": "_last" } } ] }
  ```

**Must NOT.**
- Must NOT rely on a dialect's implicit/default null ordering, even when it happens to match the
  desired output today — defaults vary across engines, across engine versions, and (for some
  engines) across session/locale configuration.
- Must NOT derive `nullsPosition` from `sortDirection` inside the **compiler** (e.g. hardcoding "ASC
  always means nulls last") — even though that mapping happens to be this document's own pinned
  adapter default (above), the compiler must still read the IR's `nullsPosition` literally rather
  than re-deriving it; the pinned mapping is the *adapter's* rule for producing the value, not the
  compiler's license to skip reading it. The IR already carries `nullsPosition` explicitly and
  independently for exactly this reason; a compiler that re-derives it is reintroducing the ambiguity
  the schema
  was designed to remove.
- When emulating with a prefix-key trick (MySQL `ISNULL`, the Mongo synthetic bucket), must NOT drop
  the original field as the secondary sort key — the emulation key only resolves null-vs-non-null
  placement, not the relative order of non-null values.
- Mongo: must NOT leave a synthetic `__<field>NullBucket` key in the pipeline's output — `$unset` it
  once it has served its `$sort` purpose (see the worked example above).
- Must NOT leave string-field collation implicit when sorting a case-insensitive field (SEM-1) — the
  same collation mechanism that governs `eq`/`in` on that field governs its `ORDER BY`/`$sort`/`sort`
  too, on every backend, or row order (not just null placement) diverges across backends for
  identical IR.

**Cross-links.** `$defs/sortItem`, `$defs/nullsPosition`, `$defs/sortDirection`.

---

## SEM-4. Dates & zones

**Rule.** The IR distinguishes a **local date** (`$defs/dateValue` — a calendar date, no
time-of-day, no zone) from an **instant** (`$defs/datetimeValue` — a point in time plus the IANA
zone used to resolve it). AG Grid emits date/datetime filter values as zone-less
`"YYYY-MM-DD HH:mm:ss"` (or `"YYYY-MM-DD"`) strings; resolving one of those strings into a
`dateValue` or `datetimeValue` is exclusively the frontend adapter's job, using **both** the field's
schema-declared type and the request context's zone — never the server process's local timezone,
and never a zone guessed from the string itself (it doesn't carry one).

**A set filter's `values` follow the same rule (pinned).** The values of a set filter (`in`, wire shape
`{filterType:'set', values:[...]}`) on a `date` or `datetime` field take the comparison filter's two wire
spellings per field type (plus, on a `datetime` field only, an ISO-8601 instant, because a Set Filter's key for a
datetime-string column is the raw data string), and the adapter resolves them with the request's zone (`requestContext.zone`,
else the adapter's default zone). `datetime`: an ISO-8601 instant with `Z` or an offset passes unchanged;
otherwise `YYYY-MM-DD HH:mm:ss` or `YYYY-MM-DD` is read as a wall-clock time in that zone and resolved to
the absolute instant (`datetimeValue`, `zone` = the zone used). `date`: `YYYY-MM-DD`, or
`YYYY-MM-DD HH:mm:ss` with a midnight time only, becomes a `dateValue` (no zone); a non-midnight time, or an
ISO instant, is rejected, never truncated (a local date is never conflated with an instant). Any other text
is a request error (`malformed-request`) raised by the adapter, not a later coercion error. A parse without
a schema keeps the verbatim string. The `customFilters` typed-value path (`notIn`) is already typed and
unaffected.

**Compilers never emit a zone clause for a `datetimeValue` (pinned).** By the time a `datetimeValue`
reaches a compiler, `value` is already an absolute instant (an ISO-8601 timestamp with an explicit
offset/`Z`) — a fixed point on the universal timeline that means the same thing regardless of any
zone. The compiler compares/stores it as that absolute instant and nothing else: no `AT TIME ZONE`,
no `$dateTrunc`-with-timezone, no ES `time_zone` parameter, ever, for a plain comparison against a
`datetimeValue`. `datetimeValue.zone` is **provenance metadata** — it records which zone the adapter
used to resolve the original wire string into that absolute instant (needed for audit/debugging and
for the adapter's own resolution step) — it is not an instruction for the compiler to act on.
(Zone-aware date-math — grouping rows by "day in the user's zone", for example — is a
*post-v1 aggregation feature*, not part of comparing a `datetimeValue` in a filter; if and when it
ships, it will need its own IR shape carrying the target zone explicitly on the aggregation, not a
compiler quietly reaching into a comparison node's provenance field.) For `inRange`, per-boundary
inclusivity (`fromInclusive`/`toInclusive`) is carried explicitly on the IR node and the compiler
MUST read it from there — never assume a fixed default.

**A `datetime` read back from a result is an absolute UTC instant (pinned; Bug #2511).** Everything above is about the
value going **in**; an execution adapter that reads a result row back must hand a `datetime` cell to its caller as the
same kind of thing: an absolute instant, expressed in UTC. In a language whose date-time type records a kind or an
offset (C#'s `DateTime`, a zone-aware value elsewhere), the value carries **UTC**, so that serialising it yields the
trailing `Z` and nothing in between can reinterpret it. Three cases, by what the driver returns:

| The driver returns | The adapter delivers |
|---|---|
| a value that already denotes UTC (a UTC kind, an offset of zero, an ISO text ending in `Z`; PostgreSQL's `timestamptz` through a driver that returns UTC) | that instant, unchanged |
| a value with an offset, or a local kind the driver produced by **converting** a zoned value (SQL Server's `datetimeoffset`) | the same instant converted to UTC; never the offset-local wall-clock reading |
| a value with **no zone** (SQL Server's `datetime2`, MySQL's `DATETIME`, a zone-less text) | that wall-clock reading **as UTC** |

The last row is the host obligation stated for the SQL arm above, seen from the other end: a column with no zone type
stores the UTC wall-clock reading (the seed of every execution-equality fixture is UTC, XEQ-2), so reading it as UTC is
the only reading under which what went in is what comes out. A driver option that merely **labels** a zone-less value as
local without converting it (MySqlConnector's `DateTimeKind=Local`) does not make it a zoned value: the host leaves such
an option at the driver's default or at UTC, or the adapter would shift the value by the server's offset. **Must NOT:** deliver a
zone-less value with an *unspecified* kind (a serialiser then drops the `Z`, and a consumer is left to guess), reinterpret
it in the server process's local zone (SEM-4 already forbids that for the way in), or treat it as local and convert it to
UTC (that would shift every instant by the server's offset). A `date` cell is unaffected (a local date has no zone).
This rule is checked by each execution adapter's own tests, not by compile fixtures: a compiler never reads a result.
Today `Craticula.Dapper` (`DapperValueReaderDatetimeTests`) and `Craticula.EntityFrameworkCore` (Bug #2798,
`EfCoreDatetimeKindTests`) are covered by such tests; MongoDB's and OpenSearch's readers return UTC by construction.
**EF Core:** the adapter has no reader of its own, so it applies the same table to every `DateTime` or `DateTimeOffset`
cell of a page or an export row after EF has materialised it, whatever the provider; a host therefore needs no UTC
value converter for the result side. The comparison side stays the host's obligation as above. For SQLite that obligation includes the **binding**: EF binds a `DateTime` in its own
`yyyy-MM-dd HH:mm:ss` form, so the host maps every datetime to and from the stored `yyyy-MM-ddTHH:mm:ss.fffZ` text on its
`DbContext`, or an `eq`, a range bound and a datetime-sorted export return wrong rows without an error (a walk that meets the row its previous chunk ended on stops with an exception) (Bug #2805,
`EfCoreHostObligationTests`).

**MongoDB representation of `dateValue` (pinned): a plain ISO date string, never a BSON `Date`.**
MongoDB's `Date` type has no "calendar date, no time-of-day" concept — every BSON `Date` is an
instant. Storing/comparing a `dateValue` as a BSON `Date` therefore requires silently promoting it to
*some* midnight instant, and "midnight in which zone?" has no answer for a value that was never an
instant in the first place — exactly the conflation this rule's own second "must NOT" (below)
forbids "without that promotion being an explicit, documented adapter decision." Rather than making
that decision implicitly inside every Mongo compiler, the pinned mechanism sidesteps it: `dateValue`
compiles to the ISO calendar-date string itself (`"1990-05-12"`), compared as a plain BSON string.
Lexicographic string comparison on `YYYY-MM-DD` already matches chronological order, so `$gte`/`$lt`
work correctly with no `Date` promotion, no zone, and no ambiguity. `datetimeValue` (an instant)
still compiles to a BSON `Date` — extended-JSON's `$date` field requires a full instant string with
an explicit offset/`Z` (`"2026-01-01T00:00:00Z"`), never a bare calendar date.

> **Not yet pinned — flagged in the TRD, stated here rather than guessed at.** The TRD (§7.4)
> explicitly marks the *exact* default boundary inclusivity that AG Grid's own simple date filter
> uses for `inRange` (its stated default is exclusive of both bounds) as "verify at implementation
> time and freeze" — i.e., a value to be captured from a live grid and locked into fixtures by
> #1630, not a certainty this document should assert today. What *is* pinned by this rule is the
> mechanism: inclusivity flags are always explicit on the IR node and always read literally by the
> compiler. What is **not yet pinned** is the specific default value the adapter should choose when
> AG Grid's own request doesn't make it explicit. Treat any inclusive/exclusive example below as
> illustrative of the mechanism, not as the frozen default.

**Rationale.** Three naive failure modes, all seen in hand-rolled translations: (1) treating every
date as a UTC instant regardless of its declared type — a local-date field compared this way shifts
by a day for any user not in UTC, the classic "date is off by one near midnight" bug; (2) parsing
AG Grid's zone-less datetime string using the server process's own local timezone, which makes the
exact same IR return different rows depending on the deployment environment's `TZ` setting — a
compiler that isn't even deterministic on its own inputs; (3) hardcoding `inRange` boundaries as
always-inclusive (SQL `BETWEEN`'s familiar default) regardless of what the IR's explicit flags say,
so a row sitting exactly on a boundary appears in the grid's client-side row model and silently
disappears once the same filter is compiled for SSRM. All three are exactly the kind of "usually
wrong" translation TRD §7's opening line calls out — dates and zones are where naive compilers most
often diverge from what the grid itself shows the user.

**Worked example** — `inRange` on `createdAt` (an instant field), from 2026-01-01T00:00:00Z
(inclusive) to 2026-02-01T00:00:00Z (exclusive), as resolved by the adapter for illustration:

- **SQL** — a local-date field needs no zone conversion at all (it never had one); a true instant
  field is compared against already-UTC-resolved boundary parameters. PostgreSQL's `timestamptz`
  stores/compares in UTC internally regardless of session timezone, so no `AT TIME ZONE` clause is
  needed once the adapter has resolved the instant; a dialect without a true timezone-aware
  timestamp type (SQL Server's `datetime2`, MySQL's `DATETIME`) is a **host obligation** instead: such a column stores
  the UTC wall-clock reading of the instant, so the same UTC-resolved boundary parameters compare against it directly,
  with no conversion in the statement and none on the way back (the result side of this rule reads it as UTC, below):
  ```sql
  WHERE created_at >= :from AND created_at < :to
  ```
- **SQLite — a fixed-width text instant, on both sides of the comparison (pinned).** SQLite has no
  timestamp type: a `datetime` column holds TEXT and `>`, `<`, `=` compare it character by character.
  Text is only chronological when every value has the same width, and the two spellings of one second,
  `...:00Z` and `...:00.001Z`, are not the same width: `.` (0x2E) sorts before `Z` (0x5A), so a stored
  `2026-01-01T00:00:00.001Z` sorts *before* a bound spelled `2026-01-01T00:00:00Z`, and `gt` on that
  bound silently drops a row that is later than it. The rule therefore has two halves, and neither is
  enough alone. **Host obligation:** a SQLite `datetime` column stores exactly three fractional digits,
  `yyyy-MM-ddTHH:mm:ss.fffZ`, UTC (the millisecond precision XEQ-2 already caps a seed at). **Compiler
  rule:** the SQLite arm binds a `datetimeValue` in the same form, so a whole-second instant is bound as
  `2026-01-01T00:00:00.000Z`, never `...:00Z`. A bound with a sub-millisecond part (a
  fraction finer than three digits that is not all zeros after the third) is **rounded to the millisecond by
  its operator**, because the text of `...:00.0005Z` sorts before the stored `...:00.000Z` although it is
  later. Stored values `s` are always millisecond-aligned, so for a bound `b` and its floor / ceiling to the
  millisecond: `x > b` is `s > floor(b)`, `x <= b` is `s <= floor(b)`, `x >= b` is `s >= ceil(b)` and
  `x < b` is `s < ceil(b)`. The SQLite arm therefore binds `floor(b)` for `gt` and `lte`, and `ceil(b)` for `gte`
  and `lt`; an `inRange` follows its two bounds' own operators (an exclusive from-bound is `gt`, an inclusive one
  `gte`; an inclusive to-bound is `lte`, an exclusive one `lt`). `eq`, `neq`, `in` and `notIn` keep the full
  value: a finer-than-millisecond value never equals a stored one, which is the correct answer. A bound that is
  already millisecond-aligned is unchanged. Postgres,
  SQL Server, MySQL and Oracle compare a typed instant, not text, and keep the form of SEM-4 above
  (`...:00Z` for a whole second). The obligation covers the path that sends the bound as text
  (`Craticula.Sql` and the Dapper adapter on top of it); the EF Core adapter hands its provider a
  `DateTime`, so a host that stores the form above maps every datetime to and from it on its `DbContext` (SEM-4's EF
  paragraph, Bug #2805; the divergence without it is recorded in `SqliteTypeAffinityDivergenceTests` and
  `EfCoreHostObligationTests`). That mapping writes millisecond text, so a finer-than-millisecond bound is truncated there, not
  floored or ceiled as above.
- **MongoDB** — an instant field (`datetimeValue`) compares against BSON `Date` values built from
  the full instant string (see the pinned representation above); a local-date field (`dateValue`)
  compares against the plain ISO date string instead, never a `Date`:
  ```json
  // instant field:
  { "createdAt": { "$gte": { "$date": "2026-01-01T00:00:00Z" }, "$lt": { "$date": "2026-02-01T00:00:00Z" } } }
  // local-date field:
  { "createdOn": { "$gte": "2026-01-01", "$lt": "2026-02-01" } }
  ```
- **OpenSearch / Elasticsearch** — a `range` query choosing `gte`/`gt` and `lt`/`lte` per the
  inclusivity flags, with an explicit `format` (pinning the accepted string shape) — **no**
  `time_zone` parameter, because both boundaries are already-resolved absolute instants (with an
  explicit `Z`/offset) and `time_zone` only affects *unqualified* date-math strings, which never
  occur here:
  ```json
  {
    "range": {
      "createdAt": {
        "gte": "2026-01-01T00:00:00Z",
        "lt": "2026-02-01T00:00:00Z",
        "format": "strict_date_optional_time"
      }
    }
  }
  ```

**Must NOT.**
- Must NOT assume a fixed server or database default timezone anywhere in the compiler; zone
  resolution happens once, in the adapter, using the request context's zone.
- Must NOT emit any dialect zone-conversion clause (`AT TIME ZONE`, `$dateTrunc`'s `timezone` option,
  ES `time_zone`) when compiling a comparison against a `datetimeValue` — the value is already an
  absolute instant; a zone clause at that point does not "correctly interpret" it, it *changes* what
  the comparison means, silently making the compiler's output depend on `datetimeValue.zone` (a
  provenance field) in a way no other backend's compiler does.
- Must NOT conflate `dateValue` and `datetimeValue` at the compiler level — a local date must never
  be silently promoted to a midnight-UTC instant and then compared against instant semantics without
  that promotion being an explicit, documented adapter decision.
- Must NOT hardcode `inRange` as inclusive-inclusive (or any other fixed combination) — the flags are
  already explicit on `rangeComparisonNode`; the compiler reads them, it never assumes them.
- Must NOT present the exact AG Grid boundary-inclusivity default as settled fact in fixtures or
  documentation before it has been verified against a live grid, per the TRD's own "verify and
  freeze" flag on this rule.
- Must NOT represent a `dateValue` as a MongoDB `Date` — see the pinned representation above; use
  the plain ISO date string.

**Fixture format note.** A `datetimeValue` fixture's expected artifacts are only reproducible if the
adapter's resolved value AND the request-context zone it used are both visible in the fixture inputs
— otherwise a port author must guess the zone the original fixture author assumed. `agGridRequest.json`
fixtures needing this carry an optional `requestContext: { "zone": "<IANA id>" }` sibling field
alongside the AG Grid wire shape (the same "documented extension beyond AG Grid's own wire format"
pattern as `customFilters`, OQ-11) — see `spec/fixtures/README.md`.

`requestContext` carries a second, related field for the same reproducibility reason: `now` (an
ISO-8601 instant), required by any fixture whose expected artifacts depend on what "now" was — i.e.
every AG-2 date-preset fixture, since `today`/`last7Days`/... resolve relative to the current
instant. The two fields differ in status, and the difference is normative: **`zone` is read off the
wire, `now` is not.** An implementation resolves presets against its own injected clock and MUST NOT
honor a client-supplied `now` — a request that could redefine what "last 7 days" means would let any
caller move the window at will. `now` exists so a conformance harness can pin its clock and replay
the fixture deterministically; it is a harness instruction, never a wire input. See
`spec/fixtures/date-presets/README.md`.

**Cross-links.** `$defs/dateValue`, `$defs/datetimeValue`, `$defs/rangeComparisonNode`
(`fromInclusive`, `toInclusive`), `$defs/typedValue`.

---

## SEM-5. Type coercion

**Rule.** Coercing a grid's stringly-typed wire value into a typed IR value (e.g. AG Grid's number
filter sending `"30"`, coerced to an `int64Value`) happens **exactly once**, in the frontend adapter,
at parse time, using the field's schema-declared type (SC-2) as the coercion target. No backend
compiler ever performs coercion or re-interprets a `typedValue` — by the time a compiler sees a
value, its type is already fixed and the compiler trusts it completely. If the adapter cannot coerce
a wire value to the field's declared type, that is a request error in Strict mode (SC-1's default) —
never a value that is passed through untyped or best-effort.

**Rationale.** The naive alternative pushes the stringly-typed value all the way down to the
database layer and lets the target engine's own implicit-coercion rules decide what `"30"` means
against an integer column. That makes behavior backend-dependent by construction — one engine
coerces, another errors, a third compares as a string and never matches an integer column at all —
which directly violates G3/G4 (identical semantics across backends and language ports). Worse is the
failure mode the TRD's problem statement (§1) attributes by name to string-DSL intermediaries like
OData/dynamic-LINQ adapters: an unparseable filter value is sometimes treated as "no constraint at
all," silently degrading a supposedly-narrowing filter into a full-table match — the opposite of what
the user asked for, and dangerous precisely because it fails silently rather than loudly.

**Worked example** — coercing a number filter's wire value against a field declared `int64`:

- **AG Grid adapter (the one and only coercion site)** — wire value
  `{"filterType":"number","type":"equals","filter":"30"}` against a field configured `type: "int64"`
  in the `GridSchema` is parsed once, here, into:
  ```json
  { "type": "int64", "value": 30 }
  ```
  Every downstream compiler (SQL/Mongo/ES) binds `30` as a native integer parameter/value; none of
  them contain coercion logic of any kind — they operate on the already-typed `int64Value` node.
- **Strict-mode rejection** — the same field, wire value `"abc"` (not parseable as an integer): the
  adapter's coercion fails before any IR node is produced, and Strict mode (SC-1's default) surfaces
  a request error (a validation failure an execution adapter typically maps to an HTTP 400-class
  response) rather than emitting a fallback value. Lenient mode (SC-1's non-default alternative)
  would need an explicit, documented fallback (e.g., dropping just that condition) — but that is a
  deliberate per-host opt-out, not this rule's canonical path.
- Boolean and date/datetime coercion (`"true"`/`"false"` → `booleanValue`; AG Grid's
  `"YYYY-MM-DD HH:mm:ss"` string → `dateValue`/`datetimeValue` per SEM-4) follow the identical
  one-layer rule — only the target type differs, not where or how coercion happens.
- A set filter's `values` on a `date` or `datetime` field are resolved by the adapter like a
  comparison filter's value, per field type (SEM-4, "A set filter's `values` follow the same rule"): the
  zone-less `YYYY-MM-DD HH:mm:ss` / `YYYY-MM-DD` spellings are resolved with `requestContext.zone`, an
  ISO instant on a `datetime` field passes unchanged, and any other text — including a non-midnight time or
  an ISO instant on a `date` field — is a `malformed-request` raised by the adapter before any typed value
  exists, not a later coercion error.

**Must NOT.**
- Compilers must NOT attempt to coerce a `typedValue`'s declared type against a schema's physical
  column/field type — that check is the adapter/validator's job, never the compiler's.
- Must NOT silently substitute an uncoercible value with a sentinel that matches everything (e.g.
  turning a bad numeric string into a SQL `1=1`) or with one that matches nothing, without surfacing
  a request error — both hide the failure instead of reporting it.
- Must NOT rely on the target engine's own implicit cast rules (e.g. a database comparing a string
  literal against an integer column via its native cast rules) as the coercion mechanism — that
  reintroduces exactly the backend-dependent behavior this rule exists to eliminate.

**Cross-links.** `$defs/typedValue` and its member shapes — `$defs/int64Value`,
`$defs/decimalValue`, `$defs/doubleValue`, `$defs/booleanValue`, `$defs/stringValue`,
`$defs/dateValue`, `$defs/datetimeValue` — the closed, tagged union that makes "compilers never
guess" structurally true: a compiler cannot receive an ambiguous scalar in the first place.

---

## SEM-6. Deterministic paging

**Rule.** Schema config declares a required, unique `stableKey` per grid. If the IR's `sort` array,
once reduced as the pinned paragraph below says, does not already reach that key, the compiler appends it as an implicit trailing tiebreaker —
after every sort key the user actually chose, never ahead of them — before compiling the final
ordering clause. The appended tiebreaker still needs a `nullsPosition` (SEM-3 applies to it exactly
as to any other sort key): since a `stableKey` is required to be unique but not required to be
`NOT NULL`, the compiler cannot skip specifying one. Use the same adapter default SEM-3 pins
(`last` on ascending, which the tiebreaker always is, since it exists purely to break ties and has
no direction the user chose) — i.e. the appended key is always `{ field: stableKey, direction: "asc",
nullsPosition: "last" }`.

**The effective sort lists a field once and stops at an exact stable key (pinned; Bug #2565).** Before the
compiler appends anything it reduces the request's `sort` array by two rules, and both only remove keys
that can never change the order:

1. **A later occurrence of a field the sort already named is dropped.** The first occurrence already
   decided every tie the later one could break (`[age desc, age asc]` orders exactly like `[age desc]`).
   This looks at the field only: a repeat that differs in direction or null placement is still redundant.
2. **When the stable key orders exactly, everything after its first occurrence is dropped.** A key on it
   orders exactly when the field is of any non-text type (numeric, boolean, date, datetime), or a text
   field declared case-sensitive (SC-3, `text.caseSensitivity`): two rows with different values never tie under it, so no key after it can break a tie (`[id desc, age asc]` orders
   exactly like `[id desc]`). When the sort stops at the stable key this way nothing is appended; when it
   does not reach it, the tiebreaker is appended as above.

"Unique" in this rule means that no two rows share a value, **NULL included**: at most one row has no
value. SQL Server's `UNIQUE` constraint and a MongoDB unique index enforce that; PostgreSQL, MySQL, SQLite
and Oracle allow many NULLs, and a host on one of them whose stable key is nullable never had SEM-6's
guarantee, since the appended tiebreaker does not break ties among NULLs either. Rule 2 relies on the same
reading of "unique" that the appended tiebreaker always did.

**A case-insensitive text stable key is the exception to rule 2.** Under SEM-1 a user's own key on a text
field resolves case-insensitively unless the field declares otherwise, and `'aB3'` and `'Ab3'` compare
equal under it (the blockquote below makes the same argument against collating the *appended* key). Such a
sort is not total, so **nothing after it is dropped and the exact tiebreaker is appended as before**. One
gap predates this rule and is left as it was: a sort that already *ends* in the case-insensitive key
(`[code]`, `[age, code]`) gets no tiebreaker, because the user's key already names the column and nothing separates
case variants there (the rows tie in the engine's own order; a host that needs more declares the key case-sensitive). Rule 1 applies regardless.
Where the exact tiebreaker *is* appended **after an earlier key on the same column** (the user's collated key, then the
exact tiebreaker), two arms cannot list a column twice, and each spells the tiebreaker as a different expression instead
(Bug #2809; fixture `sort-paging/017` carries both arms): **SQL Server** spells the repeated tiebreaker with the field's
case-*sensitive* mechanism, SC-3's own spelling, `[code] COLLATE Latin1_General_CS_AS`, **and** carries that collation inside
the tiebreaker's null-bucket `CASE` (SQL Server refuses an `ORDER BY` expression identical to an earlier one, error 169, and
accepts the same column under a different collation; measured on SQL Server 2022); **MongoDB** sorts the tiebreaker on a
synthetic field holding `{$toHashedIndexKey: "$code"}` (a non-string, which the query's collation cannot fold), added with the
null buckets and unset after the `$sort`. The other four SQL dialects accept a repeated column and render the same
case-sensitive spelling where they have one (SQLite, Oracle); PostgreSQL renders it bare (its column default) and MySQL has no
collation to spell, so there a case-insensitive column keeps folding case in the tiebreaker, which is the DDL-side host
obligation GRP-2 and SC-3 already record: the host declares such a stable key case-sensitive or on a binary collation. **The
tie order among case variants is not promised to be the same on every arm:** PostgreSQL and the Search arm order them by
the column's default and the keyword field, SQL Server by `CS_AS` (lowercase first) and MongoDB by hash. Where the tiebreaker is
exact, that order is stable and no variant is dropped or repeated; no rule says which of two case variants that tie on every
earlier key comes first, and no fixture's expected rows depend on it. The user's own null placement is not repeated for it: a null ties on the earlier key already.

**A dropped key is never a way around the allowlist.** The reductions run only on a sort **every key of
which the query knows**: on a row query, a field of the schema; on a grouped level, the group column or one
of the level's aggregate column ids (GRP-4). A sort that names anything else is left as it is, so the
compiler's own check still sees the unknown key and rejects it exactly as SC-1, SEC-6 and GRP-4 require,
wherever in the sort it sits (`adversarial/028`). Only a key that is known and redundant is ever dropped.

The result names every field at most once, except in that exception, and, whenever the stable key is among
them, ends in it. The first wording of this rule only asked whether the sort *ends* in the stable key, so
`[id desc, age asc]` compiled to `ORDER BY id DESC, age ASC, id ASC`: SQL Server refuses a column named
twice in an `ORDER BY` list (error 169), and a MongoDB `$sort` document cannot hold one key twice, so the
same request failed on one arm and was ambiguous on another. A field before the stable key is kept
(`[age asc, id desc]` stays as written). The reductions apply to the **group column** in a grouped level
exactly as to the stable key, with rule 2 unconditional (GRP-4, GRP-2: it is unique and exact across the
level's rows by construction), so an **aggregate of the level** after the group column is dropped (a Search
level used to refuse it; it can never change the order of one-bucket-per-value rows). A column the level
does *not* produce is not an aggregate and is not dropped: GRP-4 rejects it wherever it sits. The reductions also apply to every consumer of the effective sort, including the keyset walk of an
export.

Must NOT: reject a request for naming a field twice or for sorting past the stable key (the grid cannot
prevent either, and the order the user asked for is still honoured); drop a key that comes **before** the
stable key, **and** drop a key that is the first occurrence of its field; drop the keys after a
**case-insensitive** text stable key; drop a key the query does not know (it must reach the rejection);
keep a dropped key "for the record" in any backend's artifact.

> **Superseded in part by GRP-4 (#1640) for a grouped level, and by GRP-6 (#1641) for BM-3's
> distinct-values query.** This rule says the appended key is *always* the schema's `stableKey`, and
> its first Must-NOT below forbids treating anything else as unique. On a **grouped level** that is
> now wrong: the `stableKey` is not in the grouped
> projection at all, so ordering by it is invalid SQL rather than merely undesirable, and the
> **group column** plays its role instead — appended last, ascending, nulls last, and not appended
> twice when the sort already ends in it, all of which are this rule's own mechanics unchanged. The
> Must-NOT's *intent* is untouched and still binds: the substitute is not a key that "merely looks
> unique", it is unique across the level's rows **by construction**, since a `GROUP BY` emits one row
> per distinct value of it.
>
> A **BM-3 distinct-values query appends nothing at all** (GRP-6(e)) — and it is the exclusion this
> enumeration is most likely to be read past, because it carries no `groupSpec` and so answers to
> "not grouped" on the only test a compiler has in front of it. It is nonetheless not a row query:
> the `stableKey` is absent from its one-column projection exactly as it is from a grouped one, so
> appending it is the same invalid SQL, and its single `ORDER BY` key — the distinct column — is
> already unique across the result rows by this blockquote's own by-construction argument, leaving no
> tie for a tiebreaker to break. A port that appends here emits
> `ORDER BY "region" ASC NULLS LAST, "id" ASC NULLS LAST LIMIT $1` and fails
> `group-aggregation/016`-`019` on all seven arms.
>
> Everything else — an ordinary row query, and a fully-consumed drill-down
> **leaf**, which projects rows — keeps `stableKey` exactly as written here. Recorded rather than
> deleted, since the affected artifacts (`group-aggregation/001`-`004`, `007`-`015`, `020`, `021` on
> every arm) were authored against the original.

> **Superseded in part by #1640's review, for the appended tiebreaker's case sensitivity.** The
> appended key resolves **exact** — no case-folding mechanism is spelled on it — whatever SEM-1 says
> about the `stableKey`'s own field, and whether or not the query is grouped. Everything else about
> the tiebreaker is unchanged: still last, still ascending, still nulls-last, still not appended when
> the sort already ends in it.
>
> This is not a stylistic exemption, it is *this rule's own guarantee*. A `stableKey` is declared
> unique, and it is unique under the collation its **storage** uses; a compiler that attaches a
> different one is no longer comparing the text a user asked about, it is re-deciding row identity.
> The fixture suite's `craticula_ci` is declared `deterministic = false`, and under a
> non-deterministic collation `'aB3'` and `'Ab3'` compare **equal** — so a collated tiebreaker leaves
> exactly the ties it exists to break, the same statement may order those rows differently at
> `OFFSET 0` and at `OFFSET 100`, and a row is returned twice or dropped from both pages. That is the
> Rationale immediately below, and the third Must-NOT further down, reintroduced through this rule's
> own mechanism. Spelling nothing sorts the key under its storage collation, i.e. under the one its
> declared uniqueness is stated in. It is GRP-2's argument extended by one step: a key that
> establishes **identity** is not governed by how a field's *values* compare.
>
> The scope is the **appended** key only. A user's own sort key keeps SEM-1 in full, including on the
> stable key's own column when the request sorts by it explicitly (nothing was appended then) — so one
> statement legitimately reads
> `ORDER BY "last_name" COLLATE craticula_ci ASC NULLS LAST, "id" ASC NULLS LAST`, a collated user key
> beside a bare tiebreaker, and `spec/fixtures/sort-paging/001` pins it. Recorded rather than folded
> into the rule because `group-aggregation/005`/`006` are the only artifacts in the whole suite that
> ever pinned the collated form — measured across all seven backends — and both were authored, and
> re-authored, inside #1640.

**Rationale.** Paging over a sort key that isn't unique is non-deterministic at the database level:
nothing in the SQL standard (or in Mongo's or ES's own documentation) guarantees that rows tied on
the chosen sort key come back in the same relative order across two separate executions of the
identical query — including two consecutive page reads of the same filter+sort. A user sorting a
grid by `lastName` alone, with duplicate last names in the dataset, can see a row duplicated across
two pages or silently missing from both, depending on how the engine happened to break the tie that
particular time. This is a uniquely nasty bug class: the query "looks" correct, it reproduces
intermittently, and the AG Grid UI itself gives the end user no way to add a tiebreaker (a user can
only sort by the columns visible in the grid). Requiring the schema to declare a `stableKey` once,
and having every compiler append it automatically, removes the ambiguity without depending on every
sort model the UI might ever construct happening to already be unique.

**Worked example** — user sorts by `lastName ASC` only; schema declares `stableKey: "id"`:

- **SQL** — `ORDER BY` gains the tiebreaker as its final key, with its own explicit null placement
  per SEM-3 (`NULLS LAST` here, since the tiebreaker's direction is always `asc`):
  ```sql
  ORDER BY last_name ASC NULLS LAST, id ASC NULLS LAST
  ```
- **MongoDB** — the `$sort` document gains the same trailing key (object key order is significant
  and preserved for `$sort`); if `id` can itself be null/missing, it goes through the same
  null-bucket emulation SEM-3 shows for `lastName` — **bucket key before the real field**, matching
  SEM-3's own canonical order exactly (not the reverse):
  ```json
  { "$sort": { "__lastNameNullBucket": 1, "lastName": 1, "__idNullBucket": 1, "id": 1 } }
  ```
  The `__idNullBucket` stage is emitted **unconditionally, with no exception** — `stableKey` is
  usually a non-nullable primary/surrogate key in practice, making the bucket a runtime no-op, but
  `grid-schema.schema.json` has no way to *declare* NOT NULL, so there is no schema state a compiler
  could check to justify skipping it. The same unconditional rule applies everywhere else this
  document's examples show the marker (SEM-3's own worked example, and every other tiebreaker
  example in this document) — "the field is probably never null in practice" is never a license to
  omit the mechanism; the mechanism is what makes it not matter if it turns out to be null.
- **OpenSearch / Elasticsearch** — the `sort` array, whose element order *is* the tiebreak order,
  gains the mapped `stableKey` field (or its `.keyword` sub-field) as its last element, with its own
  `missing` parameter:
  ```json
  { "sort": [ { "lastName": { "order": "asc", "missing": "_last" } }, { "id": { "order": "asc", "missing": "_last" } } ] }
  ```

This is v1's *only* paging mechanism (`$defs/rangePage`'s `startRow`/`endRow`, AG-3) — the
tiebreaker's job is to make that offset-based paging deterministic, not to enable an alternative
keyset-paging mode; see the "must NOT" below.

**The page window is non-empty (AG-3, SEC-3).** A request's `startRow`/`endRow` window must satisfy
`0 <= startRow < endRow` (`endRow` is exclusive, so `endRow - startRow` is the requested size and must be at
least 1). A request with `endRow <= startRow` (an inverted window, or a zero-width one such as
`startRow: 100, endRow: 100`) is **refused at the AG Grid request boundary with a defined error before any
compilation, identically for every backend**; it is never compiled into a statement a backend may reject
(T-SQL refuses `FETCH NEXT 0 ROWS`, msg 10744) or silently answer with an empty page. The refusal is
`requestParsing` / `malformed-request` (`adversarial/027`). An IR built by hand may still carry a zero-size
`RangePage` (an adapter's count-only query), which is why `ir.schema.json` keeps `endRow >= startRow`;
the strict rule belongs to the wire request. Under EXP-1's `exportScope: "all"` the window is discarded
(EXP-2) and therefore not checked.

**Must NOT.**
- Must NOT accept a client-supplied sort model that merely *looks* unique (a field that happens to
  have distinct values in a sample dataset) as sufficient without it being the schema's declared
  `stableKey` — apparent uniqueness in a sample is not a guarantee.
- Must NOT insert the tiebreaker ahead of, or interleaved with, the user's chosen sort keys — it is
  always the final key, so every key the user actually asked for keeps full precedence.
- Must NOT treat this rule as license to switch v1 grid paging from offset-based (`$defs/rangePage`)
  to keyset-based paging — SQL keyset pagination is an explicit v2 opt-in (PERF-2), not a v1
  requirement or even a v1 option. The `stableKey` tiebreaker's job in v1 is narrower than "enabling
  keyset paging": it makes the existing `startRow`/`endRow` offset paging deterministic across page
  reads, by guaranteeing the *sort itself* has one and only one possible row ordering. EXP-3's ban
  on `OFFSET`-walking is a separate, narrower rule scoped to the export-streaming fallback path
  (chunking an unpaginated export when a driver can't stream) — it does not apply to, and must not be
  read as banning, ordinary v1 grid paging.
- Must NOT omit the tiebreaker's null-ordering marker (SQL `NULLS`, Mongo bucket, ES `missing`) on
  the theory that `stableKey` is "probably never null" — there is no schema state that licenses this
  omission (see the worked example above); every tiebreaker in every artifact carries the marker,
  unconditionally, including under `page: none` (EXP-2) and export scopes (EXP-1), which use the
  identical sort-compilation path as ordinary paged requests. (This bullet is about the *marker* on a
  tiebreaker that exists. It is not an enumeration of the shapes that get one, and in particular
  "unpaginated" does not imply "still appends": a BM-3 distinct-values query is also unpaginated and
  appends no tiebreaker at all — GRP-6(e), and the first blockquote above.)

**Cross-links.** `$defs/sortItem` (the array the compiler appends to), `$defs/fieldName`
(`stableKey` is resolved through the schema the same way any other IR field reference is),
`$defs/pageSpec` / `$defs/rangePage` (the paging context this rule protects the determinism of).

---

## SEM-7. `contains` on ES/OpenSearch

**Rule.** On OpenSearch/Elasticsearch, `contains`/`notContains` (`$defs/binaryOperator`) compile to
**substring-matching** query types — `wildcard` against a `keyword` field, or a per-field ngram-
analyzed sub-field strategy (schema-configured) — never to a tokenized `match` query. This pins
`contains`'s behavior to exactly what SQL's `LIKE '%pattern%'` does: substring presence, no
tokenization, no stemming, no stopword removal, no relevance scoring. A per-field, explicit opt-in
`searchMode: analyzed` is the documented escape hatch for a host that deliberately wants
relevance-style full-text matching instead of substring semantics for that field.

**Rationale.** ES/OpenSearch's idiomatic "search for text" mechanism is `match` against an analyzed
field, and a naive compiler reaches for it because the operator is literally named `contains` and
`match` reads as "does it contain this". That is the tokenized-match trap: `match` splits both the
indexed field and the query string into analyzer tokens (lowercased, stemmed, stopword-filtered) and
matches when any *token* overlaps — it does not check for a literal substring. `contains: "art"`
against the indexed value `"Smart Watch"` returns **no hit** under `match` (the analyzer produces
whole tokens `"smart"` and `"watch"`, neither of which is `"art"`), while the identical filter
compiled to SQL (`LIKE '%art%'`) or Mongo (`$regex`) matches that row. The same IR silently diverges
across backends — precisely the parity failure G3 exists to prevent, and the TRD's problem statement
(§1) calls out ES/OpenSearch support as the one thing "nothing exists" for in any prior art, largely
because this exact trap is unsolved elsewhere. Pinning substring semantics trades away ES's own
relevance ranking for `contains`; `searchMode: analyzed` exists so a host can make that trade
deliberately, per field, instead of getting it by accident.

**Worked example** — `contains: "art"` against `name`, where a document has `name = "Smart Watch"`:

- **Substring semantics (the default this rule pins)** — `wildcard` against the `keyword` sub-field
  matches, because the literal substring `"art"` is present, exactly mirroring `LIKE '%art%'`:
  ```json
  { "wildcard": { "name.keyword": { "value": "*art*", "case_insensitive": true } } }
  ```
  A per-field ngram-indexed sub-field (e.g. `name.ngram`, matched with a plain `match` against *that*
  field) is the higher-index-cost/lower-query-cost alternative mechanism SC-3 lets a field choose
  instead — same illustrative substring outcome, different index-time/query-time trade-off (PERF-4).
- **The tokenized trap being explicitly ruled out** — shown here only as the anti-pattern the rule
  exists to forbid, never emitted by the compiler for `contains`:
  ```json
  { "match": { "name": "art" } }
  ```
  — no hit against `"Smart Watch"`, which is exactly the silent divergence from SQL/Mongo this rule
  prevents.
- **`searchMode: analyzed` opt-in** — when a field is explicitly configured this way, `contains`
  compiles to the tokenized form instead, as a documented, deliberate divergence:
  ```json
  { "match": { "name": { "query": "art", "operator": "and" } } }
  ```
- **For comparison, the same logical outcome on the other backend families**, achieved without an
  opt-in since neither needs one: SQL `LIKE`-based substring matching, with the pattern's own
  `%`/`_` wildcard characters escaped per SEC-4 **and an explicit `ESCAPE` clause naming the escape
  character used** — required because, unlike PostgreSQL (whose default `LIKE` escape character is
  `\` unless overridden), SQL Server, SQLite and Oracle have **no default escape character at all**
  and MySQL's depends on the `NO_BACKSLASH_ESCAPES` session mode; without a compiler-supplied
  `ESCAPE` clause, SEC-4's escaping is silently a no-op on four of the five SQL dialects, and a
  user-supplied literal `%`/`_` still behaves as a wildcard:
  ```sql
  WHERE name LIKE '%' || :escapedPattern || '%' ESCAPE '\'
  ```
  MongoDB has no native non-regex substring operator, so `contains` there is necessarily a `$regex`
  built from an already-escaped literal — never compiled from a client-supplied pattern, consistent
  with SEC-5's exclusion of user-controlled regex (ReDoS surface). The escaping here is a **distinct
  character class from SEC-4**: SEC-4 covers SQL `LIKE` wildcards (`%`, `_`, `\`) and ES wildcard
  syntax (`*`, `?`) — it says nothing about *regex* metacharacters. Building `$regex` from a
  SEC-4-escaped-only pattern still leaves `.`, `+`, `*`, `(`, `)`, `[`, `]`, `{`, `}`, `|`, `^`, `$`
  live in the pattern, which is both a match-scope-widening bug (the pattern matches more than the
  literal substring the user typed) and, combined with attacker-influenced repetition/alternation,
  a ReDoS vector — the exact surface SEC-5 excludes user-controlled regex operators to avoid,
  reopened here unless this document pins its own escape set. The value MUST be escaped against
  every regex metacharacter (a full backslash-escape of every character outside `[A-Za-z0-9]`, not
  just SEC-4's four LIKE/wildcard characters) before insertion:
  ```json
  { "name": { "$regex": "escaped-pattern-here", "$options": "i" } }
  ```

**Must NOT.**
- Must NOT compile `contains`/`notContains` to a `match` query as the default — that is the
  tokenized-match trap this rule exists to rule out.
- Must NOT emit a SQL `LIKE` pattern without a matching `ESCAPE` clause — SEC-4's wildcard-escaping
  is a no-op on any dialect without a default escape character (SQL Server, SQLite) or with
  backslash-escaping disabled (MySQL's `NO_BACKSLASH_ESCAPES`). **Read this together with SQL-5 in
  the canonical-rendering addendum**, which is where the per-dialect answer lives: the operator, the
  `ESCAPE` clause's spelling, and the escape *alphabet* all vary. Taken literally as a universal
  rule, this bullet is wrong on two of the four v1 SQL dialects — SQLite's case-sensitive path is
  `GLOB`, which has no `ESCAPE` clause at all, and SQL Server's alphabet includes `[` on top of
  SEC-4's three.
- Must NOT build the MongoDB `$regex` value by applying only SEC-4's LIKE/wildcard escape set —
  regex metacharacters are a distinct, wider class (see the worked example above) and must be
  escaped in full before insertion; SEC-4 alone is not sufficient here and must NOT be treated as
  though it were, never compiled from a client-supplied regex (SEC-5).
- Must NOT let `searchMode: analyzed` become a silent or implicit default for any field — it is an
  explicit per-field opt-in (SC-3); its absence always means substring semantics.
- Must NOT assume a `wildcard` query is index-friendly without a `keyword` (or normalizer-equipped)
  field/sub-field behind it — running `wildcard` against an analyzed text field undermines the point
  of pinning substring semantics and belongs, if used, in the per-backend index-guidance docs
  (PERF-4) as an explicitly documented trade-off, not assumed silently here.

**Cross-links.** `$defs/binaryOperator` (`contains`, `notContains`), `$defs/stringValue` (the value
being substring-matched), `$defs/fieldName`.

---

## SEM-8. Empty set membership

**Rule.** A `$defs/setComparisonNode` whose `values` array is empty is valid. `in` with no values
matches **no** row; `notIn` with no values matches **every** row. Both answers hold for rows whose
field is NULL or missing: `in []` never matches one (SEM-2: `in` never matches null), and `notIn []`
matches it, the constant being true for every row, so no `IS NULL` disjunct is added next to it.
The empty list is a constant, so it composes by ordinary Boolean logic inside `and`, `or` and `not`
(`in [] OR p` matches what `p` matches; `notIn [] AND p` matches what `p` matches). The null
fan-out of SEM-2 applies at a `notNode` as ever, so `not(in [])` matches every row and `not(notIn [])`
matches exactly the rows whose field is NULL or missing. Compilers do not fold the constant out of the
tree.

**Rendering.** The empty list is never sent to the engine as a list.
- SQL: `in []` → `1 = 0`, `notIn []` → `1 = 1`, in every dialect (SQL Server and Oracle have no
  boolean literal in predicate position). Never `IN ()` (a syntax error) and never a bound empty array.
- MongoDB: `{field: {$in: []}}` and `{field: {$nin: []}}`. No string comparison happens, so no
  collation is attached for them.
- OpenSearch/Elasticsearch: `match_none` and `match_all`.

**Origin.** AG Grid's Set Filter sends `{filterType: "set", values: []}` when the user clears every
value, and its own client-side row model then shows no rows. Rejecting the request would make every
host re-implement that rule. A null "(Blanks)" element inside `values` is a different matter and
stays rejected.

**Must NOT.** Emit `IN ()` or bind an empty array; add an `IS NULL` disjunct next to the constant itself; reject
the request; fold the constant out of the tree.

**Cross-links.** `$defs/setComparisonNode`, SEM-2 (null handling), SQL-4 (typed set arrays), MDB-9, OSE-7.

**Fixtures.** `operators/057`-`062`, `dialect-parity/026`.

---

## Addendum — aggregation semantics (not numbered SEM-*, since it's beyond the TRD's own §7
enumeration of SEM-1..SEM-7; pinned here anyway because the conformance fixture suite, #1630,
needed answers that AR-8/BM-2 don't give and no other document owns)

**AGG-1. `count` aggregates non-null occurrences of the named field — never a row count.** AR-8's
`aggregation` is `(field, func)`; for `func: "count"`, the field is not decorative — `count` means
"how many rows have a non-null value for `field`", identically to SQL's `COUNT(field)` (which
already skips NULLs) and Elasticsearch's `value_count` (which already skips missing). **MongoDB's
naive `{ "$sum": 1 }` counts every document in the group regardless of the field's value and MUST
NOT be used** — it silently answers a different question the moment the aggregated field can be
null. The correct, portable Mongo form is a conditional sum:
```json
{ "$sum": { "$cond": [ { "$eq": ["$amount", null] }, 0, 1 ] } }
```
If a future host genuinely wants "count of rows in the group" regardless of nullability, that is a
`count` on the grid's own `stableKey` (never null by SEM-6/BM-2's own tiebreaker guarantee), not a
different meaning smuggled into `count` on an arbitrary field.

**AGG-2. `aggregation.alias` is set from the AG Grid `ColumnVO.id` whenever it differs from
`ColumnVO.field`; otherwise it is absent (compiler default applies).** AG Grid's `valueCols` entries
carry both an `id` (the column's identity in the grid) and a `field` (the data field being
aggregated) — when a host configures a distinct `id` for an aggregated column (a common pattern for
disambiguating two aggregations on the same field, e.g. `sum(amount)` and `avg(amount)` both keyed
off `field: "amount"`), that `id` is the label the grid UI already displays for the column and is the
only signal available for what the output key should be. The adapter therefore sets
`aggregation.alias := ColumnVO.id` **if and only if** `ColumnVO.id !== ColumnVO.field`; when they are
equal (the common case — AG Grid defaults `id` to `field` unless the host overrides it), `alias` is
left absent and the compiler's own default naming applies. This is a one-line, deterministic rule —
"is `id` distinct from `field`" — precisely so that every fixture/port computes the identical answer
from the identical `ColumnVO` shape, rather than each guessing when alias-setting is warranted.

**AGG-3. A `groupKeys` entry is a typed value (AR-7), compiled into an equality predicate against
its group column.** It is a value like any other filter value and is typed from the group column's
declared schema type before the IR is built, never left as a raw wire string.

> **Superseded in part by GRP-2 (#1640).** This rule previously also said that the drill-down match
> "follows the group column's own case-sensitivity setting (SEM-1) — it is not automatically
> exact-match". That is now **wrong**: the grouping addendum makes the drill-down, the `GROUP BY` and
> the grouped `ORDER BY` exact together, because they must agree with one another or a child level
> stops summing to its parent's aggregate, and because a collated `GROUP BY` key is not valid SQL.
> The sentence is recorded here rather than deleted silently, since the affected artifacts
> (`group-aggregation/002`-`012`, `015` on all three backends) were authored against it.

**AGG-4. ES/OpenSearch `terms` aggregation ordering (BM-3 set-filter values, and any composite group
aggregation) is pinned to ascending by key value, not the engine default.** A bare `terms` aggregation
defaults to doc-count-descending, which would return set-filter values (and, for composite grouping,
bucket order) in a different order than Postgres's `ORDER BY` or Mongo's `$sort` on the same logical
request — a user-visible list-order divergence for an operation (BM-3) whose whole purpose is
presenting a sorted list of distinct values. Compilers MUST set `"order": {"_key": "asc"}`
explicitly on any `terms` aggregation backing a set-filter-values or grouped-drill-down request.

**AGG-5. Known, accepted divergence: composite-aggregation null-bucket placement on ES/OpenSearch.**
ES/OpenSearch's composite aggregation `missing_bucket: true` (the mechanism that keeps a null group
key from being silently dropped, matching AR-8/BM-2's intent) has no `missing_order` control in the
pinned 7.10-era subset — the null bucket sorts **first** regardless of the sort direction requested,
while Postgres (`NULLS LAST`/`NULLS FIRST` per SEM-3) and Mongo (the null-bucket emulation) both honor
the requested direction. This is documented here as an accepted, host-visible divergence (per the
TRD §15 risk register's own "documented-divergence register" precedent) rather than worked around
with a client-side reorder, which would defeat server-side paging's whole purpose for the grouped
case. Fixtures exercising composite null-bucket ordering mark this explicitly rather than silently
pinning three-way-identical output that ES/OpenSearch cannot actually produce.

**AGG-6. An aggregate over a group with no non-null values: `sum` is `0`; `avg`, `min` and `max` are
`null`.** "No non-null values" covers both shapes a host can hit — a group whose every row carries
NULL in the aggregated field, and (on the backends where an aggregation runs over an empty input at
all) a group with no rows. `count` is not part of this rule and needs no clause: AGG-1 already makes
it a count of non-null occurrences, which is `0` on all four backends by construction.

*Where the four backends stand today, and who has to move.* Three of them already answer this way;
one does not:

| | `sum`, no non-null values | `avg` / `min` / `max` |
|---|---|---|
| SQL compiler | `SUM(x)` → **NULL** — the outlier | bare call → null |
| EF Core (AR-4, since #1887) | provider emits `COALESCE(SUM(x), 0.0)` → **0** | bare call → null |
| MongoDB | `{"$sum": ref}` → **0** | `$avg`/`$min`/`$max` → null |
| ES/OpenSearch | `sum` metric → **0** | `avg`/`min`/`max` → null |

So compilers targeting SQL **MUST** wrap `sum`, and only `sum`, in a two-argument null-coalesce with
a literal zero — `COALESCE(SUM(x), 0)`, which is ANSI and spelled identically by all five v1 dialects,
so it is composed in the builder rather than behind BM-1's dialect seam. They **MUST NOT**
wrap `avg`, `min` or `max`: those three already agree with the other backends, and a wrap there would
turn "this group has nothing to average" into a fabricated `0`. Mongo and Search compilers change
nothing; in particular they **MUST NOT** grow a companion count and a conditional in order to recover
a NULL.

*Why `0` and not NULL, which was the incumbent SQL answer.* NULL is **not recoverable** on the two
document stores. `$sum` and the `sum` metric return `0` for an empty set, and a genuine sum of zero is
indistinguishable from an empty one, so a NULL rule would oblige every `sum` on both backends to carry
a companion count plus a conditional on top of it. `0` costs one `COALESCE` on one backend. It is
therefore the only one of the two answers implementable on all four, which is what G3 (one logical
answer per request, whatever the backend) asks for — and it is the answer EF Core's provider already
generates unprompted.

*What this rests on, stated plainly — because no tier in this repository grades it.* An artifact
compares emitted **text**; it cannot see what a number comes back as. The four rows above are
therefore evidence of four different strengths, and collapsing them into one confident table would
be the dishonest move:

- The **SQL** row is the standard's own answer (`SUM` over an empty set is NULL) and was reproduced
  during #1886 against the SQLite database this repository's AR-4 harness already stands up. **#1888**
  is what makes it an executed case *in that harness* rather than a standalone reproduction:
  `EfCoreGroupedExecutionEqualityTests`'s case `013` compiles `group-aggregation/013` with
  `SqlQueryBuilder` and runs it against real SQLite — not the bare `SUM` this row's own name suggests,
  but the `COALESCE(SUM(x), 0)`-wrapped statement #1886 mandated, which is the SQL row's own MUST, not
  its incumbent answer.
- The **EF Core** row is measured two ways now: `EfCoreGroupingTests.An_All_Null_Group_Sums_To_Zero_And_Averages_Mins_And_Maxes_To_Null`
  (#1887, a hand-built request) and, since **#1888**, the same `group-aggregation/013` case in the AR-4
  cross-compiler harness — both assert `sum → 0` and `avg`/`min`/`max → null` as executed results,
  the second one alongside the SQL row above from the identical seeded database.
- The **MongoDB** and **ES/OpenSearch** rows are **documented engine behaviour, read from the
  vendors' documentation and not measured anywhere**. There is no live engine in this repository.

Confirming all four against real servers is the T-1b execution tier's (**#1624**), and the natural
first case is precisely an all-null group. Until that runs, this rule is a *decision* backed by
documentation, not an observation — a narrower claim than the other AGG-* rules make, recorded rather
than smoothed over.

*The ordering consequence is part of the rule, not a side effect.* GRP-4 makes a grouped level's
`ORDER BY` repeat the aggregate **expression**, so the wrap appears there too, and
`ORDER BY COALESCE(SUM(x), 0)` places a group with no non-null values among the zeroes where
`ORDER BY SUM(x)` placed it with the NULLs — i.e. wherever AR-9/SEM-3's `nullsPosition` had sent it.
Row order for such a group legitimately changes, on every SQL dialect at once. The `nullsPosition`
machinery is still emitted around the wrapped expression (MySQL's leading `ISNULL(…)` key, SQL
Server's `CASE WHEN … IS NULL`, the others' `NULLS FIRST`/`LAST`) even though it can no longer fire:
SEM-6's "no schema state licenses omitting the marker" is unconditional, and suppressing a sort key
on a nullability inference is a semantic special case no rule grants. On an `avg`/`min`/`max`
ordering key the same machinery is fully live, which is the difference the fixtures pin.

*Pinned by* every grouped SQL artifact carrying a `sum` — `group-aggregation/001`-`004`, `007`,
`012`-`015`, `020`, `021`, `023` on all five dialects, and `ag-grid-majors/004` on Postgres only —
and discriminated **in the `ORDER BY`** by `dialect-parity/024`, which orders a grouped level by an
**`avg`** while a wrapped `sum` sits beside it in the same projection. No other fixture orders a
grouped level by anything but a `sum` or a group column, so `024` is the only case that fails when
the wrap is missing from a `sum`'s `ORDER BY` **and** when it is over-applied to `avg`'s. It does not
follow that over-applying the wrap goes otherwise undetected: `AVG`/`MIN`/`MAX` appear bare in the
*projection* of `008`-`010`, `012`, `013` as well, and those fail exactly the same way `024` does if
the wrap reaches their `SELECT` list.

---

## Addendum — grouping semantics (GRP-1..GRP-6; not numbered SEM-*, for the same reason as the
aggregation addendum, and added by #1640 because BM-2's own two open contradictions could not be
settled anywhere a fixture README would be the only record; GRP-6 added by #1641 for BM-3, which is
subsidiary to BM-2 and answers the same bucket-identity question about a different construct)

BM-2 (row grouping over AG Grid SSRM) is a *protocol*, not a single query shape: one request per
expanded level, each carrying the whole group path so far. #1630's fixtures pinned that protocol's
output before anything compiled it, and left two points genuinely undecided — whether a grouped
query folds case, and whether the drill-down conjunction is IR or clause text. Both are settled
here, because a rule that lives only in a category README is a rule the next language port will
re-derive differently.

**GRP-1. One request, one level: the dispatch is `groupKeys.length` against `groupCols.length`.**
Fewer keys than columns → a **grouped level**: bucket by `groupCols[groupKeys.length]` (the next
not-yet-consumed column, and only that one — never the whole remaining list), aggregate the
`valueCols`, and restrict to the already-consumed keys. Equal → the **drill-down leaf**: every
dimension is consumed, so the answer is raw rows restricted by those keys, with no `GROUP BY` and no
aggregation (`spec/fixtures/group-aggregation/005`, `006`). More keys than columns is a malformed
request and MUST be rejected — consuming only as many as fit returns a different bucket's rows under
a label the client did not ask for.

*Where the arity check belongs.* It is a property of the **request**, not of any one backend, and
`ir.schema.json` cannot express it (JSON Schema has no way to compare two arrays' lengths) — so it
belongs in the shared `groupSpec` validator every compiler already runs, not in a compiler. Put it in
one of them and the others must each re-derive it; its failure mode is silent, so the one that
forgets returns wrong rows rather than an error.

*The colIds are client-controlled, and pass the same boundary as a filter's.* `rowGroupCols` and
`valueCols` arrive off the wire exactly as `filterModel` does, so every `groupCols` entry and every
aggregation `field` MUST pass the SC-1 allowlist, and MUST additionally satisfy SC-2's per-field
`groupable` / `aggregatable` capability flags. **A CONSUMED `groupCols` entry (#1907) additionally
satisfies `filterable`**, on top of `groupable`: the not-yet-consumed suffix is bucketed across every
value, which `groupable` alone already permits, but the consumed prefix becomes a literal drill-down
predicate (GRP-2, below) — functionally a filter condition over a different wire channel, so it is
held to the identical flag `filterModel` is, hard-failed in every mode (this is a structural colId,
not a condition — the same reasoning the paragraph above already gives for `groupCols`/aggregation
fields). See the BM-3 addendum's own remarks on `filterable` now spanning three surfaces (the
ordinary filter tree, where Lenient MAY still strip it; `setValuesRequest.colId`; and this one) and
why only the filter tree keeps Lenient's carve-out.
**SC-1's Lenient mode does not apply to either.** Lenient may silently drop an unknown *condition*,
because the result merely widens and a host can knowingly accept that; neither of these is a
condition. Dropping a `groupCol` changes which level the response describes — and, with its
`groupKey`, returns a different bucket's rows under the label the client asked for, arriving
silently at exactly what the paragraph above rejects loudly. Dropping an aggregation hands the grid
a response missing the key it asked for, i.e. a column of blanks indistinguishable from real nulls.
Both are rejected in every mode. Pinned by `spec/fixtures/adversarial/003-unknown-colid-row-group`.

**GRP-2. A grouping request is *exact* on the protocol's own keys: no case-folding mechanism is
spelled on any of them.** There are exactly three: the `GROUP BY` key, the drill-down `WHERE`
predicates a consumed `groupKeys` entry compiles into, and a **grouped level's** `ORDER BY` keys.
All render bare, whatever the column's declared `caseSensitivity`. So `"EMEA"` and `"emea"` are two
buckets with two unambiguous labels — which is also what AG Grid's own client-side grouping does.
(A fourth key answers to this rule without being part of BM-2's protocol at all: BM-3's
`SELECT DISTINCT` column and its `ORDER BY`. GRP-6 makes the argument for it; everything below
applies to it unchanged.)

*Why the three must agree, and why "exact" is the only coherent answer.* Bucket identity is decided
by the `GROUP BY`; the drill-down that expands a bucket must select **exactly** the rows that
produced it, or the child level stops summing to the parent's aggregate; and the `ORDER BY` of that
same level orders the buckets the `GROUP BY` just produced. That rules out every mixed
answer. Between the two coherent ones, "collate everywhere" is not merely undesirable, it is
**invalid SQL**: `SELECT "segment" … GROUP BY "segment" COLLATE craticula_ci` groups by an
expression the select list no longer contains, and Postgres and SQL Server both reject it. Exactness
also avoids inventing a label rule for a folded bucket (is it `EMEA` or `emea`?), which nothing in
AG Grid's wire contract supplies.

*Scope — deliberately narrow, and narrower than #1640's first draft.* GRP-2 governs the keys that
**decide or reproduce bucket identity**, not "every key of a grouping request". Two things inside
one are outside it:

- **A user's own filter.** A pre-aggregation row filter (AR-5) selects the rows that will be
  bucketed and has no say in bucket identity, so it keeps SEM-1's per-field mechanism. One statement
  may therefore compare the same column twice by two mechanisms — `WHERE ("region" = $1 AND "region"
  ILIKE '%' || $2 || '%' ESCAPE '\')` — and that is correct, not the contradiction SEM-1 forbids:
  SEM-1 governs how a field's *values* are compared, GRP-2 governs *bucket identity*, a question
  SEM-1 never asks.
- **A drill-down leaf's `ORDER BY`.** #1640's first draft keyed the `ORDER BY` rule on "the request
  carries a `groupSpec`", which swept the fully-consumed leaf in with it; its review found that
  wrong. A leaf has no `GROUP BY` and no buckets. It orders raw rows by whatever column the user
  picked, which need not be a group column at all — `group-aggregation/005` sorts on `product`,
  neither a group column nor a group key — so the bucket-identity argument above simply does not
  reach it. It is an ordinary row query in this respect and **SEM-1 governs it**, collation
  included. Leaving it bare was also a live defect and not merely an inconsistency: a leaf that
  filters `lastName eq "smith"` and sorts on `lastName` would emit a collated `WHERE` beside a bare
  `ORDER BY` — one field, two mechanisms, one statement, which SEM-1's third Must-NOT forbids
  outright. Its drill-down `WHERE` is still exact, because that IS one of the protocol's keys.
- **A leaf that sorts on a *consumed* group column**, which is the boundary between the two bullets
  above. It emits an exact `WHERE "region" = $1` beside a collated `ORDER BY "region" COLLATE
  craticula_ci` — one field, two mechanisms, one statement, and yet correct: the `WHERE` has pinned
  that column to a single group key, so the ordering is a no-op over the returned rows and there is
  no comparison for the two mechanisms to disagree about. Stated because it looks exactly like the
  SEM-1 violation the bullet above exists to prevent, and a reviewer who spots it should be able to
  find it already answered rather than re-derive it.

The one thing that must never happen is the mix SEM-1 does forbid: a **grouped level** whose
`GROUP BY` and `ORDER BY` disagree with each other, which GRP-2's per-*statement* scope removes.

*Accepted divergence, and the host obligation it creates.* "Spell nothing" means "exact" only where
the engine's own default already is. It is on Postgres (deterministic default collation) and SQLite
(`BINARY`). It is **not** on SQL Server / Azure SQL (stock `SQL_Latin1_General_CP1_CI_AS`), MySQL /
MariaDB (a `_ci` family default), or **Oracle** (default column collation `USING_NLS_COMP`, resolved
through the *session*'s `NLS_COMP`/`NLS_SORT` — the same fact SQL-6 cites as why the case-**sensitive**
direction must be spelled `COLLATE BINARY` there): on all three, a grouped string column folds case
and `"EMEA"`/`"emea"` land in one bucket. A host that wants exact buckets on those engines must
declare the groupable column with a binary / `_as_cs` / `BINARY` collation in its DDL — or, on
Oracle, run the session with `NLS_COMP = BINARY` (the default, and what the execution tier runs on; a column-level `COLLATE
BINARY` needs `MAX_STRING_SIZE = EXTENDED`, measured in SQL-6 below) — the same kind of obligation SQL-6 already records
for MySQL's case-sensitive direction, and for the same reason (no portable in-statement spelling
exists that does not break the `GROUP BY`). Recorded here as a documented divergence rather than
papered over; the execution-equality tier (T-1b, #1624) is what can grade it, and T-1a cannot see it
at all.

*Oracle is on that list for exactly the reason SQL-6 puts it there, and the two must not drift apart.*
A bucket-identity key resolves to `NotApplicable`, so on Oracle it emits nothing — while a
`caseSensitivity: "sensitive"` **filter** on the same column emits `COLLATE BINARY`, precisely because
bare is not exact there. A host running `ALTER SESSION SET NLS_COMP = LINGUISTIC NLS_SORT = BINARY_CI`
therefore gets a drill-down `"region" = :p1` that folds case, so expanding the `"EMEA"` bucket also
returns `'emea'`'s rows and the children stop summing to the parent's aggregate — silently, on
well-formed SQL, and invisibly to T-1a. Stated because the two paragraphs sit four lines apart in this
document and an earlier draft of #1642 had them disagreeing.

*Per-backend consequences beyond SQL.* ES/OpenSearch drops the `case_insensitive: true` parameter
from a drill-down `term`, leaving `{"term": {"<field>.keyword": {"value": "EMEA"}}}`, the same
exact-term form `dialect-parity/014` already uses; a composite `terms` source over a `keyword` field
is exact already and needs nothing. Its per-clause granularity means it can satisfy the scope
carve-outs above exactly — a bare drill-down `term` beside a `wildcard`/`case_insensitive` user
filter, and beside a leaf `sort` on a `search.normalizedSubField`, all in one request.

*Accepted divergence #3 — MongoDB cannot satisfy this rule and the carve-outs above at the same
time.* MongoDB's `collation` is a **query-level** option: it governs `$match`, `$group` and `$sort`
together, and there is no per-stage form. So a grouping request whose scope carve-outs ask for a
case-insensitive comparison somewhere and an exact one somewhere else has no pipeline that expresses
both, and the "a grouping request's pipeline carries no `collation` at all" shorthand an earlier
draft used hid a real choice rather than describing a consequence-free one. Three shapes reach it:

- a grouped request carrying a **user `eq`/`in` filter** on a case-insensitive string (SEM-1 wants
  the collation; the `GROUP BY` and drill-down forbid it),
- a **drill-down leaf** sorting a case-insensitive string (SEM-1 wants it; the drill-down `WHERE`
  forbids it) — which `group-aggregation/005` is, sorting on `product`. **Not `006`**, despite
  #1640's re-authoring touching the two together: `006` carries no `sortModel`, so its only key is
  SEM-6's appended tiebreaker, which resolves exact and never wanted a collation in the first
  place — and
- a **BM-3 distinct-values request** (GRP-6) carrying a user filter on some *other* case-insensitive
  string — SEM-1 wants the collation for that `$match`, while GRP-6(a)'s exact buckets forbid it on
  the `$group` that computes the distinct set. This one is easy to miss because the conflicting pair
  sits on **two different fields**: the collation is wanted for `segment` and forbidden for `region`,
  yet MongoDB has only one switch for both.

**The protocol's keys win, on all three: the pipeline carries no `collation`.** Bucket identity is a
correctness property — get it wrong and a child level's rows stop summing to the parent's aggregate,
silently — while a case-folded filter or sort is a narrower, visible difference in which rows come
back and in what order. So on MongoDB a user's own filter compares case-**sensitively**, and a
leaf's `$sort` orders case-sensitively, where the five SQL dialects collate both. Recorded here as a
documented, host-visible divergence, in the same register as GRP-2's SQL Server/MySQL DDL obligation
and AGG-5. **Exactly three fixtures reach it, and the list was wider than the truth until #1643
compiled the Mongo arm and could check:** no fixture reaches the first shape — `group-aggregation/023`
is the only case in the suite carrying both a consumed `groupKeys` and a `filterModel` (#1644's review
pass authored it for GRP-5's clause order), and its filter is on two `int64` columns, so nothing in it
ever wants a collation; **`005`** pins the second — its leaf sorts on `product`, a
case-insensitive string, while `006`'s only sort key is the exact-resolved SEM-6 tiebreaker, so `006`
never wanted a collation and is not an instance of the divergence at all; and **`017`/`022`** pin the
third, `016`/`018`/`019` carrying no collation-mechanism construct in the first place (`016` and
`019` carry no filter at all, and `018`'s only predicate is its search prefix, which GRP-6(b) makes
an ordinary `startsWith` and SEM-1 therefore assigns the *pattern-match* mechanism). The
distinction is not bookkeeping: "suppressed a collation it wanted" and "never wanted one" are
different compiler states, and only the first is evidence about this rule.
`CrossCompilerGroupingTests.The_Divergence_Is_Reached_By_Exactly_The_Three_Fixtures_The_Spec_Names`
asserts the set against this sentence. The execution-equality tier (T-1b, #1624) is what can grade
the divergence itself; T-1a cannot see it.

*Accepted divergence #4 — MySQL cannot serve exact buckets and a case-insensitive filter from one column.*
MySQL spells no collation in SQL (SQL-6), so one column has one collation: the binary one GRP-2 requires of a
groupable string column for exact buckets, or the `_ci` one SEM-1's case-insensitive filters and prefixes rely on.
A host that declares the groupable column binary (as the execution tier does) therefore gets case-**sensitive**
filters and prefixes on it, on the BM-3 requests that combine a distinct set with a user filter or search
prefix on a case-insensitive string: `group-aggregation/017`, `018` and `022`, each declaring it as an XEQ-4 `rows`
divergence for `mysql`.

*How the third shape was found, because the same trap is waiting for every other backend with a
query-level switch.* `017`'s Mongo arm was authored in #1641 carrying a query-level `collation`
beside a `$group` on `region` — the exact combination #1640 had already stripped from every grouped
arm, reintroduced on a query nobody thought of as "grouped" because it carries no `groupSpec`. The
SQL arms were right the whole time; only Mongo, where one option governs every stage at once, could
express the contradiction at all. **The test is not "does this request have a `groupSpec`" but "does
this pipeline compute a distinct set" —** and under GRP-6 a BM-3 request always does.

**GRP-3. A grouping request names its output columns at every level; an ungrouped one does not.**
A grouped level projects `<group column> AS <logical field name>` — aliased **always**, even when
the physical column and the logical name coincide — followed by one aggregate per `valueCol`. A
drill-down leaf projects every field the schema declares, in declaration order, aliased back to its
logical name **only where the physical column differs** (`"fiscal_year" AS "fiscalYear"`, but plain
`"region"`). *"Declaration order" means the order of the `fields` object's members in the schema
**document***, and an implementation must take it from there: the natural shortcut — enumerating
whatever map the schema was deserialized into — is a language-specific accident (`Dictionary<K,V>`
in .NET, `dict` in Python and `Map` in JS happen to preserve insertion order; Go's `map` and Java's
`HashMap` emphatically do not), and `group-aggregation/005`/`006` compare this column list byte for
byte. `SELECT *` is not available to the protocol at either level: it returns *physical*
column names, and a grid that asked for `fiscalYear` cannot read a `fiscal_year` key. An **ordinary
row query** is out of GRP-3's scope and still renders `SELECT *`. Widening it belonged to the export
feature, which owns the request-supplied column list any general projection rule has to compose with
— and **EXP-1(b) has now settled it, narrowly**: an *export* names its columns, an ordinary row
query still does not. So this sentence is no longer a deferral; the only projection a request can add
is an export's. (Until #1650 this sentence cited that column list as *EXP-3*, and so did its
restatement in `SqlQueryBuilder`. The TRD's EXP-3 is **streaming**; the column list is a clause of
**EXP-1**, which is why the addendum numbers it EXP-1(b).) *"Ordinary row query" and not
"ungrouped"*: BM-3's distinct-values query also carries no
`groupSpec` and is emphatically not `SELECT *` — it projects the one target column, unaliased
(GRP-6(e)). The same distinction as in SEM-6's first blockquote, for the same reason.

**GRP-4. A grouped level orders by what it projects, and breaks ties on its group column.**
- A sort key naming an **aggregated column** orders by that aggregate's **expression**
  (`ORDER BY SUM("amount")` — `ORDER BY COALESCE(SUM("amount"), 0)` for a `sum`, since AGG-6), never
  by the raw column, which the projection does not contain. The key
  is matched against `alias ?? field`, i.e. AGG-2's `ColumnVO.id` reconstructed — the grid sends the
  *column's* id, and AGG-2 sets the alias from that id exactly when it differs from the field.
- **Repeat the expression; do not refer back to the output name.** An output column name is only
  *conditionally* usable in `ORDER BY`: PostgreSQL's `SELECT` documentation states that it "has to
  stand alone, that is, it cannot be used in an expression", and T-SQL binds the same way — an alias
  inside a `CASE` resolves against the `FROM` scope and raises "Invalid column name". It rarely
  stands alone here, because SEM-3's null placement is **emulated** on two of the five dialects
  (`CASE WHEN … IS NULL THEN 1 ELSE 0 END` on SQL Server, `ISNULL(…)` on MySQL), so the ordering
  target sits inside an expression on both. The expression form is unambiguously legal in either
  position on all five engines, so it is used uniformly rather than only where the wrapper forces
  it — a per-dialect split would make a *semantic* difference look like a spelling one. (#1640's
  first draft emitted the name; its review found `020`'s mssql and mysql arms were the T-SQL failure
  above.) Mongo is unaffected and keeps the name: after `$group` the aggregate is a real field of the
  document a later `$sort` stage reads, not an alias in a scope. **Search does not order a grouped
  level by an aggregate at all** — the request has no rendering there and is refused (OSE-11(c)), so
  this bullet has no Search arm to reach.
- An aggregate with no alias takes the compiler default **`<field>_<func>`** (`amount_sum`,
  `id_count`) — stated here because it lands in query text as an identifier and every port must
  choose the same one. It names the aggregate in the projection and in the response, which is what
  the grid reads it back by; only the `ORDER BY` avoids it.
- SEM-6's tiebreaker still applies, but the **group column** plays the stable key's role: the
  schema's `stableKey` is not in the grouped projection, so ordering by it is invalid SQL, while the
  group column's values are unique across the level's rows by construction. Appended last, ascending,
  nulls last, and not appended twice when the (reduced) sort already reaches it — SEM-6's own rules, unchanged.
- A sort key that is neither the group column nor an aggregate output MUST be rejected rather than
  rendered; the engine would refuse the statement anyway, and a compiler error names the reason.
  **This is a statement about the IR's colId space, not AG Grid's** — see AG-6 below, which is what
  makes the two the same space by the time a compiler sees them.
- **A sort key that matches MORE THAN ONE aggregation's column id MUST be rejected too, not resolved
  to the first (#1886).** AGG-2's alias rule and this bullet's own `alias ?? field` match are
  independent of AGG-1's output-name uniqueness: two unaliased functions over one field
  (`sum(amount)` + `avg(amount)`, AGG-2's own example) have distinct output names — `amount_sum`,
  `amount_avg` — while sharing the column id `amount`, because that id is `alias ?? field`, never
  `alias ?? "<field>_<func>"`. A sort key naming `amount` therefore does not say which of the two the
  client means; a compiler that quietly picked one (the first declared, say) would produce the exact
  plausible-looking wrong statement the bullet above already refuses for a colId outside the
  projection entirely. Pinned by unit tests alone, there being no artifact for a request that does
  not compile (SQL-7(b)'s precedent) — a *grouped* request whose only aggregates collide on column id
  has no sort naming that id in the fixture suite, so nothing here moves an artifact.
- A drill-down **leaf** is an ordinary row query in this respect and keeps SEM-6's `stableKey`.

**AG-6. AG Grid addresses a grouped sort through the row-group *display* column, whose colId the
adapter must resolve before the IR is built.** `sortService.getSortModel()` writes
`colId: column.getId()`, and for the auto group column that id is
`columnUtils.ts`'s `GROUP_AUTO_COLUMN_ID = 'ag-Grid-AutoColumn'` — or, under
`groupDisplayType: 'multipleColumns'`, `` `${GROUP_AUTO_COLUMN_ID}-${rowGroupCol.getId()}` ``
(`autoColService.createOneAutoCol`). Neither matches any `GridSchema.fields` key, because it is a
colId in **AG Grid's** column space rather than the host's, and the SSRM sort listener passes it to
the server untouched. Resolving it is therefore the adapter's job by definition — nothing downstream
knows that AG Grid mints display columns — and until #1640's review nothing did it, which made the
single most common grouped-grid interaction, clicking the group column's header, a hard failure
against GRP-4's rejection above.

- **`ag-Grid-AutoColumn`** shows the whole group path, so it resolves to the group column *this
  request's own level buckets by*: `groupCols[groupKeys.length]`, GRP-1's dispatch exactly.
- **`ag-Grid-AutoColumn-<id>`** names its source column, and the suffix is that column's
  `ColumnVO.id` — looked up against the `rowGroupCols` entries' **ids**, which differ from their
  `field`s whenever a host gives a grouped column its own id.
- On a **drill-down leaf** every group column is consumed, there is no level to name, and every row
  shares the whole group path — so the key would order nothing and is **dropped**. SEM-6's
  tiebreaker still guarantees a total order.
- A suffix naming no `rowGroupCols` entry, and an auto-column colId on a request carrying **no group
  state at all**, are both left **unresolved and carried through verbatim**, so each fails downstream
  as the unknown colId it is. Dropping either is worse than mapping it: the response then comes back
  in a different order from the one the grid's own header shows, with no rejection and no log, and the
  auto-column prefix would be the only colId in the adapter with such a path — every other bogus colId
  reaches a compiler and is refused there. The refusal does come from the **compiler**, which resolves
  each sort field against the schema; sort colIds have no allowlist stage of their own yet (SEM-6's
  own note about the orchestrator that does not exist applies here too), so "it reaches the field
  allowlist" — which an earlier draft of this rule said — is aspirational rather than true.
- **Collapse the coupled set afterwards.** AG Grid's sort *coupling*
  (`gridOptionsUtils._isColumnsSortingCoupledToGroup`, true unless `treeData` or a custom
  `autoGroupColumnDef.comparator`) sets the sort on `[column, ...sortableRowGroupColumns]` — the
  display column **and every source column** `showRowGroupColsService.getSourceColumnsForGroupColumn`
  returns for it — and `getIndexedSortMap` gives them all the display column's index, so they are all
  emitted. For the **default single display column that is every row-group column**, not just the
  level it resolved to: `autoColService.createBaseColDef` sets
  `showRowGroup: rowGroupCol?.getColId() ?? true`, i.e. the literal `true`, and that service answers
  `true` with `rowGroupColsSvc.columns.slice(0)`. So with `rowGroupCols: [region, segment, product]`
  one user click emits `[ag-Grid-AutoColumn, region, segment, product]` — 1 + N, not a pair — and AG
  Grid means **one logical key** by it. Collapse the whole coupled set into the entry the display
  column resolved to, keeping the **first** occurrence so the user's key precedence is preserved.
  A **suffixed** display column is the other arm of the same service method: its `showRowGroup` is one
  column's id, so its coupled set is that one column and only it collapses. Scoped to entries the
  resolution itself accounts for, and only after the display column that named them: a key the client
  sent on its own is left alone. Pinned by `group-aggregation/021`.
  *(Keeping the surplus entries is not a cosmetic duplicate — with the payload above they leave the
  request sorting on a column the drill-down has pinned to one value and on a level this response does
  not produce, both of which GRP-4 rejects outright.)*

**GRP-5. The drill-down is materialised as real IR, and merged with the user's filter through the
same merge primitive as everything else.** Each consumed key becomes an `eq` comparison node against
its group column (AGG-3's typed value), the set is wrapped in an `and` node when there is more than
one, and the result is `and`-merged with the request's own filter tree exactly as `customFilters`
and static filters are (AR-5/OQ-11's one merge primitive). It is **not** assembled as clause text.

*Consequence, and the contradiction this closes.* Because it is ordinary IR, SQL-2's "every composite
wraps" applies to it with no exception: two or more consumed keys render `("region" = $1 AND
"segment" = $2)`, wrapped. #1630's fixtures had them bare, on the reading that a synthesised
conjunction is not an IR construct; that reading is rejected, because any compiler that reuses its
filter renderer for the drill-down — which is every sensible one — gets the wrapped form for free.
A single consumed key is not a composite and does not wrap.

*Order.* The drill-down leads: `WHERE (<group path> AND <user filter>)`. Nothing in the fixture suite
pins this (no case carries both), and it is stated rather than left open because the choice is
visible in `params`, which is compared exactly.

*Provenance must survive the merge.* The two halves are ordinary IR and indistinguishable by shape —
a `groupKeys` match on `region` and a user `eq` on `region` are the same node — yet GRP-2 gives them
different answers. **A compiler must therefore carry the distinction itself and must not try to
recover it from the merged tree.** Reference identity happens to work and is a trap: any later change
that rebuilds nodes between synthesis and rendering (flattening nested `and`s, or routing the group
columns through an allowlist/coercion stage, both of which mint new nodes) silently gives the
drill-down the user's mechanism, `"EMEA"` starts matching `"emea"`, and child rows stop summing to
the parent — with no error and no failing artifact. Rendering each half under its own resolution
context and composing the wrapped `and` from the two results is equivalent, byte for byte, and has no
such invariant to break.

*Resource limits (SEC-3), on two levels.* `groupKeys` is as client-controlled as any filter value, so
N consumed keys are N leaf predicates that must be counted against the SEC-3 leaf/depth budget
**together with** the user's filter, over the merged tree. This is an amplification BM-2 introduced:
before it, group state was ignored entirely. But that check only runs where the filter pipeline runs,
and a host may hand a `groupSpec` straight to a compiler — so `ir.schema.json` additionally carries a
**structural** `maxItems` on `groupCols` (and, since GRP-1's cross-array comparison is inexpressible
there, on `groupKeys` too), enforced by the same shared validator GRP-1's arity rule lives in. That is
an amplification cap in the register of `fieldName.maxLength`, deliberately **not** one of SEC-3's
named, host-configurable limits — its value is fixed at SEC-3's own *default* max-leaves, so a
structurally valid `groupSpec` can never exceed that budget by itself, while a host configuring
something tighter still gets the tighter answer from the runtime validator.

*Type coercion (SEM-5).* A `groupKey` is a filter value, so it must satisfy its group column's
declared type before a compiler sees it — a compiler that binds it is entitled to assume this, exactly
as it does for a filter value. It differs from a filter value in one respect that decides *how*: the
wire already carries each key **pre-typed** as a `typedValue` (`$defs/groupSpec` requires it, and a
frontend adapter resolves the raw wire string using the group column's declared type before building
the request), so there is nothing untyped to parse. A variant that disagrees with the declared type is
therefore a **wrongly-typed request**, rejected at the `typeCoercion` stage with SEM-5's own
`uncoercible-value` reason — never repaired, and never allowed to surface further downstream as a
compiler precondition failure on ordinary client input.

**GRP-6. BM-3's distinct-values query is a bucket query, and its cap is a ceiling rather than a
page.** A set filter asks the server "which values may I offer for this column, given the filters
currently in effect?". The answer compiles to `SELECT DISTINCT <col> … ORDER BY <col> <cap>` (DISTINCT is the default spelling; SQL Server uses
`GROUP BY <col>` instead, GRP-6(f); a
`terms` aggregation on ES/OpenSearch, a `$group` on `_id` on MongoDB), and six things about it are
decided here because each of them is a place a port would otherwise guess differently.

*(a) The `DISTINCT` key and its `ORDER BY` are exact — GRP-2's rule, reached by GRP-2's argument.*
`SELECT DISTINCT` computes a distinct set exactly as `GROUP BY` does; it is a bucketing operation
whose buckets happen to have no aggregate attached. A collated one folds `"EMEA"` and `"emea"` into a
single entry whose label is unspecified — and that entry is precisely what the grid hands straight
back, as an `in` value in the column's own filter or as a `groupKey` into a grouped request, where
GRP-2 matches it **exactly** and it selects neither original row. So the values a set filter offers
must be the values the data actually holds, one entry per distinct spelling. Read as an ordinary
query instead, SEM-1 would collate both positions; that reading is rejected, and the reason is the
same one GRP-2 gives: SEM-1 governs how a field's *values* are compared, not what a bucket *is*.
The consequences GRP-2 records carry over verbatim — including that "spell nothing" is exact only
where the engine's own default already is, so exact set-filter values on SQL Server and MySQL are the
same host DDL obligation, gradeable only at the execution tier (T-1b, #1624).

*(b) The target column's own filter is dropped; every other column's is honoured.* This is BM-3's
defining semantic and the AG Grid convention it names. A value list narrowed by the selection already
made on its own column collapses to what is already selected, and the user can never widen it again.
Everything else in the filter model still applies, so the list stays consistent with the rows the grid
is showing. **Where it happens matters**: it is a semantic rule every backend shares, so it belongs in
the request pipeline, not in one compiler and not in a frontend adapter — a host building the IR
directly must get it too. Conditions are pruned, not branches: `(region eq "EMEA" AND segment eq
"Enterprise")` targeting `region` leaves `segment eq "Enterprise"`, and a `not` whose only condition
was on the target vanishes with it rather than becoming a negation of nothing. Pinned by
`spec/fixtures/group-aggregation/017`, whose artifacts are byte-identical with and without the
`region` entry in its `filterModel` — which is the whole point of the fixture and, until #1641, was
not true of it: it carried no `region` filter at all and therefore tested nothing.

*(c) The search prefix is an ordinary `startsWith` predicate on the target column.* The set filter's
inline search box narrows the candidate values; modelled as IR it is a `startsWith` comparison
carrying the raw text, so SEM-1 picks the field's own mechanism for it and SEM-7's escaping applies
unchanged — a literal `%` typed into the box cannot widen into a wildcard. It is therefore **not**
exempt from (a)'s exactness in the way that looks contradictory: on the SQL dialects and on MongoDB
one statement legitimately matches the column case-insensitively and orders it exactly, which is
GRP-2's own first carve-out (a filter selects rows, it does not decide bucket identity) applied to a
single column. *Order:* the user's filter leads and the prefix trails —
`WHERE (<filter model, minus this column> AND <prefix>)`. It was stated here rather than left open
because the choice is visible in `params`, which is compared exactly, and #1641's review then gave it
an artifact of its own: `spec/fixtures/group-aggregation/022` carries a filter on another column, the
target column's own filter, and a `searchPrefix`, all in one request. (It is also the only case where
the exclusion and the prefix act on the **same** column, which is what makes "prune the model, then
inject the prefix" distinguishable from "prune the finished tree".) A prefix against a column that is
not declared `string` has no meaning and is a wrongly-typed request, rejected at the `typeCoercion`
stage with SEM-5's `uncoercible-value`.

> **Superseded in part by OSE-12 (#1644).** Three claims above were written before a compiler for the
> third backend existed and are false there:
> - *"no backend needs a second prefix-matching path"* — **OpenSearch/Elasticsearch does.** OSE-12
>   compiles this predicate to the `terms` aggregation's `include`, a **Lucene regex** evaluated at
>   aggregation time, which is a third pattern language: different from the `wildcard` query's syntax
>   and different again from PCRE2. Its escape alphabet is MDB-11's, not SEM-7's.
> - *"one statement legitimately matches the column case-insensitively and orders it exactly"* — not
>   on that backend. `include` has **no case-insensitivity option** in the pinned subset, so the
>   prefix matches case-**sensitively as typed** where Postgres's `ILIKE` and Mongo's `$regex`/`"i"`
>   fold. That is an accepted divergence in AGG-5's register, recorded in OSE-12 and in
>   `group-aggregation/018`'s description, and asserted as an expected difference by
>   `CrossCompilerGroupingTests`.
> - *"the order is now pinned on **seven** backends"* — on **six**. `022`'s Search arm carries no
>   query-level prefix at all: the prefix leaves the query entirely and becomes `include: "eu.*"`
>   inside `aggs`, so there is no sequence there for a port to get backwards. The `params` argument
>   for stating the order still holds on the five SQL dialects and on MongoDB's `$and`.

*(d) The cap is applied, never enforced, and never absent.* The compiled limit is
`min(requested ?? default, maximum)`, from two host-configured SEC-3 numbers: a **default** for a
request that asks for no cap of its own, and a **maximum** no request may exceed. A client asking for
more values than the host will serve has not malformed anything — a set filter over a
high-cardinality column asks for as many as it can get by design — so the server clamps and answers
rather than rejecting; `group-aggregation/019` requests 50,000 against a 10,000 maximum and compiles
to 10,000, while `016`-`018` request none and compile to the 1,000 default. The two numbers are
separate knobs, because they answer different questions (what a quiet client gets versus what the
loudest one may ever get) and a host raising the ceiling for one explicit request has not agreed to
send that many values to every set filter that opens. "No cap" is not an available answer at all.

*(e) It is a cap, not a page — so there is no offset, and no tiebreaker.* The list is fetched once;
there is no second page. So the compiled statement carries the row limit **alone**: `LIMIT $1` with no
`OFFSET`, `$limit` with no `$skip`, `"size"` with no `"from"`. On engines whose row-limiting syntax
cannot stand alone this is a real per-dialect difference rather than a shortened clause — T-SQL has no
`LIMIT`, and its `FETCH NEXT` is illegal without an `OFFSET` — so a `Dialect` seam needs its own
member for it, distinct from the paging clause:

| Dialect | Row cap | Parameters bound |
|---|---|---|
| Postgres | `LIMIT $1` | 1 |
| MySQL / MariaDB | `LIMIT ?` | 1 |
| SQLite | `LIMIT ?` | 1 |
| SQL Server | `OFFSET 0 ROWS FETCH NEXT @p1 ROWS ONLY` | 1 — the `0` is **literal** |
| Oracle (#1642) | `FETCH FIRST :p1 ROWS ONLY` | 1 |

SQL Server's zero is written rather than bound because it is not a value the request carries: it is
the syntax that makes "no offset" expressible on an engine whose `FETCH` requires one, in the same
register as the `'%'` anchors and the `ESCAPE` character a compiler already emits as literals. Oracle's
row is a genuinely **fifth** answer and not SQL Server's with a different placeholder style — a
**third clause family** across the five: its row-limiting clause admits a bare `FETCH FIRST` with no
`OFFSET` before it at all, so it needs neither that literal zero nor Postgres's `LIMIT`. A port that
assumes T-SQL's spelling generalises to every `FETCH` engine emits an `OFFSET 0` Oracle does not want
and fails the arm. Every dialect therefore binds exactly one parameter here,
and `params` stays identical across the five arms of a BM-3 fixture. (`SELECT DISTINCT TOP (@p1) …` is idiomatic T-SQL and is deliberately not used: it
would put the cap in the select list, giving one engine a different statement shape.)

For the same reason SEM-6's tiebreaker does **not**
apply: the distinct column's values are unique across the result rows by construction, and the
schema's `stableKey` is not in the projection at all, so ordering by it would be the invalid SQL GRP-4
avoids at a grouped level. The single `ORDER BY` key is the distinct column, ascending, nulls last.
The projection carries **no alias**, unlike GRP-3's: the response is one column of scalars, not rows a
grid maps by key, so there is no name for a client to look anything up by.

*(f) SQL Server spells the distinct set `GROUP BY`, not `SELECT DISTINCT`.* T-SQL refuses a
`SELECT DISTINCT` whose `ORDER BY` item is not a select-list item (msg 145), and the nulls-last key
SEM-3 requires on SQL Server is the expression `CASE WHEN <col> IS NULL THEN 1 ELSE 0 END`. So on SQL
Server (and only there) the distinct-values statement is
`SELECT <col> FROM <source> [WHERE <tree>] GROUP BY <col> ORDER BY <SEM-3 key over <col>>
OFFSET 0 ROWS FETCH NEXT @p1 ROWS ONLY`; the `ORDER BY` expression is legal because it is a function of
the grouping column alone. `GROUP BY <col>` computes exactly the set `SELECT DISTINCT <col>` does, so
(a)–(e) apply unchanged: the key is exact (no collation folded), the `WHERE` tree and search prefix are
as before, the ordering is ascending nulls last, the cap is the same literal-zero `OFFSET`/`FETCH` with
one bound parameter, and `params` is unchanged. Every other dialect keeps `SELECT DISTINCT`. The
mssql arm of a BM-3 fixture is therefore the one place the statement shape differs from the other four.

*The target `colId` is client-controlled, and no mode may drop it.* It passes the SC-1 allowlist in
**every** schema mode, on GRP-1's reasoning taken one step further: a `groupCol` that Lenient dropped
would at least leave a differently-shaped answer, whereas the `colId` here *is* the question — drop it
and a compiler has no column to select, while an empty value list would tell the grid that the column
has no values rather than that the server declined to say. The capability flag it is held to is SC-2's
`filterable` (a set filter's value list is the filter UI's own data source, so `groupable` and
`sortable` are the wrong questions even though the compiled query buckets and orders the column) —
**#1872** enforces the identical flag on the ordinary filter path too, so a host can no longer refuse
a column's set-filter values while still honouring that same column's `filterModel` entry. **#1907**
extends it to a third surface: a CONSUMED `groupCols` entry (GRP-1, above) is likewise held to
`filterable`, since a `groupKeys` drill-down predicate is functionally a filter condition arriving
over a different wire channel.

**The three paths are NOT all held to the same Lenient-mode rule, deliberately (#1872, #1907).** On
the ordinary filter path, a `filterable:false` colId referenced in `filterModel`/`customFilters` is
treated exactly like an unknown one: Strict rejects it, Lenient silently strips the condition — it is
still only a *condition*, and dropping one only widens the result set, the trade SC-1's Lenient mode
already exists to let a host accept. As a `setValuesRequest.colId`, or as a CONSUMED `groupCols`
entry, no mode may drop it, for the identical reason the paragraph above gives for the plain
unknown-field case: each one *is* the question (or, for a consumed key, changes which bucket's rows
come back under the label the client asked for), not a condition narrowing it, so there is no
narrower answer left to give once it is gone.

**GRP-7. A `nullValue` group key drills into the null group: `eq` against it is the null test, on every backend.**
A grouped level buckets rows whose group column is null into **one** group (AR-8/BM-2; GRP-4 sorts it with
`nullsPosition`), so the level below it must be reachable: `groupKeys` carries that group's key as a `nullValue`
(AR-7), and GRP-5 turns it into `eq` against the group column. Compiled as ordinary equality it expands nothing: SQL's
`= NULL` matches no row, an engine's `term` with a null value is refused, and a compiler that binds it as a parameter
answers 0 rows where MongoDB, whose `$eq: null` is the null test, answered the group's rows. The rule that replaces all
of those: **`eq` with a `nullValue` operand selects exactly the rows whose column is null**, with no bound parameter (the null test
already is the answer).
It selects `NULL` and nothing else: the empty string is a different group at a grouped level (`blank` would merge the
two, and the child level would then no longer sum to its parent's bucket), so `eq null` is **not** `blank`.

| Backend | Rendering |
|---|---|
| SQL (all five dialects) | `<col> IS NULL` |
| MongoDB | `{<path>: {$eq: null}}` (matches null and a missing path, the same set MDB-8's null bucket holds) |
| ES / OpenSearch | `{bool: {must_not: {exists: {field}}}}` on the raw field |
| EF Core | `column == null`, which EF translates to `IS NULL` |

Every other operator against a `nullValue` keeps its meaning (SEM-2's null-inclusive `neq` among them, a bound NULL
parameter that matches no row on SQL, and EF's refusal): GRP-7 gives the null test one spelling, `eq`, and nothing else, because
GRP-5 emits nothing else. A leaf drill-down, a grouped level below a
null key, and an export of a drilled group (EXP-2) all inherit it, because they all read the drill-down GRP-5 builds.
Fixtures `group-aggregation/024` (leaf rows under the null key) and `/025` (a grouped level under a null first key)
pin it, with a row whose key is the empty string beside the null ones.
On Oracle that row is not a different group: SQL-7 stores `''` as NULL, so `IS NULL` selects it with the null group and both
fixtures declare an XEQ-4 `rows` divergence for `oracle` (XEQ-2 requires the entry).

**Cross-links.** `$defs/groupSpec` (`groupCols`, `groupKeys`), `$defs/aggregation`,
`$defs/sortItem`, `$defs/setValuesSpec`, AGG-1..AGG-4 (AGG-4 pins the `terms` ordering GRP-6(a)'s
ES/OpenSearch arm depends on), SEM-1, SEM-5, SEM-6, SEM-7, SQL-2, SQL-6, and BM-2/BM-3/AR-8/AR-9 in
the TRD. `spec/fixtures/group-aggregation/` is the artifact oracle for all six.

---

## Addendum — export semantics (EXP-1(a), EXP-1(b), EXP-2; not numbered SEM-*, for the same reason as
the grouping addendum above, of which this is the sibling: the TRD's §6.1 states the export
requirements and this is where the compile-time half of them is decided)

The TRD's EXP-1..EXP-8 span a wire contract, a compilation rule, a streaming obligation and a CSV
writer. **Only EXP-1 and EXP-2 have a compiled form at all** — EXP-3 is *streaming*, and
EXP-4..EXP-8 are the CSV writer's; none of them is restated here. So this addendum owns no new
number: it refines the two that exist, splitting EXP-1's single paragraph into the two independent
rules it actually contains — the request extension with its group carve-out, EXP-1(a), and the column
list, EXP-1(b). Numbering the column list "EXP-3" is a mistake this repo has already made twice, in
GRP-3 and in its restatement in `SqlQueryBuilder`; both are corrected.

What follows is what a *compiler* and its request adapter must do, pinned because #1650 found the two
questions below answered inconsistently in the suite that was meant to pin them: whether an ordinary
row query projects, and whether an export does.

**EXP-1(a). The export is a request-shaped extension, and its group state is discarded.** The wire
request carries `exportFormat: "csv" | "tsv"`, `exportScope: "all" | "page"` (default `"all"`) and an
optional ordered `exportColumns: [{ colId, header? }]` **beside** the ordinary AG Grid SSRM members —
`filterModel` and `sortModel` are always honoured, unchanged, which is why nothing else about the
compiled query differs. Three consequences, all of them the *adapter's* to apply before a compiler
sees the IR:

- **`exportFormat` is what marks a request as an export**, and it is not optional. An `exportScope` or
  `exportColumns` arriving without one is a malformed request, not a row fetch with two ignorable
  properties: ignoring a scope returns one page where the client asked for the whole result set.
  `exportFormat` itself is otherwise **compilation-inert** — `page-export/004` and `/005` differ only
  in it and pin byte-identical artifacts on all three backends. It exists in the IR-facing contract so
  the writer can read it, and for no other reason.
- **A grouped view exports leaf rows.** `rowGroupCols`, `valueCols` **and `groupKeys`** are discarded
  outright, so the compiled IR carries no `groupSpec` and no aggregations and the GRP-1 dispatch is
  never entered. `page-export/010` and `/011` send a fully populated single- and two-level group state
  with aggregations, and `/024` adds a **non-empty `groupKeys`** — a partially consumed path, the
  shape GRP-1 would otherwise dispatch to a grouped level — and all three pin flat, ungrouped
  artifacts with no drill-down predicate. Group-structured and pivot exports are out of scope for v1.
  The discard applies to **either** scope: the output is a flat delimited row stream either way, and
  the scope decides only how many rows go into it.
- **`groupKeys` is discarded with the other two rather than refused, and the widening is accepted
  knowingly.** A drill-down key *restricts* the result to one bucket, so dropping it exports strictly
  more rows than the grid is showing. That is true — and it is equally true of dropping
  `rowGroupCols`, which this same rule mandates, so it does not distinguish the three members. The
  case that decides it is the obvious host integration: an export request built by copying the grid's
  last `getRows` payload and adding `exportFormat` carries whatever drill-down path the user had
  expanded, and refusing it would hard-fail every export taken from an expanded grid. All three
  members describe one thing — the group state of the view — and EXP-1(a) discards that state.
- **The one genuinely incoherent combination is permitted, not refused: `exportScope: "page"` over a
  grouped view.** The `startRow`/`endRow` range the grid sent was computed against *grouped* rows,
  and the export emits *leaf* rows, so the window is of questionable meaning — it is a count of one
  kind of row applied to another. It is nevertheless honoured rather than rejected, for the same
  reason the `groupKeys` discard is: refusing it would break the copy-the-last-payload integration for
  a request the client can reasonably send. **Nothing pins it**, and no fixture does, deliberately —
  the shape has no answer worth freezing until a host asks for one.

**EXP-1(b). An export names its output columns; an ordinary row query still does not.** This is the
widening GRP-3 deferred to "the export feature", and it is deliberately narrow — it did not become a
general projection rule:

- **Absent `exportColumns`**, the projection is every field the schema declares **that is
  `exportable`**, in declaration order (the `fields` object's member order in the schema *document*,
  GRP-3's rule and for GRP-3's reason). Headers come from each field's `label`, falling back to its
  colId. `page-export/009` pins the all-exportable case and `/023` the case where one field is
  declared `"exportable": false` and is absent from the projection while still being filtered on —
  `exportable` and SC-2's `filterable` are independent flags.
- **Present `exportColumns`**, the projection is exactly those columns, in **request** order, and the
  `header` strings are the writer's alone. `page-export/008` names three of seven with custom headers;
  none of the three headers appears in any of its arms. A `header` is arbitrary client text carried
  verbatim, so **EXP-6's formula-injection hardening applies to the header row exactly as it applies
  to values**: a header beginning `=`, `+`, `-`, `@`, tab or CR is prefixed with `'` like any cell.
  EXP-6's wording is about values because no header existed when it was written; the row a header
  lands in is a spreadsheet row like any other. It applies **unconditionally** here — #1652 narrowed
  EXP-6's scope for *cells*, and whatever that narrowing spares, it has nothing to exclude on this
  side, because a header is always text. What the narrowing is, is the TRD's EXP-6 to state and not
  this addendum's: the claim above is EXP-1(b)'s own (a `header` is client text), and restating the
  cell rule here is what would make the two drift.
- **A column also carries what EXP-5 declares for it, and a compiler reads none of it.** A field's
  `format` (its date pattern and decimal separator, in `GridSchema` config since #1653) is resolved onto
  the column beside its header, because the writer is handed nothing else per field. It is stated here
  for one reason, and it is a *compilation* one: like a `label`, a `format` must leave every compiled
  artifact untouched. `page-export/026` is `/013`'s request, row stream and writer config byte for byte
  with two `format` members added to its schema, and pins a byte-identical `postgres.artifact.json` —
  the same statement `/004`-`/005` and `/025` make about `exportFormat`, made for the first time about a
  *schema* member. What those overrides mean and how a value renders under them is EXP-5's, in the TRD,
  and is deliberately not restated here.
- **The resolution happens once, in the request adapter**, not per compiler: an unknown colId, a
  colId the schema declares non-exportable, a repeated colId, and an explicitly empty list are all
  refused there. All four are hard failures in **every** `GridSchema` mode — Lenient's contract is
  that an unknown filter *condition* vanishes and the result merely widens, whereas a dropped export
  column hands back a file missing something the client asked for by name, which is the same
  reasoning that keeps a `groupCol` and an aggregation field hard failures under GRP-1.
- **An ordinary row query is unchanged and still renders `SELECT *`** (and no `$project`, and no
  `_source` filter). `page-export/001`-`003` are the category's plain-paging baseline, carry no export
  member at all, and are spelled exactly like every other row query in the suite. #1630 had authored
  their Postgres arms with an explicit column list their own Mongo arms did not have; #1650 corrected
  them rather than generalising the rule, because widening every row query is a decision about the
  *grid's* response shape, which no fixture in the suite pins and this feature does not own.

*Per backend.* On **SQL** the projection is the `SELECT` list, each column aliased back to its logical
name only where the physical column differs (`"order_date" AS "orderDate"`, but plain `"status"`) —
GRP-3's drill-down-leaf rule, reused unchanged. On **MongoDB** it is a trailing `$project`, after any
`$skip`/`$limit`, re-keying a differing physical path with the expression form (`"id": "$_id"`) and a
matching one with a plain `1`, then `_id: 0` **last** (MDB-10's shape rules apply to it like any other
stage document; the suppression is written after the output list because that list's *order* is what
is normative and byte-compared). On **OpenSearch/Elasticsearch** there is **no projection at all** —
see OSE-13, which is a statement about the artifact's admitted member set, and the note there on
`_source` filtering. Column selection and ordering for that backend fall to the writer, reading
`exportColumns` from the request it already holds. That is not EXP-1(b) contradicting OSE-13; it is one
rule with a per-backend split, and the fourteen Search arms in `page-export/` pin it.

**EXP-2. `exportScope` resolves to a page mode, and nothing else in the compiler changes.**
`"all"` is `$defs/nonePage` — the whole filtered and sorted result, with the request's own
`startRow`/`endRow` **discarded**, not merely absent. `"page"` honours that range exactly as an
ordinary row fetch does. `page-export/006` and `/007` are the pair that pins this: identical requests
down to `startRow: 200, endRow: 250`, differing only in the scope, and `006` compiles with no
`LIMIT`/`OFFSET`, no `$skip`/`$limit` and no `from`/`size` on any backend. The `startRow`/`endRow`
pair is still shape-checked before the scope overrides it — a half-supplied range is malformed
whether or not this scope would have used it.

SEM-6's tiebreaker is **unaffected**: `page: none` is still a paged read as far as determinism is
concerned (a stream can be resumed, and an unordered one cannot be), so the stable key is appended
exactly as it always is. `sort-paging/012` and every `exportScope: "all"` fixture in
`page-export/` carry it.

**Cross-links.** `$defs/nonePage`, `$defs/rangePage`, `$defs/groupSpec`, GRP-1 (the dispatch the
carve-out bypasses), GRP-3 (the projection rule this one composes with), SEM-6 (the tiebreaker
`page: none` keeps), OSE-13 and MDB-10. `spec/fixtures/page-export/` is the artifact oracle, plus
`sort-paging/012` for the `page: none` shape on all three backends. EXP-3..EXP-8 — streaming and
chunking, the CSV writer, its formatting and injection hardening, and the row-count limit — have no
compiled form and are **not restated here**; the TRD §6.1 prose is their normative home. #1651 built
the writer half of EXP-4/EXP-5, #1652 EXP-6's injection hardening and #1653 EXP-5's per-field format
overrides, and their oracle is the
byte-exact `expected/export.csv`/`.tsv` files in `page-export/012`-`020`, `/022`, `/025` and `/026` —
twelve of that category's twenty-six cases, which is every writer-facing one except `021` (EXP-7's row
limit produces no output to compare). See the category README for the file shapes. #1652 also
**narrowed EXP-6's scope**, and that narrowing is stated at EXP-6 itself in the TRD — deliberately not
here, and not in summary either: it turns on a distinction fine enough (which spelling of the type
test, not just which types) that a second copy would be wrong within a story or two.
`page-export/018` is its oracle. EXP-3 and EXP-7 are the execution adapters'.

---

## Addendum — canonical SQL rendering (not numbered SEM-*, for the same reason as the aggregation
addendum: the TRD's §7 enumerates SEM-1..SEM-7 and stops, but the conformance fixture suite needs a
literal answer and no other document owns one)

The SEM-1..SEM-7 sections above pin *semantics* and say so explicitly — their snippets are
illustrative. That was enough while nothing tried to satisfy them. It stopped being enough in #1638:
the fixture suite (#1630) was hand-authored by seven parallel agents with no compiler to check it,
and a research pass found the **same IR construct rendered several different ways from identical
inputs** across categories — two spellings of `notIn`, two of `notContains`, two parenthesisations of
a null-inclusive negative, two of a composite `and`/`or`, two of `notBlank`, and identifier quoting
in one category out of nine. No single compiler can satisfy contradictory oracles under T-1a artifact
equality, so the answers are pinned here, once, and every language port inherits them instead of
rediscovering them.

Each rule below is the form the `spec/fixtures/*/expected/postgres.artifact.json` files now contain.
Postgres is the reference dialect (§5); where a rule is Postgres-specific rather than universal, it
says so and names what the other dialects do instead.

**SQL-0. `GridSchema.source` is where the table comes from.** A compiled query names a physical
collection — `FROM employees`, a Mongo collection, a Search index — and until #1638 that name existed
in no input: not in the AG Grid wire request (no SSRM payload carries one, and none should: it is
exactly the kind of thing SEC-1 keeps client-side callers away from), not in `GridSchema`, not in the
TRD. It was recoverable only from a fixture's directory name. `grid-schema.schema.json` therefore
declares a **required** `source` string, alongside the field allowlist (SC-2) and the per-backend
physical mappings (SC-4) that are already host-declared and already never client-influenced. A
compiler MUST take the collection from `schema.source` and MUST NOT accept one from the request.

**SQL-1. Always quote identifiers — every column, every alias, and the table.** Postgres renders
`SELECT * FROM "employees" WHERE "age" >= $1`, never the bare form.

*Why.* Unquoted identifiers are not "the same thing without the noise" — PostgreSQL **case-folds them
to lowercase**. The fixture suite contains real proof: `dialect-parity/` declares camelCase physical
columns (`lastName`, `employeeCode`, `jobTitle`) and, before #1638, emitted them unquoted, so
`WHERE lastName ILIKE ...` would reach the server as `where lastname ilike ...` and fail against the
table those fixtures describe. The artifact-equality tier (T-1a) cannot see that class of bug at all
— it compares strings — so it would have sat in the oracle until the execution-equality tier (T-1b,
#1624) ran the query against a real database. Quoting also makes `Dialect.QuoteIdentifier`
unambiguous: it is applied to *every* identifier, so there is no second rule about when to skip it,
and no dialect needs a keyword blocklist to stay correct.

*Must NOT.* Must NOT quote conditionally ("only when it needs it", "only mixed-case names") — that
reintroduces the blocklist and makes the fixture oracle depend on a keyword list that differs per
dialect and per server version. Must NOT quote things that are not identifiers: the collation name in
`COLLATE craticula_ci`, parameter placeholders, and the `'%'` / `'\'` / `''` literals of the ILIKE and
blank scaffolding are all left exactly as they are.

*The rule is universal, and as of #1639 so is the fixture suite.* #1638 re-authored only the
**Postgres** artifacts, because the *rule* ("always quote") is dialect-independent while the *quote
character* is not, and choosing each engine's is part of writing that engine's `Dialect`. #1639 wrote
the other three and closed the gap: **all 55 `mysql`/`mssql`/`sqlite` arms in
`spec/fixtures/dialect-parity/` are now quoted**, so `006`-`022`'s parity sets are no longer mixed —
seven artifacts each since #1642 added the `oracle` arm, six before it. The characters, with the
escape each engine uses for one appearing *inside* an identifier:

| Dialect | Quote | Escape inside an identifier |
|---|---|---|
| Postgres | `"` | `"` → `""` |
| SQL Server | `[…]` | `]` → `]]` |
| MySQL / MariaDB | `` ` `` | `` ` `` → ```` `` ```` |
| SQLite | `"` | `"` → `""` |
| Oracle (#1642) | `"` | `"` → `""` |

MySQL uses backticks rather than `"` because `"` only quotes an identifier under `ANSI_QUOTES`, which
is off by default and is a session mode a compiler must not assume of a host's connection.

**Oracle is the second engine where quoting is a correctness rule rather than a hygiene one**, and it
folds the *other* way from Postgres: an unquoted identifier is upper-cased, so `FROM employees`
reaches the server as `FROM EMPLOYEES`. Always-quoting neutralises that in the statement but moves
the obligation into the host's DDL, because Oracle also *stores* an unquoted-`CREATE`d name folded —
so a table created as `CREATE TABLE employees` cannot be reached by `FROM "employees"` at all
(ORA-00942). Every `source` and physical column in this fixture suite is lowercase or camelCase
(`employees`, `sales_fact`, `lastName`, `fiscal_year`), so on Oracle they all require quoted DDL;
that is recorded as a host obligation in `spec/fixtures/dialect-parity/README.md`, not silently
assumed. Identifier **length** is a non-issue in the other direction: Oracle's limit is 30 bytes
before 12.2 and 128 from 12.2, this project's Oracle dialect assumes 12.2+ (see SQL-6), and the
longest identifier any fixture declares is `employeeCode` at 12 characters.

SQL-3 and
SQL-4 are now exercised on every dialect too (`017`/`018`'s new arms), and SQL-4 is where the five
genuinely part company: Postgres binds one array parameter, the other **four** — SQL Server, MySQL,
SQLite and Oracle — bind N scalars, so even `params.length` differs across the arms of one fixture.

**SQL-2. Parenthesisation is structural, not cosmetic — one rule per construct, applied always.**
Correct SQL admits many equivalent bracketings; artifact equality admits one. The four cases:

- **Composite `and` / `or` (`$defs/andNode`, `$defs/orNode`): the composite is wrapped, its children
  are rendered bare.** `(a AND b)`, `(a OR b OR c)` — never `(a) AND (b)`, never `((a)) AND ((b))`. A
  child that is itself a composite (or a construct with its own wrap, below) carries its own
  parentheses, so nesting composes: `((x OR y) AND z)`. A single-child composite still wraps: `(x)`.
- **A null-inclusive negative (SEM-2) is always wrapped**, whether or not it is the whole `WHERE`
  clause: `("age" <> $1 OR "age" IS NULL)`. Never bare at the top level. This is what makes the leaf
  safe to drop into any parent without the parent knowing what it contains — a top-level `OR` left
  unwrapped inside an `AND` parent is a silent correctness bug, and pinning the wrap unconditionally
  is what removes the whole class. **Unlike the quote character, this is not a per-dialect choice at
  all**: parenthesisation is structural, so a query builder emits it and the `Dialect` interface has
  no say in it (an artifact for *any* dialect that shows the disjunction bare is therefore
  unsatisfiable by construction, not merely unusual — `dialect-parity/008`'s `mysql`/`mssql`/`sqlite`
  artifacts were fixed on exactly that ground).
- **A tree-level `notNode` (`Not(child)`)** renders `(NOT (<child>) OR <col> IS NULL [OR ...])` — the
  inner parentheses around the child, the outer around the whole null-inclusive disjunction, and one
  `IS NULL` disjunct per distinct field referenced anywhere in the child subtree, in first-appearance
  order.
- **`blank` / `notBlank`.** `blank` is `("c" IS NULL OR "c" = '')` for a `string` field and `"c" IS
  NULL` for every other type (SEM-2's fourth must-not). `notBlank` is `NOT (<blank>)` **literally
  applied to that text**, which yields `NOT (("c" IS NULL OR "c" = ''))` for a string and
  `NOT ("c" IS NULL)` otherwise. The doubled parentheses in the string case are not an accident to be
  tidied away: they are SEM-2's "negate the compiled `blank` condition, never re-derive it" made
  visible in the output. Collapsing them by hand is the first step toward the two forms drifting.
  **On an engine whose empty string *is* NULL the text arm is not this text — see SQL-7**, which
  varies the arm and leaves the `NOT (<blank>)` composition above untouched.

**SQL-3. A negative operator renders with the negated operator, not an outer `NOT (...)`.**
`notContains` is `"c" NOT ILIKE '%' || $1 || '%' ESCAPE '\'`, not `NOT ("c" ILIKE ...)`.

*Why.* Every other negative operator already does this — `neq` renders `<>`, not `NOT (=)`; `notIn`
renders `<> ALL`, not `NOT (= ANY)` — so the outer-`NOT` spelling made `notContains` the single
exception, for no gain. Keeping the negation in the operator also keeps the `ESCAPE` clause attached
to the pattern-match expression it belongs to, which is what SEM-7 requires. Note the deliberate
contrast with the previous rule: an outer `NOT (...)` is correct and required for a **tree-level
`notNode`**, because there the negation applies to an arbitrary subtree, not to one comparison. The
distinction is the IR shape, never the surface similarity of the two.

**SQL-4. Set membership is one array parameter on Postgres — `= ANY($1)` / `<> ALL($1)`, cast to the column
type for the three string-encoded types — and that is a dialect rendering, not a universal one.** The set's
values are bound as a **single** array parameter, so the placeholder count never depends on the value count:
`"status" = ANY($1)` with `params: [["active", "pending"]]`, never `IN ($1, $2)` with two scalars.

*The array is cast for `decimal`, `date` and `datetime` (Bug #2304).* Those values are strings (AR-7), so a host
binds the array as `text[]`, and PostgreSQL has no `numeric = text`, `date = text` or `timestamptz = text`
operator. On Postgres the placeholder is therefore cast to the field's column type, and only for these three
types: `"price" = ANY($1::numeric[])`, `"day" = ANY($1::date[])`, `"at" = ANY($1::timestamptz[])`, and
`<> ALL($1::numeric[])` (`::date[]`, `::timestamptz[]`) likewise. `string`, `int64`, `double` and `boolean` stay
uncast (`= ANY($1)`), and the parameter list is unchanged (`params: [[...]]`). SQL Server, MySQL, SQLite and
Oracle render exactly as before (N scalars). The cast is an explicit cast from the `text[]` a host binds for a
string array. Consequences:
(a) the host's `datetime` column is `timestamptz`, an absolute instant (SEM-4). A `timestamp` column without a
zone makes Postgres compare through the session time zone and can shift rows silently; that is a host
obligation, like SQLite's fixed-width datetime text.
(b) A `null` element in the list (AR-7 `nullValue` beside real values) is allowed and stays NULL inside the
array. An empty list is a constant under SEM-8 (`1 = 0` / `1 = 1`) and never reaches this cast.
(c) `Craticula.EntityFrameworkCore` hands typed values to the provider and is out of scope.

*Why it is behind the dialect interface.* `ANY(array)` does not exist in SQL Server, MySQL or SQLite.
#1639 renders those three as `IN (...)` with N scalar parameters. The query builder therefore MUST
NOT emit either spelling itself — it asks the dialect for an in-list rendering and passes it the
field and the set. A builder that contains an `if` for this is the BM-1 smell
`docs/architecture/c4-components-sql-compiler.md` warns about. (This rule is also the reason the two
spellings must not be treated as interchangeable in a fixture: `params.length` differs between them,
so a port that picks the other one fails on the parameter list even when the SQL text is accepted.)

**SQL-5. The substring family's pattern operator, escape clause and escape alphabet are all per
dialect — three axes, not one.** SEM-7 mandates "a SQL `LIKE` pattern with a matching `ESCAPE`
clause" and, read literally, that is wrong on two of the four v1 dialects. The rule as the fixture
suite actually pins it (#1639's D1/D3, and its review pass; `spec/fixtures/dialect-parity/README.md`
keeps the story-level rationale):

| Dialect | Operator | Escape clause | Escape alphabet |
|---|---|---|---|
| Postgres | `ILIKE` (CI) / `LIKE` (CS) | `ESCAPE '\'` | `\` `%` `_` |
| SQL Server | `LIKE` (both, + a collation — SQL-6) | `ESCAPE '\'` | `\` `%` `_` **`[`** |
| MySQL / MariaDB | `LIKE` (both) | **`ESCAPE '\\'`** | `\` `%` `_` |
| SQLite | `LIKE` (CI) / **`GLOB`** (CS) | `ESCAPE '\'` / **none** | `\` `%` `_` / **class-wrapping** |
| Oracle (#1642) | `LIKE` (both, + a collation — SQL-6) | `ESCAPE '\'` | `\` `%` `_` |

Three of those cells are correctness, not spelling, and each is invisible to the artifact-equality
tier if a port gets it wrong in isolation:

- **MySQL spells the escape character `'\\'`.** With `NO_BACKSLASH_ESCAPES` off — MySQL's default —
  a backslash is the string-literal escape character, so `ESCAPE '\'` escapes the closing quote: the
  literal never terminates and *the statement does not parse*. The escape **character** is still `\`
  on all five dialects (Oracle included — a backslash is an ordinary character in an Oracle literal),
  so the bound value is byte-identical across the arms; only the SQL text differs.
- **SQLite renders `GLOB` for a case-sensitive substring match, and drops the `ESCAPE` clause.**
  Its `LIKE` is ASCII-case-insensitive unconditionally (it is a function call, ignores collating
  sequences, and `PRAGMA case_sensitive_like` is a connection-level setting a compiler must not
  depend on), so emitting `LIKE` for a field declared `caseSensitivity: "sensitive"` silently
  returns case-insensitive rows. `GLOB` is a different pattern language, not a synonym: its
  wildcards are `*`/`?`, so the anchoring becomes `'*' || :v || '*'`, and it accepts **no `ESCAPE`
  clause at all** — a literal `*`, `?` or `[` is neutralised by wrapping it in a single-member
  character class (`[*]`, `[?]`, `[[]`). SQL-3 still applies: the negated form is `NOT GLOB`.
- **SQL Server escapes `[` as well.** T-SQL's `LIKE` treats `[` as a character-class opener, so an
  unescaped user value `A[BC]` matches `AB` or `AC` rather than itself, and `[^x]`/`[a-z]` widen the
  match set further — SEM-7's own "must NOT" about a user-supplied literal still behaving as a
  wildcard. `]`, `^` and `-` need no escaping in turn, on either this dialect or SQLite's GLOB path:
  all three are special only *inside* a class, and once the opener is neutralised no class from the
  value can exist.

**Oracle contributes no fourth surprise, and that is worth stating** so a port does not copy the
wrong neighbour: it has no `ILIKE` (so the case-insensitive direction is a collation, like SQL
Server's), but a backslash inside an Oracle string literal is an *ordinary character*, so the clause
is `ESCAPE '\'` and MySQL's doubled spelling would be wrong; and its `LIKE` has exactly two
metacharacters, `%` and `_`, so the shared escape alphabet is the whole alphabet and T-SQL's `[` is
T-SQL's alone.

*Must NOT.* A port MUST NOT read SEM-7's "`LIKE` … with a matching `ESCAPE` clause" as universal:
on the SQLite case-sensitive path there is no `LIKE` and no `ESCAPE` clause to attach one to, and a
port that emits them anyway both fails `dialect-parity/021`'s sqlite arm and returns the wrong rows.
It MUST NOT widen the shared escape alphabet to the union of all five either — `\[` in a
Postgres/MySQL/SQLite/Oracle pattern is a literal backslash followed by a bracket, which is not what
the user searched for.

**SQL-6. Where an engine's default collation disagrees with the field's declared case sensitivity,
the compiler MUST spell the mechanism explicitly — in *both* directions.** SEM-1's second Must-Not
("must NOT default to case-sensitive because the engine's default is") has a mirror image that is
just as wrong and much easier to ship: leaving a field declared `caseSensitivity: "sensitive"`
*bare* on an engine whose default collation folds case. SQL Server and Azure SQL ship
`SQL_Latin1_General_CP1_CI_AS`; MySQL's server default is a `_ci` family; Oracle's default column
collation is `USING_NLS_COMP`, which resolves through the *session*'s `NLS_COMP`/`NLS_SORT`. On all
three, "emit no case-insensitivity mechanism" can mean "compare case-insensitively", so the host's
explicit opt-in is silently discarded and the SQL reads as though it were correct.

| Dialect | Case-insensitive | Case-sensitive |
|---|---|---|
| Postgres | `COLLATE craticula_ci` | nothing — default collation is deterministic |
| SQL Server | `COLLATE Latin1_General_CI_AS` | **`COLLATE Latin1_General_CS_AS`** |
| MySQL / MariaDB | nothing — column's declared collation | nothing — **host DDL obligation** (see below) |
| SQLite | `COLLATE NOCASE` | nothing — default sequence is `BINARY` |
| Oracle (#1642) | `COLLATE BINARY_CI` | **`COLLATE BINARY`** |

*Why Oracle spells both, and what version that pins.* Oracle has no `ILIKE`, so there is exactly one
mechanism to choose and it has to serve the exact-match family, ordering, set membership, the
`ORDER BY` **and** the substring family. Two candidates exist and only one can:

- **`COLLATE BINARY_CI`** — the 12.2 data-bound-collation operator. Applies to `LIKE` as well as to
  `=`/`IN`/`ORDER BY`, which is what makes SEM-1's "the same mechanism in every context on a field"
  achievable at all. **This is the choice**, and it pins **Oracle Database 12.2 or later** (with
  `COMPATIBLE >= 12.2` and `MAX_STRING_SIZE = EXTENDED`, data-bound collation's documented
  prerequisite) — a hard version floor of the same kind SQLite's 3.30.0 `NULLS FIRST/LAST` floor is,
  and equally a loud failure when unmet (ORA-43929) rather than a silent one.
  *Measured (#2880, 2026-10-22), on Oracle Database Free 23.26.3 with `COMPATIBLE = 23.6.0` and `MAX_STRING_SIZE = STANDARD`:*
  the statement-level operator (`COLLATE BINARY_CI` and `COLLATE BINARY` on a column, in `=`, `LIKE ... ESCAPE`, `IN` and
  `ORDER BY`) runs and returns the pinned rows for all 45 `oracle` fixture arms, so on 23ai it needs **no** `EXTENDED` setting.
  Only a column **declared** with a collation in its DDL fails there (`ORA-43929: Collation cannot be specified if parameter
  MAX_STRING_SIZE=STANDARD is set`). The 12.2 floor itself, and `EXTENDED` as the prerequisite on 12.2 to 21c, are Oracle's
  documented requirements and were **not run**: no image of those versions is in the tier.
- **`NLSSORT(col, 'NLS_SORT=BINARY_CI')`** — works back to 9i and pins no version, and is **rejected**:
  it cannot express a case-insensitive *substring* match, because a collation key of a substring is
  not a substring of that string's collation key. The substring family would have to fall back to
  `UPPER(col) LIKE UPPER(:v)`, leaving one field folding case by two different mechanisms depending
  on the operator — precisely what SEM-1 forbids. It also wraps the bound *value* in a function call.

Setting `NLS_COMP = LINGUISTIC` on the session is rejected on the same ground as SQLite's
`PRAGMA case_sensitive_like`: connection-level state a compiler must not depend on. And because the
default is that session state, the case-**sensitive** direction cannot be left bare either — hence
`COLLATE BINARY`. Unlike MySQL, Oracle has one portable spelling for it, so it is a token rather than
a host DDL obligation.

Whatever a dialect spells, it spells on **every construct where SEM-1 applies at all**, per SEM-1's
"same mechanism in every context on a field": the scalar comparison, the set membership, the
substring match and the `ORDER BY`. `dialect-parity/014` (`eq`), `/018` (`notIn`) and `/021`
(`contains`) pin the case-sensitive direction; `/006`, `/016`, `/007` pin the insensitive one.

The **exception is the bucket-identity keys**, where SEM-1 does not apply in either
direction: a `GROUP BY` key, a `groupKeys` drill-down match and a grouped level's `ORDER BY` spell
nothing at all (GRP-2), and so do BM-3's `SELECT DISTINCT` column and its `ORDER BY` (GRP-6). This
table therefore has no column for them, and on the **three** engines whose default folds case — SQL
Server, MySQL and Oracle, i.e. every row of this table that spells the case-sensitive direction as
something other than "nothing" — that "nothing" is a host DDL obligation of exactly the kind the MySQL
row below records — see GRP-2's own accepted-divergence paragraph. A drill-down **leaf**'s `ORDER BY` is not one of these keys and is
covered by the table normally; so is a set filter's search prefix, which is a filter on the distinct
column rather than the distinct key itself.

*Why MySQL is the exception, and what a host owes.* Case sensitivity there is a property of the
**column's** declared collation, which the statement cannot override portably — MySQL's
case-sensitive collation names are charset-specific (`utf8mb4_bin`, `utf8mb4_0900_as_cs`, MariaDB's
own set) rather than one spelling a compiler can pin. A field declared `caseSensitivity: "sensitive"`
therefore requires a `_bin`/`_as_cs` **column** collation in the host's DDL, or the declaration has
no effect. That is a documented host obligation (PERF-4's per-backend index-guidance page), not a
gap the compiler silently fills with a guessed collation name.

*Must NOT.* A compiler MUST NOT infer "case-sensitive" from the *absence* of a case-insensitivity
mechanism, and a `Dialect` seam MUST NOT carry this decision as a boolean: `false` would have to
mean both "text, compare case-sensitively" and "not a text comparison at all", and the two need
opposite renderings — SQL Server rejects a `COLLATE` clause on an `int`/`date` expression outright
("COLLATE clause cannot be used on expressions of type int"), and Oracle likewise accepts `COLLATE`
only on a character operand. The decision is three-valued at the seam or it is wrong at one end
of it.

**SQL-7. On an engine that treats the empty string as NULL, `blank`'s text arm is `IS NULL` and
nothing more.** SEM-2 and SQL-2 give `blank` two shapes chosen by *field type*:
`("c" IS NULL OR "c" = '')` for `string`, `"c" IS NULL` for everything else. On **Oracle** the first
one is wrong, and the second is what a `string` field must compile to as well.

| Dialect | `blank` on a `string` field | `blank` on any other type |
|---|---|---|
| Postgres | `("c" IS NULL OR "c" = '')` | `"c" IS NULL` |
| SQL Server | `("c" IS NULL OR "c" = '')` | `"c" IS NULL` |
| MySQL / MariaDB | `("c" IS NULL OR "c" = '')` | `"c" IS NULL` |
| SQLite | `("c" IS NULL OR "c" = '')` | `"c" IS NULL` |
| **Oracle** | **`"c" IS NULL`** | `"c" IS NULL` |

*Why this is a correctness rule and not a redundant-disjunct tidy-up.* Oracle documents that a
character value of length zero is NULL. So `"c" = ''` is `"c" = NULL`, which under SQL's three-valued
logic is **UNKNOWN for every row** — not FALSE, and that distinction is the whole rule:

| operator | a row whose value is NULL | a row whose value is `'abc'` |
|---|---|---|
| `blank` = `(c IS NULL OR c = '')` | `TRUE OR UNKNOWN` → TRUE → **matched** ✓ | `FALSE OR UNKNOWN` → UNKNOWN → **not matched** ✓ |
| `notBlank` = `NOT (…)` | `NOT TRUE` → FALSE → not matched ✓ | `NOT UNKNOWN` → **UNKNOWN → not matched** ✗ |

A `WHERE` clause keeps only rows evaluating to TRUE, so `blank` is accidentally right and
**`notBlank` returns the empty result set** — every row filtered out, on syntactically valid SQL,
with no error. That is a silently empty grid, and the artifact-equality tier (T-1a) cannot see it,
which puts it in the same class as MySQL's unparseable `ESCAPE '\'` (SQL-5) and a bare `LIKE` on a
case-sensitive SQLite field (SQL-5's second bullet).

*Where the decision belongs.* This is an **engine fact**, not a rendering: the `blank` composition —
and therefore SEM-2's "`notBlank` is `blank`'s compiled text negated, never re-derived" — stays in
the query builder, which asks the dialect a single yes/no question ("is `''` NULL here?") and picks
the arm. A `Dialect.renderBlank` method would instead have four of five implementations byte-identical,
and every one of the five would have to reach back into the semantics layer for the *field-type* half
of the answer. Equally, the question must NOT be answered wherever that field-type half is resolved
(Craticula's `SemanticsResolver`): that layer knows the schema and nothing about engines, and teaching
it a dialect name inverts the dependency the `Dialect` seam exists to draw. ("Otherwise `blank` and
`notBlank` could drift apart" is *not* one of the reasons, though it is the first one a reader
reaches for: the negation is composed over whatever text the `blank` half returned either way, so no
design in the running admits drift.)

*Must NOT.* A compiler MUST NOT emit the `= ''` disjunct on an engine where `''` is NULL "because it
is harmless" — it is not harmless, it poisons the negation. It MUST NOT fix only `blank` and leave
`notBlank` alone: `blank` is the operator that already worked, and a port that tests only the
positive direction will see nothing wrong. And it MUST NOT reach the collapsed form by special-casing
the *field type* (e.g. treating `string` as non-text on Oracle) — the type answer and the engine
answer are different questions that happen to coincide here, and conflating them changes SEM-1's
mechanism selection for the same field.

*The Must-NOTs above are not the whole truth about Oracle, and this list is not exhaustive.* One
Oracle value escapes the rule entirely: `EMPTY_CLOB()` produces a **zero-length LOB that is not
NULL**, so a column holding it is found by neither `IS NULL` nor `= ''`, and `blank` misses it on
either arm. Detecting it needs `dbms_lob.getlength(c) = 0`, which the compiler cannot emit because
`grid-schema.schema.json` carries no physical *type* — a field declares `string`, and whether the
host stored that as `VARCHAR2`, `NVARCHAR2` or `CLOB` is not in the contract. This is therefore a
**documented limitation of `blank` on Oracle CLOB columns**, not a defect in the rule: a host that
maps a `string` field onto a CLOB and writes `EMPTY_CLOB()` into it gets a row that `blank` does not
match and `notBlank` does. Recorded so the list above reads as complete about what it covers rather
than complete about Oracle. Closing it would need a physical-type declaration in the schema, which is
a `/v1/` contract change and belongs to a story of its own.

**SQL-7(b). The same engine fact makes an empty bound *value* uncompilable on Oracle, and a compiler
targeting it MUST reject rather than render.** `$defs/stringValue`'s `value` carries a `maxLength` and
no `minLength`, so `""` is a legal IR value on every backend. On Oracle it binds as NULL, and the
resulting statement is valid SQL that returns the wrong rows in silence:

| Request | Postgres / SQL Server / MySQL / SQLite | Oracle, if rendered |
|---|---|---|
| `eq ""` | the rows whose value is the empty string | **no rows** (`c = NULL` is UNKNOWN) |
| `neq ""` | every row except those, NULLs included (SEM-2) | **only the NULL rows** — wrong rows, not no rows |
| `contains ""` | every non-NULL row (`LIKE '%%'`) | **no rows** — `'%' \|\| NULL \|\| '%'` is itself NULL |
| `in ["", "x"]` | either value matches | the `""` member is inert; `notIn` matches **no row at all** |

So the rejection covers **all three paths a string value can reach** — the scalar comparison family,
set membership, and the substring family — and not merely `eq`. It is a compiler error naming the
engine fact, in the same register as GRP-4's "a sort key the projection does not contain is rejected
rather than rendered": a plausible statement returning wrong rows is worse than a refusal.

*Why this is scoped to the dialect and not to the IR.* Adding `minLength: 1` to `stringValue` would
forbid, across the whole contract and every backend, an input the other four engines handle correctly
— a `/v1/` schema change with its own compatibility question, deliberately **deferred to its own
story** rather than taken as a side effect of adding a dialect. A caller that wants to ask "is this
value empty or absent" is asking for SEM-2's `blank`/`notBlank`, which SQL-7 above compiles correctly
on Oracle. No fixture binds an empty value on any backend, so nothing in the suite changes.

*Pinned by* `dialect-parity/019`, whose `oracle` arm is the only one of that fixture's five SQL arms
that is not its Postgres arm with tokens substituted; SQL-7(b) is pinned by unit tests alone
(`DialectRenderingTests`), there being no artifact for a request that does not compile.

**SQL-8. On Postgres the placeholder of a scalar comparison on a `decimal`, `date` or `datetime` field is cast
to the column type — and that is a dialect rendering, not a universal one.** The sibling of SQL-4, for the
scalar operators (Bug #2320). Those values are strings (AR-7) and a host binds a string parameter as `text`;
PostgreSQL has no `numeric >= text`, `date >= text` or `timestamptz > text` operator. On Postgres the placeholder
of every scalar comparison is therefore cast to the field's column type, and only for these three types:
`"amount" >= $1::numeric`, `"day" >= $1::date`, `"at" > $1::timestamptz`. "Scalar comparison" is `eq`, `neq`,
`gt`, `gte`, `lt`, `lte`, **each bound of `inRange`** (`"day" >= $1::date AND "day" < $2::date`) and **every
date preset** (AG-2), which expands to a half-open `inRange` and renders through the same comparison. `string`,
`int64`, `double` and `boolean` stay uncast, and the parameter list is unchanged (the cast is in the SQL text
only). SQL Server, MySQL, SQLite and Oracle render exactly as before, and so do the MongoDB and OpenSearch
backends. Consequences:
(a) the host's `datetime` column is `timestamptz`, as in SQL-4(a); with a `timestamp` column Postgres compares
through the session time zone and can shift rows silently.
(b) A `null` value (AR-7 `nullValue`) stays valid: `NULL::numeric` is a typed NULL, and the parameter list still
carries the `null`.
(c) `Craticula.EntityFrameworkCore` hands typed values to the provider and is out of scope.

*Why it is behind the dialect interface.* The cast is a PostgreSQL spelling; the query builder MUST NOT branch on
the dialect for it (the BM-1 smell of SQL-4). The dialect is handed the field type with the value and decides.

**Cross-links.** `grid-schema.schema.json` (`source`), `$defs/andNode`, `$defs/orNode`,
`$defs/notNode`, `$defs/unaryOperator` (`blank`, `notBlank`), `$defs/binaryOperator` (`notContains`,
`contains`), `$defs/setOperator` (`in`, `notIn`), `$defs/textOptions` (`caseSensitivity`), SEM-1,
SEM-7, SEC-4, **AGG-6** (the one aggregate wrap this family renders, and the only backend that
renders one), and BM-1's `Dialect` interface.

---

## Addendum — canonical MongoDB rendering (MDB-1..MDB-12; not numbered SEM-*, for the same reason as
the SQL addendum above, of which this is the exact parallel for the other artifact family)

The SQL addendum exists because #1638 found the *same IR construct rendered several different ways
from identical inputs* across a fixture suite seven parallel agents had hand-authored with no
compiler to check it. #1643 compiled the **Mongo** arm of that same suite for the first time and
reproduced the finding on the other side: `operators/001` spelled `eq` explicitly while
`operators/003` spelled it implicitly, all 47 `operators/` artifacts were missing SEM-3's mandatory
`$unset`, and three drill-downs were flat where five SQL arms of the same fixtures composed. So the
answers are pinned here, once, for the same reason and in the same register — and **not** as prose
under SEM-1..SEM-7, whose snippets this document's own preamble disclaims as illustrative. A
normative sentence there would contradict the framing, and that ambiguity is precisely what let
`operators/001` and `operators/003` disagree in the first place.

Each rule below is the form the `spec/fixtures/*/expected/mongo.artifact.json` files now contain.
There is **one** MongoDB, so unlike the SQL addendum nothing here is "the reference engine's
spelling, other engines differ" — every rule is universal, which is also why there is no
`MongoDialect` seam to hang any of it on (BM-1's smell, mirrored: a single-implementation interface).
SQL-0 is *not* SQL-specific and is not restated: a compiled pipeline takes its collection from
`schema.source` and never from the request.

**MDB-1. A comparison is a field document holding an explicit operator — including `$eq`.**
`{"age": {"$gt": 30}}`, and `{"status": {"$eq": "active"}}` rather than MongoDB's implicit
`{"status": "active"}`.

*Why, given the two are semantically identical for every value the IR can carry.* SEM-2's MongoDB
paragraph is the tiebreaker, and it is normative prose rather than a disclaimed snippet: it emits the
explicit composed form for `neq` **even though the naive one is correct**, "to keep the compiled
shape parallel to the SQL and ES forms" and to stay valid in an `$expr` context, where only
`{"$eq": [...]}` exists at all. A uniform operator table also needs no carve-out, which is SQL-1's
"always quote, no second rule" applied to the other backend. The hand-authored suite spelled it
**both** ways in adjacent cases of one category (`operators/001` explicit against
`003`/`005`/`007`/`046` implicit; all of `filter-tree/` explicit against every `group-aggregation/`
drill-down implicit), which is why it is pinned rather than left to taste; 21 artifacts were
re-authored onto this form in #1643.

**MDB-2. The composites, and what a tree-level `NOT` gets that a bare `$nor` lacks.** `andNode` → `$and`,
`orNode` → `$or`, and a tree-level `notNode` → `$nor` with the child as its single member, wrapped in
the null fan-out below. A
single-child composite is **not** collapsed (`{"$and": [x]}`), mirroring SQL-2's `(x)`: the tree's
own depth is what `filter-tree/011`-`013` pin against SEC-3's budget, and collapsing it would make a
boundary fixture indistinguishable from a shallower one.

A tree-level `NOT` gets the **same null fan-out as SQL-2's third bullet**, at every `notNode` at every
depth: `{"$or": [{"$nor": [<child>]}, {"<field>": null}, ...]}`, one `{field: null}` clause per distinct
field referenced in the child subtree, in first-appearance order. `$nor` alone is not enough, because
it returns a null document only when the child fails to match it, and `neq`, `blank`, an inner `not`
or an `or` whose other field matches all do match one (SEM-2). The `{field: null}` clause is the
*inclusion* SEM-2 requires and not the `{field: {$ne: null}}` guard its second MongoDB Must-NOT forbids.

**MDB-3. SEM-2's null inclusion is an explicit `$or` with a `{field: null}` clause.**
`{"$or": [{"name": {"$ne": "Alice"}}, {"name": null}]}` — emitted for `neq`, `notContains` and
`notIn` alike, and (per MDB-1's reasoning) emitted even though MongoDB's own `$ne` already matches a
missing field. `{field: null}` covers a stored null and a missing field together, so it is one
clause rather than two.

**MDB-4. `notContains` keeps the negation on the operator: `{"c": {"$not": {"$regex": …}}}`.**
SQL-3's rule reached by a different route. `$nor` is this document's rendering of a **tree-level**
`notNode` (MDB-2), so spelling a single negated comparison that way makes one leaf's negation
indistinguishable from a one-child `NOT` node in the artifact, on top of losing the field-scoped
form MongoDB can index. MDB-3's null-inclusive `$or` still wraps it: `$not` alone drops
missing-field documents.

**MDB-5. `blank`/`notBlank` are `$in`/`$nin` over `[null, ""]` on a `string`, and
`null`/`{"$ne": null}` on every other type.** SEM-2 requires `notBlank` to be `blank`'s *compiled*
negation and never a re-derived condition; MongoDB has an operator-level negation for each arm
(`$nin` for `$in`, `$ne` for the implicit equality), so the negation is applied to the very operator
the positive arm chose. SQL-7's second question does not arise here: MongoDB stores `""` as a value
distinct from null, so the field-type half is the whole answer.

**MDB-6. `inRange` is ONE field document carrying both bounds, never an `$and` of two clauses.**
`{"age": {"$gte": 18, "$lt": 65}}`, each bound spelled from its own explicit inclusivity flag
(SEM-4). This is the only place in MongoDB's query language where two constraints on one field
compose without a composite, and it is available here because `inRange` is a single
`rangeComparisonNode` — one IR leaf, not an `and` of two. It is **not** GRP-5's flattening being
readmitted: an AG Grid within-column AND of two conditions is two IR leaves and **is** an `$and`
(`ag-grid-majors/002`), and the two look nearly identical on the wire.

**MDB-7. The artifact is the bare pipeline array, or the `{pipeline, collation}` wrapper — the
wrapper if and only if a query-level collation is present.** MongoDB's `collation` is an
`aggregate()` **command** option, not a stage, so it cannot be an element of the pipeline array;
`spec/fixtures/schemas/mongo-artifact.schema.json` admits both shapes and this rule is what chooses
between them. A collation is present exactly when some construct resolved to SEM-1's *collation*
mechanism case-insensitively — a user's `$eq`/`$ne`/`$gt`/`$gte`/`$lt`/`$lte`/`$in`/`$nin` on a
case-insensitive `string`, or a `$sort` key on one. `$regex` never contributes (SEM-1 assigns the
substring family the pattern-match mechanism, which carries its own `$options: "i"`), and neither
does any pipeline that computes bucket identity (GRP-2's accepted divergence #3).

**MDB-8. SEM-3's bucket names, including the two SEM-3 does not define.** SEM-3 pins
`__<field>NullBucket` for an ordinary sort key. A grouping request needs two more names, and they
are pinned here because nothing else names them:

| Sort key | Bucket field | Sorted path |
|---|---|---|
| an ordinary field | `__<field>NullBucket` | the field's physical path |
| a grouped level's group column | **`__groupNullBucket`** | `_id` |
| an aggregate output | **`__<output name>NullBucket`** | the output name |

The group key's bucket is named for the **role**, not for the column, because the column changes per
level while the key it lands on (`_id`) does not. The trio is contiguous — `$addFields`, `$sort`,
`$unset`, nothing between them — the bucket key precedes its own field in the `$sort` document, and
the bucket's sign follows `nullsPosition` **independently** of the field's direction (`1` = nulls
last), since the bucket is `1` for null and `0` otherwise.

**MDB-9. Where a pipeline carries a collation, a case-*sensitive* string comparison renders as an
`$expr`; a case-sensitive *sort key* in that pipeline is a compiler error.** MongoDB's collation is
query-level: it governs `$match`, `$group` and `$sort` together and has no per-stage form. So a
request comparing an insensitive field and a sensitive one — which the five SQL dialects render side
by side, each spelling its own mechanism per SQL-6 — has, naively, no MongoDB pipeline that honours
both, and the naive rendering silently folds case on the field SC-3 declared sensitive. That is
SEM-1's third Must-NOT inverted, and it is a *wrong rows* bug rather than an ordering one.

The intended escape is the aggregation-expression form: it compares by simple binary comparison, which
is why SEM-2's own MongoDB paragraph notes that a case-**in**sensitive comparison inside an `$expr` has
to be spelled with `$strcasecmp`. **That premise is false on MongoDB 7.0**, which applies the
aggregate's query-level collation to `$expr` comparisons too (the engine run of `dialect-parity/023`
showed it); see *Accepted divergence #5* below. The `$expr` form is still what the compiler emits,
because it is the one spelling that keeps the sensitive comparison out of the query language and is
what the artifacts pin, but it does not hold the field case-sensitive under a collation.

| Family | Under no collation | Under a collation, on a `sensitive` field |
|---|---|---|
| scalar (`eq`…`lte`) | `{"c": {"$eq": v}}` | `{"$expr": {"$eq": ["$c", {"$literal": v}]}}` |
| set (`in`/`notIn`), non-empty | `{"c": {"$in": [...]}}` / `$nin` | `{"$expr": {"$in": ["$c", [{"$literal": v₁}, …]]}}` / `{"$expr": {"$not": [{"$in": …}]}}` |
| set, empty list (SEM-8) | `{"c": {"$in": []}}` / `{"c": {"$nin": []}}` | **unchanged** — the constant applies before any collation or `$expr` choice |
| `inRange` | one field document (MDB-6) | `{"$expr": {"$and": [{"$gte": ["$c", {"$literal": a}]}, {"$lt": ["$c", {"$literal": b}]}]}}` |
| substring | `{"c": {"$regex": …}}` | **unchanged** — a collation does not reach a `$regex` at all |
| sort key | `{"c": 1}` | **rejected** — see below |

Four consequences worth spelling out, because each is a place a port will guess:

- **The escape is per *field*, not per request.** The insensitive comparison stays in the query
  language and keeps the collation (and its index); only the sensitive one moves.
- **Every value operand MUST be wrapped in `{"$literal": v}` — this is a correctness *and* a
  security requirement, not a formatting one, and it is MDB-9's easiest rule to omit.** In the
  aggregation-expression language, and *only* there, a string beginning with `$` is a **field path
  reference**: MongoDB's own `$literal` reference states it and gives this example —
  `{"$eq": ["$price", "$1"]}` compares the `price` field against the field named `1`. So a client
  filter value of `"$salary"` on a `sensitive` field compiles, unwrapped, to
  `{"$expr": {"$eq": ["$employeeCode", "$salary"]}}`, which compares one column against **another
  column** instead of against the string the user typed. Two defects at once: silently wrong rows,
  and a client reaching any path the grid never exposed — nested (`"$salary.amount"`) and variables
  (`"$$ROOT"`) included. SEC-2 requires every compared value to be bound; the aggregation language
  has no parameters, and `{"$literal": v}` is its equivalent. The **field** operand is not wrapped —
  a compiler mints it from the schema and it is *meant* to resolve as a path.
  - **Wrap unconditionally, whatever the value's type.** Only a string can spell a path today, so a
    type-conditional wrap would be correct and is still forbidden: it is a second rule where MDB-1
    and SQL-1 both insist on one, and "only strings are at risk" is already false at the JSON level
    — a `decimal` is `{"$numberDecimal": "1000"}`, a document whose first key starts with `$`, which
    in expression position is an *operator* position. That is unreachable only because SEM-1 makes
    `Sensitive` string-only, an invariant of the *resolver* that MDB-9's correctness must not depend
    on. `$literal` returns any BSON value unevaluated, so the uniform rule costs nothing.
  - The set family's second operand is an **array expression**, whose elements are parsed as
    expressions in turn — so each member is wrapped individually rather than the array as a whole.
    The unit is "one IR value", the same unit the scalar and range rows use.
- **`inRange` is the one construct whose SHAPE changes**, from MDB-6's single field document to a
  two-clause `$and`, because an expression operator takes operands and has no field to hang two of
  them off. It is still one IR leaf.
- **A `$sort` has no escape and is therefore refused.** The aggregation language has no "order these
  documents" expression, so a key on a `sensitive` string in a pipeline that carries a collation
  cannot be rendered exactly. The compiler MUST raise an error naming both constructs rather than
  emit a plausible pipeline that returns the right rows in the wrong order — SQL-7(b)'s register,
  and GRP-4's. SEM-6's **appended** tiebreaker never triggers this: an appended key resolves
  `NotApplicable`, not `Sensitive`.

The `$`-as-path rewriting is confined to the aggregation-expression language. The *query* language
performs no such thing — in `{"c": {"$eq": "$salary"}}` the value is the four-character string, and
the only value the query language reinterprets is a BSON regex — so no ordinary field document,
`$in` array, `$regex` pattern or `blank` sentinel elsewhere in this addendum needs binding. That
asymmetry is the whole reason the requirement is easy to lose: the escape moves a value that was
safe into the one place it is not.

*Accepted divergence #5 — MongoDB cannot hold a case-sensitive field in the same request as
case-insensitive ones.* A pipeline that carries a query-level collation (SEM-1 wants one for the
case-insensitive field) compares **every** string under it, a `sensitive` field's `$expr` included, and
no per-stage or per-expression form exists in the pinned subset. A request that mixes the two
sensitivities therefore returns, on MongoDB, rows that match case-insensitively on the field SC-3
declared sensitive: SEM-1's third Must-NOT, accepted here in the same register as GRP-2's divergences
#3 and #4. `dialect-parity/023` records it as an XEQ-4 `allowedDivergence` entry for `mongo`, whose
`expected` holds the rows the engine returns (`ab-100` and `Ab-100` match `AB-100`); the six other
backends return the exact rows. A host that needs case-sensitive matching on MongoDB keeps that field
out of a request that also carries a collation.

*Pinned by* `dialect-parity/023`, the suite's only artifact containing an `$expr`. The `$literal`
binding of a `$`-prefixed value and the sort refusal are pinned by unit tests alone
(`MongoPipelineOperatorTests`, `MongoPipelineSortAndPagingTests`) — the sort refusal because there
is no artifact for a request that does not compile (exactly as for SQL-7(b)), the binding because
the other six backends bind such a value through their own parameter mechanism and would show
nothing the existing arms do not already show.

**MDB-10. Every stage MongoDB emits is a document, so every name a request can influence needs a
collision check.** A repeated key in a BSON document is last-wins, not an error, and three of the
names in a compiled pipeline are client-influenced: the `$sort` keys (a grid may send a colId twice
in `sortModel`; since SEM-6's reduction that no longer reaches the compiler, see the first collision),
the aggregate output names and hence their buckets (AGG-2 derives them from
`valueCols[].id`), and MDB-8's reserved `__groupNullBucket`. Each collision is silent and each
changes the answer:

- **two sort keys on one field** (`region asc, region desc`) — the second `$sort` entry replaces the
  first, so the *secondary* key becomes primary. **Superseded by SEM-6 (Bug #2565):** the effective
  sort lists a field once (a later occurrence is dropped before any compiler sees the sort), so a request
  that repeats a colId no longer reaches this check and the first entry, the user's primary, stays primary.
  It was a rejection when this rule was written; such a request is now served on every arm. **One shape
  still reaches it:** a case-insensitive text stable key with keys after it (SEM-6's exception) lists the
  stable key's column twice, the user's key and the exact tiebreaker, and is served since #2809 by sorting the tiebreaker on its own
  synthetic field (`__<field>ExactKey`, a `$toHashedIndexKey` of the path) instead of refusing;
- **an aggregate whose output name is `group`** — its bucket is `__groupNullBucket`, which the group
  key also claims, so `_id` becomes the primary sort key, a null sorts last where nulls-first was
  requested, and `$unset` lists one name twice;
- **two aggregates with one output name** — the second accumulator replaces the first in `$group`,
  and the grid reads one column holding another column's number.

The second and third MUST be rejected (the first no longer arises: SEM-6's reduction removes a repeat, and its one exception, a
case-insensitive text stable key, gets the synthetic tiebreaker field above). Renaming either side is not an alternative: the emitted bucket name would
then depend on what else the request happened to contain, which is a worse oracle than an error.
There is no SQL counterpart to any of this — the SQL compiler renders null placement as an inline
expression rather than as a named field, and a repeated `ORDER BY` key is merely redundant on most of
them (SQL Server refuses it, error 169, which is the bug SEM-6's reduction prevents).

**MDB-11. SEM-7's escape set is "every **ASCII** character outside `[A-Za-z0-9]`", and "character"
means one ASCII byte.** SEM-7 states the rule as "a full backslash-escape of every character outside
`[A-Za-z0-9]`" and leaves *character* undefined, which is a real ambiguity rather than a pedantic
one: a compiler iterating UTF-16 code units inserts a backslash **between the two halves of a
surrogate pair**, producing two lone surrogates — and a JSON writer then replaces each with U+FFFD,
so `contains "😀"` compiles to a pattern matching nothing, silently. Restricting the escape to ASCII
answers the question by removing it, at no semantic cost: PCRE2, the engine `$regex` uses, has no
metacharacter above U+007F, so escaping a non-ASCII character can only change the pattern's spelling.
A port that reads SEM-7 as "every character" and iterates code points emits a *different pattern for
the same IR*, which is a G4 divergence; this rule is what both ports have to agree on.
`dialect-parity/020` and `/022` pin the ASCII half (`50% off (bonus)` → `50\%\ off\ \(bonus\)`).

**MDB-12. The pinned floor is MongoDB 4.2.** Two constructs put it there, and both are emitted by
essentially every pipeline this compiler produces, so the floor is not conditional on the request:

| Construct | Introduced | Emitted by |
|---|---|---|
| `$unset` as an **aggregation stage** | **4.2** | SEM-3's null-bucket trio — i.e. every pipeline, since SEM-6 makes the tiebreaker unconditional |
| `{"$not": {"$regex": …}}` in a query | **4.0.7** | MDB-4's `notContains`; earlier servers require the BSON regex type instead of the `$regex` operator here |

Recorded explicitly, in the same register as Oracle's 12.2 floor (SQL-6) and SQLite's 3.30.0 one:
both of those are loud failures when unmet, and so is this — an unrecognised pipeline stage is a
server error, not a silent difference. A host on 4.0/4.2 that wants `$unset` avoided would need
`$project` with the buckets excluded, which changes every artifact in the suite and is therefore a
different rendering rule rather than a configuration option.

**Cross-links.** `spec/fixtures/schemas/mongo-artifact.schema.json` (the two artifact shapes),
`$defs/andNode`, `$defs/orNode`, `$defs/notNode`, `$defs/unaryOperator`, `$defs/binaryOperator`,
`$defs/setOperator`, `$defs/rangeComparisonNode`, `$defs/sortItem`, SEM-1, SEM-2, SEM-3, SEM-4,
SEM-6, SEM-7, SEC-4, SEC-5, AGG-1, AGG-2, **AGG-6** (already satisfied natively here — `$sum` returns
0 and the other three return null, so no accumulator changes), GRP-2..GRP-6, and the SQL addendum's
SQL-0 (`source`), SQL-2 (the composite wrap this one parallels) and SQL-3 (the
negation-on-the-operator rule MDB-4 reaches independently).

---

## Addendum — canonical OpenSearch/Elasticsearch rendering (OSE-0..OSE-14; not numbered SEM-*, for the
same reason as the SQL and MongoDB addenda above, of which this is the exact parallel for the third
artifact family)

The SQL addendum exists because #1638 found the *same IR construct rendered several different ways
from identical inputs* across a fixture suite seven parallel agents had hand-authored with no
compiler to check it; the MongoDB one because #1643 reproduced the finding on the second arm. #1644
compiled the **Search** arm for the first time and reproduced it on the third and last: a `term` on a
`string` was spelled long 64 times and short 4, a `term` on a `boolean` short 13 times and long once
*for the identical construct in two categories*, `must_not` took an array in one `notBlank` and an
object in three, and one artifact folded a bound value that its own six sibling arms bound as typed.
So the answers are pinned here, once, and every language port inherits them instead of rediscovering
them — and **not** as prose under SEM-1..SEM-7, whose snippets this document's own preamble disclaims
as illustrative. A normative sentence there would contradict the framing, and that ambiguity is
precisely what let those pairs disagree in the first place.

Each rule below is the form the `spec/fixtures/*/expected/search.artifact.json` files now contain —
**all 160 of them, `page-export/`'s fourteen included**. That category was excluded from the
conformance runner until #1650, on `exportScope` (#1623) and never on these rules — and four of its
arms had drifted precisely because nothing could compile them, which #1644's review pass corrected
under OSE-1 and OSE-3 before the exclusion was lifted. Where a
rule is a **refusal**, there is no artifact by construction, and the fixture that used to carry one
says so in its own `description.md` — `group-aggregation/020` is the only such case.
**There is ONE compiler and ONE artifact for both engines** (OQ-7), so unlike the SQL addendum
nothing here is "the reference engine's spelling, other engines differ" — see OSE-14 for why that is
a fact about the pinned subset rather than an aspiration. SQL-0 is *not* SQL-specific and is not
restated: a compiled request takes its index from `schema.source` and never from the request.

**OSE-0. Object key order is NOT part of this artifact contract; array order is.** Nowhere in a
search request body does a JSON object's key order carry meaning, so a conformance harness compares
these artifacts with object keys canonicalised and arrays left as written. That is the opposite of
MDB-7's arm, and deliberately: MongoDB's `$sort` document *is* order-sensitive — its key order is the
tiebreak order — so the Mongo comparison is order-sensitive too. Here the order-bearing structures
are arrays: `sort`'s element order is the tiebreak order and `composite.sources`' is the composite
key order, and both are compared as written.

*Why this is a rule rather than a harness convenience.* The hand-authored suite spells `size` before
`from` in 78 files and after it in 50. Neither is more correct, no engine reads the difference, and
picking one would have re-authored half the suite to agree about nothing. What a compiler still owes
is **determinism** — four language ports emitting one IR in four member orders would produce four
different files — so a compiler MUST fix its own order and pin it. The reference implementation emits
`query`, `sort`, `from`, `size`, `aggs`, absent members omitted.

**OSE-1. A `term` query's form is decided by the field's declared TYPE: the long form for a
`string`, the short form for every other type.**

```json
{ "term": { "status.keyword": { "value": "active", "case_insensitive": true } } }
{ "term": { "status.keyword": { "value": "EMEA" } } }
{ "term": { "age": 30 } }
```

*Why the type and not "whether a parameter is present".* SEM-1 governs `stringValue` comparisons
only, so `case_insensitive` — the parameter the long form exists to carry — can only ever appear on a
string. Keying the spelling on the type therefore gives **one field one spelling**, whatever its
declared `caseSensitivity`, which is the property the alternative loses: GRP-2 pins the parameterless
string form by hand ("ES/OpenSearch drops the `case_insensitive: true` parameter from a drill-down
`term`, leaving `{"term": {"<field>.keyword": {"value": "EMEA"}}}`") and `dialect-parity/014` uses the
identical shape for the case-sensitive opt-in, so a rule of "long only when the parameter is there"
is already contradicted twice over. **71** string `term`s in the suite now take the long form, **4**
of which had been authored short; **14** non-string `term`s take the short form, **1** of which had
been authored long (`filter-tree/001`'s boolean, whose own construct `operators/044` spells short).
**Five** artifacts were re-authored onto this rule in #1644 and its review pass — the 4 plus the 1.
*(This census read "64 long / 4 short" until #1650's review pass recounted it: the long figure was
two short of the artifacts on disk even when it was written, and `page-export/023`'s new arm has
since added a seventy-first. The counts are the argument here, so they are stated as occurrences of
`term` across every `expected/search.artifact.json`, which is what a recount reproduces.)*

*The fourth short one is worth naming, because it weakens the argument this rule would otherwise lean
on.* Three of the four were `blank`'s empty-string sentinel (`operators/029`, `/030`,
`dialect-parity/019`) — a compiler-minted value, an easy special case to explain away. The fourth,
found by the review pass in `page-export/004`, is an ordinary **client** value on a `sensitive`
`string` (`{"term": {"status.keyword": "shipped"}}`), and it survived only because `page-export` is
excluded from all three conformance runners. So the artifact evidence for "the type, not the
parameter" is 71-to-4 rather than 71-to-3-plus-a-sentinel, and the rule rests where it always really
did: on GRP-2's normative sentence and `dialect-parity/014`, not on the counts. It was corrected
rather than left for #1623 to re-adjudicate.

**OSE-2. The composites, and the one that is spelled differently from the negation a compiler
composes itself.** `andNode` → `{"bool": {"must": [...]}}`, `orNode` →
`{"bool": {"should": [...], "minimum_should_match": 1}}`, and a tree-level `notNode` →
`{"bool": {"must_not": [<child>]}}` — an **array** — wrapped in the null fan-out below. A single-child composite is **not** collapsed
(`{"bool": {"must": [x]}}`), mirroring SQL-2's `(x)` and MDB-2's `{"$and": [x]}`: the tree's own depth
is what `filter-tree/011`-`013` pin against SEC-3's budget, and collapsing it would make a boundary
fixture indistinguishable from a shallower one.

`minimum_should_match: 1` is spelled **explicitly and unconditionally**, and it is not decoration: a
`bool` that also carries `must` or `filter` defaults it to **0**, at which point the `should` clauses
become scoring hints that constrain nothing. Every `or` a compiler emits is a real constraint, and
spelling the parameter always means the same subtree renders the same way wherever it lands in the
tree — SQL-2's "one rule per construct, applied always".

A tree-level `NOT` gets the **same null fan-out as SQL-2's third bullet**, at every `notNode` at every
depth, exactly as MDB-2 records for `$nor`: `{"bool": {"should": [{"bool": {"must_not": [<child>]}},
{"bool": {"must_not": {"exists": {"field": "<raw field>"}}}}, ...], "minimum_should_match": 1}}`, one
`exists` complement per distinct field referenced in the child subtree, in first-appearance order. A
`must_not` alone matches a document with a missing field only when the child cannot match it, which
`neq`, `blank`, an inner `not` or an `or` over two fields can (SEM-2). The inner `must_not` keeps its
array spelling, so a tree `NOT` stays distinguishable from a composed negation (OSE-4).

**OSE-3. The `query` member has two forms, chosen by the request shape.** An ordinary row query
renders its filter tree directly, and `{"match_all": {}}` when it has none — a hit-returning request
always carries an explicit query. A **grouping or distinct-values** request wraps everything in
`{"bool": {"filter": [...]}}`, and omits the member entirely when there is nothing to filter.

*Why the second form exists.* Its clauses come from two provenances that must be conjoined (GRP-5's
drill-down leads, the user's own filter follows — GRP-5 pins that order), and `filter` is both this
DSL's conjunction container and its non-scoring context, which is what a request asking for buckets
rather than ranked hits wants. A top-level `and` on either side contributes its **children** to that
array rather than a nested `bool.must`, because the array already is the conjunction —
`ag-grid-majors/004` pins two range clauses side by side, `group-aggregation/003`/`004` pin the
drill-down's two and three, and **`group-aggregation/023` pins both halves at once**: a two-key
drill-down and a two-column filter model flattening into one four-element array, in GRP-5's order.
That is not SQL-2's "every composite wraps" being readmitted through the back door: the wrap is still
there, spelled as the `filter` array itself. A top-level `or` is a single element of it, wrapped
normally.

`023` was authored by #1644's review pass because **no fixture in the suite carried both a consumed
`groupKeys` and a `filterModel`**, which left GRP-5's order unpinned on all three backends at once —
reversing the two compositions passed every test in every suite. Neither `003` nor `004` has a user
filter, so citing them for the order (as an earlier draft of this rule did) proved only the
drill-down's own flattening.

**OSE-4. `blank`/`notBlank`, and the array-versus-object spelling of `must_not`.**

```json
// blank, string:      absent OR the empty term
{ "bool": { "should": [ { "bool": { "must_not": { "exists": { "field": "status" } } } },
                        { "term": { "status.keyword": { "value": "" } } } ],
            "minimum_should_match": 1 } }
// blank, any other type:
{ "bool": { "must_not": { "exists": { "field": "age" } } } }
// notBlank: THAT clause, negated
{ "bool": { "must_not": { <blank> } } }
```

`notBlank` is the compiled `blank` under a `must_not` and never a separately derived condition —
SEM-2's third Must-NOT, satisfied structurally rather than by two renderings that happen to agree.
There is no counterpart to SQL-7's second question ("does this engine treat `''` as NULL?"): both
engines store the empty string as an ordinary term distinct from a missing field, so the field-type
half is the whole answer.

**`must_not` takes a single clause OBJECT for a negation the compiler composed, and an ARRAY for a
tree-level `notNode` (OSE-2).** This DSL has one negation keyword where SQL has two constructs
(SQL-3's negated operator versus an outer `NOT (...)`) and MongoDB has two operators (MDB-4's `$not`
versus MDB-2's `$nor`), so the array is what keeps a one-child tree `NOT` distinguishable, in the
artifact, from a single negated comparison. `dialect-parity/019` spelled its `notBlank` as an array
until #1644; nine `filter-tree/` artifacts spell the tree form that way and three `operators/` ones
spell the leaf form as an object.

**The empty-string sentinel carries no `case_insensitive`, whatever the field declares.** That is not
the conditional spelling OSE-1 forbids: the parameter governs how a CLIENT's value is compared and
this value is not one — it is the sentinel SEM-2's own definition of `blank` mints. An empty string
has no case to fold, so the parameter is provably inert, and GRP-2's precedent is that a
compiler-minted key spells no mechanism.

**OSE-5. SEM-2's null inclusion is a `should` of two `must_not`s, and the `exists` clause names the
BASE field.**

```json
{ "bool": { "should": [ { "bool": { "must_not": <the affirmative clause> } },
                        { "bool": { "must_not": { "exists": { "field": "name" } } } } ],
            "minimum_should_match": 1 } }
```

Emitted for `neq`, `notContains` and `notIn` alike, and the affirmative clause is compiled first and
then negated, so the two directions cannot drift. SEM-2's own ES worked example spells both `should`
clauses and says why: the first alone *happens* to cover the missing-field case for a `term` query,
but that is a property of `term` specifically and is not guaranteed for every query type an operator
might compile to, so the second is explicit on every operator, unconditionally.

The `exists` clause names `search.field`, never `search.keywordSubField`: a `.keyword` sub-field's own
presence is an indexing detail (`ignore_above` can drop a long value from it while the base field
still holds one), so "this document has no value for this column" is a question only the base field
answers.

**OSE-6. Which of SC-4's three search names each construct addresses.** They are three independent
names and a compiler picks per construct, never once per field:

| Construct | Target |
|---|---|
| `exists` (OSE-5, OSE-4) | `search.field` — always, whatever the comparison beside it uses |
| `term` / `terms` on a `string` | `search.keywordSubField` |
| `wildcard` (SEM-7's substring family) | `search.keywordSubField` |
| `match` (SEM-7's `searchMode: analyzed` opt-in) | `search.field` — the analyzed one is the point |
| `range` / `sort` on a case-**insensitive** `string` | **`search.normalizedSubField`** (SEM-1's one real gap) — **except SEM-6's appended tiebreaker, which resolves exact and takes `search.keywordSubField`** |
| `range` / `sort` on a case-**sensitive** `string` | `search.keywordSubField` |
| anything on a non-`string` field, and an aggregation metric | `search.field` |
| a `composite` source / a BM-3 `terms` key on a `string` | `search.keywordSubField` |

`search.keywordSubField` falls back to `search.field` when a schema declares none (the identity the
schema is implicitly declaring by omitting it, the same fallback the other two compilers make for a
missing mapping), and `search.field` falls back to the colId. **`search.normalizedSubField` has no
fallback: its absence is a compiler error.** SEM-1 states it as a MUST on the schema, and both
alternatives are wrong in the way this project refuses — `.keyword` would order `"Zebra"` before
`"apple"` on a field the schema declared case-insensitive, and the analyzed base field is not
sortable at all. Wrong rows in the wrong order on a request both engines accept, invisible to the
artifact tier: SQL-7(b)'s and MDB-9's register.

**The one carve-out, and it is load-bearing: SEM-6's appended tiebreaker resolves EXACT** (see the
"Superseded in part by #1640's review" note under SEM-6), so it takes `search.keywordSubField` even on
a case-insensitive `string` and a schema declaring no `normalizedSubField` is **not** an error for
that key. Without the carve-out the table above would demand `normalizedSubField` or a refusal for a
key the compiler minted, which would fail two fixtures that are otherwise entirely ordinary:
`group-aggregation/005` and `006` declare `id` as a `string` with no `text` block — case-insensitive
by SEM-1's default — and no `normalizedSubField`, and their leaf queries sort on the bare appended
`id`. The rule is a property of the **key's provenance**, not of the field: the *same* `id`, sorted on
because the user asked, would take `normalizedSubField` and refuse without one.

**The bound value is never transformed.** See SEM-1's own note above: the sub-field is the mechanism,
a term-level query has the normalizer applied to its value at search time anyway, the compiler cannot
see what that normalizer does, and "lowercase" is not one operation across four language ports.

**`searchMode: "analyzed"` on a case-SENSITIVE field is refused, not compiled.** The `match` row
above is the SEM-7 opt-in, and a `match` has no `case_insensitive` parameter and no case control of
any kind: it is resolved entirely by the field's own analyzer, and every stock text analyzer in both
engines lowercases. So the combination emits a query that folds case on a field the schema declared
sensitive — SEM-1's **second Must-NOT**, and the same failure the missing `normalizedSubField` is
refused for, in the other direction. There is no third rendering to fall back to: a `wildcard` would
honour the case and lose the tokenization the opt-in exists to ask for. The two declarations
contradict each other, so the schema is what changes. No fixture reaches this combination —
`dialect-parity/013` is the suite's only `analyzed` field and it is case-insensitive — which is
precisely why it is written down here.

**OSE-7. Set membership is a `terms` query — except on a case-insensitive `string`, where it is a
`should` of `term` queries.** *(An empty list is SEM-8's constant, `match_none` / `match_all`, before either form.)*

```json
{ "terms": { "age": [30, 40] } }
{ "bool": { "should": [ { "term": { "status.keyword": { "value": "active",  "case_insensitive": true } } },
                        { "term": { "status.keyword": { "value": "pending", "case_insensitive": true } } } ],
            "minimum_should_match": 1 } }
```

Not a stylistic split: **`terms` has no `case_insensitive` parameter** in the pinned subset (the
parameter exists on `term`, `prefix`, `wildcard` and `regexp` only), so it cannot realize SEM-1's
mechanism at all, and emitting it anyway would silently make `in` case-sensitive on a field the schema
declared insensitive — SEM-1's second Must-NOT. The disjunction is the same set membership with the
parameter available on each member. `operators/035` and `dialect-parity/016` pin the disjunction;
`operators/037` and `dialect-parity/018` (a `sensitive` column) pin the compact form.

**OSE-8. `range` carries every bound of one IR leaf, plus an explicit `format` for a date-typed
field and nothing else.** The four ordering operators and `inRange` are all one `range` query —
`inRange` included, because it is a single `rangeComparisonNode`, the same argument MDB-6 makes for
MongoDB's single field document. An AG Grid within-column AND of two conditions IS two leaves and
does render as two clauses (`ag-grid-majors/002`).

- Each bound is spelled from its OWN explicit inclusivity flag (SEM-4), never `BETWEEN`'s familiar
  inclusive-inclusive assumption.
- `format` is **`strict_date`** for a `date` field and **`strict_date_optional_time`** for a
  `datetime` one, and absent for every other type. The two are not interchangeable: `strict_date` is
  `yyyy-MM-dd` and nothing else, which is exactly what a `dateValue` is, while spelling the datetime
  form for a calendar date would accept a time-of-day the IR guarantees is absent — SEM-4's third
  Must-NOT as a parser setting. Spelling it at all pins the accepted string shape rather than leaving
  it to the index mapping's own `format` list.
- **No `time_zone`, ever** (SEM-4's second Must-NOT names the parameter). It would also be inert:
  `time_zone` shifts only *unqualified* date-math strings, and every boundary reaching a compiler is
  already an absolute instant or a calendar date.
- A `datetimeValue` is normalised to UTC with a trailing `Z`, so the same instant written `+02:00`
  and written `Z` produces one artifact. It is spelled with **exactly three fractional digits**
  (`2026-01-01T00:00:00.000Z`, never `...:00Z`): in a `range` query this DSL's date math rounds a
  bound that omits the milliseconds **up** to the end of that second (`.999`) for `gt` and `lte`, so
  `gt 2026-01-01T00:00:00Z` would wrongly exclude a row at `.001Z`. `operators/012`, `024` and `041`
  pin it. A `date` (`strict_date`, `yyyy-MM-dd`) has no time-of-day and is unaffected.
- A `decimalValue` is written as a **JSON number whose text is the IR's own exact decimal literal**.
  This DSL's request body has no arbitrary-precision numeric literal the way Extended JSON's
  `$numberDecimal` does, so the only correct answer is to pass the token through unparsed rather than
  round-trip it through an IEEE double — which is what makes `decimal` and `double` different types in
  the first place. A host needing exact decimal arithmetic maps the field accordingly, a PERF-4
  index-guidance obligation of the same kind as GRP-2's DDL ones.

**OSE-9. Every `sort` element spells both `order` and `missing`.** SEM-3's null placement is a native
parameter here — no emulation, nothing to unset afterwards, unlike MySQL's `ISNULL` prefix key or
MongoDB's synthetic bucket. It is spelled on every key **unconditionally**, including SEM-6's appended
tiebreaker: SEM-3's first Must-NOT forbids relying on an engine's implicit default even when it
happens to match today, and SEM-6's fourth forbids "the stable key is probably never null" as a
licence to omit the marker.

A repeated sort key **does not reach this compiler**: SEM-6 drops a later occurrence of a field before
the sort is compiled (Bug #2565), so there is nothing to reject here for a repeated colId. (The one shape
that still lists a column twice, a case-insensitive text stable key with keys after it, names two
*different* sub-fields on this arm, `normalizedSubField` and `keywordSubField`, and is served.)
The difference this paragraph used to draw is still the reason the two engines needed different
answers *before* that reduction: `sort` is an ARRAY, where a colId sent twice is merely redundant and
the primary key stays primary, whereas a `$sort` **document** silently replaces the first entry and
promotes the secondary key.

**Which sub-field each key addresses is OSE-6's table, including its one carve-out**, which is easy to
lose sight of here because this rule is about the two parameters rather than the target: a user's own
key on a case-insensitive `string` takes `search.normalizedSubField` and refuses when the schema
declares none, while **SEM-6's appended tiebreaker resolves exact and takes
`search.keywordSubField`** — the same field can therefore be a hard error in one position and
perfectly ordinary in the other. `group-aggregation/005` and `006` are the fixtures that depend on it:
both sort a leaf on the appended `id`, a `string` with no `text` block and no `normalizedSubField`.

**OSE-10. `from` and `size`, and the two members a bucket request does not have.** `from` takes
`startRow` and `size` the row COUNT (`endRow - startRow`, because `endRow` is exclusive). Both are
emitted for a range page even when the offset is zero. EXP-2's `page: none` emits **neither**
(`sort-paging/012`). A grouping or distinct-values request emits `"size": 0` — it wants buckets and no
hits — and no `sort` and no `from` at all; the two request shapes are structurally different bodies
rather than one body with optional members, and `size: 0` beside a `sort` orders nothing.

**`search_after` is deliberately never emitted.** PERF-2 scopes it to deep paging beyond
`max_result_window`, with a cursor cache it assigns by name to the **execution adapter** (#1622).
`max_result_window` is index configuration absent from `GridSchema` and from the IR; the cursor is
the previous page's last sort values, which an offset-based AG Grid SSRM request never sends and
`$defs/pageSpec` has nowhere to carry. All 160 `search.artifact.json` files pin the offset form.
`spec/fixtures/schemas/search-artifact.schema.json` admits the member so that #1622 can use it
without a schema change; nothing does today.

**OSE-11. The grouped level is a `composite` aggregation, and five of its details are decided
here.**

```json
{ "size": 0,
  "aggs": { "<group column>": {
    "composite": { "size": <row window>,
                   "sources": [ { "<group column>": { "terms": { "field": "<keyword sub-field>",
                                                                 "missing_bucket": true } } } ] },
    "aggs": { "<output name>": { "<sum|min|max|avg|value_count>": { "field": "<base field>" } } } } } }
```

*(a) `composite` rather than `terms`, and `missing_bucket` rather than nothing.* A grouped level is
paged, and `composite` is the only bucket aggregation in this subset that enumerates every bucket in
key order rather than returning an approximate top-N by doc count. It is also the only one with
`missing_bucket`, which is what keeps a null group key from being silently dropped (AR-8/BM-2's
intent). `count` needs no special construction: `value_count` already skips missing values, so AGG-1
is satisfied natively — unlike MongoDB, where AGG-1 has to forbid `{"$sum": 1}` by name. The metric's
`field` is the **base** field.

*(b) **AGG-5's accepted divergence, honoured rather than worked around.*** `missing_bucket: true` has
no `missing_order` control in the pinned 7.10-era subset: the null bucket sorts **first regardless of
the direction requested**, while Postgres (`NULLS FIRST`/`NULLS LAST`) and MongoDB (its bucket
emulation) both honour it. The group key's own `nullsPosition` therefore compiles to **nothing at
all** here, and that silence is the rule rather than an omission. A client-side reorder would defeat
server-side paging's whole purpose for the grouped case.

*(c) The bucket ordering: the group column alone, and every other ordering is REFUSED.* AGG-4 exists
because a bare `terms` aggregation defaults to doc-count-descending, an order no other backend would
produce. A composite source is ordered by its key *by construction*, so there is no wrong default to
guard against, and its `order` parameter carries the DIRECTION the request asked for (GRP-4) rather
than a fixed `asc`. It is spelled **only for `desc`**, the source's documented default being
ascending — `group-aggregation/021` pins the one, the other **fifteen** composite artifacts pin its
absence.

**A grouped level ordered by anything other than its own group column is a compiler error.** A
composite source can only order by its own key, and the obvious workaround — a `bucket_sort`
sub-aggregation — does not answer the question that was asked. A composite **always** enumerates
buckets in composite-key order and returns `size` of them; `bucket_sort` is post-processing that
reorders only the buckets that page already contains. So "the 100 largest regions by revenue" would
compile to *the first 100 regions in key order, rearranged by revenue* — with more distinct regions
than the window, a **different set of groups**, silently, and invisibly to the artifact tier.
Elasticsearch's own composite documentation states the general form of this rather than a "limit": a
composite aggregation is **not compatible with pipeline aggregations**, and gives exactly this reason.

So the refusal is in OSE-11(d)'s own register, and in SQL-7(b)'s and MDB-9's: a plausible request that
answers a different question is worse than an error naming the reason. **This is a real, user-visible
capability gap on this backend and must be stated as one** — ordering a grouped level by an aggregate
does not work on OpenSearch/Elasticsearch. Closing it needs a different grouped-ordering *strategy* (a
two-pass `terms`-then-`composite` plan, or a full bucket enumeration reordered client-side), not a
different spelling; that is the execution adapter's business (**#1622**) and gradeable only against a
live cluster (**#1624**).

> **Superseded in part by #1644's review pass.** This rule previously rendered such an ordering as a
> `bucket_sort` sub-aggregation named `sortBy<PascalCase(first sort colId)>`, pinned by
> `group-aggregation/020`, with a recorded T-1b risk asking #1624 whether 7.10-era servers *accept* a
> pipeline aggregation under a composite. **Acceptance was never the real question**: even when
> accepted, the result answers a different question from every other backend's arm, which is settled
> here and needs no cluster. `020`'s Search arm has been deleted, the rule is a refusal, and the
> `bucket_sort` naming and its collision rule are gone with it.

*(d) The two row windows that are refused.* A composite pages forward with an `after` key rather than
an offset, so a grouped level asked for a **non-zero `startRow`** has no rendering, and one asked for
EXP-2's **`page: none`** has no bucket count to give. Both are compiler errors. Emitting `size` and
dropping the offset would answer every page with the first one — a plausible request answering a
different question, silently — which is SQL-7(b)'s and MDB-9's register again.

**The offset half is a first-page-only limitation, not a deep-paging one**, and conflating it with
PERF-2's `search_after` (OSE-10) understates it badly. `search_after` escalates only beyond
`max_result_window`, 10 000 rows by default, so an ordinary grid never reaches it; AG Grid SSRM's
default block size is **100 rows**, so the **second block of any grouped level** — one screen of
scrolling past the first hundred groups — lands here. Every grouped grid on this backend hits it, not
only the deep ones. The owner is the same (the execution adapter, **#1622**, because the `after` key
is the previous response's own `after_key` and neither `$defs/pageSpec` nor `GridSchema` can carry
it), but the urgency is not.

*(e) Aggregation names are validated, not assumed.* An aggregate's output name is AGG-2's `alias` when
one is set and `<field>_<func>` otherwise, and **the default is held to the same
`^[A-Za-z_][A-Za-z0-9_]*$` pattern `ir.schema.json` already imposes on `alias`**. That pattern exists
because the name "lands in generated query text as an identifier … where SEC-2's values-are-parameters
rule cannot apply", but `$defs/fieldName` carries no pattern at all, so a nested colId such as
`customer.name` composes a default `customer.name_sum` that no validator has ever seen — and here an
aggregation name is read through a `buckets_path` mini-language in which `>` navigates into a
sub-aggregation and `.` selects a metric. A default name failing the pattern is refused, naming
`alias` as the fix. The **bucket** aggregation's own name (the group column, or BM-3's colId) is held
to the engines' own narrower rule instead — no `[`, `]` or `>`, which both engines reject outright —
because a dotted colId is a perfectly good container key and refusing it would break a nested-document
schema for nothing. Two names, two standards, because they are read by two different things: one is an
identifier the grid reads a number back by, the other is only ever a key. MDB-10's third collision
also applies here verbatim: two aggregates resolving to one output name are refused, since the `aggs`
container is a JSON object and the second would silently replace the first.

**OSE-12. BM-3's distinct values are a `terms` aggregation, and GRP-6(c)'s search prefix is its
`include`.**

```json
{ "size": 0,
  "aggs": { "<colId>": { "terms": { "field": "<keyword sub-field>",
                                    "size": <resolved cap>,
                                    "include": "<escaped prefix>.*",
                                    "order": { "_key": "asc" } } } } }
```

- **AGG-4 DOES reach this one**, and is spelled explicitly and unconditionally: a bare `terms`
  aggregation defaults to doc-count-descending, which would hand the grid its value list in a
  different order from Postgres's `ORDER BY` and Mongo's `$sort` on the identical request.
- **GRP-6(a)'s exactness costs nothing to arrange**: an aggregation has no `case_insensitive`
  parameter in the first place, so the distinct key is exact by construction.
- **GRP-6(e)**: the cap is a ceiling, so there is no `from` and no SEM-6 tiebreaker.
- **The prefix leaves the query entirely.** Filtering the *buckets* rather than the documents is
  equivalent for this one construct — a bucket exists exactly when some document holds its value, and
  the predicate is on the very column being bucketed — and `group-aggregation/018`/`022` pin the move.
  The escaped prefix is followed by the compiler's own `.*`, appended AFTER the escape so a literal
  `.` the user typed cannot merge into it.
- **The escape set is "every ASCII character outside `[A-Za-z0-9]`", MDB-11's rule for MDB-11's
  reason.** `include` is a **Lucene** regex — a third pattern language, different again from the
  `wildcard` query's syntax (OSE-2's SEC-4 alphabet) and from PCRE2. Lucene's `RegExp` reads `\` as
  "the next character, literally" for any next character, so over-escaping an ordinary ASCII
  character costs nothing and removes the need to carry a metacharacter table; under-escaping widens
  the bucket filter and reopens the ReDoS surface SEC-5 excludes user-controlled regex to avoid. The
  ASCII scope is what stops a backslash landing between the two halves of a surrogate pair, which a
  JSON writer then turns into two U+FFFD and a pattern matching nothing.
- **Accepted divergence: `include` has no case-insensitivity option** in the pinned subset, unlike the
  query-time `case_insensitive` on `term`/`wildcard`/`prefix`/`regexp`. So a set filter's search
  prefix matches **case-sensitively as typed** here, where Postgres's `ILIKE` and Mongo's
  `$regex`/`"i"` fold — SEM-1 assigning that predicate the pattern-match mechanism on both. Recorded
  in the same register as AGG-5; a field needing a case-insensitive value search would have to fold at
  index time, which is SEM-1's `search.normalizedSubField` obligation reappearing on the bucket side.
  `group-aggregation/018`'s description states it and `CrossCompilerGroupingTests` asserts it as an
  expected difference.

**OSE-13. There is no projection member: neither GRP-3 nor EXP-1(b) has a counterpart on this backend.**
`spec/fixtures/schemas/search-artifact.schema.json` declares `additionalProperties: false` over a
member set with no `_source` in it, so this is a contract rather than an omission. GRP-3's concern is
a *physical* column name reaching a grid that asked for a logical one; a hit's `_source` carries the
document's own field names, which the index mapping decides once rather than per query, so the
question is answered at index time. A drill-down leaf therefore emits no column list where SQL emits
an aliased one and MongoDB emits a `$project` — asserted as an expected difference rather than left
as an absence.

*EXP-1(b)'s export column list reaches the same answer, and `_source` filtering is **declined**, not
overlooked.* Elasticsearch and OpenSearch both support `_source: [...]` (and `_source: {includes,
excludes}`) on a search body, so narrowing is available here in a way it is not for GRP-3's aliasing
problem — the omission is therefore a decision and is recorded as one. Three grounds: it would be a
*narrowing* only, never a **renaming** or a **reordering**, so it could not deliver EXP-1(b)'s ordered,
logically-named column list and the writer would still have to do the whole job from `exportColumns`;
adding a member to the artifact's closed set would make it the one place where this backend's
compiled body varies with a property that changes nothing else about which documents match; and the
saving is bandwidth between the engine and the host process, which is an *execution*-adapter
trade-off (the same register as EXP-3's streaming and chunking, which is what that id really names)
rather than a compiled-query
semantic. The fourteen `page-export/` Search arms pin the absence: `008` narrows to three of seven
columns on SQL and MongoDB and its Search arm carries only a `query` and a `sort`. If a host wants the
bandwidth, `_source` is an adapter-level addition to the request it sends, not a change to this
contract.

**OSE-14. One compiler, both engines, and no target flag — a fact about the pinned subset, not an
aspiration.** #1621's DoD asks for OpenSearch-versus-Elasticsearch divergences to sit "behind a target
flag, not a second compiler". **No such divergence exists in this subset**, so there is no flag: a
one-setting flag is the same smell as a one-implementation dialect seam, which is why there is no
`IMongoDialect` either. Every construct this addendum names predates the fork (OpenSearch forked
Elasticsearch 7.10.2) and is spelled identically on both sides of it. The one parameter worth checking
is `case_insensitive`, SEM-1's mechanism here, which Elasticsearch added in **7.10** — the very
release OpenSearch forked from — so OpenSearch 1.0 inherited it and every supported version of both
engines has it. That is also this compiler's version floor, recorded in the same register as Oracle's
12.2 (SQL-6), SQLite's 3.30.0 and MongoDB's 4.2 (MDB-12), and it is a loud failure when unmet
(`unknown parameter [case_insensitive]`) rather than a silent one. If a future construct genuinely
does diverge, the seam to add is the one this project already uses for that shape of problem
(BM-1's `Dialect`), not a boolean threaded through a builder.

**OSE-15. The one place the two engines differ is the point-in-time lifecycle, and it is client
configuration, not part of the artifact.** OSE-14 holds for everything a compiler writes: one artifact, no
target flag. An execution adapter that pages beyond `max_result_window` (PERF-2, OSE-10) or exports (EXP-3) opens a
point-in-time first and closes it last, and **that** call differs, in exactly four places and nowhere else:

| | OpenSearch 2.x | Elasticsearch 8.x |
|---|---|---|
| create | `POST /{index}/_search/point_in_time?keep_alive=<duration>` | `POST /{index}/_pit?keep_alive=<duration>` |
| key holding the id in the answer | `pit_id` | `id` |
| close | `DELETE /_search/point_in_time` | `DELETE /_pit` |
| close body | `{"pit_id":["<id>"]}` | `{"id":"<id>"}` |

Searching with the point-in-time is the same on both: `pit` (`id`, `keep_alive`) in the request body, `search_after`
from the previous hit's `sort`, and `pit_id` in the answer. An adapter therefore takes the engine as a **host
setting** (`OpenSearch`, the default, or `Elasticsearch`) and applies it only to those four places. The setting never
reaches `search.artifact.json`, the compiler or a fixture; a conformance harness does not see it. An adapter that
cannot tell which engine it talks to uses `OpenSearch`, and against Elasticsearch fails loudly (HTTP 400), never
silently. The close stays best-effort and the keep-alive is still sent on every search (OSE-10).

**OSE-16. The row count above `max_result_window` is unknown by default, and a host may opt in to the exact count.**
PERF-3 asks for a bounded count, and the one a search engine gives cheaply is capped: `track_total_hits: <window>` clamps the
reported `value` at the window and reports `relation: "gte"` once the true total is larger. The adapter therefore reports **no
count** (`RowCount` null, so the grid's `lastRow` stays unknown and the grid keeps asking for blocks, PERF-2) when the total exceeds
`max_result_window`, and the exact one below it; it never reports the clamped number as if it were exact. The default stays, because
the exact count costs the cluster a count of every matching document on each first-block request. A host that wants the total opts in
with one setting (`ExactRowCount`), which changes **only** the count request to `track_total_hits: true`: the page query, the
point-in-time walk and the compiled artifact are unchanged, so no fixture and no other backend is affected. A grouped level's count
is a `cardinality` aggregation (approximate beyond its precision threshold) and is not affected by the setting.

**Cross-links.** `spec/fixtures/schemas/search-artifact.schema.json` (the member set OSE-13 rests on),
`$defs/andNode`, `$defs/orNode`, `$defs/notNode`, `$defs/unaryOperator`, `$defs/binaryOperator`,
`$defs/setOperator`, `$defs/rangeComparisonNode`, `$defs/sortItem`, `$defs/setValuesSpec`, SEM-1,
SEM-2, SEM-3, SEM-4, SEM-6, SEM-7, SEC-4, SEC-5, AGG-1, AGG-2, AGG-4, **AGG-5**, **AGG-6** (already
satisfied natively here — the `sum` metric returns 0 and the other three return null, so no metric
aggregation changes), GRP-2..GRP-6, and the SQL addendum's SQL-0 (`source`) and SQL-2 (the composite
wrap OSE-2 parallels).

---

## Addendum — execution equality (XEQ-1..XEQ-4; not numbered SEM-*, for the same reason as the aggregation addendum above)

T-1's second tier. Where artifact equality (T-1a) compares what a compiler **writes**, execution equality (T-1b)
compares what the compiled query **returns** when a real engine runs it over a seeded table. It exists because a
string comparison cannot see a collation that is silently ignored, a null that sorts the wrong way, or a window that
one engine rejects. Its inputs are two files at a fixture's root, `dataset.json` and `expectedRows.json`, validated by
[`fixtures/schemas/dataset.schema.json`](fixtures/schemas/dataset.schema.json) and
[`fixtures/schemas/expected-rows.schema.json`](fixtures/schemas/expected-rows.schema.json). **This addendum is the only
place the comparison rule is stated**; the fixture README, the conformance-runner spec and the schemas point here.

**XEQ-1. What a fixture carries.** A fixture carries `dataset.json` and `expectedRows.json` together or neither. The
seed belongs to the fixture: there are no cross-fixture seed references in v1, so one case can be read, changed and
re-derived without looking at another. The engine loads the seed into the table named by the fixture's `schema.json`
`source` (SQL-0), then runs the compiled query for that backend with the request's own `startRow`/`endRow`. The tier
applies to every backend the fixture has an `expected/<backend>.artifact.json` for and the harness can reach, and every
such backend is held to the **same** `expectedRows.json` unless XEQ-4 says otherwise. A fixture whose query returns no
rows (a rejection) carries neither file. A writer-tier fixture's compiled query does return rows, so it may carry the
pair beside its `rowStream.json`, which is a different file: a row stream is what an adapter yields *after* the query, a
seed is what is stored *before* it.

**XEQ-2. Value encodings.** Seed rows and expected rows are keyed or aligned by **logical** colId, never by a physical
name, and encode each cell by the field's declared GridSchema type:

| Type | JSON form |
|---|---|
| `int64` | a JSON integer; a fixture stays within ±2^53 so every language reads it back exactly |
| `double` | a JSON number |
| `decimal` | a JSON **string** carrying the exact digits (`"12.50"`), the same reason a Mongo artifact spells one `{"$numberDecimal": …}` |
| `boolean` | `true` / `false` |
| `string` | a JSON string, stored and compared exactly as written (no trimming, no case change) |
| `date` | `"YYYY-MM-DD"`, a local date with no zone (SEM-4) |
| `datetime` | `"YYYY-MM-DDTHH:MM:SS[.fff]Z"`, an absolute UTC instant (SEM-4), **at most millisecond precision**: MongoDB's `Date` and Search's `date` keep no more, so a finer seed would be truncated differently per engine and could move across a range bound. A SQLite seed is written with all three fractional digits, `...:00.000Z` for a whole second (SEM-4's host obligation) |
| absent value | an explicit JSON `null`; **never** an omitted key |

Every field the fixture's `schema.json` declares appears in every seed row, so a reader can tell a null from an
oversight. A seed row may carry a `why`; an authored fixture always does. Two further rules keep the oracle well-formed:

- the seed's **stableKey column is unique and non-null** in every row: SEM-6's tiebreaker makes a result order total only
  over such a key, and XEQ-3 depends on that;
- a fixture that has an `oracle` artifact **avoids `''` in any seeded column**, or declares an XEQ-4 `rows` divergence
  for `oracle`: Oracle stores the empty string as NULL (SQL-7), so a seeded `''` comes back as null there and, in a sorted
  column, moves from first among the strings to NULLS LAST.

**XEQ-3. The comparison rule.** The result's column list is compared **exactly**, then the rows **in order**, then each
cell by its type. The column list is the **logical** one, whatever an engine physically returns: an ordinary row query's
columns are the schema's fields in declaration order (GRP-3's leaf rule), a grouped level's are GRP-3's group column then
each aggregation's `valueCols` entry `id` (not its compiled key), and a BM-3 values query's is the one schema field named by `setValuesRequest.colId`, and an export's is its own list. A harness maps each
engine's rows onto it before comparing (physical to logical, dropping `_id`, hit metadata and any column the compiled
query never projected), so a harness that keeps MongoDB's `_id` and one that drops it cannot both conform.

- order is part of the contract: with a unique, non-null stableKey (XEQ-2), SEM-6's tiebreaker makes the result order
  total, so two correct engines cannot legitimately differ in row order. The one accepted difference is AGG-5's composite
  null bucket on Search, which a fixture declares under XEQ-4;
- `int64`, `boolean`, `date` and `string` are compared exactly (strings by code point, with no collation, no case
  folding and no normalization: the point of the tier is to see the engine's own);
- `decimal` is compared **as a number**, so `"1.50"` equals `"1.5"` (an engine's scale is not semantics);
- `double` is compared with a relative tolerance of 1e-9, `|a − b| ≤ 1e-9 · max(|a|, |b|)`, and exactly when either side is 0;
  the one exception is an **`avg` aggregate column**, compared as a double with a relative tolerance of **1e-6**
  (same formula, same exactness against 0), because an engine's average carries its own scale and rounding
  (SQL Server returns `decimal(38,6)`, so its average of `10.00`, `10.00`, `10.01` is `10.003333` where an engine
  keeping more digits returns `10.0033333…`);
- `datetime` is compared as an **instant**, so `…:00Z` equals `…:00.000Z`;
- `null` equals only `null`: an empty string is not a null (it is a value on every engine except Oracle, where XEQ-2's
  seed rule applies) and a missing cell is a failure.

**Aggregate columns are typed by the aggregation, not by the field.** On a grouped level (`rowGroupCols` outnumber
`groupKeys`) a column named by a `valueCols` entry is an aggregate, and takes its type from the function: `count` is
`int64`; `sum`, `min` and `max` take the aggregated field's type; `avg` is **always compared as a double** under the
tolerance above, whatever the field's type, because engines differ in the scale of an average (Postgres `AVG(numeric)`
keeps about sixteen fractional digits, SQL Server `decimal(38,6)`, Search returns a double), and under the
**1e-6** tolerance above, not the 1e-9 of a plain double field. A grouped level's aggregate column in
`expectedRows.json` is **named by the `valueCols` entry's `id`**; a compiled alias such as `<field>_<func>`
(AGG-2) is physical, and a harness maps it onto that `id` before comparing. A decimal `sum`, `min` or
`max` keeps the exact-decimal rule against another decimal; a Search double metric is compared against a decimal under
the double tolerance. The `id` may equal the aggregated field's own name (`amount` summed with `id` `amount`); the compiled
alias (`amount_sum`) still differs and is what the harness maps onto the `id`. A drill-down leaf (`rowGroupCols` equal to `groupKeys`) sends `valueCols` too but projects plain fields, so
none of this applies to it. An **export** (a request carrying `exportFormat`, EXP-1) discards group state
(EXP-1(a)), so it is never a grouped level: its `valueCols` entries are not aggregates and its columns are plain
fields or the export's own list (`page-export/010`, `011`, `024`). A column that is neither a schema field nor a `valueCols` `id` of a grouped level is a mistake in the
fixture, not an unchecked cell.

**XEQ-4. Accepted divergence.** When a real cross-engine difference is known and accepted, the fixture says so in
`expectedRows.json`'s `allowedDivergence` array rather than silently passing or silently failing. One entry per backend:
the backend (the `expected/<backend>` stem), an optional `engine` (`opensearch` or `elasticsearch`, valid only with
backend `search`, because that one artifact (OQ-7) runs on both engines and one can differ alone; an entry without it
covers both, and the two forms are not mixed), a mandatory `reason` naming the rule or engine fact behind it, and an
`outcome`: **`rows`** (the backend returns a different result, given in the entry's own `expected`) or **`error`** (the
backend refuses the query; the harness asserts that it does). A backend with an entry is held to that entry and only
that entry; a backend without one must match the fixture's main result. An `error` entry is asserted on purpose: a fix
that makes the error disappear is a change someone should notice and delete the entry for, not a pass nobody sees.

## Addendum — cross-backend parity property (PAR-1..PAR-4; not numbered SEM-*, for the same reason as the XEQ addendum above)

T-3 (TRD §11) asks that one request, run over one seeded dataset on more than one backend, return the same rows. XEQ
grades that for requests an author wrote by hand; this addendum states it as a **property** over generated requests, so
a combination nobody thought to write down is still checked. It adds no query semantics: every rule it relies on is
stated where it is cited, and **this addendum is the only place the property and its register are stated**; the test
code and the fixture README point here.

**PAR-1. The property.** For a seeded dataset (XEQ-2's encodings: unique non-null stableKey, no `''`, datetimes at
millisecond precision) and a request that is an **ordinary row request** (no `rowGroupCols`, `valueCols`,
`setValuesRequest` or `exportFormat`), every backend that can run the request returns the **same sequence of stableKey
values, in order, window included**: the rows `startRow` up to `endRow` of the ordered result, not merely the same set.
Order is total over such a key (SEM-6's tiebreaker, SEM-3's null placement), so two correct engines cannot differ in it
(XEQ-3). **All engine pairs are compared**, not one reference engine against the rest: each engine runs the case once and
every pair of its id sequences must be equal, so a failure names the two engines that disagree. **The engines are the
eight of T-2** (TRD §11): PostgreSQL, SQL Server, MySQL, Oracle, SQLite, MongoDB, OpenSearch and Elasticsearch, so 28 pairs
(Oracle joined with #2880 once OQ-6 was closed; the first runs, below, were on the other seven and 21 pairs). A backend that refuses
a request the generator produced (an error, or a compile rejection) fails the property, because the generator only
produces requests inside SEC-3's limits and the profile of PAR-3. The property is stated at the **IR level**: the case
is an AG Grid wire request, parsed and validated by the real adapter and filter pipeline into the IR every compiler
receives, with SEC-3's default limits and nothing stubbed. A generated case is a pure function of `(seed, index)`, so
a failure is replayed by those two values alone.

**PAR-2. What the property does not cover.** It compares id sequences, so it covers only requests that have one.
Grouped levels (GRP-1, including AGG-5's null bucket on Search and GRP-2's accepted divergences #3 and #4), drill-down
leaves, BM-3 distinct-values queries and exports (EXP-1) have no stableKey sequence comparable across engines, or have
a documented different one. They stay with their fixtures under XEQ-1..XEQ-4 (for example `group-aggregation/001`,
`group-aggregation/017`, `page-export/010`). Column values other than the key are XEQ-3's concern, not PAR-1's.

**PAR-3. The divergence register.** The generator **excludes** each construct below because a cross-engine difference
is recorded for it, or because the rule it depends on is pinned by a fixture that the property would only restate. A
construct is on the register only with the rule that explains it and the one fixture that covers it; a construct with
neither is not excluded and the generator must produce it.

| Excluded construct | Rule | Covering fixture |
|---|---|---|
| A string field in a sort key (`sortModel` on a text column); the string field itself stays filterable | SEM-1: a string sorts under the field's one collation, and the order of case variants and of non-letter characters is each engine's own (XEQ-3 compares by code point, not by collation) | `sort-paging/001-single-key-string-asc-nulls-last-default` |
| A `caseSensitivity: "sensitive"` string field, therefore also a request mixing case-sensitive and case-insensitive comparisons | SEM-1 and MDB-9's accepted divergence #5 (it sits beside GRP-2's #3 and #4): MongoDB has one query-level collation | `dialect-parity/023-sem1-mixed-case-sensitivity-one-request` |
| An empty string `''` as a seeded value or a filter bound | SQL-7 and XEQ-2: Oracle stores `''` as NULL | `dialect-parity/019-sem2-blank-notblank-exact-negation` |
| `searchMode: "analyzed"` on a text field | SEM-7: tokenized matching is an explicit opt-in whose result differs from substring semantics by design | `dialect-parity/013-sem7-searchmode-analyzed-optin` |
| Pattern metacharacters in a `contains`, `startsWith` or `endsWith` operand (the operands are plain letters and digits) | SEM-7, MDB-11 and SEC-4: the escape alphabet differs per engine and is graded as artifact text | `dialect-parity/020-sem7-mongo-regex-full-metacharacter-escaping` |
| A `datetime` seed or bound finer than a millisecond, or a SQLite seed written without three fractional digits | SEM-4's SQLite fixed-width host obligation and its bound-rounding rule; XEQ-2's millisecond cap | `dialect-parity/025-sqlite-datetime-fixed-width` |
| A `groupable` string field | GRP-2's accepted divergence #4 (MySQL's binary column for exact buckets makes comparisons case-sensitive) and #3 | `group-aggregation/017-set-filter-values-excludes-own-field-filter` |
| The ordering operators (`gt`, `gte`, `lt`, `lte`) and `inRange` on a string field; `eq`, `neq`, the substring family, `in`, `notIn` and the blank tests on it stay | OSE-6 (its `range` / `sort` row: a case-insensitive `string` is ordered on `search.normalizedSubField`, and a schema without one is a compiler error, so the Search engines refuse) and SEM-1 (case folding: `range` has no `case_insensitive` parameter, so the fold is an index-time obligation the parity schema does not pay) | `dialect-parity/015-sem1-case-insensitive-ordering-gt` pins the ordering semantics on a schema that declares the normalizer; **no fixture pins the refusal itself**, which is pinned by the Search compiler unit test `Craticula.Search.Tests` `SearchQueryOperatorTests.A_Case_Insensitive_String_Range_On_A_Field_With_No_Normalizer_Sub_Field_Is_Refused` |

A set-membership operator (`in`, `notIn`) is **not** on the register: the generator produces it on all seven field types
(string, int64, double, decimal, boolean, date and datetime). The last row is the one row whose covering fixture does not pin the
exclusion's cause (the refusal); it is kept because ordering strings is meaningful only where the schema pays SEM-1's
index-time cost, and the fixture shows the result on such a schema.

The first row is a generator rule rather than an XEQ-4 entry: no fixture declares an `allowedDivergence` for string
order, because `sort-paging/001` agrees on every engine for the letters it seeds. The fixture is named as the evidence
of what is pinned, and PAR-4 applies the moment a broader string sort is shown to differ. As of the first runs (2026-10-10: the default seed and several other seeds, seven engines, all 21 pairs), the property
found one true gap: set membership on decimal, date and datetime fields was refused by PostgreSQL. That was a **defect**
(Bug #2304), not a divergence; it was fixed (SQL-4's array cast; the Dapper adapter also binds Postgres parameters unnamed, which set membership through it needed); scalar comparisons on those types were the same defect (Bug #2320), fixed by SQL-8's placeholder cast; and the
generator produces those operators again. **No accepted divergence has been recorded by the property**; the register lists
only generator exclusions.

**PAR-4. A found divergence becomes a fixture.** When the property finds a difference between engines, the outcome is
one of: a defect fixed (a compiler or a spec correction), or a divergence the Tech Lead accepts. An accepted divergence
is **promoted to a fixture** whose `expectedRows.json` carries an `allowedDivergence` entry (XEQ-4) with its mandatory
`reason`, and a row is added to the register in PAR-3 naming that fixture. A divergence is never excused by a generator
rule alone: excluding a construct from the generator without a register row and a covering fixture is not allowed.
A true defect the property finds is not an accepted divergence and the generator alone does not excuse it: it is tracked by a
Bug and fixed in the compiler or the spec, and any exclusion made while it is open is removed when the Bug is fixed.

## Addendum — query time limit (TL-1..TL-5; not numbered SEM-*, for the same reason as the aggregation addendum above)

A host can ask the MongoDB and Search compilers to carry a server-side time limit in the artifact, so that the engine, not the
application, cuts a query that runs too long. The setting is the host's: `ResourceLimits.MaxQueryTimeMs` in C#, a
nullable whole number of milliseconds. It is the one SEC-3 limit that is **unset by default**: SEC-3's other limits bound the
shape of a request, and the library cannot know how slow a host's database is, so a default would be a guess. (This is a
recorded deviation from SEC-3's "no limit is unlimited".)

**TL-1. MongoDB: the member `maxTimeMS`.** When a limit N is configured, a row or set-values artifact carries the
top-level member `maxTimeMS` with the value N. `maxTimeMS` is an `aggregate()` command option, like `collation`, so it
cannot be a pipeline stage: the artifact takes the `{ "pipeline": [...] }` wrapper form (`schemas/mongo-artifact.schema.json`), with the members in the order
`pipeline`, `collation` (when present), `maxTimeMS`. Without a limit, the artifact is the bare array, or the wrapper with
`collation` alone, exactly as before.

**TL-2. Search: the member `timeout`.** When a limit N is configured, the body carries the top-level member `timeout` with the string
`"<N>ms"`. Without a limit the member is absent.

**TL-3. Absent means unchanged, and unpaginated requests are excluded.** Without a configured limit every artifact is exactly what it was.
An artifact for an unpaginated request, an export of everything or an explicit all-rows request (PG-4), never carries the limit: it is long by design and an export has its own cancellation hook (EXP-7). The SQL
engines carry no limit in compiled text (their limit is a connection or statement setting).

**TL-4. The value is validated when the limits are configured.** Zero, a negative number, a number that is not whole, or a value above
2,147,483,647 is rejected before any request is compiled. The limit comes only from the host: no member of a request sets,
raises or removes it. A `maxQueryTimeMs` on the wire is ignored, like `requestContext.now` (SEM-4). Inside a conformance fixture,
`requestContext.maxQueryTimeMs` is an instruction **to the harness** (`conformance-runner.md` §3), never a field a production parser reads.
The limit applies to each engine call an artifact makes (a page and its row count each get the full limit), not to a request as a whole.

**TL-5. A time-out is one distinct error.** An execution adapter reports an engine time-out as `QueryTimeoutException`
(error kind `query-timeout`), which names no query text. MongoDB: the server's "maximum time expired" error (code 50). Search: a response whose `timed_out`
is true, which an adapter never returns as a page of partial hits. The Search `timeout` is a soft limit: the shards stop at their next
check, not at once.

## Addendum — default page size (PG-1..PG-5; not numbered SEM-*, for the same reason as the aggregation addendum above)

Before this addendum a row request with neither `startRow` nor `endRow` meant "every matching row" (the unpaginated page
of EXP-2), so a client that forgot its window asked for the whole table. That is no longer the default: getting every row
is something the request and the host both have to ask for on purpose.

**PG-1. No window, not an export: a default page.** A row request whose `startRow` and `endRow` are both absent or null, and
that is not an export of everything, resolves to the range page `[0, DefaultPageSize)`. `DefaultPageSize` is a host setting
(a whole number of at least 1; **default 100**, AG Grid's own block size). It is checked like any other window against SEC-3's
maximum page size, so a default above the maximum is refused, not silently clamped. A half-supplied window (one of the two
present) stays a malformed request.

**PG-2. An export of everything stays unpaginated.** `exportScope: "all"` (EXP-1) still resolves to the unpaginated page,
whatever `startRow` and `endRow` say (EXP-2). An export is the explicit way to ask for every row, and the execution adapters
stream it page by page (EXP-3), so memory holds one chunk at a time.

**PG-3. The explicit all-rows request: `ignorePageLimit`.** A non-export request with no window that carries the top-level
boolean `ignorePageLimit: true` resolves to the unpaginated page, **only when the host has allowed it**
(`AgGridParseOptions.AllowUnboundedRows`, default off). When the host has not allowed it, a request carrying
`ignorePageLimit: true` is refused with the parse error `unbounded-not-allowed`; it is never silently capped, because the
client asked for something else. When the request has a window, the window wins and the flag changes nothing. The member must be a
boolean or null; anything else is a malformed request. Inside a conformance fixture, `requestContext.allowUnboundedRows` and
`requestContext.defaultPageSize` are instructions **to the harness** (`conformance-runner.md` §3), like `now`.

**PG-4. The unpaginated page is now always deliberate.** The unpaginated page (`NonePage`) comes only from an export of
everything (PG-2) or an allowed `ignorePageLimit` (PG-3). A host that calls a compiler directly with the unpaginated page has
chosen it. TL-3's exclusion of the query time limit therefore reads: **an export or an explicit all-rows request carries no
limit; every other row request, including one that got a default page, carries it.**

**PG-5. Streaming.** A request for every row is meant for the streaming entry points of the execution adapters (EXP-3), which
read in chunks and never hold the whole result. The paged entry points keep their behavior.
