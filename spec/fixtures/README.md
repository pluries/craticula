# `spec/fixtures/` — the conformance fixture suite

Per **T-1** (the maintainers' private TRD, §11): this is the shared,
language-agnostic contract every backend compiler, in every language port, is graded against. If a
fixture and an implementation disagree, the implementation has a bug — see `spec/semantics.md`'s
own framing of the same principle for the rules these fixtures enforce.

**How an implementation is graded** — the driver protocol, what a driver pins, the per-backend equality rules and what
the runner reports — is defined once, in [`../conformance-runner.md`](../conformance-runner.md). This file describes
the fixtures; that one describes how they are run.

## Fixture shape

```
<category>/<NNN-slug>/
  description.md          — what this case proves, which requirement id(s) it backs
  agGridRequest.json       — the raw AG Grid SSRM wire request (IServerSideGetRowsRequest shape)
  schema.json               — the GridSchema config this request compiles against (see ../grid-schema.schema.json):
                              the field allowlist + per-field physical mappings, the SEM-6 stableKey,
                              and `source` — the table/collection/index the query reads from, which
                              lives here because no AG Grid request carries one (added in #1638)
  expected/
    postgres.artifact.json   — present only for the backends this case targets (see policy below)
    mssql.artifact.json
    mysql.artifact.json
    oracle.artifact.json     — community-tested tier (see below); added by #1642
    sqlite.artifact.json
    mongo.artifact.json
    search.artifact.json     — shared OpenSearch/Elasticsearch artifact (OQ-7: one compiler, one DSL subset)
    export.csv? / export.tsv? — optional, CSV/TSV writer tier (EXP-4/EXP-8) — see below
  rowStream.json?           — optional, CSV/TSV writer tier: the rows an adapter yields (added #1651)
  writerConfig.json?        — optional, CSV/TSV writer tier: the HOST's delimiter/BOM/header/decimal
                              separator (EXP-5's PER-FIELD overrides live in schema.json instead)
  dataset.json?             — optional, execution-equality tier (T-1b): the seed — see "Execution equality" below
  expectedRows.json?        — optional, execution-equality tier (T-1b): the expected result — see "Execution equality" below
```

**The writer tier (EXP-4/EXP-8), added by #1651.** A CSV/TSV export has three inputs, only one of
which is a request: the resolved column list (EXP-1(b), from the request + schema), the row stream an
execution adapter yields, and the host's writer configuration. A case carrying `rowStream.json` is
compared **byte for byte** — BOM, CRLF and UTF-8 encoding are the substance of EXP-4, and all three
survive a string comparison — against `expected/export.csv`/`.tsv`, whose extension is the request's
own `exportFormat`. `writerConfig.json` is present **only** when the case overrides a writer default,
so a case proving a default is graded against bytes the defaults produced. `rowStream.json` and
`writerConfig.json` validate against `schemas/row-stream.schema.json` and
`schemas/writer-config.schema.json`. Twelve cases carry the tier, all in `page-export/`: `012`-`015`
and `025` (#1651, EXP-4/EXP-5), `016`-`020` and `022` (#1652, EXP-6's formula-injection prefixing), and
`026` (#1653, EXP-5's per-field date pattern and decimal separator).
That is every writer-facing case in that category except `021`, whose subject — EXP-7's row limit —
produces no output to compare; the category README says so and says why.
Note that a **fourth** input reaches the writer and is not a file of its own: EXP-5 puts per-field
format overrides in *schema config*, so `026`'s two overrides live in its `schema.json` and reach the
writer through the request adapter, exactly as a `label` does. `writerConfig.json` carries only what
EXP-4 makes host configuration. **These files are deliberately
not `dataset.json`/`expectedRows.json`** — see the "Execution equality" section below for what those two names are
for, and the category README for why a row stream is not a database seed.

Every `expected/<backend>.artifact.json` validates against its shape schema in `schemas/`
(`sql-artifact.schema.json` for every SQL dialect, `mongo-artifact.schema.json`,
`search-artifact.schema.json`). Every `schema.json` validates against `../grid-schema.schema.json`
— itself a spec-level assumption authored here ahead of the actual `GridSchema` model (#1631), which
must conform to this shape rather than the reverse.

**Adversarial fixtures are a distinct shape.** SEC-6 requires injection/unknown-field/type-confusion/
depth-bomb cases to produce a "clean rejection" — no backend ever sees a compilable IR, because
validation rejects the request before compilation reaches a compiler. These cases have
`expected/rejection.json` (validating against `schemas/rejection.schema.json`) **instead of** any
`expected/<backend>.artifact.json`.

## Backend coverage policy

Not every fixture carries every backend's artifact — that would multiply ~150 cases into ~1000+
files with no proportional gain in what's actually being proven:

- **General/structural/semantic fixtures** (most of the suite): Postgres (the SQL reference
  dialect) + MongoDB + one shared Search artifact.
- **Dialect-specific fixtures**: exactly the one dialect whose mechanics the case exists to pin
  (MySQL's `ISNULL` null-ordering emulation, SQL Server's `OFFSET/FETCH` paging, SQLite as the
  cheap in-proc CI target).
- **Cross-backend parity showcase fixtures**: all five SQL dialects + Mongo + Search, reserved for
  the handful of cases whose entire point is proving identical semantics across every backend
  (SEM-1 case sensitivity, SEM-2 null handling) — these back T-3's property-test intent directly.

### Dialect support tiers

Not every dialect this suite grades is supported to the same level, and the fixture tree does not
distinguish them — a passing artifact means the same thing for all five. The difference is what runs
outside T-1a:

| Tier | Dialects | What that means |
|---|---|---|
| **v1 supported** (§5) | Postgres, SQL Server, MySQL/MariaDB, SQLite | Graded by T-1a; on the release path; execution-equality (T-1b, Feature #1624) will cover them. |
| **Community-tested** | **Oracle** (added #1642) | Graded by T-1a exactly like the four above — 45 arms across `dialect-parity/` (20) and all of `group-aggregation/` (25) — and, since #2880, run against a real **Oracle Database Free 23ai** container in the execution tier (T-1b, all 45 arms) and in the parity property (T-3). That tier is the Docker one: it is not part of the pull-request gate, the release workflow does run it (a failing Oracle test stops a release), and **12.2 to 21c were not run** (OQ-6 is closed on that footing). Its host obligations (12.2+, quoted DDL, binary grouping columns) are recorded in `dialect-parity/README.md` and in the index guidance. |

An Oracle artifact disagreeing with a compiler is still a bug in one of the two, on the same terms as
any other arm; the tier is about *coverage beyond the artifact*, not about how seriously the artifact
is taken. Do not quietly promote it — nothing here has been executed.

## Execution equality: `dataset.json` / `expectedRows.json` (T-1b)

The second assertion tier. T-1a compares the artifact a compiler writes; T-1b runs the compiled query on a real engine
over a seeded table and compares the rows it returns. **The rules are normative in `spec/semantics.md`'s
"Addendum — execution equality" (XEQ-1..XEQ-4)**, not here: what a fixture carries, the value encodings, the
comparison rule and how an accepted divergence is declared. In short:

- `dataset.json` is the seed (`{"rows": [{"row": {<logical colId>: value}, "why": "…"}]}`); `expectedRows.json` is
  the ordered result (`{"columns": […], "rows": [[…]]}`, optionally with `allowedDivergence`). Both validate against
  `schemas/dataset.schema.json` and `schemas/expected-rows.schema.json`.
- A fixture carries both or neither. The seed belongs to the fixture; nothing is shared across fixtures.
- The expected rows are **hand-derived from the semantics, never copied from an engine run**. An oracle taken from the
  implementation it grades only proves the implementation agrees with itself, which is the failure this tier exists to
  catch. Each category README says which fixtures are in scope and why the others are not.
- A `rowStream.json` is *not* a small `dataset.json`: a seed is what a database holds before the query runs, a row
  stream is what an adapter yields **after** filtering, sorting, projection and physical-to-logical aliasing. The two
  sit in the same directory without either meaning the other.

**Worked example: `operators/001-eq-string`.** Its seed holds seven rows chosen to sit on each side of every boundary
(`"active"`, `"ACTIVE"`, `"Approved"`, `"pending"`, a null, `""`, `"activex"`), and its expected result is the three rows
that match case-insensitively, in `id` order: `[[1,"active"],[2,"ACTIVE"],[3,"Approved"]]`. Without the collation only
id 1 would match; as a `startsWith`, id 7 would join. 228 fixtures carry the pair today, in every category that can
be executed; the rule lives in `semantics.md` XEQ-1..XEQ-4.

## SQL artifact rendering — one canonical form, pinned in `spec/semantics.md`

Every `expected/*.artifact.json` for a SQL dialect is byte-compared under T-1a, so "correct SQL" is
not enough — there is exactly one accepted spelling per construct, and it is normative in
`spec/semantics.md`'s **"Addendum — canonical SQL rendering"** (SQL-0..SQL-8), not here. In short:
identifiers are **always quoted**, including the table and every alias (`SELECT "region" AS "region"
FROM "sales_fact"`); a composite `and`/`or` wraps itself and renders its children bare; a SEM-2
null-inclusive negative is always wrapped; `notContains` renders `NOT ILIKE`, not `NOT (... ILIKE
...)`; `notBlank` is literally `NOT (<blank>)` applied to whatever text that engine's `blank` produced
(**SQL-7**); and Postgres set membership is `= ANY($1)` /
`<> ALL($1)` against **one array parameter** (cast to the column type, `$1::numeric[]`, for `decimal`, `date` and `datetime` fields), and a Postgres scalar comparison on those three types casts its placeholder too (**SQL-8**: `"amount" >= $1::numeric`). Three rules there are per dialect rather than universal
and are the ones a port is most likely to get silently wrong: **SQL-5** (the substring family's
operator, `ESCAPE` clause and escape alphabet all vary — MySQL spells `ESCAPE '\\'`, SQLite's
case-sensitive path is `GLOB` with no `ESCAPE` clause at all, SQL Server escapes `[` as well),
**SQL-6** (an engine whose default collation folds case must spell the case-**sensitive** mechanism
explicitly, not leave it bare) and **SQL-7** (an engine whose empty string *is* NULL — Oracle —
compiles `blank` on a text field to a bare `IS NULL`; emitting the `= ''` disjunct there makes
`notBlank` return no rows at all). Read that addendum before authoring or reviewing any SQL artifact.

**The one cross-dialect divergence once known here is settled**: a zero-width page window
(`{"startRow": 100, "endRow": 100}`) returned an empty page on Postgres/MySQL/SQLite and a server error
on SQL Server (T-SQL msg 10744). The wire request is now rejected at the parser (`semantics.md` SEM-6,
"The page window is non-empty"), so no backend sees it; pinned by `adversarial/027-zero-width-page-window`.

This was not always so. Fixtures authored in #1630 disagreed with each other on all six of those
points (the suite was written by seven parallel agents with no compiler to check it). #1638 picked
one form per construct and re-authored the minorities — 144 Postgres artifacts gained quoting, and 9
had a rendering rewritten (`dialect-parity/008`, `/017`, `/018`, `/019`; `filter-tree/006`;
`operators/001`, `/004`, `/007`; `page-export/005`) — so the previously-recorded "cross-category
quoting contradiction" (`ag-grid-majors/README.md`) is **resolved for Postgres**.

Both arms of it have since closed — one in #1639, the other in #1640 and #1641 — and both are
recorded where the affected artifacts live rather than only here. **The register is therefore empty:
`grep -rn "Known open contradiction" spec/` finding nothing is the convention working, not a record
that went missing.** An artifact that disagrees with a compiler is a bug in one of the two, never an
expected divergence, with no exception: the zero-width page window that was once one is rejected at the
parser (SEM-6, `adversarial/027`).

- **CLOSED (#1639): the `mysql`/`mssql`/`sqlite` artifacts in `dialect-parity/` are now quoted too.**
  The *rule* was always universal; only the quote character (`"` vs `[…]` vs backticks) was each
  engine's own, and it is chosen when that engine's `Dialect` is written. #1639 wrote all three and
  re-authored the 19 pre-existing arms accordingly, then added 30 more (`011`-`020` promoted to full
  parity coverage) — plus a new `021` for the case-sensitive substring case its own coverage audit
  found missing and a new `022` for T-SQL's `[` wildcard, found by its code review: 55 non-Postgres
  arms in total, every one quoted, and each engine's escape for a quote character *inside* an
  identifier pinned with it (`]`→`]]`, `` ` ``→```` `` ````, `"`→`""`). See
  `dialect-parity/README.md`, which also records that story's five decisions (MySQL's `ESCAPE '\\'`,
  the per-dialect arm coverage policy, SQLite's `GLOB` for a case-sensitive substring match, SQL
  Server's explicit case-**sensitive** collation, and its `[` escaping) — now normative in
  `spec/semantics.md` as **SQL-5**/**SQL-6** — along with the host DDL obligations and the one known
  divergence then deferred to T-1b (the zero-width page window, since settled at the parser, SEM-6).
- **CLOSED by #1642: the `blank`/`notBlank` composition was scoped to four dialects and Oracle
  falsified it.** `ISqlDialect` had recorded, since #1638, that `IS NULL`/`= ''` were pushed down to
  the query builder because "every v1 dialect spells them identically" — true of four engines and
  false of the fifth, where the empty string *is* NULL. It was not a redundant disjunct: `"c" = ''`
  is `"c" = NULL`, hence UNKNOWN for every row, so `notBlank` (which negates the whole composition)
  returned the **empty result set** on Oracle. Now normative as **SQL-7**; the composition stays
  builder-owned and only a `bool EmptyStringIsNull` engine fact varies inside it (the seam's third
  widening — see `dialect-parity/README.md`'s **D6**). `dialect-parity/019`'s oracle arm pins it and
  is the only artifact in the suite whose structure differs from its Postgres arm rather than only
  its tokens.
- **CLOSED by #1640 (BM-2) for the 16 grouped cases, and by #1641 (BM-3) for `016`-`019`.**
  Both splits turned on BM-2 design calls, and both are now normative in `spec/semantics.md`'s
  **grouping addendum (GRP-1..GRP-6)** rather than in a fixture README: a grouping request is
  **exact** on the protocol's own keys, so its `GROUP BY`, drill-down `WHERE` and a **grouped
  level's** `ORDER BY` render with no case-folding mechanism (GRP-2 — which is why those `ORDER BY`
  keys carry no `COLLATE craticula_ci` and the drill-down predicates lost theirs), and the drill-down
  **is** real IR, so SQL-2's wrap applies to it and `003`/`004`/`005` now read
  `("region" = $1 AND "segment" = $2)` (GRP-5). `ag-grid-majors/004`'s artifacts were already correct
  under GRP-2; its stated rationale was not, and #1640's review corrected it. The same story authored
  the missing `mssql`/`mysql`/`sqlite` arms for `group-aggregation/001`-`015` and `020`, so BM-2's
  "identical grouping protocol across all four dialects" is checkable rather than asserted.

  *Two corrections from #1640's own review, both recorded in `group-aggregation/README.md`.* GRP-2
  was **narrowed**: a fully-consumed drill-down **leaf**'s `ORDER BY` is not one of the protocol's
  keys (it has no `GROUP BY` and no buckets), so SEM-1 governs it and `005`'s user-chosen `product`
  key collates again on the dialects that spell it. (`005` and `006` were re-authored together, but
  only `005` ends up collating anything: `006` carries no `sortModel`, and the same review's second
  round settled the appended tiebreaker as exact on every backend.) And the original register's entry (a) claimed all 20 of this category's
  artifacts; only 16 were settled, leaving `016`-`019` open for #1641.

  *#1641 closed those four, as **GRP-6**.* A distinct-values query **is** a bucket query: its
  `SELECT DISTINCT` column and that column's `ORDER BY` are exact, on GRP-2's own argument — the
  entries are handed straight back to the grid as `in` values or a `groupKey`, which a grouped query
  matches exactly, so a folded entry would match neither original row. The four artifacts already
  rendered that way and none was re-authored for it. GRP-6 also pins the three things around it that
  no artifact stated: the own-field exclusion (BM-3's defining semantic), the search prefix as an
  ordinary `startsWith` predicate governed by SEM-1/SEM-7, and the cap as
  `min(requested ?? default, maximum)` — clamped rather than rejected, and rendered as a row limit
  with no offset, which is the one place BM-3 had to widen the dialect seam. The same story authored
  those four cases' missing `mssql`/`mysql`/`sqlite` arms, so the whole category is now
  six-backend. Its review pass then added `group-aggregation/022`, because one of those three — the
  `WHERE` order when a filter model and a `searchPrefix` are both present — was `params`-visible and
  pinned by **no** artifact: `017` had filters and no prefix, `018` a prefix and no filters, so a port
  could emit the two conjuncts in either order and pass everything. `022` carries both.

## Mongo artifact rendering — pinned by compiling it (#1643)

Until #1643 nothing compiled a pipeline: the 157 `mongo.artifact.json` files were hand-authored
across #1630-#1642 as a secondary arm no runner had ever executed. Compiling 144 of
them found six disagreements. Five had a clear verdict from an existing rule and the losing side was
corrected — the SEM-3 `$unset` (missing from all 47 `operators/` artifacts), GRP-5's composite
drill-down (`group-aggregation/003`-`005`), SEM-2's derived-not-negated `notBlank`
(`dialect-parity/019`), AR-7's Decimal128 literal (`group-aggregation/020`) and SEM-1's collation
wrapper on two pipelines with no text comparison in them (`filter-tree/004`, `/006`). Each is
recorded in the affected category's own README.

**The forms themselves are NOT written down here.** #1643 first recorded the nine rules it had
settled in this README, which is the repo's own named recurring defect class — a rendering rule
living in a fixture README rather than in the normative document is exactly the state the SQL
addendum was written to end, and #1630's parallel hand-authoring produced it on the SQL arm for the
same reason. Its review pass moved them: `spec/semantics.md` now carries an **"Addendum — canonical
MongoDB rendering" (MDB-1..MDB-12)**, parallel in status and structure to the SQL one, and that is
where a port reads them. The rules that had no normative home before it — the explicit `$eq`, the
`$and`/`$or`/`$nor` mapping, the uncollapsed single-child composite, SEM-2's null-inclusive `$or`,
`notContains`'s `$not`, `blank`/`notBlank`'s `$in`/`$nin`, `inRange`'s single field document, SEM-3's
two grouping bucket names, and the wrapper-iff-collation shape — are MDB-1..MDB-8. MDB-9..MDB-12 were
added by the same review pass and are new rules rather than relocated ones (the `$expr` escape, the
stage-document collision checks, SEM-7's ASCII scope, and the MongoDB 4.2 floor).

**One call was genuinely close and is recorded as a ratified decision rather than a self-evident
one: the spelling of `eq` (MDB-1).** MongoDB admits both `{"status": {"$eq": "active"}}` and the
implicit `{"status": "active"}`, they are semantically identical for every value the IR can carry,
and the hand-authored suite used **both, in adjacent cases of one category** —
`operators/001-eq-string` explicit against `operators/003`/`005`/`007`/`046` implicit, all of
`filter-tree/` explicit against every `group-aggregation/` drill-down implicit. SEM-1's own Mongo
snippet shows the implicit form but the document disclaims its SEM-1..SEM-7 snippets as illustrative
rather than literal. #1643 chose the **explicit** form on three grounds: SEM-2's Mongo paragraph,
which is normative prose rather than a snippet, emits the explicit composed form for `$ne` *even
though the naive one is correct*, "to keep the compiled shape parallel to the SQL and ES forms" and
to stay valid in an `$expr` context where only `{"$eq": [...]}` exists; a uniform operator table
needs no carve-out, which is SQL-1's "always quote, no second rule" applied here; and the suite's own
canonical `eq` fixture (`operators/001`) plus its two most recently authored artifacts
(`group-aggregation/017`, `/022`, #1641) already spelled it. 21 artifacts were re-authored for it.
It is now MDB-1; re-settling it the other way means re-authoring those 21 artifacts,
`MongoPipelineBuilder.ScalarOperator`, and `CrossCompilerGroupingTests`'s drill-down reader, which
matches on the explicit form's `{`.

**One coverage gap, recorded here in #1643 and CLOSED by #1650: SC-4's Mongo path mapping.** Every
in-scope fixture's `physical.mongo.path` was the identity mapping, so the code that turns
`customerName` into `customer.name` (and `id` into `_id`) in a `$match` key, a `$sort` key,
`$group._id`, a `$cond` reference and a `$project` value was exercised by unit tests alone. The only
schemas in the suite declaring a differing path belong to `page-export/`, whose whole category was
excluded from the runner for an unrelated reason (`exportScope`) — bringing it in scope closed the
gap. `MongoConformanceFixtureTests` now asserts the *inverse*
(`Exercises_SC4_Path_Mapping_On_Fixtures_That_Really_Remap_A_Mongo_Path`), so it fails if the last
remapping fixture ever leaves the suite and the gap silently reopens.

## Search artifact rendering — pinned by compiling it (#1644)

The third and last arm, and the same story a third time: the 158 `search.artifact.json` files were
hand-authored across #1630-#1643 as a **tertiary** arm — the least-scrutinised of the three — that
nothing had ever executed. Compiling 145 of them found **five disagreeing artifacts** in **four rule
classes** — six clause-level corrections, since `dialect-parity/019` was wrong on two counts at once
— every one decided against the artifact by an existing rule and a near-unanimous set of siblings:

- a `term` on a `string` spelled with the bare shorthand instead of the long `{"value": …}` form —
  three artifacts (`operators/029`, `/030`, `dialect-parity/019`), against 64 that already spelled it
  long and GRP-2's own hand-written drill-down form. A **fourth** was found by the review pass in the
  then-excluded `page-export/004` and corrected there too (see below);
- a `term` on a `boolean` spelled long instead of short — one artifact (`filter-tree/001`), for the
  identical construct `operators/044` spells short, against 13 non-string terms that already did;
- a `notBlank` whose `must_not` took an array instead of a single clause object
  (`dialect-parity/019`), which is the spelling reserved for a tree-level `notNode` — nine
  `filter-tree/` artifacts use it that way and three `operators/` ones use the object form for a leaf;
- a bound value **lowercased by the compiler** to match a normalizer (`dialect-parity/015`), where
  the fixture's own six other arms bind it as typed and its own description said so twice.

**The forms themselves are NOT written down here** — the same discipline #1643 had to be corrected
into. `spec/semantics.md` carries an **"Addendum — canonical OpenSearch/Elasticsearch rendering"
(OSE-0..OSE-14)**, parallel in status and structure to the SQL and MongoDB ones, and that is where a
port reads them. Beyond the four rules the disagreements above settle, it pins the things that had no
normative home at all: object key order being outside the contract (OSE-0), the two `query` forms and
the `bool.filter` container (OSE-3), which of SC-4's three search names each construct addresses
(OSE-6), the `range` `format` names (OSE-8), the `composite` grouping shape with AGG-5's silence and
the orderings and row windows that are refused (OSE-11), the `terms.include` prefix and its Lucene
escape (OSE-12), the absence of any projection member (OSE-13), and the 7.10 floor that makes one
compiler serve both engines with no target flag (OSE-14).

**No genuinely contested call.** The nearest thing to one — `term`'s long-versus-short form, this
backend's analogue of MDB-1's `eq` spelling — is settled by GRP-2's own normative sentence naming
`{"term": {"<field>.keyword": {"value": "EMEA"}}}` for a drill-down, and by counts of 64-to-4 and
13-to-1 rather than MDB-1's 21-to-21.

### The review pass: two capability findings and four more artifacts (#1644 review)

Neither of the first two is a spelling:

- **`group-aggregation/020` lost its Search arm entirely.** A grouped level ordered by an aggregate
  has **no rendering on this backend**: a `composite` enumerates buckets in key order and returns
  `size` of them, and a `bucket_sort` reorders only that page, so "the top 100 regions by revenue"
  would have compiled to "the first 100 regions alphabetically, rearranged". Elasticsearch states the
  general rule — a composite aggregation is not compatible with pipeline aggregations. The arm was
  deleted and the compiler now refuses (OSE-11(c)); see that fixture's own `description.md`. It is a
  real user-visible gap on OpenSearch/Elasticsearch, owned by #1622/#1624.
- **`group-aggregation/023` was authored to close a suite-wide hole.** No fixture anywhere carried
  both a consumed `groupKeys` and a `filterModel`, so GRP-5's clause **order** was unpinned on **all
  three backends** — a reviewer's mutation reversing it passed every test. `023` pins it, plus each
  backend's composition of two conjunctions, on all seven arms.
- **`page-export/004`-`007` were corrected** although the category was still excluded from all three
  runners at the time: four wrapped an ordinary row query in OSE-3's grouping-only
  `{"bool": {"filter": […]}}` container, and `004` also carried the suite's fourth short-form string
  `term`. The exclusion was about `exportScope` (#1623), not about the rendering rules — and #1650
  lifted it, along with four more drifted Mongo arms the same reasoning predicted. See
  `page-export/README.md`.

**One coverage gap, recorded rather than closed: SC-4's Search *base*-field mapping.** Every in-scope
fixture's `physical.search.field` is the identity mapping, so the code that would turn `customerName`
into `customer_name` in a `term` key, an `exists` clause, a `sort` key, a composite source and an
aggregation metric is exercised by unit tests alone. The **sub-field** halves of the same mapping
(`keywordSubField`, `normalizedSubField`) are richly covered; it is only the base field that is always
the identity. `SearchConformanceFixtureTests` asserts the gap
(`Records_That_No_In_Scope_Fixture_Maps_A_Search_Field_Away_From_Its_ColId`), so it fails — and this
paragraph becomes deletable — the day a fixture closes it.

## `page-export/` unblocked, and the last exclusion removed (#1650)

Until #1650 the AG Grid adapter could not read EXP-1's `exportFormat`/`exportScope`/`exportColumns`,
so no export request could be fed end to end. That single gap kept **the whole `page-export/`
category** and **`sort-paging/012`** out of all three conformance runners. Both are gone: **every
fixture in this suite is now executed by something**, and all three runners have an *empty*
`ExcludedFixtures` and no excluded category that carries a compiled artifact. That property is
asserted, not just stated — each runner's `The_End_To_End_Suite_…` test now also asserts
`Assert.Empty(ExcludedFixtures)`.

The compile-time export rules are pinned in `spec/semantics.md`'s **EXP-1/EXP-2** addendum, not
here — the same discipline #1643 had to be corrected on. Executing 23 Postgres and 13 Mongo/Search
arms nothing had ever run found **five disagreements**, every one of them the fixture's:

- **`page-export/001`-`003`'s Postgres arms carried an explicit column list** although the three
  requests carry no export member at all — and their **own Mongo arms had no `$project`**, which is
  what settled it: a within-fixture disagreement means the SQL arm was the accident. GRP-3 says an
  ordinary row query renders `SELECT *`; the three now do.
- **`sort-paging/012` had the opposite defect**: an export (`exportFormat: "csv"`,
  `exportScope: "all"`) rendering `SELECT *` and no `$project`. It gained both.
- **Eight `page-export` Mongo arms wrote `_id: 0` FIRST** in their `$project`, against
  `group-aggregation/005`/`006` and this category's own `008`, which write it last. MongoDB accepts
  either, so the tie-break is that the output list's order is normative and byte-compared while the
  suppression names no output column — and that the executed arms already spelled it last.
- **`004`'s `$match` still spelled `eq` implicitly** (`{"status": "shipped"}`) — the residue of the
  21 artifacts #1643 re-authored onto MDB-1's explicit `$eq`, missed only because this category was
  excluded.
- **`006`/`007` wrote a `decimal` bound as a plain JSON number** (`{"$gte": 100}`) where
  `operators/046`/`047` pin `{"$numberDecimal": "…"}`.

One fixture was **authored**, `023`, for the standing reason that a compiler path whose only oracle
is a unit test by the implementation's own author is weak: `FieldConfig.Exportable` defaults to
`true` and **no schema in the suite had ever declared `exportable: false`**, so every arm was
exercising one branch of EXP-1(b)'s default projection. `023` declares it on `notes`, pins the
six-column projection that follows on all three backends, and filters on that same non-exportable
field to pin that `exportable` and SC-2's `filterable` are independent.

**#1650's review pass authored a second one, `024`, and reversed a decision to do it.** The story had
*refused* an export carrying a non-empty `groupKeys` (a drill-down key restricts the result, so
discarding it widens the export) — but discarding `rowGroupCols` widens it just as much and is
mandated, so the argument did not separate the three group members, and the refusal broke the obvious
host integration: an export request built by copying the grid's last `getRows` payload hard-failed
whenever a user had expanded a group node. EXP-1(a) now discards all three. That made `010`/`011` a
weak oracle for the change — both send `groupKeys: []`, so the discard was pinned by nothing — and
`024` sends a partially-consumed two-level path whose three arms are byte-identical to `010`'s. The
category's contribution is therefore **24 Postgres and 14 Mongo/Search arms**, not the 23 and 13 the
census above was taken over.

## The writer tier arrives, and one fixture was authored for it (#1651, completed by #1652)

`Craticula.Export.Csv` is the first module in this repo that is not a compiler: it consumes a row
stream and emits bytes, so nothing it does can be graded by an artifact. #1651 gave EXP-4's four
delimiter/BOM cases (`page-export/012`-`015`) a real oracle — an input row stream and a byte-exact
expected file each — rather than leaving them, as they had been, prose plus a unit test written by
the writer's own author.

**`page-export/025` was authored** for the gap that exercise exposed: `004` and `005` prove
`exportFormat` never affects **compilation** and rightly stay compilation-only, but that left the
format field's *actual* effect — which delimiter the writer uses — pinned by nothing, while `012` and
`013` covered only `,` and `;`. `025` is `012`'s request with `exportFormat: "tsv"`; its compiled arm
is byte-identical to `012`'s and its expected bytes are not. That takes the category to **25 Postgres
arms** (Mongo and Search stay at 14 — a writer case carries a single representative backend).

**#1652 converted the last six (`016`-`020`, `022`)** when it implemented EXP-6's `'`-prefixing, taking
the tier to eleven cases and **no new fixture** — the six already existed and already documented the
rule in prose, so the story's whole delivery on this side was replacing prose with bytes. One of them
was widened rather than merely converted: `018` now carries a **negative `decimal`** beside its hostile
string, the only negative number in the suite, because #1652 narrowed EXP-6 to spare the cells the
writer formatted from a numeric, date/time or boolean value (a literal reading would render `-500.25`
as `'-500.25`, i.e. as text) and nothing else here could have caught that regressing. The `662` artifacts and the three compiler runners' counts did not
move: a converted case compiles exactly as it did.

`021` is the one writer-facing case still prose, and permanently: EXP-7's row limit is an
execution-adapter concern with no writer output at all to compare.

## The reserved fixture is authored, and formatting is proved invisible to compilation (#1653)

EXP-5 has two halves. #1651 shipped the collision guard and left the other — *"per-field overrides in
schema config (date pattern, decimal separator)"* — with **no schema member to carry it**, recording in
the category README that a future story should give the legal `;`+`,` pairing a fixture. #1653 added
the member (`fields.<colId>.format` in `../grid-schema.schema.json`, `FieldConfig.Format` in
`Craticula.Core`) and authored **`page-export/026`**, which is the reserved case: `013`'s request, row
stream and `writerConfig.json` **byte for byte**, over a schema declaring `decimalSeparator: ","` on
`totalAmount` and `datePattern: "dd/MM/yyyy"` on `orderDate`.

Two properties make it worth a whole fixture rather than a unit test:

- **A format reaches no compiler.** `026`'s `postgres.artifact.json` is **byte-identical to `013`'s**
  over a real `schema.json` difference — the same claim `025` makes for `exportFormat`, now made for a
  *schema* member rather than a request one, which is the half nothing covered.
  `CsvWriterConformanceFixtureTests.The_Per_Field_Format_Fixture_Is_The_Semicolon_Fixtures_Inputs_With_Only_Its_Schema_Changed`
  asserts the whole relation, down to *which* schema members differ.
- **Per-field means per field.** The two overrides land on two different columns of every record while
  five columns beside them are untouched. One override alone cannot tell "resolved per column" from
  "resolved once and applied to whatever matched"; an implementation with that bug would still emit a
  well-formed file and would fail here.

The counts moved: `page-export` **25 → 26**, the Postgres runner **173 → 174**, artifacts on disk
**662 → 663** (Mongo 161, Search 160 and the 168 non-Postgres SQL arms unmoved — a writer case carries
one representative backend), the writer tier **11 → 12**. All four runners' `ExcludedFixtures` are
still empty.

The story also widened EXP-5's collision guard, which is the part with no fixture: a **per-field**
decimal separator equal to the delimiter is the identical defect to the writer-wide one — a well-formed
WRONG file — and would have been written out silently. It is refused before the first byte, naming the
offending field, and unit-tested; a refused export produces no bytes to compare, which is why neither
form of the collision can be a fixture.

## AGG-6 lands, and 61 SQL artifacts move with it (#1886)

`spec/semantics.md`'s **AGG-6** settles what an aggregate over a group with no non-null values is:
`sum` is `0`, `avg`/`min`/`max` are `null`. The three other backends already answer that way — the EF
provider generates `COALESCE(SUM(x), 0.0)` unprompted, and MongoDB's `$sum` and Elasticsearch's `sum`
metric both return `0` for an empty set — so **SQL was the outlier, one against three**, and the SQL
compiler is the only one that changed. AGG-6 itself records how strong the evidence for each of those
four rows is, which is not the same for all four and is not something any artifact can grade.

**61 artifacts gained a `COALESCE`**: 13 Postgres, 12 each on MSSQL/MySQL/SQLite/Oracle, across
`group-aggregation/001`-`004`, `007`, `012`-`015`, `020`, `021`, `023` and `ag-grid-majors/004`. The
`AVG`/`MIN`/`MAX` calls in ten of those same artifacts were **not** touched, which is the rule's other
half. No Mongo or Search artifact changed, and none should have.

*The transformation is textual, and applied to the fixtures' own hand-authored SQL* — never a dump of
the compiler's output, the standing rule this suite has kept since #1638. `COALESCE` is ANSI and
spelled identically by all five dialects, so no arm needed anything but the wrap, and none of the five
diverges here.

**One statement's ordering moved, and that is the rule working.**
`group-aggregation/020` orders a grouped level by its `sum`, so its `ORDER BY` now repeats
`COALESCE(SUM(…), 0)` (three times over on MySQL and SQL Server, whose null-placement emulation wraps
the expression twice more). A group with no non-null values therefore sorts **with the zeroes**, where
it previously sorted with the NULLs at AR-9's requested `nullsPosition` — an ordering change, on every
dialect at once, stated in AGG-6 rather than absorbed as a byte diff. The `nullsPosition` keys are
still emitted around the wrapped expression even though they can no longer fire: SEM-6 licenses no
omission of a null marker on a nullability inference.

**`dialect-parity/024` was authored** as the discriminator none of the 61 provides. It orders a
grouped level by an **`avg`** while a wrapped `sum` sits beside it in the same projection — the only
case in the suite whose `ORDER BY` fails both when the wrap is missing and when it is over-applied to
the `avg`, since no other fixture orders a grouped level by anything but a `sum` or a group column.
(Over-applying the wrap to a *projected* `avg`/`min`/`max` is separately caught by `group-aggregation/008`-`010`,
`012`, `013`, which carry those bare in their `SELECT` list.) It carries **five SQL
arms and no document-store arm**, a third coverage tier for that category: `$sum` and the `sum` metric
are the same token before and after AGG-6, so a Mongo or Search arm would grade nothing. The honest
limit is recorded in AGG-6 itself — those two backends' engine behaviour is *documented*, not measured
in this repository, and confirming it belongs to the T-1b execution tier (**#1624**).

**`adversarial/023` was authored** for the second rule the same story carried: two aggregations
resolving to one GRP-4 output name are refused in `Craticula.Core`'s shared `AggregationValidator`,
upstream of all four backends. MongoDB and Elasticsearch each already refused it in their own
compiler; `Craticula.Sql` did not — it emitted `SELECT SUM("x") AS "n", AVG("x") AS "n"` and let the
driver decide which one the grid read. It is the category's first `duplicate-output-name` case, and
its `reason` is the first value added to `rejection.schema.json`'s enum after that file was written.

The counts moved: `dialect-parity` **23 → 24** directories, `adversarial` **22 → 23**, the Postgres
runner **174 → 175**, the non-Postgres SQL arms **168 → 172**, artifacts on disk **663 → 668**. Mongo
(161) and Search (160) are unmoved, as is the writer tier (12). All four runners' `ExcludedFixtures`
are still empty.

**`adversarial/024`/`025` (#1872) added `field-not-filterable`** — the new rejection reason for a
colId present in `GridSchema.fields` but declared `filterable: false` (SC-2), referenced in a filter
condition or as `setValuesRequest.colId`. `adversarial` moves **23 → 25** directories; no other
runner or artifact count moves, since every case in this category compiles to `expected/rejection.json`
alone and none of the four backend runners ever iterates it.

**`adversarial/026` (#1907, found by #1872's own code review)** extends `field-not-filterable` to a
third surface: a `groupable: true, filterable: false` colId consumed as a `groupKeys` drill-down key
(`DrillDownFilter.Synthesize` turns it into a literal filter predicate, same as `filterModel` would).
`adversarial` moves **25 → 26** directories; no other runner or artifact count moves, for the same
reason as `024`/`025`.

**`adversarial/027` (#2208) pins the zero-width page window** (`startRow: 100, endRow: 100`): refused at the request
boundary, `requestParsing` / `malformed-request`, before any compilation, so no backend ever sees a `FETCH NEXT 0 ROWS`
(T-SQL error 10744). `adversarial` moves **26 → 27** directories; no runner or artifact count moves.

## Case-insensitivity mechanism policy (SEM-1)

Two distinct mechanisms, never mixed: **`eq`/`neq`/`gt`/`gte`/`lt`/`lte`/`in`/`notIn`, plus sort,
use a case-insensitive COLLATION** (Postgres: the `craticula_ci` ICU collation; SQL Server/MySQL:
their native CI collations; Oracle: `COLLATE BINARY_CI`, which is also how it reaches the substring
family, having no `ILIKE`; Mongo: query-level `collation: {locale, strength:2}`; ES/OpenSearch:
`term`+`case_insensitive` for equality, a schema-declared `search.normalizedSubField` for ordering).
**`contains`/`notContains`/`startsWith`/`endsWith` use `ILIKE`/pattern-match** (SEM-7 owns the
substring mechanics and escaping). **Bucket-identity keys are the documented third case: they use
neither** — the `GROUP BY` key, the `groupKeys` drill-down match and a **grouped level's**
`ORDER BY` are all exact, per `spec/semantics.md`'s grouping addendum (**GRP-2**), because they must
agree with one another and a collated `GROUP BY` key is not valid SQL; BM-3's `SELECT DISTINCT`
column and its `ORDER BY` join them (**GRP-6**). That scope is narrow and every edge matters: a user
filter inside the same grouped request still follows the split above, so does a fully-consumed
drill-down **leaf**'s `ORDER BY`, which orders raw rows rather than buckets, and so does a set
filter's own search prefix, which filters the distinct column rather than being its key.

**MongoDB is the one backend where "per field" and "per statement" collide** (**MDB-9**,
`dialect-parity/023`): its collation is a query-level option, so a request comparing one
case-insensitive field and one case-sensitive field cannot spell both mechanisms the way a `COLLATE`
clause does. The sensitive comparison is moved into an `$expr`, where aggregation expressions compare
binarily and the collation does not apply; a sensitive *sort* key in the same pipeline has no
equivalent escape and is a compiler error. Do not reach for `ILIKE`/`$regex` for an exact-match or
set-membership operator "because it's already case-insensitive that way" — it reintroduces an
escaping trap (a literal `%`/`_` in the value silently becomes a wildcard) that a collation doesn't
have. See `spec/semantics.md` SEM-1 for the full rationale.

**ES/OpenSearch is the opposite case, and #1644 measured it rather than assuming it.** Its mechanism
is a **per-clause** parameter — `case_insensitive` sits on the individual `term`/`wildcard` that wants
it — so the same request can spell SEM-1 on a user's filter and GRP-2's exactness on the protocol's
keys, with a drill-down `term` and a `composite` source simply not carrying the parameter. Nothing is
ever suppressed there, which is why the three fixtures MongoDB's accepted divergence #3 reaches
(`group-aggregation/005`, `/017`, `/022`) show a Search arm that agrees with the five SQL dialects
instead. `CrossCompilerGroupingTests.Only_Mongo_Suppresses_Case_Insensitivity_For_Bucket_Identity`
asserts both halves, so "the divergence disappeared" and "the divergence spread" both fail. The one
place this backend does lose the mechanism is a *bucket* filter rather than a query clause: GRP-6(c)'s
set-filter search prefix compiles to a `terms.include`, a Lucene regex with no case-insensitivity
option (OSE-12) — a second accepted divergence, in AGG-5's register.

**The case-SENSITIVE direction is a mechanism too, not the absence of one** (`spec/semantics.md`
**SQL-6**, added in #1639's review pass). Where an engine's own default collation folds case — SQL
Server's stock `SQL_Latin1_General_CP1_CI_AS`, MySQL's `_ci` server default — leaving a field
declared `caseSensitivity: "sensitive"` bare silently discards the declaration. SQL Server therefore
spells `COLLATE Latin1_General_CS_AS` (`dialect-parity/014`, `/018`, `/021`); Oracle spells
`COLLATE BINARY` in the same three, because its default collation resolves through the *session*'s
`NLS_COMP`/`NLS_SORT`; MySQL cannot express it in the statement at all and defers to a
`_bin`/`_as_cs` column collation in host DDL. Postgres and SQLite spell nothing, because their
defaults already distinguish case — four different answers that happen to share a spelling on two of
the five, which is why an artifact showing "no collation" says nothing on its own about which reason
applies.

## `agGridRequest.json` wire shape (grounded in `github/ag-grid`, the local reference clone)

Top level (`IServerSideGetRowsRequest`, `packages/ag-grid-community/src/interfaces/iServerSideDatasource.ts`):
```
{ startRow: number|null, endRow: number|null, rowGroupCols: ColumnVO[], valueCols: ColumnVO[],
  pivotCols: [], pivotMode: false, groupKeys: string[], filterModel: FilterModel|null,
  sortModel: SortModelItem[] }
```
- `ColumnVO` (`iColumnVO.ts`): `{ id, displayName, field?, aggFunc? }`.
- `SortModelItem` (`iSortModelItem.ts`): `{ colId, sort: "asc"|"desc" }` in v31-v34. **From v35 it also
  carries `type?: SortType` (`"absolute"|"default"`)** — optional in the declared type, but the emitter
  always populates it: v35's `sortService.ts` `collectSortItems` builds `{ sort, type }` with
  `_normalizeSortType()` returning `"default"` when unset, and v36's `_getSortModel` writes
  `{ sort, type, colId }`. So a real v35/v36 payload always has three keys. Nothing in the IR consumes
  it (it selects AG Grid's *client-side* comparator, not a server ordering), so an adapter reads only
  `colId`/`sort` and ignores it — see `ag-grid-majors/005` and `/006`, which pin exactly that.
  There is **no null-placement field** on the wire in any major; SEM-3's `nullsPosition` is always
  derived by the adapter.
- `filterModel` is a map keyed by `colId`. Per column, either a single condition or a **combined**
  form. Current form (`iSimpleFilter.ts`'s `ICombinedSimpleModel`): `{ filterType, operator:
  "AND"|"OR", conditions: [<condition>, <condition>] }`. **Legacy form** (pre-v29, AG-1 still
  requires parsing it): `{ filterType, operator: "AND"|"OR", condition1: <condition>, condition2:
  <condition> }` — same per-condition shape, just two named slots instead of an array.
  - Text condition (`iTextFilter.ts`): `{ filterType: "text", type: "equals"|"notEqual"|
    "contains"|"notContains"|"startsWith"|"endsWith"|"blank"|"notBlank", filter?: string,
    filterTo?: string }`.
  - Number condition (`iNumberFilter.ts`): `{ filterType: "number", type: "equals"|"notEqual"|
    "lessThan"|"lessThanOrEqual"|"greaterThan"|"greaterThanOrEqual"|"inRange"|"blank"|"notBlank",
    filter?: number, filterTo?: number }`.
  - Date condition (`iDateFilter.ts`): same `type` vocabulary as number, plus `dateFrom`/`dateTo`
    strings. **The emitted form is `"YYYY-MM-DD hh:mm:ss"`, not `"YYYY-MM-DD"`** — `createCondition`
    calls `_serialiseDate(value)` and `utils/date.ts` declares
    `_serialiseDate(date, includeTime = true, separator = '-')`, so v31-v35 always include the time
    part. The date-only form becomes possible only at v36, which threads an `includeTime` parameter
    through (`params.includeTime ?? dataTypeSvc.getDateIncludesTimeFlag(cellDataType) ?? true`), so it
    appears only for a column explicitly configured `includeTime: false` or `cellDataType: 'date'`;
    v36 can also emit `"YYYY-MM-DDThh:mm:ss"` under `useIsoSeparator: true`. A fixture using the
    date-only form must say which of those it is modelling.
    **Date presets** (AG-2) use a preset `type` (`"today"`, `"last7Days"`, ...). Their `dateFrom`/
    `dateTo` are **present and explicitly `null`**, not absent: `createCondition` returns
    `{ dateFrom: null, dateTo: null, filterType, type, ...model }` and a preset contributes nothing to
    `model` (it is in `simpleFilterUtils.ts`'s `zeroInputTypes`), so the real payload is
    `{"dateFrom":null,"dateTo":null,"filterType":"date","type":"last30Days"}`. AG Grid's own
    `PresetDateRangeFilterModel` doc comment says they are "always `undefined`" — that prose
    contradicts the emitter beside it; the fixtures follow the emitter. The preset
    vocabulary (`ISimpleFilterModelPresetType`) is closed and has 22 members, each resolving to a
    half-open `[from, to)` range published in AG Grid's own spec table — the adapter resolves it
    against an injected clock + zone, so no compiler ever sees an unresolved preset. See
    `date-presets/README.md` for the full table and the pinned-clock convention.
  - Set condition (`iSetFilter.ts`): `{ filterType: "set", values: string[]|null }` — maps to
    `in`/`notIn`.
  - Multi condition (`iMultiFilter.ts`): `{ filterType: "multi", filterModels: [<condition>, ...] }`
    — stacks several filter UIs on one column, combined with AND.
  - Boolean: AG Grid core has no dedicated boolean filter type — represent as a `set` condition
    with `values: ["true"]` / `["false"]` / `["true","false"]`; note this modeling choice in the
    fixture's `description.md`.
- **`customFilters` (OQ-11 extension, not part of AG Grid's own wire format):** an optional
  sibling field on the request, `{ customFilters: <filterNode> }` — a host-defined IR fragment
  merged into the filter tree by the adapter (see
  `docs/architecture/c4-components-core-ir.md`'s "Custom Filter Merge" component). This is the
  **only** way a fixture can exercise anything the AG Grid wire format itself cannot express: SEC-3
  **depth** adversarial cases (AG Grid's own `filterModel` is structurally shallow — a flat per-column
  map whose per-column condition count is bounded by `ISimpleFilterParams.maxNumConditions`, a
  documented grid option defaulting to `2`, so the native tree is at most `And(columns...)` over
  `And`/`Or(conditions...)`: three levels, never deeper, whatever `maxNumConditions` is set to),
  `inRange` boundary inclusivity (AG Grid's
  `inRange` carries no inclusivity flags at all — do not invent an inclusivity default and assert it
  as if it were the AG Grid default; use `customFilters` with explicit flags instead, per SEM-4's own
  "must NOT present the exact AG Grid boundary-inclusivity default as settled fact" rule), and a set
  filter's `notIn` direction (AG Grid's `SetFilterModel` carries only an inclusion list — there is no
  wire-level invert flag).
  - **Known gap (stated, not covered).** `max-depth-exceeded` is genuinely unreachable from a native
    `filterModel` — the shape caps out at three levels. `max-leaves-exceeded` is **not**: leaf count
    is `columns x maxNumConditions`, and a grid configured with a high `maxNumConditions` (or simply
    with many filtered columns) can breach the limit from a pure `filterModel` with no extension in
    sight. No adversarial fixture currently covers that path — every SEC-3 leaf-count case routes
    through `customFilters` — so the leaf limit is pinned only on the extension, not on the wire form
    a real grid emits. Authoring it is deliberately out of scope of #1637; recorded here so the gap is
    known rather than implied to be impossible.
- **`requestContext` (extension, not part of AG Grid's own wire format):** an optional sibling field,
  `{ requestContext: { zone: "<IANA id>", now: "<ISO-8601 instant>" } }`. Required on any fixture
  whose expected artifacts depend on a specific zone resolution or on a specific "current time" —
  without it, a port author must guess what the fixture author assumed.
  - `zone` carries the zone the adapter used to resolve any `datetime`-typed filter value in this
    request (SEM-4). An adapter **does** read this off the request: it takes precedence over whatever
    default zone the adapter was configured with, and an id it cannot resolve is a clean rejection,
    never a silent fallback.
  - `now` (added by AG-2's `date-presets/` category) pins the instant a **date preset** resolves
    against — preset resolution is clock-dependent, so a preset fixture is not reproducible without
    it. Unlike `zone`, this is an instruction **to the conformance harness**, not a field an adapter
    reads off the wire: the harness sets its injected clock to this instant before parsing. An
    implementation must not honour a client-supplied `now`, or any caller could redefine what
    "last 7 days" means. Absent on every fixture that does not use a preset.
  - `maxQueryTimeMs` (added by the `query-time-limit/` category) is the same kind of instruction: it sets the host's
    maximum query time for the compile (TL-4), and a production parser never reads it.
  - `defaultPageSize` and `allowUnboundedRows` (added by the `default-page-size/` category) are the same kind of instruction: the host's
    default page size and its switch for `ignorePageLimit` (PG-1, PG-3).

## Categories

| Directory | Proves | Target count |
|---|---|---|
| `operators/` | AR-6's 17-operator closed set, across field types | ~62 |
| `date-presets/` | AG-2 date presets resolved to absolute half-open ranges (SEM-4 type + zone) | ~28 |
| `filter-tree/` | AR-5 And/Or/Not composition, nesting/depth variation | ~15 |
| `sort-paging/` | SEM-3 null ordering, SEM-6 stableKey tiebreaker, AR-9 | ~17 |
| `group-aggregation/` | BM-2 grouping, BM-3 set-filter values, AR-8 aggregation funcs | ~20 |
| `page-export/` | AG-3/EXP-2 page spec, EXP-1 export + EXP-4/EXP-5/EXP-8 byte-exact writer output (delimiters, BOM, per-field formats) + EXP-6 hostile CSV values | ~20 |
| `adversarial/` | SEC-6: injection attempts, unknown fields, type confusion, depth bombs, oversized limits, duplicate aggregation output names | ~20 |
| `dialect-parity/` | Dialect-specific mechanics + cross-backend parity showcases (SEM-1/2/3/7/8, SQL-5/6/7, MDB-9) + AGG-6's five-SQL-dialect aggregate case | ~26 |
| `ag-grid-majors/` | AG-4: one SSRM payload per supported AG Grid major (v31-v36), plus the two rejections any major can emit (AG-5 Advanced Filter, SEM-4 native `inRange`) — **derived from each release tag's published types, not captured from a running grid** (see its README) | 8 |
| `community-infinite/` | AG-7: flat requests in the shape AG Grid Community's Infinite Row Model sends — text, number and date filter operators, both join operators, sort and paging — compiled with the same semantics as the SSRM; every case labelled `derived` or `captured` | 27 |
| `query-time-limit/` | TL-1..TL-5: the optional `maxTimeMS` (MongoDB) and `timeout` (Search) members, absent when no limit is set, never on an export, never set from the wire | 6 |
| `default-page-size/` | PG-1..PG-4: a request with no window gets a default page, an allowed `ignorePageLimit` is unpaginated, the time limit follows the page | 5 |

Each category directory has its own `README.md` enumerating its cases and the specific requirement
each one backs.
