# Craticula TypeScript: walking skeleton

This folder is the first step of the TypeScript port. It is a **skeleton**: a conformance driver that compiles one family of the
shared fixtures, `sort-paging`, to **PostgreSQL** SQL with bound parameters, and nothing else. It is **not published** to npm, it
claims no conformance beyond that family, and its package name is a placeholder.

What it proves: the folder layout, the toolchain (strict TypeScript, Node 22 or newer, ES modules, no runtime dependency), and the
public CI path. The real port starts in the features after it.

## Run it

Needs Node 22 or newer. Python 3.10 or newer runs the shared runner.

```bash
cd typescript
npm ci
npm test            # builds, then runs the package tests
npm run conformance # the shared runner against the driver, narrowed to sort-paging on PostgreSQL
```

The runner is the same one that grades the C# implementation (`conformance/run.py`, defined in `spec/conformance-runner.md`). The
narrowed run is a debugging aid; a driver that answers only one family fails the rest of the tree on purpose.

## What the driver compiles

An AG Grid request against a `GridSchema`, to a parameterised query for five SQL dialects: PostgreSQL, SQL Server, MySQL, Oracle and
SQLite. It covers filters (every operator, `not`, set and range conditions), sorting with SEM-1 case rules, SEM-3 null positions and
SEM-6's stable-key tiebreak, paging, grouping with drill-down and aggregates, count mode, the distinct-values query of a set filter,
the export projection and the schema's static filter. The runner reports 246 of 246 passed for PostgreSQL and every case of the other
four. MongoDB, OpenSearch and the CSV writer are later features, so a request for them gets an `error` answer.

Before that, every request goes through the stages a host runs: the AG Grid request becomes the IR, then the allowlist over every
column it names (sort, group, aggregation, set-values target, filter), the SEC-3 limits (depth 8, 64 leaves, 1,000 values in a set,
page size 1,000, each configurable and none switchable off) and the coercion of values to the declared field types. The driver
declares the `rejection` capability, so the 33 shared rejection fixtures run against it:

```bash
python3 ../conformance/run.py --driver "node dist/src/driver.js" --only "*#rejection"
```

`npm test` also prints line coverage of `src/` and fails below 90%.

Values are always bound parameters. The only text of a request or schema that reaches the SQL is a column name the schema
declares, quoted by the dialect's one `quoteIdentifier`; a column the schema does not declare is refused. `python3 scripts/lint-sec2-ts.py`
fails when query text is built from anything else.
