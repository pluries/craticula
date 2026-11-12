# Craticula.EntityFrameworkCore

The Entity Framework Core execution adapter of Craticula. It compiles the canonical IR straight to `IQueryable<T>`
expression trees and runs them, so no SQL text is produced here. It works with any relational provider (you choose
the provider package) and supports paging, row counts and streamed export.

## Install

```
dotnet add package Craticula.EntityFrameworkCore
```

Depends on `Microsoft.EntityFrameworkCore.Relational` `[10.0.12, 11.0)`.

## Example

```csharp
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.EntityFrameworkCore;

public static class Example
{
    public static async Task<EfCoreGridPage> Fetch<TRow>(
        IQueryable<TRow> source, GridSchema schema, FilterNode? filter, IReadOnlyList<SortItem>? sort, PageSpec page)
        where TRow : class
    {
        var request = new EfCoreQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page };

        // EfCoreProviderSemantics.Sqlite is the one measured preset; declare your own for other engines.
        return await EfCoreGridQuery.FetchPageAsync(
            source, request, EfCoreProviderSemantics.Sqlite, includeRowCount: true);
    }
}
```

## Two host obligations that fail silently

Both run without error and return wrong rows, so the adapter documents them; it cannot see the host's model or collations.

- **SQLite instants.** Store a `datetime` as `yyyy-MM-ddTHH:mm:ss.fffZ` text (SEM-4) and map every `DateTime` to and from that text in your
  `DbContext` (`configurationBuilder.Properties<DateTime>().HaveConversion<YourStoredInstantConverter>()`). EF's own mapping binds a
  value as `yyyy-MM-dd HH:mm:ss`; on the value's own date `'T'` sorts after a space. Without the mapping an `eq` at a stored time finds
  nothing, a `neq` finds every row, a range bound counts the whole bound date as later (13,335 rows for 13,321 on the demo), and a
  datetime-sorted export repeats or drops rows at chunk edges (20,060 and 19,947 rows for 20,000). An export whose walk meets the row
  the previous chunk ended on stops with an exception rather than loop. The mapping writes millisecond text, so a finer-than-millisecond
  bound is truncated, not floored or ceiled as the SQL compiler does (SEM-4).
- **`PatternMatchFoldsCase`** says what the engine's `LIKE` does. SQLite: `true` (its `LIKE` folds ASCII case whatever the column is, and `true`
  is what makes a `caseSensitivity: "sensitive"` field refuse instead of answering case-insensitively). SQL Server and MySQL: `false`, unless
  every searchable column's collation folds case, because `true` sends a bare `LIKE` that follows the column's collation and a
  binary-collated column (`..._BIN2`, `utf8mb4_bin`) then matches exact case only: `contains "germ"` finds no `Germany`. `false` lowers both
  sides and is right for every case-insensitive field.

`EfCoreHostObligationTests` shows each: wrong rows without it, right rows with it.

## Datetime cells

A `datetime` cell leaves a page or an export row as a UTC instant, whatever kind the provider materialised (SEM-4, result side): a
UTC value is kept, a local one is converted, a zone-less one (SQL Server `datetime2`, MySQL `DATETIME`, SQLite text) is read as UTC.
A host needs no UTC value converter for the way out. The values it stores must still be UTC readings.

## Compatibility

Implements Craticula spec version 0.2.0 (the language-neutral semantics and conformance fixtures in the
[repository](https://github.com/pluries/craticula), `spec/`). Targets .NET 10.

## License

Apache-2.0. Source and issues: <https://github.com/pluries/craticula>.
