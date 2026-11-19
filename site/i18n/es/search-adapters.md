---
translates: search-adapters
title: Adaptadores de MongoDB y OpenSearch
description: Ejecute consultas compiladas de MongoDB y OpenSearch con los adaptadores opcionales, incluida la paginación profunda.
source_fingerprint: 48d257e31e0add276e9f93959d7b0b4c8302bb0209dc059498cdbe72961005ce
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Adaptadores de MongoDB y OpenSearch {#mongodb-and-opensearch-adapters}

Esta página trata de los dos paquetes opcionales que ejecutan consultas de Craticula en un almacén de documentos: `Craticula.MongoDB.Driver` para MongoDB y `Craticula.OpenSearch.Client` para OpenSearch y Elasticsearch. Está dirigida al desarrollador que usa uno de esos almacenes y quiere que Craticula ejecute la consulta además de escribirla.

## Qué ofrece el núcleo y qué añaden los adaptadores {#what-the-core-gives-you-and-what-the-adapters-add}

Los compiladores escriben la consulta y se detienen ahí.

- `Craticula.Mongo` convierte una solicitud en un pipeline de agregación. `MongoPipelineBuilder.Build` devuelve un `MongoQuery` con el nombre de la colección y las etapas del pipeline.
- `Craticula.Search` convierte una solicitud en un cuerpo de búsqueda. `SearchQueryBuilder.Build` devuelve un `SearchQuery` con el nombre del índice y el cuerpo, que `ToArtifact()` le entrega como JSON.

Ninguno de los dos compiladores depende de una biblioteca cliente, y ninguno abre una conexión. Puede ejecutar usted mismo su salida.

Los adaptadores la ejecutan por usted. Instálelos desde NuGet: `dotnet add package Craticula.MongoDB.Driver` o `dotnet add package Craticula.OpenSearch.Client`. Consulte [la guía de inicio rápido de C#](quickstart-csharp.html).

## MongoDB {#mongodb}

`Craticula.MongoDB.Driver` compila con `Craticula.Mongo` y ejecuta el pipeline mediante el controlador oficial de MongoDB, en el intervalo `[3.13.0, 4.0)`.

```csharp
MongoGridPage result = await MongoGridQuery.FetchPageAsync(
    database,
    new MongoQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    includeRowCount: true);
```

Lo que ofrece:

- `MongoGridQuery.FetchPageAsync` devuelve un `MongoGridPage` con `Columns`, `Rows` y un `RowCount` opcional.
- `MongoGridQuery.CountAsync` ejecuta solo el recuento. El recuento es una agregación aparte que descarta la ordenación y la ventana de página, porque un recuento no necesita ninguna de las dos.
- `MongoExportStream.StreamAsync` transmite todos los documentos coincidentes para una exportación. Lee el cursor del controlador lote a lote, sin ningún desplazamiento que recorrer. Consulte [Exportación a CSV](csv-export.html).
- Un límite de tiempo, si usted lo establece. Con `ResourceLimits.MaxQueryTimeMs`, la agregación compilada lleva `maxTimeMS`, MongoDB cancela una consulta que se ejecuta durante más tiempo y el adaptador lanza `QueryTimeoutException`. El recuento también recibe el límite, y una exportación no. Consulte [Límites](limits.html).
- `FetchPageAsync` rechaza la página sin paginar. Una solicitud de todas las filas pasa por `MongoExportStream`, que nunca mantiene el resultado completo.

Lo que necesita de usted:

- Un `IMongoDatabase` abierto. El adaptador nunca lo abre ni lo cierra.
- Un esquema que asigne cada campo a una ruta de documento, como `"physical": { "mongo": { "path": "address.city" } }`, y un `source` que indique la colección.
- MongoDB 4.2 o posterior. Consulte [Dialectos y proveedores](dialects-and-providers.html).

## OpenSearch y Elasticsearch {#opensearch-and-elasticsearch}

`Craticula.OpenSearch.Client` compila con `Craticula.Search` y ejecuta el cuerpo mediante el cliente de bajo nivel de `OpenSearch.Client`, en el intervalo `[2.2.0, 3.0)`. Envía el JSON compilado tal cual. No construye la solicitud por segunda vez con el cliente tipado.

```csharp
OpenSearchGridPage result = await OpenSearchGridQuery.FetchPageAsync(
    client,
    new SearchQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    gridSessionId,
    cache);
```

Aquí `client` es un `IOpenSearchLowLevelClient`, `gridSessionId` es una cadena que usted elige para la sesión de la cuadrícula y `cache` es un `ISearchCursorCache`.

Lo que ofrece:

- `OpenSearchGridQuery.FetchPageAsync` devuelve un `OpenSearchGridPage` con `Columns`, `Rows`, un `RowCount` que puede ser nulo y un indicador `LastRow`.
- `OpenSearchExportStream.StreamAsync` transmite todos los resultados coincidentes para una exportación. Escribe siempre todas las columnas del esquema, en el orden de `schema.FieldOrder`, porque el compilador de búsqueda no tiene proyección de columnas. Pase a `CsvWriter` un `ExportColumn` por cada campo de `schema.FieldOrder`; una lista más reducida hace que falle por un número de celdas que no coincide.
- Un límite de tiempo, si usted lo establece. Con `ResourceLimits.MaxQueryTimeMs`, cada cuerpo de búsqueda lleva `timeout`. Una búsqueda que se queda sin tiempo responde igualmente con los resultados que encontró y `timed_out: true`; el adaptador lo convierte en una `QueryTimeoutException` y nunca devuelve los resultados parciales como página, ni en una página de la cuadrícula ni en un bloque de exportación. Las solicitudes propias de una exportación no llevan `timeout`. `FetchPageAsync` rechaza la página sin paginar; use `OpenSearchExportStream`.

Lo que necesita de usted:

- Un cliente abierto. El adaptador nunca lo construye ni lo cierra.
- Un mapeo de índice que coincida con su esquema. Las consultas compiladas nombran los subcampos que su esquema declara, como un campo `keyword`. Si falta uno, un filtro puede no coincidir con ninguna fila sin que se produzca un error. Consulte [Guía de índices y bases de datos](index-guidance.html).
- Una caché de cursores que viva tanto como la sesión de la cuadrícula. Véase más abajo.

### La caché de cursores {#the-cursor-cache}

OpenSearch rechaza la paginación simple más allá de 10,000 filas. El adaptador cambia a un punto en el tiempo y a `search_after`, y recuerda dónde terminó el último bloque. Esa memoria es el `ISearchCursorCache` que usted le pasa.

`InMemorySearchCursorCache` es la que se incluye. Créela una vez para el proceso y compártala. Una caché nueva por cada solicitud hace que cada página profunda empiece de nuevo desde la fila cero. `InMemorySearchCursorCache` guarda sus entradas en un único proceso. Si las solicitudes de una misma sesión de cuadrícula pueden llegar a varios servidores, una página profunda en otro servidor no tiene cursor y vuelve a recorrer desde la fila cero. Una caché compartida por todos los servidores evitaría esto, pero no se incluye ninguna.

El mismo cursor sirve para los niveles agrupados. Un nivel agrupado usa una agregación compuesta, que no puede empezar en una fila distinta de cero. El adaptador guarda la clave del último grupo y la envía de vuelta para pedir el siguiente bloque.

### Opciones {#options}

`OpenSearchDeepPagingOptions` cambia la paginación:

| Ajuste | Valor predeterminado | Qué hace |
|---|---|---|
| `MaxResultWindow` | 10,000 | El número de filas a partir del cual el adaptador cambia al cursor. |
| `WalkBatchSize` | 1,000 | Cuántas filas avanza un paso de puesta al día. |
| `PitKeepAlive` | 5 minutos | Cuánto tiempo sigue siendo válido un cursor inactivo. |
| `ExactRowCount` | `false` | Pide al motor el recuento exacto cuando usted solicita un recuento de filas. |
| `Flavour` | `OpenSearch` | El motor, `OpenSearch` o `Elasticsearch`. |

Sin `ExactRowCount`, un recuento por encima de la ventana se notifica como desconocido, lo cual es barato. Con él, el motor cuenta todas las coincidencias en cada primera solicitud.

### Elasticsearch {#elasticsearch}

La solicitud compilada es la misma para ambos motores. Solo difieren las llamadas que abren y cierran un punto en el tiempo. Establezca la variante del motor en ambos registros de opciones cuando el clúster sea Elasticsearch:

```csharp
var paging = new OpenSearchDeepPagingOptions { Flavour = SearchEngineFlavour.Elasticsearch };
var export = new OpenSearchExportOptions { Flavour = SearchEngineFlavour.Elasticsearch };
```

Con la variante predeterminada frente a Elasticsearch, una ventana de más de 10,000 filas y toda exportación fallan con HTTP 400.

## Lo que nunca hacen {#what-they-never-do}

- Nunca abren, cierran ni configuran una conexión o un cliente.
- Nunca reintentan una solicitud fallida ni establecen un tiempo de espera.
- Nunca imponen un número máximo de filas exportadas.
- Nunca aplican sus límites de recursos ni las comprobaciones de columnas de su esquema. Ejecute primero `GridFilterPipeline.Process`. Consulte [El modelo de seguridad](safety-model.html).
- Nunca exportan un resultado agrupado. Una exportación es una lista plana de filas, y los flujos de exportación rechazan una solicitud que lleve un grupo.

## De dónde procede esta página {#where-this-comes-from}

- [csharp/src/Craticula.MongoDB.Driver/README.md](../../csharp/src/Craticula.MongoDB.Driver/README.md)
- [csharp/src/Craticula.OpenSearch.Client/README.md](../../csharp/src/Craticula.OpenSearch.Client/README.md)
- [csharp/src/Craticula.MongoDB.Driver/MongoGridQuery.cs](../../csharp/src/Craticula.MongoDB.Driver/MongoGridQuery.cs)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchDeepPagingOptions.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchDeepPagingOptions.cs)
- [csharp/src/Craticula.Mongo/README.md](../../csharp/src/Craticula.Mongo/README.md)
- [csharp/src/Craticula.Search/README.md](../../csharp/src/Craticula.Search/README.md)
- Páginas relacionadas: [Entity Framework Core y Dapper](relational-adapters.html), [Paginación y ordenación](paging-and-sorting.html), [Agrupación y agregación](grouping-and-aggregation.html)
