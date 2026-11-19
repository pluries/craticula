---
translates: limits
title: Límites
description: Los límites de recursos predeterminados, qué hace cada uno y cómo cambiarlos.
source_fingerprint: 4ebb0479bf2bf034db02fbe9221ed719f6f737678d26a8c1dee647b249dba066
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Límites {#limits}

Esta página enumera los límites de recursos que Craticula impone a cada solicitud, qué protege cada uno y cómo cambiarlo. Está dirigida al desarrollador que ejecuta una cuadrícula pública o que quiere saber por qué se rechazó una solicitud grande.

## Por qué existen los límites {#why-there-are-limits}

Una solicitud es una entrada que procede de un desconocido. Sin límites, una solicitud podría pedir un árbol de filtros anidado mil niveles, una lista de un millón de valores o una página de diez millones de filas. Cada una de esas cosas le cuesta a su base de datos mucho trabajo.

Craticula rechaza una solicitud así antes de construir una consulta.

## Los límites y sus valores predeterminados {#the-limits-and-their-defaults}

| Ajuste | Valor predeterminado | Qué limita |
|---|---|---|
| `MaxDepth` | 8 | Hasta qué profundidad pueden anidarse los filtros. Una condición simple tiene profundidad 1. |
| `MaxLeaves` | 64 | El número de condiciones de todo el filtro, sumadas en todas las ramas. |
| `MaxInValues` | 1000 | El número de valores de una lista "in" o "not in". |
| `MaxPageSize` | 1000 | El número de filas de una página, es decir, `endRow - startRow`. |
| `MaxSetValuesResults` | 10000 | El máximo de valores que puede devolver una solicitud de valores distintos, por muchos que pida la cuadrícula. |
| `DefaultSetValuesResults` | 1000 | Cuántos valores devuelve esa solicitud cuando la cuadrícula no lo indica. |
| `MaxQueryTimeMs` | no establecido | Cuánto tiempo puede ejecutarse una consulta de MongoDB o de Search, en milisegundos. El único límite opcional; consulte [El límite de tiempo de consulta](#the-query-time-limit). |

Estas son propiedades de `ResourceLimits`.

Los cuatro primeros son comprobaciones: una solicitud que supera el límite se rechaza. Los dos siguientes son topes. `MaxQueryTimeMs` no es ninguna de las dos cosas: se incorpora a la consulta y la base de datos lo hace cumplir. Una solicitud de valores distintos para un filtro de conjunto nunca se rechaza por ser demasiado grande. Craticula la limita al tope y usa el valor predeterminado cuando la cuadrícula no envía ningún número.

Una solicitud que no envía `startRow` ni `endRow` tampoco es ilimitada: recibe una página predeterminada de 100 filas (`AgGridParseOptions.DefaultPageSize`), y el límite de tamaño de página comprueba esa página como cualquier otra. Consulte [Paginación y ordenación](paging-and-sorting.html).

El límite de tamaño de página no se aplica a una exportación del resultado completo (`exportScope` con el valor `"all"`), que no tiene página. Una exportación limitada a una página conserva su rango de filas, y a ella sí se aplica el límite de tamaño de página. Consulte [Exportación a CSV](csv-export.html).

Craticula cuenta los grupos que un usuario ha abierto junto con los filtros. Cada grupo abierto es una condición más, y una solicitud agrupada cuenta un nivel más de los que escribe, por lo que su límite de profundidad efectivo es 7 con el valor predeterminado.

## Límites que son fijos {#limits-that-are-fixed}

Algunos límites están integrados y no pueden cambiarse:

- como máximo 64 columnas de grupo en una solicitud;
- un valor de texto en un filtro de como máximo 8192 caracteres;
- un valor decimal de como máximo 128 caracteres;
- un id de columna de como máximo 256 caracteres, en una clave de ordenación, una columna de grupo, una agregación o la columna de un filtro de conjunto.

## Cómo es un rechazo {#what-a-refusal-looks-like}

Cuando una solicitud incumple un límite, `GridFilterPipeline.Process` lanza una `ResourceLimitExceededException`. Su lista `Violations` nombra cada límite incumplido, con el número real y el máximo. Capture la excepción en su endpoint y devuelva un error de cliente. Si una solicitud incumple dos límites, verá ambos.

## Cómo cambiar un límite {#how-to-change-a-limit}

Los límites no forman parte del archivo de esquema. Son código, y usted los pasa. Así es como los establece la demo:

```csharp
public static ResourceLimits Default { get; } = new()
{
    MaxPageSize = 500,
    MaxDepth = 6,
    MaxLeaves = 32,
    MaxInValues = 200,
    MaxSetValuesResults = 1_000,
    DefaultSetValuesResults = 200
};
```

Después, pase el valor a las llamadas que lo aceptan. La guía de inicio rápido pasa `new ResourceLimits()`, que significa los valores predeterminados.

```csharp
FilterNode? filter = GridFilterPipeline.Process(
    parsed.NativeFilter, parsed.CustomFilters, parsed.Page, schema, limits, parsed.Group, parsed.Aggregations);
```

Una solicitud de valores distintos pasa por `GridFilterPipeline.ProcessSetValues`, y su tope procede de `ResourceLimitsValidator.ResolveSetValuesLimit`.

Puede elevar un límite tanto como quiera. No hay ninguna comprobación de límite superior. Elija números que su base de datos pueda soportar.

## El límite de tiempo de consulta {#the-query-time-limit}

`MaxQueryTimeMs` es para un anfitrión cuya base de datos es compartida o pública. Los demás límites acotan la forma de una solicitud; este acota el trabajo que la base de datos realiza para ella. Establézcalo en un número entero de milisegundos, de 1 a 2,147,483,647, y los compiladores lo incorporan a la consulta:

| Motor | Qué lleva la consulta | Qué ocurre cuando se agota el tiempo |
|---|---|---|
| MongoDB | `maxTimeMS` en el comando aggregate | MongoDB cancela la operación y el adaptador lanza `QueryTimeoutException`. |
| OpenSearch y Elasticsearch | un miembro `timeout` del cuerpo de búsqueda, por ejemplo `"2000ms"` | El motor se detiene en su siguiente comprobación (un límite flexible) y responde con `timed_out: true`. El adaptador lanza `QueryTimeoutException` y nunca devuelve los resultados parciales como página. |

El límite procede únicamente de su código. Una solicitud no puede establecerlo, elevarlo ni eliminarlo, y un `maxQueryTimeMs` en una solicitud se ignora. Una exportación no lleva límite, porque es larga por diseño; detenga una exportación con el token de cancelación. Los motores SQL no tienen un límite compilado: establezca en su lugar un tiempo de espera de sentencia en la conexión o en la cuenta de la base de datos (la demo pública lo hace para PostgreSQL).

Si lo deja sin establecer, nada cambia: las consultas son exactamente las que eran. Un valor cero o negativo lanza una excepción al construir los `ResourceLimits`, y los compiladores también lo rechazan si usted rellena una solicitud a mano. Consulte las reglas en [Límite de tiempo de consulta](query-time-limit.html).

## No se puede desactivar un límite {#you-cannot-turn-a-limit-off}

Todos los límites salvo uno son un número positivo simple, y no existe ningún valor "ilimitado". Establecer un límite en cero o menos lanza una `ArgumentOutOfRangeException` al construir los `ResourceLimits`. La excepción es `MaxQueryTimeMs`, que no está establecido de forma predeterminada porque la biblioteca no puede saber lo lenta que es su base de datos; establecerlo en un número nunca desactiva nada.

Esto es deliberado. Un límite de cero no significaría "sin límite". Rechazaría todas las solicitudes, y un ajuste dejado en blanco por error podría hacerlo sin que nadie lo advirtiera.

## Dónde se ejecutan las comprobaciones {#where-the-checks-run}

Los límites los comprueba `GridFilterPipeline.Process`. El adaptador que lee la solicitud de AG Grid no los comprueba, y los compiladores tampoco. Si omite el pipeline y llama usted mismo a un compilador, no se comprueba ningún límite. La guía de inicio rápido llama al pipeline por esa razón. Consulte [Cómo una solicitud se convierte en una consulta](request-to-query.html).

## De dónde procede esta página {#where-this-comes-from}

- [csharp/src/Craticula.Core/Schema/ResourceLimits.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimits.cs)
- [csharp/src/Craticula.Core/Schema/ResourceLimitsValidator.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimitsValidator.cs)
- [csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs](../../csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs)
- [csharp/src/Craticula.Core/Ir/GroupSpecValidator.cs](../../csharp/src/Craticula.Core/Ir/GroupSpecValidator.cs)
- [spec/semantics.md](../../spec/semantics.md), los apéndices sobre el límite de tiempo de consulta y el tamaño de página predeterminado
- [examples/demo/Api/Grid/DemoLimits.cs](../../examples/demo/Api/Grid/DemoLimits.cs)
- [spec/ir.schema.json](../../spec/ir.schema.json)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
- Páginas relacionadas: [El modelo de seguridad](safety-model.html), [Paginación y ordenación](paging-and-sorting.html), [El GridSchema](the-gridschema.html)
