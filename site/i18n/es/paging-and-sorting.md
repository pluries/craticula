---
translates: paging-and-sorting
title: Paginación y ordenación
description: Cómo se acotan y se ordenan las filas, y por qué la paginación es determinista.
source_fingerprint: c01a09b912527d1a95923a5776c7b4abb3290f980e8c9111c4751565b710b445
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Paginación y ordenación {#paging-and-sorting}

Esta página explica cómo el rango de filas y el orden de una solicitud de AG Grid se convierten en paginación y ordenación en la consulta. Está dirigida a un desarrollador que quiere saber por qué las filas llegan en un orden determinado y qué hace cada backend para recorrerlas por páginas.

## De startRow y endRow a una página {#from-startrow-and-endrow-to-a-page}

AG Grid pide un bloque de filas con `startRow` y `endRow`. `endRow` es exclusivo. El tamaño de página es `endRow - startRow`.

Craticula lo convierte en un número de filas y un desplazamiento. El número de filas es el tamaño de página. El desplazamiento es `startRow`. Una solicitud de las filas 50 a 100 pide 50 filas tras omitir 50.

El adaptador rechaza una ventana que no tiene sentido:

- un `startRow` negativo;
- un `endRow` inferior a `startRow`;
- un `endRow` igual a `startRow`, que es una ventana vacía.

Una página también tiene un tamaño máximo. El valor por defecto es 1000 filas. Consulte [Límites](limits.html).

## Una solicitud sin ventana {#a-request-with-no-window}

Algunas solicitudes no envían `startRow` ni `endRow`: un cliente personalizado, o una solicitud construida a mano. Desde la versión 1.2.0, una solicitud así recibe una página por defecto de 100 filas, `[0, 100)`. El tamaño es `AgGridParseOptions.DefaultPageSize`, y el límite de tamaño de página lo comprueba como cualquier otra ventana. Antes de la versión 1.2.0, una solicitud sin ventana significaba todas las filas coincidentes.

Hay dos maneras de pedir todas las filas, y ambas son deliberadas:

- **Una exportación de todo** (`exportScope` establecido en `"all"`). No tiene página y los adaptadores la transmiten por bloques. Consulte [Exportación CSV](csv-export.html).
- **El indicador `ignorePageLimit: true`**, que solo funciona cuando su host ha activado `AgGridParseOptions.AllowUnboundedRows` (desactivado por defecto). Sin ese interruptor, la solicitud se rechaza con el error de análisis `unbounded-not-allowed`; nunca se limita en silencio. Una solicitud que lleva ventana conserva su ventana y el indicador no cambia nada.

Los adaptadores leen una solicitud de todas las filas mediante transmisión. El `FetchPageAsync` paginado de los adaptadores de MongoDB, Dapper, EF Core y OpenSearch rechaza la página sin paginar, de modo que ninguna llamada carga todo el resultado en memoria. Use el flujo de exportación para esas solicitudes. Las reglas están en [Tamaño de página por defecto](default-page-size.html).

## Qué hace cada backend {#what-each-backend-does}

| Backend | Cómo se escribe la página |
|---|---|
| PostgreSQL, MySQL, SQLite | `LIMIT n OFFSET m` |
| SQL Server, Oracle | `OFFSET m ROWS FETCH NEXT n ROWS ONLY` |
| MongoDB | una etapa `$skip` y después una etapa `$limit` |
| OpenSearch y Elasticsearch | `from` y `size` |

Para SQL, los dos números son parámetros, no parte del texto. SQL Server y Oracle enlazan el desplazamiento antes del número de filas. PostgreSQL, MySQL y SQLite enlazan primero el número de filas. No tiene que preocuparse por ello, porque la lista de parámetros sigue el orden en que aparecen los marcadores.

Una exportación de todo no tiene página en absoluto. Pide todas las filas coincidentes y no recibe ninguna cláusula de paginación. Consulte [Exportación CSV](csv-export.html).

## Orden de clasificación {#sort-order}

La cuadrícula envía una lista de claves de ordenación en `sortModel`. Craticula las conserva en ese orden. Cada clave tiene una columna y una dirección, `asc` o `desc`.

Una ordenación sobre una columna que el esquema no enumera se rechaza, tanto en modo Strict como en modo Lenient. El rechazo procede del compilador, que lanza su propia excepción de compilación. Consulte [Strict y Lenient](strict-and-lenient.html).

El esquema tiene un indicador `sortable` para cada columna. Nada lo lee (en esta versión). Una columna que está en el esquema puede ordenarse sea cual sea su indicador. No confíe en el indicador para impedir que una columna se ordene.

## Dónde van los nulos {#where-nulls-go}

AG Grid no dice dónde deben ordenarse los valores nulos. Craticula lo decide, y lo decide de la misma manera para todos los backends:

- una ordenación ascendente coloca los nulos al final;
- una ordenación descendente coloca los nulos al principio.

Las bases de datos discrepan sobre esto por defecto, así que Craticula nunca lo deja en manos de la base de datos. Escribe la posición en cada clave de ordenación.

PostgreSQL, SQLite y Oracle tienen `NULLS FIRST` y `NULLS LAST`, y Craticula los usa. SQLite necesita la versión 3.30.0 o posterior para ello. SQL Server y MySQL no tienen esa sintaxis, así que Craticula añade una prueba inicial que coloca las filas nulas en su propio grupo: `CASE WHEN ... IS NULL` en SQL Server e `ISNULL(...)` en MySQL. MongoDB recibe un campo auxiliar por cada clave de ordenación que se elimina de nuevo después de ordenar. OpenSearch recibe `"missing": "_last"` o `"_first"`.

## El texto se ordena sin distinguir mayúsculas y minúsculas {#text-sorts-without-regard-to-case}

Una columna de texto se compara por defecto sin distinguir mayúsculas y minúsculas. La ordenación sigue la misma regla, de modo que `apple` y `Apple` se ordenan juntas. Una columna puede pedir distinción exacta en el esquema con `text.caseSensitivity` establecido en `sensitive`.

Cada motor llega al mismo resultado a su manera:

- PostgreSQL nombra una intercalación, `craticula_ci`, que usted crea una sola vez.
- SQL Server y SQLite nombran una intercalación en línea dentro de la consulta.
- MySQL usa la intercalación de la propia columna.
- MongoDB establece una intercalación para toda la consulta.
- OpenSearch ordena sobre un subcampo normalizado que usted mapea en el índice.

Lo que debe configurar para cada base de datos está en [Guía de índices y bases de datos](index-guidance.html).

## La clave estable mantiene el orden de la paginación {#the-stable-key-keeps-paging-in-order}

La paginación solo es fiable si el orden es total. Si dos filas empatan en todas las claves de ordenación, la base de datos puede devolverlas en cualquier orden, y una fila puede aparecer en dos páginas o en ninguna.

Para evitarlo, el esquema nombra una `stableKey`, una columna cuyos valores son únicos. Cuando la ordenación no termina ya en esa clave, Craticula la añade al final, ascendente, con los nulos al final.

La solicitud del inicio rápido ordena por `amount` de forma descendente. La instrucción termina así:

```sql
ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST
```

Craticula también ordena la lista de claves antes de añadir nada:

- una columna nombrada dos veces conserva solo su primera aparición;
- si la clave estable ordena de forma exacta, se descartan todas las claves posteriores, porque ya no queda ningún empate que deshacer.

Una clave estable de texto que no distingue mayúsculas y minúsculas es la excepción. Dos claves que solo difieren en las mayúsculas se comparan como iguales, de modo que las claves posteriores se conservan y se añade un desempate exacto.

Esto solo funciona si la clave estable es verdaderamente única. La mayoría de las bases de datos permiten que una columna única contenga muchos nulos, lo que rompe la garantía. Declare la clave como `NOT NULL`. Consulte [Guía de índices y bases de datos](index-guidance.html).

## Paginación profunda {#deep-paging}

Las páginas de cuadrícula en SQL y MongoDB usan un desplazamiento. La base de datos tiene que recorrer todas las filas omitidas, así que una página situada muy adentro de una tabla grande es más lenta que una página cercana al inicio. Indexe sus filtros y mida.

OpenSearch rechaza `from` y `size` simples a partir de 10,000 filas. El adaptador de OpenSearch se ocupa de esto por usted. Pasado ese punto, cambia a un punto en el tiempo y `search_after`, y mantiene un cursor entre solicitudes. De ello se derivan tres consecuencias:

- Debe proporcionarle una caché de cursores que viva tanto como la sesión de la cuadrícula. `InMemorySearchCursorCache` es la que se incluye. Una caché nueva para cada solicitud anula el cursor.
- La primera solicitud que cruza el umbral avanza desde la fila cero. Los bloques siguientes son rápidos.
- El número total de filas por encima de 10,000 se informa como desconocido, salvo que usted pida el recuento exacto, lo cual cuesta un recuento completo en cada primera solicitud.

Consulte [Adaptadores de MongoDB y OpenSearch](search-adapters.html).

## De dónde procede esto {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/sort-paging](../../spec/fixtures/sort-paging/README.md)
- [csharp/src/Craticula.Core/Schema/SemanticsResolver.cs](../../csharp/src/Craticula.Core/Schema/SemanticsResolver.cs)
- [csharp/src/Craticula.Core/Ir/PageSpecValidator.cs](../../csharp/src/Craticula.Core/Ir/PageSpecValidator.cs)
- [csharp/src/Craticula.Sql](../../csharp/src/Craticula.Sql/README.md)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs)
- [site/pages/quickstart-csharp.md](quickstart-csharp.md)
- Páginas relacionadas: [Cómo una solicitud se convierte en una consulta](request-to-query.html), [Agrupación y agregación](grouping-and-aggregation.html), [Dialectos y proveedores](dialects-and-providers.html)
