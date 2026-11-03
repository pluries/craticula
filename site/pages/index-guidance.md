# Index and database guidance

Craticula compiles queries; it never creates a table, an index or a collation. This page lists, for each database, what **you**
have to set up so the compiled queries return the right rows and run fast. The rules behind it are in
[semantics](semantics.html); the per-database fixtures that pin the statements are in
[`spec/fixtures/dialect-parity`](../../spec/fixtures/dialect-parity/README.md).

Two kinds of obligation appear below, and the difference matters:

- **Loud:** the database rejects the statement (a missing collation, an old server). You notice at once.
- **Silent:** the statement runs and returns wrong rows (a column that folds case when it should not). Nothing tells you, so these
  are the ones to read twice.

## At a glance

| Database | You must provide | If you do not |
|---|---|---|
| PostgreSQL | version 12 or later with ICU; the `craticula_ci` collation; `timestamptz` for datetimes | loud for the first two (every case-insensitive comparison fails), silent for `timestamp` |
| SQL Server | binary or case-sensitive collation on grouping columns; `datetime2` holding UTC | silent: `EMEA` and `emea` share a group |
| MySQL / MariaDB | `_bin` or `_as_cs` collation on case-sensitive and grouping columns; `DATETIME` holding UTC | silent: the declaration is ignored |
| SQLite | version 3.30.0 or later; datetimes stored as `yyyy-MM-ddTHH:mm:ss.fffZ` | loud for the version, silent for the datetime text |
| Oracle | 12.2 or later; quoted identifiers; binary collation on grouping columns (the default session setting) | loud for the first two, silent for the last |
| MongoDB | server 4.2 or later | loud: the pipeline is rejected |
| OpenSearch / Elasticsearch | `keyword` sub-fields, a normalizer for case-insensitive sorting, a precise number type for decimals | silent for a missing `keyword` sub-field in a filter (no rows match), loud in a sort; silent for rounding |

Every engine also needs the schema's **stable key to be unique, with at most one `NULL`**
([Deterministic paging](semantics.html#sem-6)). Most engines let a unique constraint hold many `NULL`s, which breaks the paging guarantee; declare the
key `NOT NULL`. A text stable key that is case-insensitive also needs a binary or case-sensitive collation on MySQL and SQL
Server, or two keys that differ only by case tie.

## Indexes for every database

- **Filters.** A text field compares case-insensitively by default ([Case sensitivity](semantics.html#sem-1)). The rule is built so a plain
  index on the column can still be used for equality: the compiler states a collation on the comparison instead of wrapping the
  column in `lower()`. Make the index match that collation (below). Substring matches (`contains`, `endsWith`) start with a
  wildcard, which no ordinary B-tree index serves; see each engine.
- **Sorting.** Every ordered query ends with the schema's stable key, ascending with nulls last ([Deterministic paging](semantics.html#sem-6)),
  and Craticula spells null placement itself ([Null ordering](semantics.html#sem-3)). An index serves the sort only if it matches that
  exact order. On PostgreSQL, SQLite and Oracle the quickstart's order is `amount DESC NULLS FIRST, id ASC NULLS LAST`, so the
  matching index is `(amount DESC NULLS FIRST, id ASC NULLS LAST)`; a plain `(amount, id)` index does not match a descending sort.
  On SQL Server and MySQL the statement orders by a null test first (`CASE WHEN ... IS NULL`, `ISNULL(...)`), which no column index
  serves, and on MongoDB the sort runs on computed helper fields. So there, index your **filters** and expect the sort to
  happen after them. Check the plan (`EXPLAIN`) on your own data; Craticula cannot know your table sizes.
- **Paging.** `OFFSET` typically gets slower the deeper the page. The CSV export walks the result in key order and does not use
  `OFFSET`.

## PostgreSQL

Needs PostgreSQL 12 or later built with ICU (a nondeterministic collation). One-time setup, in the database that holds your tables:

```sql
CREATE COLLATION craticula_ci (provider = icu, locale = 'und-u-ks-level2', deterministic = false);
```

Without it every case-insensitive `=`, `IN`, range and `ORDER BY` fails with an unknown collation
([Case sensitivity](semantics.html#sem-1)).

- **Equality and sorting** on a case-insensitive text field name `craticula_ci`. An index created with that collation
  (`CREATE INDEX ... ON orders (customer COLLATE craticula_ci)`) is the one that matches; confirm with `EXPLAIN`.
- **`contains`, `startsWith`, `endsWith`** compile to `ILIKE`. Back them with a trigram index: `CREATE EXTENSION pg_trgm;`
  then `CREATE INDEX ... USING gin (customer gin_trgm_ops);`.
- **Dates:** declare `datetime` columns `timestamptz`. With plain `timestamp` the server compares through the session time zone and
  rows shift without an error ([Dates and time zones](semantics.html#sem-4)).
- Grouping columns need no collation: PostgreSQL's default collation is deterministic, so `EMEA` and `emea` are two groups, as
  [Grouping and drill-down](semantics.html#grp-2) requires.

## SQL Server

No collation setup for filters: the statement carries `COLLATE Latin1_General_CI_AS` (or `Latin1_General_CS_AS` for a field you
declared case-sensitive) inline, so neither direction depends on the database's own collation.

- **Grouping columns, silent obligation.** A `GROUP BY` and a drill-down must be exact ([Grouping and drill-down](semantics.html#grp-2)), and the
  statement names no collation there. SQL Server's usual default (`SQL_Latin1_General_CP1_CI_AS`) folds case, so a grouped
  column declared with it puts `EMEA` and `emea` in one group. Declare each groupable column, and the stable key if it is text,
  with a binary or case-sensitive collation. The column definition is, for example:

  ```sql
  country nvarchar(100) COLLATE Latin1_General_100_BIN2 NULL
  ```

  Filters on that column still compare case-insensitively, because they state their own collation inline. The price is
  speed: a comparison that names a collation different from the column's usually cannot seek on it, so measure a
  case-insensitive filter on a column you also group by.
- **Dates.** `datetime2` has no time zone. Store the UTC reading; the compiler compares the UTC instant against it
  directly, and results come back as UTC ([Dates and time zones](semantics.html#sem-4)).
- **Entity Framework Core:** set `PatternMatchFoldsCase = false` on the provider semantics unless every searchable column's
  collation folds case; `true` sends a bare `LIKE`, which on a binary-collated column matches exact case only. See the
  [adapter's README](../../csharp/src/Craticula.EntityFrameworkCore/README.md).

## MySQL and MariaDB

Case sensitivity there belongs to the **column's** collation, which a statement cannot override portably.

- **Case-insensitive fields** (the default) work on any `_ci` column, such as `utf8mb4_0900_ai_ci`, and a plain index on the
  column serves equality on them (not a substring match, which starts with a wildcard).
- **Case-sensitive fields, silent obligation.** A field declared `caseSensitivity: "sensitive"` needs a `_bin` or `_as_cs`
  column collation (`utf8mb4_bin`, `utf8mb4_0900_as_cs`). On a `_ci` column the declaration has no effect and comparisons stay
  case-insensitive; the compiled statement does not tell you.
- **Grouping columns** need the same binary or `_as_cs` collation for exact groups ([Grouping and drill-down](semantics.html#grp-2)):

  ```sql
  country varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin
  ```

  A column has one collation, so a groupable column made binary also makes the case-insensitive filters and prefixes on that
  same column case-**sensitive**, silently (GRP-2's accepted divergence #4). If you need both on one field, decide which matters
  more; the compiler cannot give you both from one column.
- **Entity Framework Core:** like SQL Server, set `PatternMatchFoldsCase = false` unless every searchable column's collation folds case.
- **Dates.** `DATETIME` has no time zone: store UTC. If you use MySqlConnector, leave `DateTimeKind` at its default or set UTC;
  `Local` only labels the value and would shift every instant by the server's offset ([Dates and time zones](semantics.html#sem-4)).

## SQLite

- **Version 3.30.0 or later**, for `NULLS FIRST` / `NULLS LAST`. An older library rejects the statement.
- **Case-insensitive** fields use `COLLATE NOCASE`, which folds ASCII letters only (`É` and `é` stay different). An index
  declared `(customer COLLATE NOCASE)` serves them.
- **Datetimes, silent obligation.** SQLite has no timestamp type and compares text character by character. Store every
  `datetime` as exactly `yyyy-MM-ddTHH:mm:ss.fffZ`, in UTC, with three fraction digits ([Dates and time zones](semantics.html#sem-4)). Another
  width (`...:00Z`, `yyyy-MM-dd HH:mm:ss`) returns wrong rows without an error.
- **Entity Framework Core** binds a `DateTime` in its own `yyyy-MM-dd HH:mm:ss` form, so map every datetime to and from the
  stored text in your `DbContext`. Without the mapping an `eq` finds nothing, a range bound counts the whole date as later and
  a datetime-sorted export can repeat rows. The
  [adapter's README](../../csharp/src/Craticula.EntityFrameworkCore/README.md) has
  the details.

## Oracle

- **Server 12.2 or later.** The statements use `COLLATE BINARY_CI` and `COLLATE BINARY`; an older server rejects them.
  Oracle documents `COMPATIBLE >= 12.2` and `MAX_STRING_SIZE = EXTENDED` as the prerequisite of data-bound collation.
- **What was verified.** The compiled statements were run against Oracle Database Free 23.26.3 in a container
  (`gvenzl/oracle-free:23.26.3-slim-faststart`, `COMPATIBLE = 23.6.0`, `MAX_STRING_SIZE = STANDARD`): all 45 Oracle fixtures
  return the expected rows, and the cross-backend parity property passes with Oracle among eight engines. On that server the
  `COLLATE` operator inside a statement works without `EXTENDED`; only **declaring** a collation on a column fails
  (`ORA-43929`). Oracle 12.2 to 21c were **not** run: the floor above is Oracle's documentation, not a measurement.
- **Quoted identifiers.** Create the table and every column with quoted names that match the schema's `source` and `column`
  spelling exactly. Oracle upper-cases an unquoted name, and the compiled statement quotes every identifier
  (`ORA-00942` if they differ).
- **Session settings.** The compiled statements pass dates, datetimes and decimals as text and add no cast, so Oracle converts
  them by the session's settings. Set `NLS_DATE_FORMAT = 'YYYY-MM-DD'`,
  `NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD"T"HH24:MI:SS.FF"Z"'` and `NLS_NUMERIC_CHARACTERS = '.,'` on the connection; without them
  every date, datetime or decimal filter fails (`ORA-01861`, `ORA-01722`), and a client culture with a comma decimal can cause
  it only on some machines.
- **Grouping columns, silent obligation.** Run the session with `NLS_COMP = BINARY` and `NLS_SORT = BINARY` (the defaults for an English client; the verified setup), or, on a
  server with `MAX_STRING_SIZE = EXTENDED`, declare each groupable column and the stable key with `COLLATE BINARY`. The default
  collation follows the session and can fold case. The column definition is, for example:

  ```sql
  "country" VARCHAR2(100) COLLATE BINARY
  ```

## MongoDB

- **Server 4.2 or later**, for the `$unset` stage that every sorted pipeline uses to drop its null-placement helper fields.
- **Case-insensitive** fields compile to a query-level collation (`locale: "en"`, `strength: 2`). An index serves a collated
  query only if it was created with the same collation: `createIndex({ customer: 1 }, { collation: { locale: "en", strength: 2 } })`.
- **`contains`, `startsWith`, `endsWith`** compile to an escaped `$regex` (there is no collation-friendly substring operator in
  MongoDB). A regex does not use a collation-aware index the way an equality does, so expect to scan on a large collection and
  measure.
- **Sorting.** The sort runs on computed helper fields that hold the null placement, so no index serves it as a whole; index your
  filters ([Null ordering](semantics.html#sem-3)).
- **Grouping requests compare case-sensitively.** MongoDB has one collation per query. A grouping request must keep its
  buckets exact, so its pipeline carries no collation and a user filter in the same request compares case-**sensitively**
  (GRP-2's accepted divergence #3). The other databases fold case in that filter.

## OpenSearch and Elasticsearch

One compiler serves both. The index mapping is yours, and the compiled queries name the sub-fields your schema declares.

- **Version:** Elasticsearch 7.10 or later, OpenSearch 1.0 or later (for `case_insensitive` on `term` and `wildcard`).
- **`keyword` sub-field, silent in a filter.** Every text field that is filtered, sorted or grouped needs the `keyword` sub-field
  you declared as `physical.search.keywordSubField`, a multi-field in the index mapping. If it is missing, a filter on it
  matches **no rows** without an error; only a sort on it fails.
- **Case-insensitive ordering and range.** Declare `physical.search.normalizedSubField` and map it as a `keyword` with a folding
  `normalizer`. This costs index space and is the only way to sort or compare a text field case-insensitively; the compiler
  refuses to compile such a request for a field that does not declare one.
- **Decimals.** Map a `decimal` field as `scaled_float` with a sufficient `scaling_factor`, or as `keyword` if you only compare for
  equality. A `double` mapping rounds silently.
- **Deep paging and counts.** Past `max_result_window` (10,000 rows) the client pages with a point-in-time and `search_after`;
  set `Flavour` to `Elasticsearch` on **both** the deep-paging options and the export options for Elasticsearch, or every export
  fails with HTTP 400. The total row count above 10,000 is reported as unknown unless
  you opt in to the exact count, which counts every match on each first request.
- **`contains`** is a wildcard on the `keyword` field; a leading wildcard walks the term dictionary, so measure it on large indexes.

## What stays out of this page

Per-engine tuning (partitions, covering indexes, shard counts) depends on your data and workload. The compiled statements are in
the [conformance fixtures](../../spec/fixtures/), one folder per case, with the exact
text each database receives; run `EXPLAIN` on those against your own tables.
