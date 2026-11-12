# Craticula.Core

The shared core of Craticula, a compile-only library that turns AG Grid Server-Side Row Model requests into native,
injection-safe queries. This package holds the canonical query IR, the `GridSchema` (the allowlist and typing
boundary), resource limits and the semantics every compiler shares. It has no dependencies and never opens a
connection. You usually install a compiler or an adapter package instead, and get this one with it.

## Install

```
dotnet add package Craticula.Core
```

## Example

Validate a filter tree against your schema before any compiler sees it:

```csharp
using Craticula.Core.Ir;
using Craticula.Core.Schema;

public static class Example
{
    public static FilterNode? Validate(string schemaJson, FilterNode? clientFilter, PageSpec page)
    {
        GridSchema schema = GridSchema.Parse(schemaJson);

        // Allowlist, resource limits, type coercion, then your static filter, in that order.
        return GridFilterPipeline.Process(
            clientFilter, customFilters: null, page, schema, new ResourceLimits());
    }
}
```

## Compatibility

Implements Craticula spec version 0.2.0 (the language-neutral semantics and conformance fixtures in the
[repository](https://github.com/pluries/craticula), `spec/`). Targets .NET 10.

## License

Apache-2.0. Source and issues: <https://github.com/pluries/craticula>.
