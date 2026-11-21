---
translates: safety-model
title: El modelo de seguridad
description: Cómo los valores, los identificadores y los límites mantienen segura una consulta compilada, y qué queda a cargo de usted.
source_fingerprint: cad40472e319059d27fe5a7517ac79ed14efb07866e1630c2883f9c7419a959c
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# El modelo de seguridad {#the-safety-model}

Esta página enumera lo que hace Craticula para impedir que una solicitud hostil dañe su base de datos, y lo que no hace. Está dirigida a un desarrollador o revisor que necesita juzgar si Craticula es adecuado para un sistema expuesto al público.

## Los valores son parámetros {#values-are-parameters}

Todo valor de la solicitud entra en la consulta como parámetro. Nunca se pega en el texto.

Para SQL, la instrucción contiene marcadores como `$1` y los valores viajan en una lista aparte. Para la solicitud del inicio rápido, el texto no contiene "acme" ni 100. Consulte [Cómo una solicitud se convierte en una consulta](request-to-query.html).

La especificación aplica la misma idea a MongoDB y OpenSearch. Allí, los valores entran en el pipeline o en el documento de consulta como datos. Un valor de búsqueda de texto que contiene caracteres de patrón se escapa. Los compiladores tienen funciones auxiliares para ello.

Un valor como `'; DROP TABLE users; --` enviado en un filtro de texto ordinario es solo una cadena. Se compara y no hace nada más. Los fixtures adversarios tratan de la forma de la solicitud, no del contenido de las cadenas.

## Los identificadores proceden de su esquema {#identifiers-come-from-your-schema}

Los nombres de tabla, de colección y de columna proceden únicamente del esquema que usted escribió. La solicitud nunca aporta ninguno.

La solicitud nombra las columnas por su identificador de cuadrícula, como `customer`. Craticula busca ese identificador en el esquema y usa el nombre físico que usted declaró. Para SQL, el nombre se entrecomilla según el dialecto, y un carácter de comillas dentro de un nombre se duplica.

## Las columnas desconocidas se rechazan {#unknown-columns-are-refused}

Una columna que no está en el esquema se rechaza antes de que exista ninguna consulta. El inicio rápido muestra el rechazo de un filtro sobre `password`.

Una columna que no está en el esquema no se puede usar para agrupar, agregar ni ordenar, en ningún modo. Un filtro sobre esa columna se rechaza en modo Strict y se descarta en modo Lenient; consulte [Strict y Lenient](strict-and-lenient.html). Un esquema también puede marcar una columna como no filtrable, no agrupable o no exportable.

## La entrada mal formada se rechaza {#malformed-input-is-refused}

El adaptador y las comprobaciones rechazan la entrada que no reconocen:

- un operador de filtro desconocido, incluidos un error tipográfico o `regex`;
- un valor de filtro enviado como objeto o como matriz donde se espera un único valor;
- claves duplicadas en el JSON;
- un valor que no encaja con el tipo de la columna, como texto en una columna numérica;
- nombres de salida duplicados para las agregaciones.

Cada uno de estos casos tiene un fixture que espera un rechazo limpio.

## Límites de recursos {#resource-limits}

Una solicitud no puede pedir trabajo ilimitado. Estos son los valores por defecto de `ResourceLimits`:

| Límite | Valor por defecto |
|---|---|
| Profundidad del árbol de filtros | 8 |
| Condiciones en todo el filtro | 64 |
| Valores en una lista in o not-in | 1000 |
| Filas en una página | 1000 |
| Filas devueltas por una solicitud de valores distintos | como máximo 10000 |
| Filas en una solicitud que no envía ventana de filas | una página por defecto de 100 (todas las filas solo mediante una exportación, o mediante un indicador que usted active) |
| Tiempo de consulta en MongoDB y Search | no establecido; lo establece usted y la base de datos lo aplica |

Puede fijar cada uno más alto o más bajo. No puede desactivar un límite, salvo que el límite de tiempo de consulta es opcional y queda sin establecer hasta que usted lo establezca. Cero o un número negativo se rechaza al establecerlo. Consulte [Límites](limits.html).

Los fixtures prueban cada límite un paso más allá del borde, y con valores extremos como una lista de 5000 valores o una página de un millón de filas.

## De qué no protege Craticula {#what-craticula-does-not-protect-against}

- **La cuenta de la base de datos.** Craticula no controla lo que puede hacer la cuenta. Dé a la cuenta que ejecuta estas consultas los mínimos derechos que necesite, como solo lectura sobre la única tabla.
- **La ejecución de la consulta.** Craticula nunca la ejecuta. La gestión de conexiones, los límites de coste y la forma de ejecutar la instrucción le corresponden a usted. Para MongoDB y Search puede hacer que la consulta compilada lleve un límite de tiempo (`MaxQueryTimeMs`) que la base de datos aplica; para SQL, establezca un tiempo de espera de instrucción en la conexión o en la cuenta.
- **Quién puede usar la cuadrícula.** La autenticación y el acceso por usuario quedan fuera de su alcance. El esquema puede añadir un filtro fijo a cada consulta, pero decidir cuál debe ser ese filtro le corresponde a usted.
- **Un esquema incorrecto.** Si su esquema enumera una columna que debería permanecer oculta, Craticula la servirá.
- **Consultas lentas.** Una solicitud dentro de los límites puede seguir siendo lenta si la columna no tiene índice. Consulte la [guía de índices](index-guidance.html).

## De dónde procede esto {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
- [csharp/src/Craticula.Core/Schema/ResourceLimits.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimits.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/src/Craticula.Sql/PostgresDialect.cs](../../csharp/src/Craticula.Sql/PostgresDialect.cs)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
