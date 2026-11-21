---
translates: strict-and-lenient
title: Strict y Lenient
description: Qué hacen los dos modos de esquema con las columnas que el esquema no permite.
source_fingerprint: 20ab3fa199820cb9e052565112f509257cd8428bafaf7eced343e56e4ea4c25a
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Strict y Lenient {#strict-and-lenient}

Esta página explica los dos modos en que puede funcionar un esquema y qué hace cada uno cuando una solicitud nombra una columna que el esquema no permite. Está dirigida a un desarrollador que está escribiendo un esquema y tiene que elegir un modo.

En resumen: use Strict salvo que tenga un motivo para no hacerlo. Strict es el valor por defecto.

## Dónde se establece el modo {#where-you-set-the-mode}

El modo es un ajuste del esquema, con los valores `strict` y `lenient`.

```json
{
  "mode": "strict",
  "source": "orders",
  "stableKey": "id",
  "fields": { }
}
```

En C#, `GridSchema.Mode` es `Strict` por defecto. El esquema JSON del archivo indica `mode` como obligatorio, así que escríbalo explícitamente en su archivo de esquema.

## Strict {#strict}

En modo Strict, se rechaza un filtro sobre una columna que el esquema no enumera. Craticula lanza una `UnknownFieldException` que nombra todas las columnas rechazadas. No se produce ninguna consulta.

Lo mismo ocurre con una columna que el esquema enumera pero marca con `filterable: false`. Craticula la trata como una columna desconocida.

Los fixtures adversarios lo demuestran. Un filtro, una ordenación y una agrupación de filas sobre una columna desconocida se rechazan todos. El filtro y la agrupación de filas lanzan `UnknownFieldException`; la ordenación la rechaza el compilador (véase el último punto más abajo). Lo mismo ocurre con un nombre de columna formado por SQL, como `amount'); DROP TABLE users; --`.

## Lenient {#lenient}

En modo Lenient, Craticula descarta una condición de filtro sobre una columna desconocida o no filtrable y continúa con el resto.

Descartar una condición amplía la respuesta. Es posible que la cuadrícula reciba más filas de las que pidió. Elija Lenient solo si lo acepta.

Algunos detalles de cómo se elimina una condición descartada:

- Un grupo AND u OR que pierde todas sus condiciones desaparece.
- Un grupo que se queda con una sola condición se convierte en esa condición.
- Un NOT cuya condición desaparece también desaparece. No se convierte en "coincide con todo" ni en "no coincide con nada".

## Lo que ningún modo relaja {#what-no-mode-relaxes}

Lenient solo perdona una condición de filtro. La especificación establece que todo lo que determina la forma de la respuesta se rechaza en cualquier modo:

- una columna de grupo que no está en el esquema, o que no está marcada como agrupable;
- una clave de grupo que profundiza en una columna que no es filtrable;
- una agregación sobre una columna que no está en el esquema, o que no tiene permitido usar esa función;
- la columna de una solicitud de valores distintos para un filtro de conjunto;
- una columna de exportación que es desconocida, no exportable, repetida, o una lista vacía.

El motivo es que descartar estos elementos daría a la cuadrícula una respuesta distinta de la que pidió, sin ningún error. Una clave de grupo descartada podría devolver las filas de otro grupo bajo la etiqueta que espera la cuadrícula.

El modo tampoco tiene efecto sobre las demás comprobaciones. Una solicitud demasiado profunda, demasiado ancha, que pide demasiadas filas o que tiene un valor que no encaja con el tipo de la columna se rechaza en ambos modos. Consulte [El modelo de seguridad](safety-model.html).

Un punto más: una ordenación sobre una columna que el esquema no enumera se rechaza en ambos modos. El rechazo procede del compilador, que lanza su propia excepción de compilación en lugar de `UnknownFieldException`, así que capture ambas en su endpoint y devuelva un error de cliente.

## Cómo elegir {#how-to-choose}

- Elija **Strict** si la cuadrícula es suya y una columna desconocida significa un error o un ataque. Lo descubre de inmediato.
- Elija **Lenient** solo si acepta que una solicitud que nombra una columna desconocida o no filtrable devuelva más filas en lugar de un error.

Si tiene dudas, use Strict.

## De dónde procede esto {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridSchemaMode.cs](../../csharp/src/Craticula.Core/Schema/GridSchemaMode.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
