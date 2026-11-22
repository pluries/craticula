# Backends

Per-backend detail for the table in `SKILL.md`. The snippets stay in `SKILL.md`; this page only points to them.

## SQL: PostgreSQL, SQL Server, MySQL, SQLite

- Packages: Craticula.Core, Craticula.AgGrid and Craticula.Sql.
- Compile with `SqlQueryBuilder.Build` and one dialect: `PostgresDialect`, `MssqlDialect`, `MySqlDialect` or `SqliteDialect`. Each dialect has a single shared `Instance`.
- The compiled `SqlQuery` holds the statement text with placeholders and the values as parameters.
- The count is a separate statement. The snippet for the SQL family is `sql-compile` in `SKILL.md`.
- The dialects differ in placeholders, quoting and paging, and in how they ignore case. The page on dialects and providers on the site lists them.
- MariaDB goes through the MySQL dialect and is untested. Oracle has a dialect, is community-tested and outside the v1 promise.

## MongoDB

- Packages: Craticula.Core, Craticula.AgGrid and Craticula.Mongo.
- Compile with `MongoPipelineBuilder.Build` for the page and `MongoPipelineBuilder.BuildCount` for the row count. Both return a `MongoQuery` with the collection name and the pipeline stages.
- The schema gives each field a `physical.mongo.path`. The snippet is `mongo-compile` in `SKILL.md`.

## OpenSearch and Elasticsearch

- Packages: Craticula.Core, Craticula.AgGrid and Craticula.Search.
- One compiler serves both engines: `SearchQueryBuilder.Build` for the page and `SearchQueryBuilder.BuildCount` for the row count. Both return a `SearchQuery` with the index name and the body.
- The schema gives each field a `physical.search.field`, and a keyword sub-field where the field is text. The index mapping must match the schema. The snippet is `search-compile` in `SKILL.md`.

## Not covered

Any other engine is not supported. Do not invent a dialect for it.
