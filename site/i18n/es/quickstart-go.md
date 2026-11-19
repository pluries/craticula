---
translates: quickstart-go
title: Go
description: Lo que seguirá un port de Go.
source_fingerprint: 99c3a5a56c06d2a70375387b75d972430756a414510521cfe4542daa3fea3e3a
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Inicio rápido: Go {#quickstart-go}

**Todavía no existe una implementación en Go.** Esta página lo dice a propósito, para que no busque un paquete que no existe.

## Por qué {#why}

Craticula parte de la especificación: las reglas y los fixtures de conformidad de `spec/` van primero, y toda
implementación en un lenguaje debe superar los mismos fixtures. El port a Go está previsto para **después del congelamiento de la especificación** (la
especificación se congela en la versión 1.0). Hasta entonces la especificación aún puede cambiar, y un port escrito ahora tendría que reescribirse.

No hay nada publicado para Go: ni paquete ni comando de instalación.

## Lo que puede hacer hoy {#what-you-can-do-today}

- Use la biblioteca de C#, que es la implementación de referencia: [Inicio rápido: C#](quickstart-csharp.html).
- Lea las reglas que deberá seguir un port a Go: la [semántica](semantics.html) y las
  referencias de esquemas ([GridSchema](grid-schema.html), [IR](ir-schema.html)).
- Consulte la prueba que debe superar un port: los fixtures de conformidad
  (`spec/fixtures`) y el ejecutor independiente del lenguaje descrito en
  [`spec/conformance-runner.md`](../../spec/conformance-runner.md). Un controlador escrito en cualquier lenguaje responde a las solicitudes del ejecutor y el
  ejecutor califica las respuestas.
