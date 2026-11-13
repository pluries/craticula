# Craticula

[![CI](https://github.com/pluries/craticula/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/pluries/craticula/actions/workflows/ci.yml)
[![coverage gate](https://img.shields.io/badge/coverage%20gate-%E2%89%A590%25%20per%20assembly-brightgreen)](https://github.com/pluries/craticula/actions/workflows/ci.yml)
[![license](https://img.shields.io/github/license/pluries/craticula)](LICENSE)
[![spec version](https://img.shields.io/badge/spec-0.2.0-blue)](spec/VERSION)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/pluries/craticula/badge)](https://scorecard.dev/viewer/?uri=github.com/pluries/craticula)

> A compiler, not a client: translate AG Grid Server-Side Row Model requests into native,
> secure backend queries — SQL, MongoDB, OpenSearch/Elasticsearch — from one canonical IR,
> across four languages.

**Maintainer:** Christian Stephan ([cstephan.dev](https://cstephan.dev), [LinkedIn](https://www.linkedin.com/in/christian-stephan), [GitHub](https://github.com/cstephan-dev)). Craticula is open source under Apache-2.0;
the project site is [craticula.pluries.dev](https://craticula.pluries.dev).

**Status:** early design. The maintainers keep a technical requirements document (TRD: architecture,
security model, roadmap, open questions) privately; its requirement ids (AR-1, SEM-1, GRP-7 and so on)
are cited throughout this repository, and the normative rules are in [`spec/semantics.md`](spec/semantics.md).

## Why

Every backend team re-implements the translation of an AG Grid SSRM request
(`filterModel`, `sortModel`, `rowGroupCols`, `groupKeys`, `valueCols`, `startRow`/`endRow`)
into database queries — usually with string DSL intermediaries, missing operators, broken
null/case semantics, injection surface, and no grouping or search-engine support. No
maintained open-source library covers this end to end.

## How it works

![How a request becomes a query: an AG Grid request passes the request adapter into the canonical IR, and the query compiler turns it into a query artifact (SQL with parameters, a MongoDB aggregation pipeline or an OpenSearch query), all checked against the GridSchema; optional execution adapters run the artifact and shape the rows back into the grid response.](site/diagrams/how-it-works.svg)

The core never opens a connection: compilation is a pure function from a grid request plus
a schema configuration (the security and typing boundary) to a plain query artifact.
Execution — running the artifact and shaping results back into the grid response — lives in
separate, optional per-ecosystem adapter packages.

## Scope (v1)

- **Request adapter** (the spec calls it the *frontend adapter*; it is the compiler's input side, and it runs in your server, not in the browser): AG Grid SSRM (v31–v36). AG Grid Community's Infinite Row Model is supported for flat grids
  (sort, text, number and date filters, paging; see [`spec/fixtures/community-infinite`](spec/fixtures/community-infinite/README.md)).
  Row grouping, aggregation, pivot and the set filter are Enterprise features and are not part of that promise.
- **Query compilers** (the spec's *backend compilers*, also in your server): PostgreSQL, SQL Server, MySQL/MariaDB, SQLite, MongoDB, OpenSearch,
  Elasticsearch. Oracle is community-tested: the same SQL pipeline, with `FETCH FIRST` paging (12c and later).
- **Reference implementation:** C#/.NET, ported to TypeScript, Python, and Go after the spec
  freezes at 1.0.
- **Semantics** (case sensitivity, null handling/ordering, dates & zones, deterministic
  paging) are normative and enforced by a shared, language-agnostic conformance fixture suite.
- CSV/TSV streaming export shares the same compile-only input model.

The TRD's §2.2 (non-goals) and §14 (roadmap) say what is explicitly out of scope for v1.

## Repository layout (planned)

```
spec/         IR JSON Schema, semantics.md, conformance fixtures — the source of truth
csharp/       reference implementation (Core, AgGrid adapter, compilers, execution adapters)
typescript/   TypeScript port (after spec freeze)
python/       Python port (after spec freeze)
go/           Go port (after spec freeze)
docs/adr/     architecture decision records (why the design is the way it is)
examples/     demo app (React + AG Grid + one sample backend)
```

## Packaging

The C# implementation is split into ten NuGet packages, all published on nuget.org:

[![NuGet](https://img.shields.io/nuget/v/Craticula.Core?label=nuget)](https://www.nuget.org/packages/Craticula.Core)

[`Craticula.Core`](https://www.nuget.org/packages/Craticula.Core),
[`Craticula.AgGrid`](https://www.nuget.org/packages/Craticula.AgGrid),
[`Craticula.Sql`](https://www.nuget.org/packages/Craticula.Sql),
[`Craticula.Mongo`](https://www.nuget.org/packages/Craticula.Mongo),
[`Craticula.Search`](https://www.nuget.org/packages/Craticula.Search),
[`Craticula.Export.Csv`](https://www.nuget.org/packages/Craticula.Export.Csv),
[`Craticula.EntityFrameworkCore`](https://www.nuget.org/packages/Craticula.EntityFrameworkCore),
[`Craticula.Dapper`](https://www.nuget.org/packages/Craticula.Dapper),
[`Craticula.MongoDB.Driver`](https://www.nuget.org/packages/Craticula.MongoDB.Driver) and
[`Craticula.OpenSearch.Client`](https://www.nuget.org/packages/Craticula.OpenSearch.Client).
Install one with `dotnet add package <name>`. To check that the packages build and a clean consumer compiles against them, run
`bash scripts/pack-smoke.sh` (Python 3.10+ and the .NET 10 SDK; about 3 minutes).

## Dependency licenses

Every NuGet package under `csharp/`, transitive ones and test projects included, must carry a license the project accepts.
`python3 scripts/check-licenses.py` checks it (Python 3.10+, the .NET 10 SDK and nuget.org; restore the solution first with
`dotnet restore Craticula.sln` in `csharp/`, and the pinned tool with `dotnet tool restore` there). The same script runs in the
`license-check` job of every pull request and takes a few seconds with a warm package cache.

- **Allowed:** MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, 0BSD, Unlicense, PostgreSQL, Zlib
  ([`scripts/license-allowlist.json`](scripts/license-allowlist.json)).
- **Refused:** GPL, LGPL, AGPL, SSPL, BUSL, Elastic, Commons Clause and any non-commercial license. The failure line names the
  package, its version, the license and the project.
- **MPL-2.0:** only when an accepted ADR (a `Status: Accepted` line) in `docs/adr/` names MPL-2.0 and the package.
  It fails closed by design: with no such ADR, an MPL-2.0 package is refused.
- **Overrides:** when the tool cannot read a license (a license file or a bare URL instead of an SPDX id), add an entry to
  [`scripts/license-overrides.json`](scripts/license-overrides.json) with the package, its exact version, the real license and a
  written reason. The license must be an allowed SPDX id (or `"vendor_terms": true` for a vendor's own non-SPDX terms). An override
  never lifts a license the tool read as denied or MPL-2.0. An entry without a reason fails the check, and so does an entry that
  no longer matches a package.
- **Traps:** `MySql.Data` (GPL) is rejected by name: use `MySqlConnector`. The Oracle driver `Oracle.ManagedDataAccess.Core` and
  `Testcontainers.Oracle` are accepted in the test projects under `csharp/tests` only, never in a package under `csharp/src`.

## Demo

Try it live: [PostgreSQL](https://craticula-pg.pluries.dev) and [MongoDB](https://craticula-mongo.pluries.dev). Both show the same
synthetic orders through the same AG Grid page; they are read-only and rate-limited.

[`examples/demo`](examples/demo/README.md) is the app behind them: one AG Grid page that reads the same orders from PostgreSQL or
MongoDB through a C# API built on the library. To run it yourself it needs Docker, the .NET 10 SDK and Node 20.19 or newer. It is a
showcase that installs the published packages from nuget.org, as a user of the library would.

## Compatibility

| Spec version | .NET target |
|---|---|
| 0.2.0 | net10.0 |

The spec version is the one in [`spec/VERSION`](spec/VERSION); every package states it in its own README.
How versions are chosen is written in [VERSIONING.md](VERSIONING.md).
The packages declare version ranges for the libraries they wrap, never one exact version.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
