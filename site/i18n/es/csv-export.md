---
translates: csv-export
title: Exportación a CSV
description: Transmita las filas de una cuadrícula a CSV con el mismo modelo de solicitud y las mismas comprobaciones.
source_fingerprint: fa1523a098455aba885855279c19504be3084b49be415b2a066c79e11c573ace
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Exportación a CSV {#csv-export}

Esta página explica cómo Craticula exporta las filas que muestra una cuadrícula como archivo CSV o TSV: qué parte corresponde a Craticula, qué parte le corresponde a usted y los ajustes que cambian el archivo. Está dirigida al desarrollador que añade un botón de exportación a una cuadrícula basada en Craticula.

## Dos partes, un flujo entre ellas {#two-parts-one-stream-between-them}

Una exportación se realiza en dos pasos, y dos piezas de Craticula los llevan a cabo.

1. **Leer las filas.** Un adaptador de ejecución ejecuta la consulta y devuelve un flujo de filas. `DapperExportStream`, `EfCoreExportStream`, `MongoExportStream` y `OpenSearchExportStream` hacen esto para sus respectivos backends. Consulte [Entity Framework Core y Dapper](relational-adapters.html) y [Adaptadores de MongoDB y OpenSearch](search-adapters.html).
2. **Escribir el archivo.** El paquete `Craticula.Export.Csv` toma ese flujo y escribe los bytes. No sabe nada de la base de datos. `CsvWriter` es su punto de entrada.

Como el escritor lee una fila cada vez y escribe cada registro sobre la marcha, una exportación de un millón de filas usa aproximadamente la misma memoria que una de diez filas. Los adaptadores relacionales y el de OpenSearch leen las filas por bloques (5,000 de forma predeterminada) y el adaptador de MongoDB lee un único cursor lote a lote, nunca con un desplazamiento creciente, y las llamadas paginadas `FetchPageAsync` rechazan una solicitud de todas las filas para que solo el flujo de exportación pueda leer el resultado completo. Una descarga lenta ralentiza la lectura en lugar de llenar la memoria.

## Qué envía la cuadrícula {#what-the-grid-sends}

Una solicitud de exportación es una solicitud de cuadrícula normal con hasta tres miembros más:

- `exportFormat`, que vale `"csv"` o `"tsv"`. Marca la solicitud como una exportación. Enviar los otros dos miembros sin él se rechaza.
- `exportScope`, que vale `"all"` o `"page"`. El valor predeterminado es `"all"`: todas las filas que coinciden con el filtro y la ordenación, sea cual sea el valor de `startRow` y `endRow`. `"page"` conserva el rango de filas de la solicitud. Una solicitud que no envía ninguna ventana y que no es una exportación recibe en su lugar una página predeterminada de 100 filas; consulte [Paginación y ordenación](paging-and-sorting.html).
- `exportColumns`, una lista opcional de entradas `{ "colId": "...", "header": "..." }`.

El filtro y la ordenación siempre se respetan.

## Qué columnas y qué dicen los encabezados {#which-columns-and-what-the-headers-say}

Si la solicitud no incluye `exportColumns`, la exportación contiene todas las columnas que el esquema marca como `exportable`, en el orden en que el esquema las declara. Una columna es exportable salvo que el esquema indique `"exportable": false`.

Si la solicitud incluye `exportColumns`, la exportación contiene esas columnas, en ese orden. Se rechaza una columna que no está en el esquema, que no es exportable o que aparece dos veces, así como una lista vacía. Esto es así tanto en modo Strict como en modo Lenient.

El encabezado de una columna procede, por orden, de:

1. el `header` de la solicitud;
2. el `label` del esquema;
3. el id de la columna.

El analizador lo resuelve una sola vez y lo guarda en `ExportSpec.Columns`.

## Se descarta la agrupación {#grouping-is-dropped}

Una exportación es una lista plana de filas. El adaptador descarta `rowGroupCols`, `valueCols` y `groupKeys` de una solicitud de exportación, de modo que la exportación de una cuadrícula agrupada devuelve filas simples bajo el filtro y la ordenación actuales.

## Cómo encaja todo {#putting-it-together}

El analizador necesita el esquema para resolver una exportación, así que páselo en `AgGridParseOptions`. Este ejemplo resumido trata `exportScope` con el valor `"all"`. Con `"page"`, `parsed.Page` es un rango de filas y `StreamAsync` lo rechaza. Usa Dapper y PostgreSQL. `connection` es un `IDbConnection` abierto y `destination` es un `Stream`, como el cuerpo de la respuesta HTTP.

```csharp
// using Craticula.AgGrid; using Craticula.Core.Export; using Craticula.Core.Ir;
// using Craticula.Core.Schema; using Craticula.Dapper; using Craticula.Export.Csv; using Craticula.Sql;
AgGridParsedRequest parsed = AgGridRequestParser.Parse(requestJson, new AgGridParseOptions { Schema = schema });
ExportSpec export = parsed.Export!;

FilterNode? filter = GridFilterPipeline.Process(
    parsed.NativeFilter, parsed.CustomFilters, parsed.Page, schema, new ResourceLimits());

IAsyncEnumerable<ExportRow> rows = DapperExportStream.StreamAsync(
    connection,
    new SqlQueryRequest
    {
        Schema = schema,
        Filter = filter,
        Sort = parsed.Sort,
        Page = parsed.Page,
        Projection = export.ProjectionColumns
    },
    PostgresDialect.Instance);

long rowsWritten = await CsvWriter.WriteAsync(
    rows, export.Columns, CsvWriterOptions.ForFormat(export.Format), destination);
```

`CsvWriterOptions.ForFormat` es el modo en que el formato solicitado llega al archivo. Elige una coma para CSV y un tabulador para TSV. El escritor nunca ve la solicitud, por lo que no puede hacerlo por sí mismo. El resultado de la tarea es el número de filas de datos escritas, sin contar la fila de encabezado.

Los flujos de exportación de los adaptadores aceptan únicamente el resultado completo (`exportScope` con el valor `"all"`). Una exportación limitada a una página es un único bloque acotado, la misma consulta que ejecuta un bloque de la cuadrícula. Obténgala con el método de página del adaptador y escriba usted mismo esas filas.

## Cómo es el archivo {#what-the-file-looks-like}

De forma predeterminada:

- primero va una fila de encabezado;
- los campos se separan con una coma y las filas terminan con un retorno de carro y un salto de línea;
- un campo que contiene el delimitador, unas comillas dobles o un salto de línea se encierra entre comillas dobles;
- el archivo empieza con una marca de orden de bytes, porque Excel interpreta mal el texto Unicode que no la lleva;
- un valor nulo es un campo vacío;
- los booleanos son `true` y `false`;
- las fechas se escriben como `2026-01-05`, y los valores de fecha y hora como `2026-01-05T14:30:45`, con el desfase cuando el valor lo tiene;
- un decimal conserva su propio número de dígitos tras la coma decimal.

## Qué puede cambiar {#what-you-can-change}

`CsvWriterOptions` tiene estos ajustes:

| Ajuste | Valor predeterminado | Qué hace |
|---|---|---|
| `Delimiter` | `,` | El separador de campos. |
| `IncludeHeaderRow` | `true` | Si se escribe la fila de encabezado. |
| `WriteByteOrderMark` | `true` | Si el archivo empieza con una marca de orden de bytes. |
| `DecimalSeparator` | `.` | El separador de los números fraccionarios. |
| `HardenFormulaInjection` | `true` | Véase más abajo. |

`CsvWriterOptions.SemicolonPreset` establece el delimitador en un punto y coma, para las configuraciones regionales en las que Excel lo espera.

El esquema puede sustituir el formato de una sola columna con un bloque `format`:

```json
"orderDate": { "type": "date", "format": { "datePattern": "dd/MM/yyyy" } },
"amount": { "type": "decimal", "format": { "decimalSeparator": "," } }
```

El escritor rechaza un separador decimal igual al delimitador. Una coma en ambos lugares convertiría cada número fraccionario en texto entrecomillado. También rechaza un patrón de fecha que no puede aplicar. `GridSchema.Parse` comprueba el patrón al cargar el esquema, de modo que uno incorrecto falla al arrancar y no a mitad de una descarga.

## Protección contra fórmulas de hoja de cálculo {#protection-against-spreadsheet-formulas}

Una hoja de cálculo trata como fórmula una celda que empieza por `=`, `+`, `-`, `@`, un tabulador o un retorno de carro. Un valor escrito por un usuario podría entonces ejecutarse en la hoja de cálculo de quien abra la exportación.

De forma predeterminada, el escritor antepone un apóstrofo a ese texto. Esto cubre todos los encabezados y todas las celdas de texto. No afecta a los números, fechas ni booleanos que el propio escritor ha formateado, de modo que un número negativo sigue siendo un número.

Puede desactivarlo con `HardenFormulaInjection = false`. El apóstrofo no se puede retirar después, así que desactívelo solo cuando un programa lea el archivo y ninguna persona lo abra en una hoja de cálculo.

## Lo que sigue siendo cosa suya {#what-stays-with-you}

- **El tope de filas.** Ni los adaptadores ni el escritor imponen un número máximo de filas exportadas. Añada su propio límite si la exportación es pública.
- **El límite de tamaño de página.** No se aplica a una exportación del resultado completo (`exportScope` con el valor `"all"`), que no tiene página. Una exportación limitada a una página conserva su rango de filas, y a ella sí se aplica el límite de tamaño de página. Consulte [Límites](limits.html).
- **Dapper rechaza algunas exportaciones.** `DapperExportStream` rechaza un esquema cuya clave estable sea una columna de texto, y una exportación en la que una clave de ordenación de texto contenga una cadena vacía en las filas exportadas (en todos los dialectos salvo Oracle). Use una clave estable numérica o de fecha, u obtenga los datos página a página con `DapperGridQuery.FetchPageAsync`. `EfCoreExportStream` no tiene esa comprobación.
- **La descarga.** El tipo de contenido, el nombre del archivo y la conexión son cosa suya. La demo los establece en `examples/demo/Api/Routes/GridRoutes.cs`.
- **La lista de columnas de OpenSearch.** La exportación de OpenSearch escribe siempre todas las columnas del esquema, en el orden de `schema.FieldOrder`. Pase a `CsvWriter` la lista completa, un `ExportColumn` por cada campo de `schema.FieldOrder`. Un `export.Columns` más reducido hace que `CsvWriter` falle con una `CsvWriterException`, porque el número de celdas no coincide.

## De dónde procede esta página {#where-this-comes-from}

- [csharp/src/Craticula.Export.Csv/README.md](../../csharp/src/Craticula.Export.Csv/README.md)
- [csharp/src/Craticula.Export.Csv/CsvWriter.cs](../../csharp/src/Craticula.Export.Csv/CsvWriter.cs)
- [csharp/src/Craticula.Export.Csv/CsvWriterOptions.cs](../../csharp/src/Craticula.Export.Csv/CsvWriterOptions.cs)
- [csharp/src/Craticula.AgGrid/ExportSpec.cs](../../csharp/src/Craticula.AgGrid/ExportSpec.cs)
- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/page-export](../../spec/fixtures/page-export/README.md)
- [examples/demo/Api/Routes/GridRoutes.cs](../../examples/demo/Api/Routes/GridRoutes.cs)
- Páginas relacionadas: [Paginación y ordenación](paging-and-sorting.html), [El GridSchema](the-gridschema.html), [El modelo de seguridad](safety-model.html)
