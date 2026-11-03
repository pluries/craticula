# Quickstart: C#

This page takes you from an AG Grid request to the parameterized SQL that answers it, in one small program. It needs no
database and no driver: Craticula compiles the query and never runs it.

**Nothing is published yet.** No Craticula package is on NuGet, so there is no package to install. You build from the
repository, which is also how this page was checked.

## What you need

- the .NET 10 SDK;
- the repository: clone or download <https://github.com/pluries/craticula>.

## Run it

From the `csharp` folder of the repository:

```
dotnet run --project samples/Craticula.Quickstart
```

The program is the file below. The solution builds it, so a change to the library that breaks it breaks the build. It does
five things: it declares a schema (the allowlist), takes an AG Grid request, parses it into the canonical IR, compiles it for
two databases, and shows a request for an unlisted column being refused.

{{include csharp/samples/Craticula.Quickstart/Program.cs csharp}}

## What you should see

The same request gives each database its own statement. Values are never part of the text: they are the parameters listed
under each statement, in the order the placeholders appear. The last line shows the refusal of the column that is not in the
schema.

{{include csharp/samples/Craticula.Quickstart/expected-output.txt text}}

## Read the output

- `ILIKE` and `COLLATE Latin1_General_CI_AS` are how each database spells the default case-insensitive match
  ([Case sensitivity](semantics.html#sem-1)); the two statements agree on which rows they return.
- `ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST` ends in `id`, the schema's stable key, so paging is deterministic
  ([Deterministic paging](semantics.html#sem-6)). SQL Server has no `NULLS FIRST`, so it spells the same order with a leading `CASE`
  ([Null ordering](semantics.html#sem-3)).
- The decimal `100` is printed `'100'` because a decimal parameter is carried as a string, so no precision is lost on the way
  to the driver (AR-7). Bind it as a decimal in your driver.
- `"password"` was refused because the schema lists no such column; the request never reached a compiler.

## Run it on a real database

Compile and run in one call with an execution adapter, which takes an open connection or a `DbContext` from you. Their READMEs show
the install line for when packages are published; today you reference the projects from the repository instead.

- [`Craticula.Dapper`](../../csharp/src/Craticula.Dapper/README.md): runs the statement
  on an `IDbConnection`, with paging, row counts and streamed CSV export.
- [`Craticula.EntityFrameworkCore`](../../csharp/src/Craticula.EntityFrameworkCore/README.md):
  builds `IQueryable` expression trees; read its two host obligations first.
- MongoDB and OpenSearch have their own compilers and clients (`Craticula.Mongo`, `Craticula.MongoDB.Driver`,
  `Craticula.Search`, `Craticula.OpenSearch.Client`).

For the whole path with a browser grid, ten providers on seven database engines and a script that compares them against each other, follow the
[demo](../../examples/demo/README.md).

## Next

- What each database needs from you before the statements are right: [index and database guidance](index-guidance.html).
- The rules behind the output: [semantics](semantics.html).
- Every setting of the schema: the [GridSchema reference](grid-schema.html).
