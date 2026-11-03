# What Craticula is

This page explains what Craticula does, what it leaves to you, and where the project stands today. It is for a developer who has an AG Grid server-side grid and has never seen Craticula.

Craticula is a .NET library that turns an AG Grid server-side row model request into a database query. It supports SQL, MongoDB and OpenSearch.

## The problem it solves

An AG Grid server-side grid sends your server a JSON request. The request says which rows the grid wants, how to sort them, how to filter them and how to group them.

Every backend team ends up writing the same code to turn that JSON into a query. That code is easy to get wrong. Null handling, case sensitivity, paging and injection safety all need care.

Craticula is that translation, written once and tested against shared examples.

## What it compiles

You give Craticula two things:

- the request exactly as AG Grid sent it;
- a schema that lists the columns the grid may touch and how they map to your database.

Craticula gives back a query you can run:

- for SQL, a statement and a list of parameters;
- for MongoDB, an aggregation pipeline;
- for OpenSearch and Elasticsearch, a query in their JSON query language.

## What it never does

Craticula is a compiler, not a client.

- It never opens a connection to a database.
- It never runs a query.
- It never reads your data.

Running the query is your job. Optional adapter packages can do it for you, but they are separate from the core. The core packages never depend on them.

## Supported backends and AG Grid versions

The first version targets these backends:

- PostgreSQL
- SQL Server
- MySQL and MariaDB
- SQLite
- MongoDB
- OpenSearch
- Elasticsearch

Oracle is not in the v1 list, and the project treats it as an open question. The repository contains an Oracle dialect, but it is not part of the promise.

On the grid side, the README names AG Grid server-side row model versions 31 to 36. It also supports the Community infinite row model for flat grids. That means sorting, text, number and date filters, and paging. Row grouping, aggregation, pivot and the set filter are Enterprise features and are not part of the Community promise.

Pivot mode is not supported. The request parser refuses a request with pivot mode on.

## Current state

Craticula is pre-release. No package is published yet, and nobody runs a demo for visitors. The repository has a demo app you run yourself (`examples/demo`), which needs Docker, the .NET 10 SDK and Node.

To try it, build from source. The [C# quickstart](quickstart-csharp.html) shows how. The C# library is the reference implementation. The repository describes TypeScript, Python and Go ports as planned for after the specification is frozen. None of them exists yet.

## Where to go next

- [How a request becomes a query](request-to-query.html) follows one request through the pipeline.
- [Strict and Lenient](strict-and-lenient.html) explains the two ways to treat unknown columns.
- [The safety model](safety-model.html) lists what Craticula protects and what it does not.

## Where this comes from

- [README.md](../../README.md)
- [spec/README.md](../../spec/README.md)
- [csharp/src/Craticula.Core/README.md](../../csharp/src/Craticula.Core/README.md)
- [csharp/src/Craticula.AgGrid/AgGridRequestParser.cs](../../csharp/src/Craticula.AgGrid/AgGridRequestParser.cs)
