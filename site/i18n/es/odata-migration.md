---
translates: odata-migration
title: Migrar desde OData
description: Pase una cuadrícula de OData a consultas compiladas y vea qué cambia.
source_fingerprint: fd82735ea37c07ef6fc24c75d469d2a95817109d4cb1345e8240e4df38b66ee0
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Migrar desde OData {#migrating-from-odata}

Esta página es para un equipo cuya cuadrícula se comunica hoy con un servicio OData y que quiere pasar a Craticula. Muestra, construcción por
construcción, lo que usted escribía en OData y la solicitud que Craticula recibe en su lugar. Cada ejemplo es un archivo que una prueba compila, de modo que la
solicitud y la sentencia que figura debajo son reales y no pueden quedar obsoletas.

Hay dos diferencias desde el principio:

- **Craticula recibe la solicitud que AG Grid ya envía.** No hay que construir ninguna cadena de consulta en la URL. El Server-Side Row Model de la cuadrícula
  envía un cuerpo JSON (`filterModel`, `sortModel`, `startRow`, `endRow`, `rowGroupCols`, `valueCols`, `groupKeys`), y Craticula
  lo compila. El lado «OData» de lo que sigue es lo que recibía su servicio; el lado «Craticula» es lo que envía la cuadrícula.
- **Craticula compila; no atiende solicitudes.** Devuelve una sentencia y sus parámetros. Usted la ejecuta con su propio controlador y
  escribe el endpoint (consulte el [inicio rápido de C#](quickstart-csharp.html)).

Todos los ejemplos usan un pequeño esquema sintético, `orders` (id, customer, amount, active, status, region, country), e imprimen la
sentencia de PostgreSQL. Las demás bases de datos tienen su propia escritura de la misma solicitud.

````json
{
  "mode": "strict",
  "source": "orders",
  "stableKey": "id",
  "fields": {
    "id": {
      "type": "int64",
      "sortable": true,
      "physical": {
        "sql": {
          "column": "id"
        }
      },
      "aggregatable": [
        "count"
      ]
    },
    "customer": {
      "type": "string",
      "filterable": true,
      "sortable": true,
      "physical": {
        "sql": {
          "column": "customer"
        }
      }
    },
    "amount": {
      "type": "decimal",
      "filterable": true,
      "sortable": true,
      "aggregatable": [
        "sum",
        "avg",
        "min",
        "max",
        "count"
      ],
      "physical": {
        "sql": {
          "column": "amount"
        }
      }
    },
    "active": {
      "type": "boolean",
      "filterable": true,
      "sortable": true,
      "physical": {
        "sql": {
          "column": "active"
        }
      }
    },
    "status": {
      "type": "string",
      "filterable": true,
      "sortable": true,
      "physical": {
        "sql": {
          "column": "status"
        }
      }
    },
    "region": {
      "type": "string",
      "filterable": true,
      "sortable": true,
      "physical": {
        "sql": {
          "column": "region"
        }
      },
      "groupable": true
    },
    "country": {
      "type": "string",
      "filterable": true,
      "sortable": true,
      "groupable": true,
      "physical": {
        "sql": {
          "column": "country"
        }
      }
    }
  }
}
````

## `$filter` {#filter}

### Una comparación sobre una columna {#a-comparison-on-one-column}

OData: `$filter=status eq 'active'`. Lo mismo vale para `ne`, `gt`, `ge`, `lt`, `le`: se convierten en los tipos de filtro `equals`,
`notEqual`, `greaterThan`, `greaterThanOrEqual`, `lessThan`, `lessThanOrEqual`.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "status": {
      "filterType": "text",
      "type": "equals",
      "filter": "active"
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE "status" COLLATE craticula_ci = $1 ORDER BY "id" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: 'active', 100, 0
````

La comparación es `COLLATE craticula_ci`: **el texto se compara sin distinguir mayúsculas de minúsculas de forma predeterminada** ([Case sensitivity](semantics.html#sem-1)). En OData
el resultado suele depender del servicio y de su base de datos. Si sus usuarios dependían de la capitalización exacta, declare el campo
`caseSensitivity: "sensitive"` en el esquema.

### `contains`, `startswith`, `endswith` y `and` entre columnas {#contains-startswith-endswith-and-and-across-columns}

OData: `$filter=contains(customer,'acme') and amount gt 100`. Las funciones de texto son los tipos de filtro `contains`, `startsWith`
y `endsWith`; `notContains` es la única negación que tiene el filtro de texto de la cuadrícula. Los filtros sobre columnas distintas se unen con AND,
con una entrada de `filterModel` por columna.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "customer": {
      "filterType": "text",
      "type": "contains",
      "filter": "acme"
    },
    "amount": {
      "filterType": "number",
      "type": "greaterThan",
      "filter": 100
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE ("customer" ILIKE '%' || $1 || '%' ESCAPE '\' AND "amount" > $2::numeric) ORDER BY "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'acme', '100', 100, 0
````

La coincidencia `contains` lleva escape: los `%` y `_` del usuario son caracteres literales, nunca comodines ([Substring matching on OpenSearch](semantics.html#sem-7)).

### `or` sobre una columna {#or-on-one-column}

OData: `$filter=amount gt 100 or amount lt 10`. Dos condiciones sobre la misma columna van en la matriz `conditions` de la columna con
`operator: "OR"` (o `"AND"`).

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "amount": {
      "filterType": "number",
      "operator": "OR",
      "conditions": [
        {
          "filterType": "number",
          "type": "greaterThan",
          "filter": 100
        },
        {
          "filterType": "number",
          "type": "lessThan",
          "filter": 10
        }
      ]
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE ("amount" > $1::numeric OR "amount" < $2::numeric) ORDER BY "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: '100', '10', 100, 0
````

### `in` {#in}

OData (4.01): `$filter=status in ('active','pending')`. Este es el filtro de conjunto de la cuadrícula.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "status": {
      "filterType": "set",
      "values": [
        "active",
        "pending"
      ]
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE "status" COLLATE craticula_ci = ANY($1) ORDER BY "id" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: ['active', 'pending'], 100, 0
````

### `ne` y `not` {#ne-and-not}

OData: `$filter=status ne 'blocked'` o `$filter=not (status eq 'blocked')`. En la cuadrícula este es el tipo de filtro `notEqual`.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "status": {
      "filterType": "text",
      "type": "notEqual",
      "filter": "blocked"
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE ("status" COLLATE craticula_ci <> $1 OR "status" IS NULL) ORDER BY "id" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: 'blocked', 100, 0
````

Lea la sentencia con atención. `status ne 'blocked'` también devuelve las filas donde `status` es `NULL`. Los operadores negativos de Craticula
incluyen las filas nulas a propósito ([Null handling](semantics.html#sem-2)), de modo que la cuadrícula se comporta como el filtro en memoria del propio AG Grid. La
lógica trivaluada de SQL descartaría esas filas, y un servicio OData puede hacerlo o no. Compruebe el comportamiento anterior con una prueba antes de
migrar un filtro que excluye valores.

### `eq null` y `ne null` {#eq-null-and-ne-null}

OData: `$filter=region eq null`. Hay dos formas, y difieren en las columnas de texto.

- El tipo de filtro `blank` de la cuadrícula: nulo **o la cadena vacía** en una columna de texto, solo `NULL` en una columna numérica o de fecha.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "region": {
      "filterType": "text",
      "type": "blank"
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE ("region" IS NULL OR "region" = '') ORDER BY "id" ASC NULLS LAST LIMIT $1 OFFSET $2
-- parameters: 100, 0
````

- Un `eq` con un valor nulo, escrito en la extensión `customFilters`: exactamente `NULL` y nada más
  ([Grouping and drill-down](semantics.html#grp-7)). Este es el `eq null` de OData.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {},
  "sortModel": [],
  "customFilters": {
    "type": "comparison",
    "field": "region",
    "op": "eq",
    "value": {
      "type": "null"
    }
  }
}
````

````sql
SELECT * FROM "orders" WHERE "region" IS NULL ORDER BY "id" ASC NULLS LAST LIMIT $1 OFFSET $2
-- parameters: 100, 0
````

`ne null` no tiene una forma exacta en una columna de texto. `notBlank` devuelve las filas que no son ni nulas ni vacías. No escriba
`neq` con un valor nulo (devuelve solo las filas nulas, por la combinación de la lógica trivaluada de SQL y SEM-2) ni `not` alrededor de la prueba
de nulo (devuelve todas las filas).

### Rangos y booleanos {#ranges-and-booleans}

`$filter=amount ge 10 and amount le 20` son dos condiciones sobre una columna unidas por AND.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "amount": {
      "filterType": "number",
      "operator": "AND",
      "conditions": [
        {
          "filterType": "number",
          "type": "greaterThanOrEqual",
          "filter": 10
        },
        {
          "filterType": "number",
          "type": "lessThanOrEqual",
          "filter": 20
        }
      ]
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE ("amount" >= $1::numeric AND "amount" <= $2::numeric) ORDER BY "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: '10', '20', 100, 0
````

La opción de rango propia de la cuadrícula (in-range) se rechaza porque sus dos límites no indican si son inclusivos; la extensión `customFilters` tiene un operador `inRange`
con la inclusividad escrita de forma explícita. Una propiedad booleana, `$filter=active eq true`, es el filtro de conjunto sobre una columna booleana, que
se compila al operador `true`.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "active": {
      "filterType": "set",
      "values": [
        "true"
      ]
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE "active" = $1 ORDER BY "id" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: true, 100, 0
````

### Fechas y fechas con hora {#dates-and-date-times}

Un filtro de fecha recibe la forma de transporte de la cuadrícula: `yyyy-MM-dd`, o `yyyy-MM-dd HH:mm:ss` como hora local leída en la zona que lleva la solicitud
(`requestContext.zone`) o que nombran las opciones del analizador, UTC de forma predeterminada ([Dates and time zones](semantics.html#sem-4)). Un literal de OData como
`2026-01-01T00:00:00Z`, o uno con desfase, no encaja en esa forma. Conviértalo a la zona de la solicitud, o envíe el instante exacto
mediante `customFilters` como un valor `datetime` tipado que nombre su zona.

### Cualquier otra cosa: un árbol de `and`, `or`, `not` {#anything-else-a-tree-of-and-or-not}

Los filtros de AG Grid cubren una columna a la vez. Para un anidamiento como `not startswith(customer,'test') and (status eq 'active' or
amount gt 1000)`, Craticula acepta una extensión junto a `filterModel`: `customFilters`, un árbol de nodos `and`, `or`, `not` y
de comparación sobre el conjunto cerrado de 17 operadores: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `contains`, `notContains`,
`startsWith`, `endsWith`, `in`, `notIn`, `inRange`, `blank`, `notBlank`, `true`, `false`. Es también donde viven un `startsWith` o
`endsWith` negados, porque la cuadrícula no tiene ese tipo de filtro. El árbol se combina con `filterModel` mediante AND. Su profundidad y su tamaño están
limitados (los límites de recursos de SEC-3), de modo que un `$filter` enorme se rechaza en lugar de compilarse.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {},
  "sortModel": [],
  "customFilters": {
    "type": "and",
    "nodes": [
      {
        "type": "not",
        "node": {
          "type": "comparison",
          "field": "customer",
          "op": "startsWith",
          "value": {
            "type": "string",
            "value": "test"
          }
        }
      },
      {
        "type": "or",
        "nodes": [
          {
            "type": "comparison",
            "field": "status",
            "op": "eq",
            "value": {
              "type": "string",
              "value": "active"
            }
          },
          {
            "type": "comparison",
            "field": "amount",
            "op": "gt",
            "value": {
              "type": "decimal",
              "value": "1000"
            }
          }
        ]
      }
    ]
  }
}
````


````sql
SELECT * FROM "orders" WHERE ((NOT ("customer" ILIKE $1 || '%' ESCAPE '\') OR "customer" IS NULL) AND ("status" COLLATE craticula_ci = $2 OR "amount" > $3::numeric)) ORDER BY "id" ASC NULLS LAST LIMIT $4 OFFSET $5
-- parameters: 'test', 'active', '1000', 100, 0
````


## `$orderby`, `$top`, `$skip`, `$count` {#orderby-top-skip-count}

OData: `$orderby=amount desc,id&$top=20&$skip=40`. `$orderby` es `sortModel`, con la primera entrada primero. `$skip` es `startRow` y
`$skip + $top` es `endRow` (exclusivo), de modo que `$skip=40&$top=20` es `startRow: 40`, `endRow: 60`.

````json
{
  "startRow": 40,
  "endRow": 60,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {},
  "sortModel": [
    {
      "colId": "amount",
      "sort": "desc"
    },
    {
      "colId": "id",
      "sort": "asc"
    }
  ]
}
````


````sql
SELECT * FROM "orders" ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST LIMIT $1 OFFSET $2
-- parameters: 20, 40
````


Dos diferencias:

- **Posición de los nulos.** El estándar de OData ordena el nulo como el valor más bajo: primero en sentido ascendente, último en sentido descendente. La cuadrícula
  no envía ninguna posición de nulos, así que Craticula usa la regla fija opuesta: **al final en sentido ascendente, al principio en sentido descendente**
  ([Null ordering](semantics.html#sem-3)), que se muestra arriba como `amount DESC NULLS FIRST`. Toda ordenación ascendente sobre una columna que contiene nulos
  devuelve esas filas en otro lugar después de la migración.
- **Un orden estable.** Un servicio tiene que mantener estables `$skip`/`$top` entre solicitudes. Craticula lo garantiza sea cual sea el criterio de ordenación de la cuadrícula:
  siempre termina la ordenación con la **clave estable** del esquema ([Deterministic paging](semantics.html#sem-6)), de modo que dos filas nunca se intercambian entre
  páginas.

`$count=true` (el `@odata.count` de la respuesta) es el recuento de filas que devuelven los adaptadores de ejecución junto a la página cuando lo solicita
(`includeRowCount`: `RowCount`, y el `lastRow` de AG Grid). En SQL y MongoDB es una segunda consulta. En OpenSearch y Elasticsearch está
limitado de forma predeterminada y se informa como desconocido por encima de 10,000 filas (consulte la [guía de índices](index-guidance.html)).

## `$apply`: `groupby` y `aggregate` {#apply-groupby-and-aggregate}

OData: `$apply=groupby((country),aggregate(amount with sum as total))`. La agrupación de filas de la cuadrícula envía `rowGroupCols` (las columnas de
grupo, de la más externa a la más interna), `valueCols` (los agregados: `sum`, `min`, `max`, `avg`, `count`) y `groupKeys` (los grupos que el usuario ha
abierto).

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [
    {
      "id": "country",
      "displayName": "Country",
      "field": "country"
    }
  ],
  "valueCols": [
    {
      "id": "amount",
      "displayName": "Amount",
      "field": "amount",
      "aggFunc": "sum"
    }
  ],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {},
  "sortModel": [
    {
      "colId": "country",
      "sort": "asc"
    }
  ]
}
````


````sql
SELECT "country" AS "country", COALESCE(SUM("amount"), 0) AS "amount_sum" FROM "orders" GROUP BY "country" ORDER BY "country" ASC NULLS LAST LIMIT $1 OFFSET $2
-- parameters: 100, 0
````


Una solicitud devuelve **un nivel**. Con `groupby((country,region))` la cuadrícula pide primero los países. Cuando el usuario abre Germany,
envía la clave de grupo `Germany` y recibe las regiones de Germany:

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [
    {
      "id": "country",
      "displayName": "Country",
      "field": "country"
    },
    {
      "id": "region",
      "displayName": "Region",
      "field": "region"
    }
  ],
  "valueCols": [
    {
      "id": "amount",
      "displayName": "Amount",
      "field": "amount",
      "aggFunc": "sum"
    }
  ],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [
    {
      "type": "string",
      "value": "Germany"
    }
  ],
  "filterModel": {},
  "sortModel": [
    {
      "colId": "region",
      "sort": "asc"
    }
  ]
}
````


````sql
SELECT "region" AS "region", COALESCE(SUM("amount"), 0) AS "amount_sum" FROM "orders" WHERE "country" = $1 GROUP BY "region" ORDER BY "region" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: 'Germany', 100, 0
````


Un nivel más allá, con ambas claves consumidas, recibe las filas:

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [
    {
      "id": "country",
      "displayName": "Country",
      "field": "country"
    },
    {
      "id": "region",
      "displayName": "Region",
      "field": "region"
    }
  ],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [
    {
      "type": "string",
      "value": "Germany"
    },
    {
      "type": "string",
      "value": "Bavaria"
    }
  ],
  "filterModel": {},
  "sortModel": [
    {
      "colId": "id",
      "sort": "asc"
    }
  ]
}
````


````sql
SELECT "id", "customer", "amount", "active", "status", "region", "country" FROM "orders" WHERE ("country" = $1 AND "region" = $2) ORDER BY "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'Germany', 'Bavaria', 100, 0
````


La solicitud propia de AG Grid lleva las claves como cadenas simples (`groupKeys: ["Germany"]`). El analizador que incluye Craticula toma cada clave como un
valor tipado (`{"type": "string", "value": "Germany"}`), de modo que un pequeño paso en el adaptador de su frontend tipa las claves a partir de los tipos de
columna antes de analizar la solicitud. El `toWireRequest` de la demo ([`datasource.ts`](../../examples/demo/web/src/datasource.ts)) son diez líneas que lo hacen, incluida una clave nula.

Diferencias que conviene conocer:

- `count` cuenta los valores no nulos de una columna, no las filas ([AGG-1](semantics.html#agg-1)), y la columna debe incluir `count` en su ajuste
  `aggregatable`. Para contar filas, cuente la clave estable.
- La suma de un grupo sin valores es `0`, y `avg`, `min`, `max` son `NULL` ([AGG-6](semantics.html#agg-6)).
- El grupo cuya clave es nula es un grupo propio, y se abre con una clave de grupo nula ([Grouping and drill-down](semantics.html#grp-7)).
- El agregado vuelve con el nombre `<field>_<function>` (`amount_sum`), salvo que el identificador de columna de la cuadrícula indique otra cosa.
- Ordenar los grupos por un agregado no está disponible en los motores de búsqueda (una agregación compuesta enumera los grupos solo en el orden de la clave).

## Lo que no tiene equivalente {#what-has-no-equivalent}

| OData | Por qué no, y qué hacer |
|---|---|
| `$expand`, propiedades de navegación, `$filter` a través de una relación | Un esquema lee un solo origen (una tabla, una colección o un índice) y cada columna es un campo de él. Construya una vista o un índice que una los datos y declare la vista como origen. |
| `$select` | Las columnas son las del esquema. Una solicitud no puede pedir un subconjunto de ellas, y los **adaptadores de ejecución** devuelven solo los campos declarados. Con el compilador a secas, una consulta de filas ordinaria es `SELECT *`, de modo que una columna que usted no declara sigue estando en el resultado: déjela fuera de la vista que declara como origen. Una exportación puede nombrar sus columnas. |
| `$search` | No hay búsqueda de texto libre entre campos. Use el filtro de texto sobre una columna, o un índice de un motor de búsqueda con el filtro `contains`. |
| `any` y `all` (operadores lambda) | Necesitan una propiedad de colección, que un origen plano no tiene. Desnormalice, o filtre en una vista. |
| Aritmética (`add`, `sub`, `mul`, `div`, `mod`) y `$compute` | El conjunto de operadores es cerrado para que cada operador tenga un significado probado en todas las bases de datos (AR-6 de los requisitos técnicos). Exponga el valor calculado como una columna del origen. |
| Funciones en `$filter` y `$orderby` (`tolower`, `toupper`, `trim`, `concat`, `substring`, `length`, `indexof`, `year`, `month`, `day`, `round`, `now`) | El mismo motivo. Ignorar la diferencia entre mayúsculas y minúsculas ya es el comportamiento predeterminado del texto, y una parte de una fecha es una columna o un rango sobre la fecha. |
| `$apply=filter(...)` **antes de** `groupby` | Póngalo en `filterModel` o `customFilters`: filtra las filas antes de agruparlas, como hace OData. |
| `$apply` con un filtro **después de** `aggregate` (el `HAVING` de SQL), `topcount`, `concat`, `join`, `compute`, `rollup` | Una solicitud de agrupación tiene un nivel y los cinco agregados, y `filterModel` siempre filtra las filas antes de agregarlas. Filtre los grupos después de la consulta. |
| `countdistinct`, `$count` dentro de `aggregate`, agregados personalizados | El conjunto de agregados es cerrado: `sum`, `min`, `max`, `avg`, `count`. |
| `$batch`, `$format`, `$metadata`, `$value`, acciones y funciones | Tienen que ver con el transporte y el servicio, no con la consulta. Craticula compila una consulta y no tiene capa de servicio. |

## Siguientes pasos {#next}

- Las reglas en las que se apoyan estos ejemplos: la [semántica](semantics.html).
- Cada ajuste del esquema: la [referencia de GridSchema](grid-schema.html).
- Ejecute las mismas solicitudes en una base de datos real: el [inicio rápido de C#](quickstart-csharp.html).
