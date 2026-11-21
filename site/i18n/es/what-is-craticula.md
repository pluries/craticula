---
translates: what-is-craticula
title: Qué es Craticula
description: Qué compila Craticula, qué no hace nunca y en qué estado se encuentra.
source_fingerprint: e8f756cfd41d5e8621dce7f0e9a10a459e2c9061e1f4434abe57c82e8adc1664
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Qué es Craticula {#what-craticula-is}

Esta página explica qué hace Craticula, qué le deja a usted y en qué estado se encuentra el proyecto hoy. Está dirigida a un desarrollador que tiene una cuadrícula del lado del servidor de AG Grid y que nunca ha visto Craticula.

Craticula es una biblioteca de .NET que convierte una solicitud de AG Grid Server-Side Row Model en una consulta de base de datos. Admite SQL, MongoDB y OpenSearch.

## El problema que resuelve {#the-problem-it-solves}

Una cuadrícula del lado del servidor de AG Grid envía a su servidor una solicitud JSON. La solicitud indica qué filas quiere la cuadrícula, cómo ordenarlas, cómo filtrarlas y cómo agruparlas.

Todo equipo de backend termina escribiendo el mismo código para convertir ese JSON en una consulta. Es un código fácil de hacer mal. El tratamiento de los valores nulos, la distinción entre mayúsculas y minúsculas, la paginación y la protección contra la inyección exigen cuidado.

Craticula es esa traducción, escrita una sola vez y probada con ejemplos comunes.

## Qué compila {#what-it-compiles}

Usted entrega dos cosas a Craticula:

- la solicitud exactamente como la envió AG Grid;
- un esquema que enumera las columnas que la cuadrícula puede tocar y cómo se corresponden con su base de datos.

Craticula le devuelve una consulta que usted puede ejecutar:

- para SQL, una instrucción y una lista de parámetros;
- para MongoDB, un pipeline de agregación;
- para OpenSearch y Elasticsearch, una consulta en su lenguaje de consulta JSON.

## Qué no hace nunca {#what-it-never-does}

Craticula es un compilador, no un cliente.

- Nunca abre una conexión con una base de datos.
- Nunca ejecuta una consulta.
- Nunca lee sus datos.

La ejecución de la consulta le corresponde a usted. Unos paquetes de adaptadores opcionales pueden encargarse de ella, pero están separados del núcleo. Los paquetes del núcleo nunca dependen de ellos.

## Backends y versiones de AG Grid admitidos {#supported-backends-and-ag-grid-versions}

La primera versión apunta a estos backends:

- PostgreSQL
- SQL Server
- MySQL y MariaDB
- SQLite
- MongoDB
- OpenSearch
- Elasticsearch

Oracle no figura en la lista de la v1, y el proyecto lo trata como una cuestión abierta. El repositorio contiene un dialecto de Oracle, pero no forma parte del compromiso.

Por el lado de la cuadrícula, el README menciona las versiones 31 a 36 de AG Grid Server-Side Row Model. También admite el Infinite Row Model de la edición Community para las cuadrículas planas, es decir, ordenación, filtros de texto, de número y de fecha, y paginación. La agrupación de filas, la agregación, el pivote y el filtro de conjunto son funciones Enterprise y no forman parte del compromiso para la edición Community.

El modo pivote no es compatible. El analizador de solicitudes rechaza una solicitud que tenga el modo pivote activado.

## Estado actual {#current-state}

Craticula está en versión preliminar. Todavía no se ha publicado ningún paquete, y nadie aloja una demostración para los visitantes. El repositorio contiene una aplicación de demostración que usted mismo ejecuta (`examples/demo`) y que requiere Docker, el SDK de .NET 10 y Node.

Para probarlo, compile desde el código fuente. La [guía de inicio rápido de C#](quickstart-csharp.html) muestra cómo hacerlo. La biblioteca de C# es la implementación de referencia. El repositorio describe portaciones a TypeScript, Python y Go previstas tras la congelación de la especificación. Ninguna existe todavía.

## Para continuar {#where-to-go-next}

- [Cómo una solicitud se convierte en una consulta](request-to-query.html) sigue una solicitud a lo largo del pipeline.
- [Strict y Lenient](strict-and-lenient.html) explica las dos maneras de tratar las columnas desconocidas.
- [El modelo de seguridad](safety-model.html) enumera de qué protege Craticula y de qué no.

## De dónde procede esto {#where-this-comes-from}

- [README.md](../../README.md)
- [spec/README.md](../../spec/README.md)
- [csharp/src/Craticula.Core/README.md](../../csharp/src/Craticula.Core/README.md)
- [csharp/src/Craticula.AgGrid/AgGridRequestParser.cs](../../csharp/src/Craticula.AgGrid/AgGridRequestParser.cs)
