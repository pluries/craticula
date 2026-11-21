---
translates: relational-adapters
title: Entity Framework Core y Dapper
description: Qué ofrecen los dos adaptadores relacionales, qué necesitan y qué no hacen nunca.
source_fingerprint: c7c6226b52fe85563de296ccf30f4b6133346e53ef471b90257c33696e64481f
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Entity Framework Core y Dapper {#entity-framework-core-and-dapper}

Esta página trata de los dos paquetes opcionales que ejecutan consultas de Craticula en una base de datos relacional: `Craticula.Dapper` y `Craticula.EntityFrameworkCore`. Está dirigida al desarrollador que tiene una base de datos SQL y quiere que Craticula ejecute la consulta además de escribirla.

## Por qué existen los adaptadores {#why-adapters-exist}

Los paquetes del núcleo solo compilan. Nunca abren una conexión ni ejecutan nada. Un adaptador cubre esa carencia para una biblioteca de acceso a datos concreta. Compila la solicitud, la ejecuta y le entrega filas.

Los adaptadores son opcionales. Los paquetes del núcleo nunca dependen de ellos. Puede prescindir de ellos y ejecutar usted mismo la sentencia compilada con la biblioteca que prefiera.

Instálelos desde NuGet: `dotnet add package Craticula.Dapper` o `dotnet add package Craticula.EntityFrameworkCore`. Consulte [la guía de inicio rápido de C#](quickstart-csharp.html).

## Dapper {#dapper}

`Craticula.Dapper` compila con `Craticula.Sql` y ejecuta la sentencia en una conexión que usted le entrega. Úselo cuando quiera ver y controlar el SQL.

```csharp
DapperGridPage result = await DapperGridQuery.FetchPageAsync(
    openConnection,
    new SqlQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    PostgresDialect.Instance,
    includeRowCount: true);
```

Lo que ofrece:

- `DapperGridQuery.FetchPageAsync` devuelve una página. `DapperGridPage` contiene `Columns`, `Rows` y un `RowCount` opcional.
- `DapperGridQuery.CountAsync` ejecuta solo el recuento.
- `DapperExportStream.StreamAsync` transmite todas las filas coincidentes para una exportación. Consulte [Exportación a CSV](csv-export.html).
- `FetchPageAsync` rechaza la página sin paginar (`NonePage`), de modo que una llamada nunca carga todas las filas en memoria. Una solicitud de todas las filas pasa por `DapperExportStream`.

Lo que necesita de usted:

- Un `IDbConnection` abierto. El adaptador nunca lo abre ni lo cierra.
- El dialecto que corresponda a su base de datos. Consulte [Dialectos y proveedores](dialects-and-providers.html).
- El propio Dapper, en el intervalo `[2.1.89, 3.0)`.

Las solicitudes agrupadas funcionan con el mismo método. El compilador de SQL ya escribe la sentencia agrupada, así que el adaptador se limita a ejecutarla.

## Entity Framework Core {#entity-framework-core}

`Craticula.EntityFrameworkCore` no escribe texto SQL. Construye árboles de expresión `IQueryable<T>`, y el proveedor de EF Core los convierte en SQL. Úselo cuando ya tenga un `DbContext` y quiera que se apliquen sus filtros de consulta globales, como un filtro de inquilino.

```csharp
var request = new EfCoreQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page };

EfCoreGridPage result = await EfCoreGridQuery.FetchPageAsync(
    source, request, EfCoreProviderSemantics.Sqlite, includeRowCount: true);
```

Lo que ofrece:

- `EfCoreGridQuery.FetchPageAsync` devuelve una página, en un `EfCoreGridPage` con la misma forma que el de Dapper.
- `EfCoreGridQuery.CountAsync` ejecuta solo el recuento.
- `EfCoreExportStream.StreamAsync` transmite filas para una exportación.
- `FetchPageAsync` rechaza la página sin paginar, igual que el adaptador de Dapper. Una solicitud de todas las filas pasa por `EfCoreExportStream`.

Lo que necesita de usted:

- **Una consulta de origen.** Pase un `DbSet<T>` o, si no tiene clases de entidad, `GridSchemaPropertyBag.Query(context, schema)`. Para la segunda forma, llame a `GridSchemaPropertyBag.Configure` en `OnModelCreating`.
- **Nombres de propiedad coincidentes.** Cada campo se lee como una propiedad de EF con el nombre de su `physical.sql.column` o, si no la hay, con el id de la columna. Una clase que renombre sus columnas con `HasColumnName` debe ajustarse a eso.
- **Un valor `EfCoreProviderSemantics`.** Declara cinco hechos sobre su base de datos que EF no puede comunicar a Craticula, como el nombre de la colación que no distingue mayúsculas de minúsculas. Solo se incluye `EfCoreProviderSemantics.Sqlite`, porque es el único que se ha medido. Para otro motor, declare el suyo una sola vez, junto a su `DbContext`.

Los campos del esquema deben usar un `physical.sql.column` simple. Se rechaza un campo con `qualifiedColumn` o `expression`, porque ninguno tiene forma en un árbol de expresión.

Si un mismo tipo de `DbContext` puede construirse a partir de más de un esquema, registre `GridSchemaModelCacheKeyFactory` e implemente `IGridSchemaModel` en el contexto. Sin eso, EF reutiliza el modelo del primer esquema para el siguiente y falla con errores que no mencionan la caché.

### Dos trampas silenciosas {#two-silent-traps}

Ambas producen filas incorrectas sin ningún error. El adaptador no puede ver su modelo ni sus colaciones, así que no puede protegerse contra ellas.

- **Valores de fecha y hora de SQLite.** Guarde un `datetime` como texto `yyyy-MM-ddTHH:mm:ss.fffZ` y asigne cada `DateTime` hacia y desde ese texto en su `DbContext`. La asignación propia de EF usa otra forma, y SQLite compara el texto carácter a carácter.
- **`PatternMatchFoldsCase`.** Indica si el `LIKE` del motor ignora las mayúsculas y minúsculas. Use `true` para SQLite. Para SQL Server y MySQL use `false`, salvo que cada columna de búsqueda tenga una colación que ignore mayúsculas y minúsculas. De lo contrario, una columna con colación binaria solo coincide con la capitalización exacta.

Las celdas de fecha y hora salen de una página o de una exportación como valores UTC, sea cual sea lo que devolvió el proveedor.

## Lo que comparten ambos adaptadores {#what-both-adapters-share}

- **Los recuentos de filas son opcionales.** El recuento es un segundo viaje de ida y vuelta, así que está desactivado salvo que pase `includeRowCount`. Una cuadrícula lo necesita una vez por cada cambio de filtro, no una vez por bloque.
- **Las exportaciones nunca usan desplazamiento.** Leen las filas en bloques de 5,000 recorriendo las claves de ordenación, de modo que un bloque tardío cuesta lo mismo que uno temprano. `DapperExportOptions` y `EfCoreExportOptions` tienen un `ChunkSize` para cambiarlo. La exportación necesita una clave estable realmente única. Un duplicado se detecta y provoca una excepción.
- **Dapper rechaza algunas exportaciones.** `DapperExportStream` rechaza un esquema cuya clave estable sea una columna de texto. También rechaza una exportación en la que una clave de ordenación de texto contenga una cadena vacía en las filas exportadas, en todos los dialectos salvo Oracle. En ambos casos use una clave estable numérica o de fecha, u obtenga los datos página a página con `DapperGridQuery.FetchPageAsync`. `EfCoreExportStream` no tiene esa comprobación.
- **Se rechaza una exportación limitada a una página.** Los flujos de exportación toman el resultado completo. Una página acotada pasa por el método de página.
- **Un resultado neutro.** Cada página tiene un método de extensión `ToGridPageResult()`. El de OpenSearch también toma el `SearchQueryRequest` que usó. `LoadSuccessParamsMapper.Map` de `Craticula.AgGrid` lo convierte en la forma que AG Grid espera.

## Lo que nunca hacen {#what-they-never-do}

- Nunca abren, cierran ni mantienen en un pool una conexión, y nunca inician una transacción.
- Nunca reintentan una consulta fallida ni establecen un tiempo de espera. La conexión y los ajustes del comando son cosa suya.
- Nunca imponen un número máximo de filas exportadas.
- Nunca aplican sus límites de recursos ni las comprobaciones de columnas de su esquema. Ejecute primero `GridFilterPipeline.Process`, como hace la guía de inicio rápido. Consulte [El modelo de seguridad](safety-model.html).

## Cuál elegir {#which-one-to-pick}

| Usted tiene | Use |
|---|---|
| Un `IDbConnection` simple y quiere ver el SQL | Dapper |
| Cualquiera de los cinco dialectos SQL, sin código adicional | Dapper |
| Un `DbContext` con filtros de consulta globales que quiere conservar | Entity Framework Core |

La demo ejecuta ambos en PostgreSQL, de modo que puede compararlos con los mismos datos.

## De dónde procede esta página {#where-this-comes-from}

- [csharp/src/Craticula.Dapper/README.md](../../csharp/src/Craticula.Dapper/README.md)
- [csharp/src/Craticula.EntityFrameworkCore/README.md](../../csharp/src/Craticula.EntityFrameworkCore/README.md)
- [csharp/src/Craticula.Dapper/DapperGridQuery.cs](../../csharp/src/Craticula.Dapper/DapperGridQuery.cs)
- [csharp/src/Craticula.EntityFrameworkCore/EfCoreGridQuery.cs](../../csharp/src/Craticula.EntityFrameworkCore/EfCoreGridQuery.cs)
- [csharp/src/Craticula.EntityFrameworkCore/EfCoreProviderSemantics.cs](../../csharp/src/Craticula.EntityFrameworkCore/EfCoreProviderSemantics.cs)
- [csharp/src/Craticula.EntityFrameworkCore/GridSchemaPropertyBag.cs](../../csharp/src/Craticula.EntityFrameworkCore/GridSchemaPropertyBag.cs)
- [examples/demo/README.md](../../examples/demo/README.md)
- Páginas relacionadas: [Exportación a CSV](csv-export.html), [Adaptadores de MongoDB y OpenSearch](search-adapters.html), [Paginación y ordenación](paging-and-sorting.html)
