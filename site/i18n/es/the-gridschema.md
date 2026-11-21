---
translates: the-gridschema
title: El GridSchema
description: El esquema que enumera lo que una cuadrícula puede tocar y cuáles de sus indicadores se aplican hoy.
source_fingerprint: cdf6e47e0fa6a2ef7b974c3b2ac02ea7892b7f9a31ffa33a18595708e80d8a45
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# El GridSchema {#the-gridschema}

Esta página explica el esquema que usted escribe para cada cuadrícula: qué contiene, cuáles de sus ajustes aplica Craticula hoy y cómo empezar uno. Está dirigida al desarrollador que está a punto de describir a Craticula una tabla, una colección o un índice. Para la lista completa de miembros, consulte la [referencia de GridSchema](grid-schema.html).

## Para qué sirve el esquema {#what-the-schema-is-for}

El esquema es la frontera entre la solicitud y sus datos. Es un documento JSON que usted escribe y conserva en el servidor. Nombra la tabla, la colección o el índice. Enumera todas las columnas que la cuadrícula puede tocar. Para cada columna indica un tipo y el nombre físico en su base de datos.

Una columna que no está en el esquema nunca puede llegar a una consulta. Los nombres de tabla y de columna de una consulta proceden del esquema, nunca de la solicitud. Consulte [El modelo de seguridad](safety-model.html).

Ninguna solicitud puede llevar un esquema. La cuadrícula envía las columnas por su id de cuadrícula, y Craticula busca cada una.

## Un ejemplo pequeño {#a-small-example}

Este es el esquema de la guía de inicio rápido. Describe una tabla `orders`.

```json
{
  "mode": "strict",
  "source": "orders",
  "stableKey": "id",
  "fields": {
    "id":       { "type": "int64",    "sortable": true, "physical": { "sql": { "column": "id" } } },
    "customer": { "type": "string",   "filterable": true, "sortable": true, "physical": { "sql": { "column": "customer" } } },
    "amount":   { "type": "decimal",  "filterable": true, "sortable": true, "physical": { "sql": { "column": "amount" } } },
    "status":   { "type": "string",   "filterable": true, "sortable": true, "physical": { "sql": { "column": "status" } } }
  }
}
```

En C#, cárguelo con `GridSchema.Parse(json)`.

## Los miembros del esquema completo {#the-members-of-the-whole-schema}

| Miembro | Qué hace |
|---|---|
| `mode` | `strict` o `lenient`. El JSON Schema lo exige; el analizador de C# usa strict de forma predeterminada cuando falta. Consulte [Strict y Lenient](strict-and-lenient.html). |
| `source` | La tabla o vista, la colección de MongoDB o el índice de OpenSearch. No puede estar en blanco. |
| `stableKey` | Una columna con valores únicos. Debe ser uno de los `fields`. |
| `fields` | La lista de permitidos, indexada por el id de columna de la cuadrícula. Necesita al menos un campo. |
| `staticFilter` | Un filtro que se añade a toda consulta. Opcional. |

`GridSchema.Parse` rechaza un esquema que incumpla estas reglas. También rechaza miembros desconocidos, claves duplicadas y un `physical.sql` que no establezca exactamente uno de `column`, `qualifiedColumn` y `expression`.

## Los miembros de un campo {#the-members-of-one-field}

| Miembro | Qué hace |
|---|---|
| `type` | `string`, `int64`, `decimal`, `double`, `boolean`, `date` o `datetime`. Craticula convierte cada valor de la solicitud a este tipo. |
| `physical` | Dónde reside la columna: `sql`, `mongo`, `search` o las tres. |
| `text` | Para un `string`: `caseSensitivity` (`insensitive` de forma predeterminada) y `searchMode`. |
| `filterable`, `sortable`, `groupable`, `aggregatable` | Lo que la cuadrícula puede hacer con la columna. Véase más abajo. |
| `exportable`, `label`, `format` | Cómo aparece la columna en una exportación a CSV. Consulte [Exportación a CSV](csv-export.html). |

Solo necesita los mapeos de los backends que use. Un mapeo SQL es una columna simple. Un mapeo de MongoDB es una ruta de documento. Un mapeo de búsqueda nombra el campo del índice y también puede nombrar un `keywordSubField` y un `normalizedSubField`. Un campo sin ningún mapeo usa su id de columna como nombre.

## Qué hace hoy cada indicador {#what-each-flag-does-today}

No dé por sentado que se aplican todos los indicadores. Esto es lo que hace el código hoy:

| Indicador | Valor predeterminado | ¿Se aplica? |
|---|---|---|
| `filterable` | `true` | Sí. Un filtro sobre una columna marcada como `false` se rechaza en modo Strict y se descarta en modo Lenient. La columna de la lista de valores de un filtro de conjunto, y una clave de grupo que el usuario ha abierto, deben ser filtrables y se rechazan en ambos modos. |
| `groupable` | `false` | Sí. Una columna de grupo debe ser agrupable. Se rechaza en ambos modos. |
| `aggregatable` | ninguno | Sí. Una agregación debe usar una función de esta lista. Se rechaza en ambos modos. |
| `exportable` | `true` | Sí. Determina las columnas de exportación predeterminadas, y una columna marcada como `false` no puede nombrarse en `exportColumns`. |
| `sortable` | `true` | **No.** Hoy nada lo lee. Una columna del esquema puede ordenarse sea cual sea el valor del indicador. |

La lista `aggregatable` contiene cualquiera de `sum`, `min`, `max`, `avg` y `count`. Consulte [Agrupación y agregación](grouping-and-aggregation.html).

Si necesita impedir que una columna se ordene, déjela fuera del esquema o apóyese en una comprobación propia. El indicador no lo hará.

## La clave estable {#the-stable-key}

La `stableKey` es lo que mantiene el orden de la paginación. Craticula la añade al final de toda ordenación. Debe nombrar una columna cuyos valores sean únicos. Declare la columna `NOT NULL` en su base de datos, porque la mayoría de las bases de datos permiten muchos nulos en una columna única y eso rompe la garantía. Consulte [Paginación y ordenación](paging-and-sorting.html).

## El filtro estático {#the-static-filter}

`staticFilter` es una condición que Craticula añade a toda consulta con AND. Es el lugar para un id de inquilino o un indicador de borrado lógico. La solicitud no puede cambiarlo ni eliminarlo.

```json
"staticFilter": {
  "type": "comparison",
  "op": "eq",
  "field": "tenantId",
  "value": { "type": "int64", "value": 42 }
}
```

El campo que nombra un `staticFilter` debe declararse también en `fields`, para que el compilador pueda encontrar su columna. La condición forma parte del esquema, de modo que la solicitud no puede alcanzarla. Decidir cuál debe ser el filtro es cosa suya. Craticula solo lo aplica. Consulte [El modelo de seguridad](safety-model.html).

## El orden de los campos {#field-order}

El orden de los campos en el documento cuenta. Una solicitud de exportación sin lista de columnas recibe los campos exportables en ese orden. Las filas dentro de un grupo abierto también se devuelven en ese orden.

## De dónde procede esta página {#where-this-comes-from}

- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridSchema.cs](../../csharp/src/Craticula.Core/Schema/GridSchema.cs)
- [csharp/src/Craticula.Core/Schema/FieldConfig.cs](../../csharp/src/Craticula.Core/Schema/FieldConfig.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
- [spec/fixtures/schemas](../../spec/fixtures/schemas)
- Páginas relacionadas: [Límites](limits.html), [Dialectos y proveedores](dialects-and-providers.html), [Cómo una solicitud se convierte en una consulta](request-to-query.html)
