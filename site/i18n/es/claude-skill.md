---
translates: claude-skill
title: Skill de Claude
description: Una skill de Claude que enseña a Claude a añadir Craticula a un proyecto de C#, cómo instalarla y qué esperar de ella.
source_fingerprint: 63b1738da63b9355a6d5c64ab072a81d4f2fa969df1e3817fc06403b6cb6dba0
drafter: claude
drafted_on: 2026-11-22
status: approved
---
# Skill de Claude {#claude-skill}

Craticula tiene una skill para Claude. Una skill es una carpeta de instrucciones en texto plano que Claude lee antes de ayudarle. Esta enseña a Claude a añadir Craticula a un proyecto de C#.

Para usarla, instálela con los dos comandos de abajo o copie su carpeta a mano. Después pida a Claude que añada Craticula a su proyecto. Cuando termine, lea [El modelo de seguridad](safety-model.html) para ver qué protege Craticula.

## Dos maneras de instalar {#two-ways-to-install}

La primera manera es un plugin de Claude Code. Ejecute los dos comandos en un terminal:

```text
claude plugin marketplace add pluries/craticula
claude plugin install craticula@craticula
```

El primer comando añade el marketplace de Craticula desde el repositorio. El segundo instala la skill desde él. Los comandos son los mismos en todos los idiomas de este sitio.

La segunda manera es una copia. Tome la carpeta `skills/craticula` del [repositorio de Craticula](https://github.com/pluries/craticula) y colóquela en `~/.claude/skills/craticula/`. Esa es su carpeta personal de skills, así que la skill funciona en todos los proyectos que abra. Para usarla solo en un proyecto, coloque la carpeta en la carpeta de skills de ese proyecto.

## Qué hace la skill {#what-the-skill-does}

- Indica a Claude qué paquetes de Craticula necesita su proyecto.
- Muestra cómo declarar un esquema, analizar la solicitud de la cuadrícula y compilarla en una consulta.
- Trata los adaptadores que ejecutan consultas como opcionales.
- Remite a Claude a los mismos datos que este sitio, para que ambos no se desvíen.

La skill respeta las reglas de seguridad y los límites de la biblioteca. Consulte [El modelo de seguridad](safety-model.html) y [Límites](limits.html).

## Qué no hace {#what-it-does-not-do}

La skill es texto. No puede ejecutar código, abrir una conexión ni modificar un archivo. Claude realiza cualquier cambio en su proyecto en su propia sesión, con sus propios ajustes de permisos.

La skill no indica una versión. Le dice a Claude que use el paquete más reciente de nuget.org, o la versión que su proyecto ya usa.

## Lenguajes {#languages}

La skill cubre la biblioteca de C#, que es la implementación de referencia. Todavía no existe ninguna implementación de TypeScript, Python ni Go. Sus páginas de inicio rápido lo dicen: [Python](quickstart-python.html), [Go](quickstart-go.html) y [TypeScript](quickstart-typescript.html). La skill ofrece en su lugar la biblioteca de C#.

## Qué copia es la oficial {#which-copy-is-official}

La copia oficial es la carpeta `skills/craticula` del [repositorio de Craticula](https://github.com/pluries/craticula). Las versiones de los paquetes llevan etiquetas que empiezan por `dotnet-v`. Comunique un problema de seguridad como describe [SECURITY.md](https://github.com/pluries/craticula/blob/main/SECURITY.md).

Un fork, o una copia de otro lugar, no tiene nada de esta procedencia. Compárela con el repositorio antes de fiarse de ella.

## Qué esperar de Claude {#what-to-expect-from-claude}

El comportamiento de un agente no está garantizado: la skill es texto, y la prueba de que un agente llega a una ejecución que funciona es una demostración manual, no una prueba automatizada.

Lea el código que escribe Claude antes de ejecutarlo, como haría con cualquier código.

## Lecturas adicionales {#further-reading}

- [Dialectos y proveedores](dialects-and-providers.html) indica para qué bases de datos compila Craticula y en qué se diferencian.
- [Límites](limits.html) enumera los topes del tamaño y la complejidad de una solicitud.
- [El modelo de seguridad](safety-model.html) enumera qué protege Craticula y qué no.
- [El inicio rápido de C#](quickstart-csharp.html) muestra los mismos pasos a mano.
