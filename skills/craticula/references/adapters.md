# Adapters

The core packages compile and never open a connection or run a query. Four optional adapter packages run the compiled query on the user's own connection. They have no sample.

| Package | Backend | Public static methods |
|---|---|---|
| Craticula.Dapper | SQL, through Dapper | `FetchPageAsync`, `CountAsync` |
| Craticula.EntityFrameworkCore | SQL, through EF Core | `FetchPageAsync`, `CountAsync` |
| Craticula.MongoDB.Driver | MongoDB | `FetchPageAsync`, `CountAsync` |
| Craticula.OpenSearch.Client | OpenSearch and Elasticsearch | `FetchPageAsync` |

- `FetchPageAsync` returns one page with its columns and rows, and a row count where the adapter provides one.
- `CountAsync` returns only the row count.
- The user opens and owns the connection or client. The adapter never builds or closes it.
- The OpenSearch adapter needs a cursor cache that lives as long as the grid session. Ask the user to read the adapters page on the site before adding it.
- Add an adapter only when the user wants Craticula to run the query. Add the package with the package command of `SKILL.md`, nothing else.
