# Craticula.AgGrid

The AG Grid frontend adapter of Craticula. It parses a Server-Side Row Model request (the `getRows` JSON, AG Grid
v31 to v36) into the canonical IR that the Craticula compilers consume, and maps a page of results back to the
shape the grid expects. It does not talk to any database.

## Install

```
dotnet add package Craticula.AgGrid
```

## Example

```csharp
using Craticula.AgGrid;
using Craticula.Core.Ir;
using Craticula.Core.Schema;

public static class Example
{
    public static (AgGridParsedRequest Request, FilterNode? Filter) Parse(string requestJson, GridSchema schema)
    {
        AgGridParsedRequest parsed =
            AgGridRequestParser.Parse(requestJson, new AgGridParseOptions { Schema = schema });

        FilterNode? filter = GridFilterPipeline.Process(
            parsed.NativeFilter, parsed.CustomFilters, parsed.Page, schema, new ResourceLimits(),
            parsed.Group, parsed.Aggregations);

        return (parsed, filter);
    }
}
```

Pass the parsed request and the filter to a compiler package (`Craticula.Sql`, `Craticula.Mongo` or
`Craticula.Search`) or to an execution adapter.

## AG Grid Community (Infinite Row Model)

A flat grid on the free Community edition works too. The Infinite Row Model sends `startRow`, `endRow`, `sortModel` and
`filterModel` (no group, value or pivot fields), and the parser accepts exactly that.

- **Works:** the text, number and date filters with every operator Community offers except native in-range, both ways
  of joining two conditions (`condition1`/`condition2` and `conditions[]`), single- and multi-column sort, paging.
  Each compiles with the same semantics as the Server-Side Row Model.
- **Needs Enterprise, so not covered:** row grouping, aggregation, pivot and the set filter.
- **Not accepted:** the native in-range option is rejected (its two bounds carry no inclusivity); send a range through
  the `customFilters` extension with the inclusivity you mean, or hide the option on the column.
- **Dates:** a `date` column needs no zone. A `datetime` column resolves in the zone from `AgGridParseOptions.DefaultZone`
  (UTC unless you set one), because Community sends no `requestContext.zone`.
- **Status:** proven by derived test requests (`spec/fixtures/community-infinite`), not yet by payloads recorded from a
  real grid; the folder's README says how to swap one in.

A minimal datasource for the Infinite Row Model posts the `getRows` params and hands the rows back with the last row:

```ts
const datasource = {
  async getRows(params) {
    const response = await fetch('/api/rows', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        startRow: params.startRow,
        endRow: params.endRow,
        sortModel: params.sortModel,
        filterModel: params.filterModel,
      }),
    });
    const page = await response.json(); // { rows, lastRow } produced by your host from the compiled query
    params.successCallback(page.rows, page.lastRow);
  },
};
```

## Compatibility

Implements Craticula spec version 0.2.0 (the language-neutral semantics and conformance fixtures in the
[repository](https://github.com/pluries/craticula), `spec/`). Targets .NET 10.

## License

Apache-2.0. Source and issues: <https://github.com/pluries/craticula>.
