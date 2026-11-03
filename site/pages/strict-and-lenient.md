# Strict and Lenient

This page explains the two modes a schema can run in, and what each does when a request names a column the schema does not allow. It is for a developer who is writing a schema and has to pick a mode.

Short version: use Strict unless you have a reason not to. Strict is the default.

## Where you set the mode

The mode is a setting in the schema, with the values `strict` and `lenient`.

```json
{
  "mode": "strict",
  "source": "orders",
  "stableKey": "id",
  "fields": { }
}
```

In C#, `GridSchema.Mode` defaults to `Strict`. The JSON schema for the file lists `mode` as required, so write it out in your schema file.

## Strict

In Strict mode, a filter on a column that the schema does not list is refused. Craticula throws an `UnknownFieldException` that names every column it rejected. No query is produced.

The same happens for a column the schema lists but marks `filterable: false`. Craticula treats it like an unknown column.

The adversarial fixtures show this. A filter, a sort and a row group on an unknown column are all refused. The filter and the row group throw `UnknownFieldException`; the sort is refused by the compiler (see the last point below). So is a column name made of SQL, such as `amount'); DROP TABLE users; --`.

## Lenient

In Lenient mode, Craticula drops a filter condition on an unknown or non-filterable column and goes on with the rest.

Dropping a condition makes the answer wider. The grid may get more rows than it asked for. Choose Lenient only if you accept that.

Some details of how a dropped condition is removed:

- An AND or OR group that loses all its conditions disappears.
- A group left with one condition becomes that condition.
- A NOT whose condition disappears also disappears. It does not turn into "match everything" or "match nothing".

## What no mode relaxes

Lenient only forgives a filter condition. The specification says that anything that decides the shape of the answer is refused in every mode:

- a group column that is not in the schema, or not marked groupable;
- a group key that drills into a column that is not filterable;
- an aggregation on a column that is not in the schema, or not allowed to use that function;
- the column of a distinct-values request for a set filter;
- an export column that is unknown, not exportable, repeated, or an empty list.

The reason is that dropping these would give the grid a different answer than the one it asked for, with no error. A dropped group key could return another group's rows under the label the grid expects.

The mode also has no effect on the other checks. A request that is too deep, too wide, asks for too many rows, or has a value that does not fit the column type is rejected in both modes. See [The safety model](safety-model.html).

One more point: a sort on a column the schema does not list is refused in both modes. The refusal comes from the compiler, which throws its own compilation exception rather than `UnknownFieldException`, so catch both in your endpoint and return a client error.

## How to choose

- Choose **Strict** if the grid is yours and an unknown column means a bug or an attack. You find out at once.
- Choose **Lenient** only if you accept that a request naming an unknown or non-filterable column returns more rows instead of an error.

If you are unsure, use Strict.

## Where this comes from

- [spec/semantics.md](../../spec/semantics.md)
- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridSchemaMode.cs](../../csharp/src/Craticula.Core/Schema/GridSchemaMode.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
