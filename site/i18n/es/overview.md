---
translates: overview
title: Visión general
description: Qué es Craticula, qué compila y en qué punto se encuentra.
source_fingerprint: cb2f7ba8d0a8f913a3ba9325faa592f2848c491ea50ec01ab0f778647e71ecf8
drafter: claude
drafted_on: 2026-11-27
status: approved
---
# Craticula {#craticula}

[![CI](https://github.com/pluries/craticula/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/pluries/craticula/actions/workflows/ci.yml)
[![coverage gate](https://img.shields.io/badge/coverage%20gate-%E2%89%A590%25%20per%20assembly-brightgreen)](https://github.com/pluries/craticula/actions/workflows/ci.yml)
[![license](https://img.shields.io/github/license/pluries/craticula)](LICENSE)
[![spec version](https://img.shields.io/badge/spec-1.0.0-blue)](spec/VERSION)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/pluries/craticula/badge)](https://scorecard.dev/viewer/?uri=github.com/pluries/craticula)

> Un compilador, no un cliente: traducir las solicitudes de AG Grid Server-Side Row Model a consultas
> nativas y seguras para el backend — SQL, MongoDB, OpenSearch/Elasticsearch — a partir de una única IR
> canónica, en cuatro lenguajes.

**Responsable del mantenimiento:** Christian Stephan ([cstephan.dev](https://cstephan.dev), [LinkedIn](https://www.linkedin.com/in/christian-stephan), [GitHub](https://github.com/cstephan-dev)). Craticula es de código abierto bajo la licencia Apache-2.0;
el sitio del proyecto es [craticula.pluries.dev](https://craticula.pluries.dev).

**Estado:** diseño inicial. Los responsables del mantenimiento conservan en privado un documento de requisitos técnicos (TRD: arquitectura,
modelo de seguridad, hoja de ruta, preguntas abiertas); sus identificadores de requisitos (AR-1, SEM-1, GRP-7, etc.)
se citan en todo este repositorio, y las reglas normativas están en [`spec/semantics.md`](spec/semantics.md).

## Por qué {#why}

Cada equipo de backend reimplementa la traducción de una solicitud SSRM de AG Grid
(`filterModel`, `sortModel`, `rowGroupCols`, `groupKeys`, `valueCols`, `startRow`/`endRow`)
a consultas de base de datos, normalmente con intermediarios DSL basados en cadenas, operadores que faltan, una semántica
defectuosa de valores nulos y de mayúsculas y minúsculas, superficie de inyección, y sin compatibilidad con agrupación ni con motores de búsqueda. Ninguna
biblioteca de código abierto mantenida cubre esto de extremo a extremo.

## Cómo funciona {#how-it-works}

![Cómo una solicitud se convierte en una consulta: una solicitud de AG Grid pasa por el adaptador de solicitudes hacia la IR canónica, y el compilador de consultas la convierte en un artefacto de consulta (SQL con parámetros, un pipeline de agregación de MongoDB o una consulta de OpenSearch), todo comprobado contra el GridSchema; los adaptadores de ejecución opcionales ejecutan el artefacto y dan forma a las filas para la respuesta de la cuadrícula.](site/diagrams/how-it-works.svg)

El núcleo nunca abre una conexión: la compilación es una función pura que toma una solicitud de cuadrícula y
una configuración de esquema (el límite de seguridad y de tipos) y produce un artefacto de consulta simple.
La ejecución — ejecutar el artefacto y dar forma a los resultados para la respuesta de la cuadrícula — corresponde a
paquetes de adaptadores independientes y opcionales, uno por ecosistema.

## Alcance (v1) {#scope-v1}

- **Adaptador de solicitudes** (la especificación lo llama *frontend adapter*; es el lado de entrada del compilador y se ejecuta en su servidor, no en el navegador): AG Grid SSRM (v31–v36). El Infinite Row Model de AG Grid Community es compatible con cuadrículas planas
  (ordenación, filtros de texto, número y fecha, paginación; véase [`spec/fixtures/community-infinite`](spec/fixtures/community-infinite/README.md)).
  La agrupación de filas, la agregación, el pivote y el filtro de conjunto son funciones Enterprise y no forman parte de ese compromiso.
- **Compiladores de consultas** (los *backend compilers* de la especificación, también en su servidor): PostgreSQL, SQL Server, MySQL/MariaDB, SQLite, MongoDB, OpenSearch,
  Elasticsearch. Oracle está probado por la comunidad: el mismo pipeline SQL, con paginación `FETCH FIRST` (12c y posteriores).
- **Implementación de referencia:** C#/.NET, portada a TypeScript, Python y Go después de que la especificación
  se congele en la 1.0.
- **La semántica** (distinción entre mayúsculas y minúsculas, tratamiento y orden de los valores nulos, fechas y zonas horarias, paginación
  determinista) es normativa y está garantizada por un conjunto de fixtures de conformidad compartido e independiente del lenguaje.
- La exportación CSV/TSV en streaming comparte el mismo modelo de entrada, que solo compila.

El §2.2 del TRD (exclusiones) y su §14 (hoja de ruta) indican qué queda explícitamente fuera de la v1.

## Estructura del repositorio (prevista) {#repository-layout-planned}

```
spec/         IR JSON Schema, semantics.md, conformance fixtures — the source of truth
csharp/       reference implementation (Core, AgGrid adapter, compilers, execution adapters)
typescript/   TypeScript port (after spec freeze)
python/       Python port (after spec freeze)
go/           Go port (after spec freeze)
docs/adr/     architecture decision records (why the design is the way it is)
examples/     demo app (React + AG Grid + one sample backend)
```

## Paquetes {#packaging}

La implementación en C# se divide en diez paquetes NuGet, todos publicados en nuget.org:

[![NuGet](https://img.shields.io/nuget/v/Craticula.Core?label=nuget)](https://www.nuget.org/packages/Craticula.Core)

[`Craticula.Core`](https://www.nuget.org/packages/Craticula.Core),
[`Craticula.AgGrid`](https://www.nuget.org/packages/Craticula.AgGrid),
[`Craticula.Sql`](https://www.nuget.org/packages/Craticula.Sql),
[`Craticula.Mongo`](https://www.nuget.org/packages/Craticula.Mongo),
[`Craticula.Search`](https://www.nuget.org/packages/Craticula.Search),
[`Craticula.Export.Csv`](https://www.nuget.org/packages/Craticula.Export.Csv),
[`Craticula.EntityFrameworkCore`](https://www.nuget.org/packages/Craticula.EntityFrameworkCore),
[`Craticula.Dapper`](https://www.nuget.org/packages/Craticula.Dapper),
[`Craticula.MongoDB.Driver`](https://www.nuget.org/packages/Craticula.MongoDB.Driver) y
[`Craticula.OpenSearch.Client`](https://www.nuget.org/packages/Craticula.OpenSearch.Client).
Instale uno con `dotnet add package <name>`. Para comprobar que los paquetes compilan y que un consumidor limpio compila contra ellos, ejecute
`bash scripts/pack-smoke.sh` (Python 3.10+ y el SDK de .NET 10; unos 3 minutos).

## Skill de Claude {#claude-skill}

Una skill para Claude le guía desde cero hasta una primera solicitud de grid compilada y le indica a Claude que rechace los atajos inseguros. Instálela como plugin de Claude Code:

```text
claude plugin marketplace add pluries/craticula
claude plugin install craticula@craticula
```

O copie la carpeta [`skills/craticula`](skills/craticula/SKILL.md) en `~/.claude/skills/craticula/`. La skill es texto: el comportamiento de Claude no está garantizado. Consulte la [página de la skill de Claude](https://craticula.pluries.dev/claude-skill.html).

## Licencias de las dependencias {#dependency-licenses}

Cada paquete NuGet de `csharp/`, incluidos los transitivos y los proyectos de prueba, debe tener una licencia que el proyecto acepte.
`python3 scripts/check-licenses.py` lo comprueba (Python 3.10+, el SDK de .NET 10 y nuget.org; restaure primero la solución con
`dotnet restore Craticula.sln` en `csharp/`, y la herramienta fijada con `dotnet tool restore` en el mismo lugar). El mismo script se ejecuta en el
job `license-check` de cada pull request y tarda unos segundos con una caché de paquetes caliente.

- **Permitidas:** MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, 0BSD, Unlicense, PostgreSQL, Zlib
  ([`scripts/license-allowlist.json`](scripts/license-allowlist.json)).
- **Rechazadas:** GPL, LGPL, AGPL, SSPL, BUSL, Elastic, Commons Clause y cualquier licencia no comercial. La línea de error nombra el
  paquete, su versión, la licencia y el proyecto.
- **MPL-2.0:** solo cuando un ADR aceptado (una línea `Status: Accepted`) en `docs/adr/` nombra MPL-2.0 y el paquete.
  Está diseñado para rechazar por defecto: sin ese ADR, un paquete MPL-2.0 se rechaza.
- **Excepciones:** cuando la herramienta no puede leer una licencia (un archivo de licencia o una simple URL en lugar de un identificador SPDX), añada una entrada a
  [`scripts/license-overrides.json`](scripts/license-overrides.json) con el paquete, su versión exacta, la licencia real y un
  motivo por escrito. La licencia debe ser un identificador SPDX permitido (o `"vendor_terms": true` para los términos propios de un proveedor que no son SPDX). Una excepción
  nunca levanta una licencia que la herramienta haya leído como rechazada o como MPL-2.0. Una entrada sin motivo hace fallar la comprobación, y también una entrada que
  ya no coincide con ningún paquete.
- **Trampas:** `MySql.Data` (GPL) se rechaza por su nombre: use `MySqlConnector`. El controlador de Oracle `Oracle.ManagedDataAccess.Core` y
  `Testcontainers.Oracle` solo se aceptan en los proyectos de prueba de `csharp/tests`, nunca en un paquete de `csharp/src`.

## Demostración {#demo}

Pruébela en línea: [PostgreSQL](https://craticula-pg.pluries.dev) y [MongoDB](https://craticula-mongo.pluries.dev). Ambas muestran los mismos
pedidos sintéticos a través de la misma página de AG Grid; son de solo lectura y tienen límite de frecuencia.

[`examples/demo`](examples/demo/README.md) es la aplicación que hay detrás: una página de AG Grid que lee los mismos pedidos de PostgreSQL o de
MongoDB a través de una API en C# construida sobre la biblioteca. Para ejecutarla usted mismo se necesita Docker, el SDK de .NET 10 y Node 20.19 o posterior. Es un
escaparate que instala los paquetes publicados desde nuget.org, como lo haría un usuario de la biblioteca.

## Compatibilidad {#compatibility}

| Versión de la especificación | Destino de .NET |
|---|---|
| 1.0.0 | net10.0 |

Los paquetes apuntan a `net10.0`. También se ejecutan en el runtime de .NET 11: la compilación y las pruebas sin conexión pasan con el SDK de .NET 11.0.100 (comprobado el 2026-11-27; el razonamiento está en ADR-0015).

La versión de la especificación es la de [`spec/VERSION`](spec/VERSION); cada paquete la indica en su propio README.
La forma en que se eligen las versiones se describe en [VERSIONING.md](VERSIONING.md).
Los paquetes declaran rangos de versiones para las bibliotecas que envuelven, nunca una única versión exacta.

## Licencia {#license}

Apache License 2.0 — véase [LICENSE](LICENSE).
