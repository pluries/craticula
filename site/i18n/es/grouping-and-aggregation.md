---
translates: grouping-and-aggregation
title: Agrupación y agregación
description: Cómo una cuadrícula agrupada pide un nivel cada vez y cómo se comportan las agregaciones.
source_fingerprint: 10e3bdf6eb7dc0f59a4e20738237bb2f9f7ebac06181756626f1c01f952450a5
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Agrupación y agregación {#grouping-and-aggregation}

Esta página trata de la agrupación de filas y la agregación: cómo una cuadrícula agrupada pide un nivel cada vez, cómo responde Craticula a cada nivel y qué tiene que permitir el esquema. Está dirigida a un desarrollador cuya cuadrícula agrupa filas y muestra totales. La agrupación de filas y la agregación son funciones de AG Grid Enterprise.

## Un nivel por solicitud {#one-level-per-request}

Una cuadrícula agrupada no pide el árbol completo. Pide un nivel cada vez, y cada solicitud lleva el camino recorrido hasta ese momento.

Dos listas de la solicitud describen ese camino:

- `rowGroupCols` enumera las columnas por las que agrupa la cuadrícula, en orden.
- `groupKeys` enumera los grupos que el usuario ya ha abierto, una clave por cada nivel.

Craticula compara las longitudes de ambas:

- **Menos claves que columnas.** La solicitud pide un nivel agrupado. Craticula agrupa por la siguiente columna que todavía no tiene clave, y solo por esa. Calcula las agregaciones de cada grupo.
- **Tantas claves como columnas.** Todos los niveles están abiertos. La solicitud pide las filas del interior del último grupo. Craticula devuelve filas simples y no agrupa.
- **Más claves que columnas.** La solicitud está mal formada y se rechaza.

El modo pivote no es compatible. Una solicitud con `pivotMode` establecido en `true`, o con cualquier `pivotCols`, se rechaza.

## Un ejemplo {#an-example}

Tomemos una cuadrícula agrupada por `region`, después `segment`, después `product`, con una suma de `amount`. El usuario ha abierto la región `EMEA`. La cuadrícula pide ahora los segmentos dentro de `EMEA`.

Para PostgreSQL, Craticula escribe:

```sql
SELECT "segment" AS "segment", COALESCE(SUM("amount"), 0) AS "amount_sum" FROM "sales_fact" WHERE "region" = $1 GROUP BY "segment" ORDER BY "segment" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: 'EMEA', 100, 0
```

El grupo abierto se convirtió en `WHERE "region" = $1`. La siguiente columna, `segment`, se convirtió en el `GROUP BY`. El agregado se llama `amount_sum`.

## Las claves de grupo llegan como valores tipados {#group-keys-arrive-as-typed-values}

Craticula lee cada entrada de `groupKeys` como un valor tipado, con el tipo que corresponde al tipo declarado de la columna, y no como la cadena simple que envía AG Grid:

```json
"groupKeys": [ { "type": "string", "value": "EMEA" } ]
```

Su página tiene que convertir las claves antes de enviar la solicitud. La demostración lo hace en `toWireRequest`, en `examples/demo/web/src/datasource.ts`. También cambia el nombre de las columnas agregadas a la vuelta, porque la respuesta las llama `amount_sum` y la cuadrícula lee `amount`. Si copia la demostración, copie ambos pasos.

## Qué funciones puede usar {#which-functions-you-can-use}

Craticula admite cinco funciones de agregación: `sum`, `min`, `max`, `avg` y `count`. Cualquier otra función, como `first`, se rechaza. También se rechaza una entrada de `valueCols` sin `aggFunc`.

El nombre de cada agregado en el resultado es el identificador de la columna cuando difiere del nombre del campo. En caso contrario, es el nombre del campo, un guion bajo y la función, como `amount_sum`.

Algunos detalles que importan para las cifras:

- `count` cuenta las filas en las que el campo no es nulo. No cuenta filas. Para contar todas las filas, cuente la clave estable, que nunca es nula.
- Una `sum` sobre un grupo sin valores es `0` en todos los backends. Los compiladores SQL envuelven `sum` para que coincida.
- `avg`, `min` y `max` sobre un grupo sin valores son nulos.

## Qué debe permitir el esquema {#what-the-schema-must-allow}

El esquema decide qué columnas pueden agruparse y agregarse. Ambos indicadores están desactivados por defecto.

```json
"region": { "type": "string", "groupable": true, "physical": { "sql": { "column": "region" } } },
"amount": { "type": "decimal", "aggregatable": ["sum", "avg"], "physical": { "sql": { "column": "amount" } } }
```

- Una columna de grupo debe estar en el esquema y marcada como `groupable`.
- Una agregación debe nombrar una columna del esquema y una función de la lista `aggregatable` de esa columna.
- Una columna que se ha abierto, de modo que su clave está en `groupKeys`, debe ser también `filterable`. Abrir un grupo equivale a filtrar por un solo valor.

Cada uno de estos casos se rechaza en ambos modos, Strict y Lenient. Descartar una columna de grupo o una clave daría a la cuadrícula una respuesta distinta de la que pidió. Consulte [Strict y Lenient](strict-and-lenient.html).

## Abrir un grupo coincide de forma exacta {#opening-a-group-matches-exactly}

Cuando se abre un grupo, su clave se convierte en una coincidencia exacta sobre la columna de grupo. La agrupación, la apertura de un grupo y la ordenación de los grupos usan comparación exacta, de modo que `EMEA` y `emea` son dos grupos. Un grupo que no coincidiera de forma exacta no sumaría con su padre.

Eso solo es cierto si la base de datos compara de forma exacta por defecto. PostgreSQL y SQLite lo hacen. SQL Server, MySQL y Oracle suelen ignorar la distinción entre mayúsculas y minúsculas, así que declare cada columna por la que agrupa con una intercalación binaria. Consulte [Guía de índices y bases de datos](index-guidance.html).

MongoDB tiene una sola intercalación para toda la consulta. Una solicitud de agrupación no lleva ninguna, así que un filtro de la misma solicitud compara allí distinguiendo mayúsculas y minúsculas. Las bases de datos SQL ignoran la distinción en ese filtro.

## Claves de grupo nulas {#null-group-keys}

Las filas con un valor de grupo nulo forman un solo grupo. Para abrirlo, envíe una clave `{ "type": "null" }`. Craticula escribe una prueba de nulo para ella, como `"region" IS NULL`.

La cadena vacía es un grupo distinto del nulo, de modo que sus filas no se unen al grupo nulo. Oracle es la excepción, porque Oracle almacena una cadena vacía como nulo.

## Ordenar y contar un nivel agrupado {#sorting-and-counting-a-grouped-level}

Un nivel agrupado puede ordenarse por su columna de grupo o por uno de sus agregados. Una ordenación sobre cualquier otra columna se rechaza. La columna de grupo actúa como clave estable, de modo que el orden de los grupos es estable. Un agregado que figura después de la columna de grupo en la ordenación no tiene efecto y se descarta.

El recuento de filas de un nivel agrupado es el número de grupos, no el número de filas que contienen.

OpenSearch y Elasticsearch tienen aquí dos limitaciones:

- No pueden ordenar un nivel agrupado por un agregado. Una solicitud así se rechaza.
- El grupo que contiene valores nulos siempre se ordena primero, sea cual sea la dirección.

## Las exportaciones ignoran la agrupación {#exports-ignore-grouping}

Una exportación devuelve filas simples. El adaptador elimina `rowGroupCols`, `valueCols` y `groupKeys` de una solicitud de exportación. Consulte [Exportación CSV](csv-export.html).

## De dónde procede esto {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/group-aggregation](../../spec/fixtures/group-aggregation/README.md)
- [csharp/src/Craticula.Core/Ir/Aggregation.cs](../../csharp/src/Craticula.Core/Ir/Aggregation.cs)
- [csharp/src/Craticula.Core/Ir/GroupingPlan.cs](../../csharp/src/Craticula.Core/Ir/GroupingPlan.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/src/Craticula.AgGrid/AgGridRequestParser.cs](../../csharp/src/Craticula.AgGrid/AgGridRequestParser.cs)
- [examples/demo/web/src/datasource.ts](../../examples/demo/web/src/datasource.ts)
- Páginas relacionadas: [Paginación y ordenación](paging-and-sorting.html), [El GridSchema](the-gridschema.html), [Cómo una solicitud se convierte en una consulta](request-to-query.html)
