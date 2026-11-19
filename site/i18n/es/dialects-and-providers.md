---
translates: dialects-and-providers
title: Dialectos y proveedores
description: En qué se diferencia cada motor de base de datos en el entrecomillado, la paginación, el orden de los nulos y la comparación sin distinguir mayúsculas.
source_fingerprint: e3cadc85fee286141cd8091c6103e2780064d51e19a1428afa783d8f20b83081
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Dialectos y proveedores {#dialects-and-providers}

Esta página enumera las bases de datos para las que Craticula puede escribir consultas, en qué se diferencian sus consultas y qué versiones se han probado. Está dirigida al desarrollador que elige una base de datos o un dialecto, o que quiere saber por qué la misma solicitud produce un texto distinto en cada una.

## Qué es un dialecto {#what-a-dialect-is}

La misma solicitud significa lo mismo en todos los backends. Craticula decide una sola vez qué significa, en la forma canónica. Después, un escritor por base de datos la expresa en el lenguaje de esa base de datos.

Para SQL, ese escritor es un dialecto. Una clase de dialecto tiene una única `Instance` compartida, como `PostgresDialect.Instance`. Usted la pasa a `SqlQueryBuilder.Build`. Hay cinco:

| Base de datos | Clase de dialecto |
|---|---|
| PostgreSQL | `PostgresDialect` |
| SQL Server | `MssqlDialect` |
| MySQL (MariaDB pasa por el mismo dialecto, pero nunca se ha probado) | `MySqlDialect` |
| SQLite | `SqliteDialect` |
| Oracle | `OracleDialect` |

MongoDB y OpenSearch tienen sus propios compiladores, `MongoPipelineBuilder` y `SearchQueryBuilder`. No toman un dialecto. Consulte [Adaptadores de MongoDB y OpenSearch](search-adapters.html).

## En qué se diferencia el SQL {#how-the-sql-differs}

| Base de datos | Marcador de posición | Entrecomillado | Paginación |
|---|---|---|---|
| PostgreSQL | `$1`, `$2` | `"name"` | `LIMIT` y `OFFSET` |
| SQL Server | `@p1`, `@p2` | `[name]` | `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` |
| MySQL | `?` | `` `name` `` | `LIMIT` y `OFFSET` |
| SQLite | `?` | `"name"` | `LIMIT` y `OFFSET` |
| Oracle | `:p1`, `:p2` | `"name"` | `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` |

En todos los casos los valores son parámetros, enumerados en el orden en que aparecen los marcadores de posición. Todos los nombres de tabla y de columna se entrecomillan, y un carácter de comillas dentro de un nombre se duplica. Consulte [El modelo de seguridad](safety-model.html).

PostgreSQL pasa una lista "in" como un único parámetro de matriz. Las demás bases de datos escriben un marcador de posición por cada valor.

## Orden de los nulos {#null-ordering}

Craticula indica dónde se ordenan los nulos en cada consulta, de modo que el orden no depende del valor predeterminado de la base de datos. La forma de indicarlo depende de la base de datos:

- PostgreSQL, SQLite y Oracle tienen `NULLS FIRST` y `NULLS LAST`. SQLite necesita la versión 3.30.0 o posterior.
- SQL Server no tiene esa sintaxis. La consulta ordena primero por `CASE WHEN column IS NULL THEN 1 ELSE 0 END` y después por la columna.
- MySQL tampoco la tiene. La consulta ordena primero por `ISNULL(column)` y después por la columna.
- MongoDB ordena por un campo auxiliar que marca los nulos, y la consulta lo elimina después.
- OpenSearch usa `"missing": "_first"` o `"_last"`.

Consulte [Paginación y ordenación](paging-and-sorting.html).

## Comparación sin distinguir mayúsculas {#case-insensitive-comparison}

Un campo de texto se compara sin tener en cuenta las mayúsculas y minúsculas salvo que el esquema indique lo contrario. Cada base de datos lo consigue de manera distinta:

| Base de datos | Cómo ignora las mayúsculas y minúsculas |
|---|---|
| PostgreSQL | `COLLATE craticula_ci` en las comparaciones y ordenaciones, que usted crea una sola vez. `ILIKE` para `contains`, `startsWith` y `endsWith`. |
| SQL Server | `COLLATE Latin1_General_CI_AS` en la consulta. Un campo que distingue mayúsculas y minúsculas recibe `Latin1_General_CS_AS`. |
| MySQL | Nada en la consulta. Decide la colación propia de la columna. Un campo que distingue mayúsculas y minúsculas necesita una columna `_bin` o `_as_cs`. |
| SQLite | `COLLATE NOCASE`, que pliega solo las letras ASCII. |
| Oracle | `COLLATE BINARY_CI`. Un campo que distingue mayúsculas y minúsculas recibe `COLLATE BINARY`. |
| MongoDB | Una colación en toda la consulta, con la configuración regional `en` y la intensidad 2. |
| OpenSearch y Elasticsearch | La opción `case_insensitive` en las consultas term y wildcard, y un subcampo normalizado para ordenaciones y rangos. |

Dos casos son silenciosos: un campo que distingue mayúsculas y minúsculas en MySQL, y las columnas de agrupación en SQL Server, MySQL y Oracle. La sentencia se ejecuta y devuelve filas incorrectas si la colación de la columna no es la que Craticula supone. La guía de índices y bases de datos enumera qué configurar en cada caso: [Guía de índices y bases de datos](index-guidance.html).

## Versiones {#versions}

Estas son las versiones más bajas que necesitan las consultas compiladas, tomadas de la especificación y de la documentación de los fabricantes, no de una ejecución de pruebas. Solo se ejecutó la columna de lo probado. El adaptador de Elasticsearch está documentado para la serie 8.x.

| Base de datos | Mínimo | Contra qué se ejecutaron las pruebas |
|---|---|---|
| PostgreSQL | 12, con ICU | 16 |
| SQL Server | ninguno indicado | 2022 |
| MySQL | ninguno indicado | 8.4 |
| SQLite | 3.30.0 | no registrado |
| Oracle | 12.2 | Database Free 23ai |
| MongoDB | 4.2 | 7.0 |
| OpenSearch | 1.0 | 2.19 |
| Elasticsearch | 7.10 | 8.17 |

"Ninguno indicado" significa que el código y la especificación no fijan ningún mínimo, no que se haya probado cada versión antigua. MariaDB usa el dialecto de MySQL, pero ninguna prueba se ejecuta en MariaDB.

Las pruebas ejecutan las consultas compiladas contra bases de datos reales en contenedores. Esa ejecución necesita Docker y no forma parte de la ejecución rápida de pruebas, así que consulte el repositorio para conocer el estado más reciente.

## El estado de Oracle {#oracles-status}

Oracle es compatible como un dialecto probado por la comunidad, no como un dialecto central de la versión 1. Se evalúa del mismo modo que los demás: cada sentencia se compara con un texto esperado almacenado. La diferencia es la cobertura. Se comprueba con un conjunto de ejemplos más pequeño que el de los otros cuatro, 45 en total. Esos 45 también se ejecutan contra un servidor real de Oracle Database Free 23ai.

Oracle 12.2 a 21c no se han ejecutado. El mínimo de 12.2 procede de la documentación de Oracle, no de una medición.

Tres hechos de Oracle determinan la salida:

- **El texto vacío es nulo.** Un valor de texto `""` en una comparación coincidiría silenciosamente con las filas equivocadas, así que el dialecto de Oracle lo rechaza. Use en su lugar los operadores de vacío y no vacío.
- **Los nombres deben ir entrecomillados.** Cree la tabla y sus columnas con nombres entrecomillados que coincidan exactamente con el esquema.
- **Ajustes de sesión.** Los formatos de fecha, marca de tiempo y número proceden de la sesión, así que configúrelos como describe [Guía de índices y bases de datos](index-guidance.html).

## Proveedores {#providers}

Aquí, un proveedor es la biblioteca que realmente se comunica con la base de datos. Craticula no elige uno por usted.

- Para SQL, `Craticula.Dapper` ejecuta cualquier dialecto en un `IDbConnection` abierto, sea cual sea el proveedor de ADO.NET que lo creó.
- `Craticula.EntityFrameworkCore` usa el proveedor de su `DbContext`. Necesita un `EfCoreProviderSemantics` que describa su motor, y solo se suministra el de SQLite. Consulte [Entity Framework Core y Dapper](relational-adapters.html).
- MongoDB se ejecuta mediante el controlador oficial de MongoDB para .NET, y OpenSearch mediante el cliente de bajo nivel `OpenSearch.Client`.

El repositorio tiene una aplicación de demostración en `examples/demo` que usted mismo ejecuta. Lee los mismos pedidos sintéticos de varias de estas bases de datos y compara las respuestas.

## De dónde procede esta página {#where-this-comes-from}

- [csharp/src/Craticula.Sql/README.md](../../csharp/src/Craticula.Sql/README.md)
- [csharp/src/Craticula.Sql/OracleDialect.cs](../../csharp/src/Craticula.Sql/OracleDialect.cs)
- [csharp/src/Craticula.Sql/MssqlDialect.cs](../../csharp/src/Craticula.Sql/MssqlDialect.cs)
- [spec/fixtures/dialect-parity](../../spec/fixtures/dialect-parity/README.md)
- [spec/fixtures/README.md](../../spec/fixtures/README.md)
- [spec/semantics.md](../../spec/semantics.md)
- [csharp/tests/Craticula.Integration.Tests/Sql/SqlEngine.cs](../../csharp/tests/Craticula.Integration.Tests/Sql/SqlEngine.cs)
- [examples/demo/README.md](../../examples/demo/README.md)
- Páginas relacionadas: [Guía de índices y bases de datos](index-guidance.html), [Paginación y ordenación](paging-and-sorting.html), [El GridSchema](the-gridschema.html)
