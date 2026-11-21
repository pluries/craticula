---
translates: request-to-query
title: Cómo una solicitud se convierte en una consulta
description: El camino desde una solicitud de AG Grid hasta una instrucción con parámetros.
source_fingerprint: 6c0315a52de692dbf39fc149aa86390474630dd3c2eb2282d8985f93da818dc0
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Cómo una solicitud se convierte en una consulta {#how-a-request-becomes-a-query}

Esta página sigue una solicitud de AG Grid a través de Craticula, paso a paso, hasta que se convierte en una consulta con parámetros. Está dirigida a un desarrollador que quiere saber qué ocurre entre la cuadrícula y la base de datos, y por qué hay varios pasos.

## El camino {#the-path}

```text
request JSON -> adapter -> canonical form -> compiler -> query + parameters
```

1. **JSON de la solicitud.** La envía la cuadrícula. Craticula no modifica lo que envía la cuadrícula.
2. **Adaptador.** El adaptador de AG Grid lee el JSON y lo convierte en la forma canónica. Rechaza el JSON que no entiende.
3. **Forma canónica.** El proyecto la llama IR, abreviatura de intermediate representation (representación intermedia). Es una descripción única de los filtros, la ordenación, la agrupación y la paginación, que no depende de AG Grid ni de ninguna base de datos.
4. **Comprobaciones.** Antes de compilar, Craticula comprueba la forma canónica frente a su esquema y a los límites de recursos. También convierte cada valor al tipo que declara el esquema.
5. **Compilador.** Un compilador por backend escribe la consulta. El compilador SQL tiene un escritor por cada dialecto de base de datos.
6. **Consulta y parámetros.** Para SQL, se obtiene el texto de la instrucción más una lista de valores. Los valores nunca forman parte del texto.

Como todos los backends leen la misma forma canónica, una misma solicitud significa lo mismo en todas partes. Las reglas para detalles como el tratamiento de los nulos y la distinción entre mayúsculas y minúsculas se escriben una sola vez, en la especificación, y todos los compiladores las siguen.

## El esquema es la frontera {#the-schema-is-the-boundary}

El esquema es un documento JSON que usted escribe. Nombra la tabla o la colección y las columnas que la cuadrícula puede usar. Cada columna tiene un tipo y un nombre físico en la base de datos. También nombra una clave estable, una columna con valores únicos que Craticula usa para mantener la paginación en un orden fijo.

Una columna que no está en el esquema no puede llegar a una consulta. Consulte [El modelo de seguridad](safety-model.html) para ver cómo funciona.

## Qué puede pedir la solicitud {#what-the-request-can-ask-for}

- **Paginación.** La cuadrícula pide un rango de filas, por ejemplo las primeras 50. Craticula lo convierte en un límite y un desplazamiento, o en el equivalente para su backend. Una página tiene un tamaño máximo.
- **Ordenación.** La ordenación se aplica en el orden en que la envió la cuadrícula. Craticula añade la clave estable al final para que las filas con valores iguales siempre vuelvan en el mismo orden.
- **Filtrado.** Los filtros de texto, de número y de fecha se convierten en comparaciones unidas con AND u OR. La comparación sin distinguir mayúsculas y minúsculas es el comportamiento por defecto para el texto.
- **Agrupación.** Para las cuadrículas agrupadas, la solicitud lleva las columnas de grupo, las claves de grupo ya abiertas y las agregaciones que se deben calcular. Craticula construye la consulta agrupada para el nivel que se solicita.

## Un ejemplo breve {#a-small-example}

Esta es la solicitud del inicio rápido. Pide los clientes que contienen "acme" con un importe superior a 100, primero los importes mayores, filas de la 0 a la 50.

```json
{
  "startRow": 0,
  "endRow": 50,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "customer": { "filterType": "text", "type": "contains", "filter": "acme" },
    "amount": { "filterType": "number", "type": "greaterThan", "filter": 100 }
  },
  "sortModel": [ { "colId": "amount", "sort": "desc" } ]
}
```

Para PostgreSQL, el programa del inicio rápido imprime esta instrucción y estos parámetros:

```sql
SELECT * FROM "orders" WHERE ("customer" ILIKE '%' || $1 || '%' ESCAPE '\' AND "amount" > $2::numeric) ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'acme', '100', 50, 0
```

Observe lo que ocurrió:

- "acme" y 100 no están en el texto. Son los parámetros.
- Los nombres de la tabla y de las columnas proceden del esquema, no de la solicitud.
- La ordenación termina con `id`, la clave estable del esquema.
- El rango de la página se convirtió en `LIMIT 50 OFFSET 0`.

SQL Server recibe una instrucción distinta a partir de la misma solicitud, porque expresa de otra manera la comparación sin distinguir mayúsculas y minúsculas y el orden de los nulos. El [inicio rápido de C#](quickstart-csharp.html) muestra ambas.

## Lo que usted escribe en C# {#what-you-write-in-c}

En el inicio rápido, el código hace cuatro cosas en este orden:

1. Analiza el esquema con `GridSchema.Parse`.
2. Analiza la solicitud con `AgGridRequestParser.Parse`.
3. Valida con `GridFilterPipeline.Process`. Esto aplica la comprobación de columnas, los límites y la conversión de tipos.
4. Compila con `SqlQueryBuilder.Build` y un dialecto como `PostgresDialect.Instance`.

MongoDB y OpenSearch tienen sus propios constructores, `MongoPipelineBuilder` y `SearchQueryBuilder`.

Para mostrar el número total de filas junto a una página, todos los compiladores tienen también `BuildCount`. Usa el mismo filtro, pero sin ordenación ni ventana de filas, porque un recuento no las necesita. Pase un `NonePage` a `GridFilterPipeline.Process` para un recuento, de modo que un tamaño de página grande no pueda hacerlo fallar.

## De dónde procede esto {#where-this-comes-from}

- [site/pages/quickstart-csharp.md](quickstart-csharp.md)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
- [spec/semantics.md](../../spec/semantics.md)
- [spec/ir.schema.json](../../spec/ir.schema.json)
- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs](../../csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs)
- [spec/fixtures/operators](../../spec/fixtures/operators/001-eq-string/description.md)
