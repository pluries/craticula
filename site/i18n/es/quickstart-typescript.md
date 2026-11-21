---
translates: quickstart-typescript
title: TypeScript
description: Lo que seguirá un port de TypeScript.
source_fingerprint: 072ec77c552dd32b4086a7e68bb381e3e721e82ea24a817d6929470d27629ac2
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Inicio rápido: TypeScript {#quickstart-typescript}

**Todavía no existe una implementación en TypeScript.** Esta página lo dice a propósito, para que no busque un paquete que no existe.

## Por qué {#why}

Craticula parte de la especificación: las reglas y los fixtures de conformidad de `spec/` van primero, y toda
implementación en un lenguaje debe superar los mismos fixtures. El port a TypeScript está previsto para **después del congelamiento de la especificación** (la
especificación se congela en la versión 1.0). Hasta entonces la especificación aún puede cambiar, y un port escrito ahora tendría que reescribirse.

No hay nada publicado para TypeScript: ni paquete ni comando de instalación.

## Lo que puede hacer hoy {#what-you-can-do-today}

- Use la biblioteca de C#, que es la implementación de referencia: [Inicio rápido: C#](quickstart-csharp.html).
- Lea las reglas que deberá seguir un port a TypeScript: la [semántica](semantics.html) y las
  referencias de esquemas ([GridSchema](grid-schema.html), [IR](ir-schema.html)).
- Consulte la prueba que debe superar un port: los fixtures de conformidad
  (`spec/fixtures`) y el ejecutor independiente del lenguaje descrito en
  [`spec/conformance-runner.md`](../../spec/conformance-runner.md). Un controlador escrito en cualquier lenguaje responde a las solicitudes del ejecutor y el
  ejecutor califica las respuestas.
