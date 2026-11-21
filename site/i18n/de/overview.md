---
translates: overview
title: Übersicht
description: Was Craticula ist, was es kompiliert und wo es steht.
source_fingerprint: 3929869b5367531388935cc42945f515177b84bf6d3ffe925cbccd06c8cf38e0
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Craticula {#craticula}

[![CI](https://github.com/pluries/craticula/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/pluries/craticula/actions/workflows/ci.yml)
[![coverage gate](https://img.shields.io/badge/coverage%20gate-%E2%89%A590%25%20per%20assembly-brightgreen)](https://github.com/pluries/craticula/actions/workflows/ci.yml)
[![license](https://img.shields.io/github/license/pluries/craticula)](LICENSE)
[![spec version](https://img.shields.io/badge/spec-0.3.0-blue)](spec/VERSION)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/pluries/craticula/badge)](https://scorecard.dev/viewer/?uri=github.com/pluries/craticula)

> Ein Compiler, kein Client: Anfragen des AG Grid Server-Side Row Model in native, sichere
> Backend-Abfragen übersetzen — SQL, MongoDB, OpenSearch/Elasticsearch — aus einer einzigen
> kanonischen IR, in vier Sprachen.

**Maintainer:** Christian Stephan ([cstephan.dev](https://cstephan.dev), [LinkedIn](https://www.linkedin.com/in/christian-stephan), [GitHub](https://github.com/cstephan-dev)). Craticula ist Open Source unter Apache-2.0;
die Projektwebsite ist [craticula.pluries.dev](https://craticula.pluries.dev).

**Status:** frühe Entwurfsphase. Die Maintainer führen intern ein technisches Anforderungsdokument (TRD: Architektur,
Sicherheitsmodell, Roadmap, offene Fragen); seine Anforderungs-IDs (AR-1, SEM-1, GRP-7 und so weiter)
werden im gesamten Repository zitiert, und die normativen Regeln stehen in [`spec/semantics.md`](spec/semantics.md).

## Warum {#why}

Jedes Backend-Team implementiert die Übersetzung einer Anfrage von AG Grid SSRM
(`filterModel`, `sortModel`, `rowGroupCols`, `groupKeys`, `valueCols`, `startRow`/`endRow`)
in Datenbankabfragen neu — meist mit String-DSL-Zwischenschritten, fehlenden Operatoren, fehlerhafter
Semantik bei Null-Werten und Groß-/Kleinschreibung, Angriffsfläche für Injection und ohne Unterstützung für Gruppierung und Suchmaschinen. Keine
gepflegte Open-Source-Bibliothek deckt das durchgängig ab.

## So funktioniert es {#how-it-works}

![Wie aus einer Anfrage eine Abfrage wird: Eine Anfrage von AG Grid durchläuft den Request-Adapter in die kanonische IR, und der Abfrage-Compiler macht daraus ein Abfrageartefakt (SQL mit Parametern, eine MongoDB-Aggregationspipeline oder eine OpenSearch-Abfrage), jeweils gegen das GridSchema geprüft; optionale Ausführungsadapter führen das Artefakt aus und bringen die Zeilen wieder in die Form der Grid-Antwort.](site/diagrams/how-it-works.svg)

Der Kern öffnet nie eine Verbindung: Die Kompilierung ist eine reine Funktion, die aus einer Grid-Anfrage und
einer Schemakonfiguration (der Sicherheits- und Typgrenze) ein einfaches Abfrageartefakt erzeugt.
Die Ausführung — das Artefakt laufen lassen und die Ergebnisse wieder in die Form der Grid-Antwort bringen — liegt in
separaten, optionalen Adapterpaketen, eines je Ökosystem.

## Umfang (v1) {#scope-v1}

- **Request-Adapter** (die Spezifikation nennt ihn *frontend adapter*; er ist die Eingangsseite des Compilers und läuft in Ihrem Server, nicht im Browser): AG Grid SSRM (v31–v36). Das Infinite Row Model von AG Grid Community wird für flache Grids unterstützt
  (Sortierung, Text-, Zahlen- und Datumsfilter, Paging; siehe [`spec/fixtures/community-infinite`](spec/fixtures/community-infinite/README.md)).
  Zeilengruppierung, Aggregation, Pivot und der Set-Filter sind Enterprise-Funktionen und nicht Teil dieses Versprechens.
- **Abfrage-Compiler** (die *backend compilers* der Spezifikation, ebenfalls in Ihrem Server): PostgreSQL, SQL Server, MySQL/MariaDB, SQLite, MongoDB, OpenSearch,
  Elasticsearch. Oracle wird von der Community getestet: dieselbe SQL-Pipeline, mit `FETCH FIRST`-Paging (12c und neuer).
- **Referenzimplementierung:** C#/.NET, portiert nach TypeScript, Python und Go, nachdem die Spezifikation
  mit 1.0 eingefroren ist.
- **Die Semantik** (Groß-/Kleinschreibung, Behandlung und Sortierung von Null-Werten, Datumsangaben und Zeitzonen, deterministisches
  Paging) ist normativ und wird durch eine gemeinsame, sprachunabhängige Suite von Konformitäts-Fixtures durchgesetzt.
- Der CSV/TSV-Streaming-Export nutzt dasselbe Eingabemodell, das nur kompiliert.

§2.2 des TRD (Nicht-Ziele) und §14 (Roadmap) legen fest, was für v1 ausdrücklich ausgeschlossen ist.

## Repository-Aufbau (geplant) {#repository-layout-planned}

```
spec/         IR JSON Schema, semantics.md, conformance fixtures — the source of truth
csharp/       reference implementation (Core, AgGrid adapter, compilers, execution adapters)
typescript/   TypeScript port (after spec freeze)
python/       Python port (after spec freeze)
go/           Go port (after spec freeze)
docs/adr/     architecture decision records (why the design is the way it is)
examples/     demo app (React + AG Grid + one sample backend)
```

## Pakete {#packaging}

Die C#-Implementierung ist in zehn NuGet-Pakete aufgeteilt, die alle auf nuget.org veröffentlicht sind:

[![NuGet](https://img.shields.io/nuget/v/Craticula.Core?label=nuget)](https://www.nuget.org/packages/Craticula.Core)

[`Craticula.Core`](https://www.nuget.org/packages/Craticula.Core),
[`Craticula.AgGrid`](https://www.nuget.org/packages/Craticula.AgGrid),
[`Craticula.Sql`](https://www.nuget.org/packages/Craticula.Sql),
[`Craticula.Mongo`](https://www.nuget.org/packages/Craticula.Mongo),
[`Craticula.Search`](https://www.nuget.org/packages/Craticula.Search),
[`Craticula.Export.Csv`](https://www.nuget.org/packages/Craticula.Export.Csv),
[`Craticula.EntityFrameworkCore`](https://www.nuget.org/packages/Craticula.EntityFrameworkCore),
[`Craticula.Dapper`](https://www.nuget.org/packages/Craticula.Dapper),
[`Craticula.MongoDB.Driver`](https://www.nuget.org/packages/Craticula.MongoDB.Driver) und
[`Craticula.OpenSearch.Client`](https://www.nuget.org/packages/Craticula.OpenSearch.Client).
Installieren Sie eines mit `dotnet add package <name>`. Um zu prüfen, dass die Pakete bauen und ein sauberer Consumer dagegen kompiliert, führen Sie
`bash scripts/pack-smoke.sh` aus (Python 3.10+ und das .NET-10-SDK; etwa 3 Minuten).

## Lizenzen der Abhängigkeiten {#dependency-licenses}

Jedes NuGet-Paket unter `csharp/`, einschließlich transitiver Abhängigkeiten und Testprojekte, muss eine Lizenz tragen, die das Projekt akzeptiert.
`python3 scripts/check-licenses.py` prüft das (Python 3.10+, das .NET-10-SDK und nuget.org; stellen Sie zuerst die Solution mit
`dotnet restore Craticula.sln` in `csharp/` wieder her, dann das angeheftete Tool mit `dotnet tool restore` ebenda). Dasselbe Skript läuft im
Job `license-check` jedes Pull Requests und braucht mit warmem Paket-Cache einige Sekunden.

- **Erlaubt:** MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, 0BSD, Unlicense, PostgreSQL, Zlib
  ([`scripts/license-allowlist.json`](scripts/license-allowlist.json)).
- **Abgelehnt:** GPL, LGPL, AGPL, SSPL, BUSL, Elastic, Commons Clause und jede nicht kommerzielle Lizenz. Die Fehlerzeile nennt
  Paket, Version, Lizenz und Projekt.
- **MPL-2.0:** nur, wenn ein akzeptiertes ADR (eine Zeile `Status: Accepted`) in `docs/adr/` MPL-2.0 und das Paket nennt.
  Die Prüfung lehnt von Haus aus ab, mit Absicht: Ohne ein solches ADR wird ein MPL-2.0-Paket abgelehnt.
- **Ausnahmen:** Wenn das Tool eine Lizenz nicht lesen kann (eine Lizenzdatei oder eine bloße URL statt einer SPDX-ID), fügen Sie einen Eintrag in
  [`scripts/license-overrides.json`](scripts/license-overrides.json) hinzu, mit dem Paket, seiner exakten Version, der tatsächlichen Lizenz und einer
  schriftlichen Begründung. Die Lizenz muss eine erlaubte SPDX-ID sein (oder `"vendor_terms": true` für die eigenen, nicht SPDX-konformen Bedingungen eines Herstellers). Eine Ausnahme
  hebt nie eine Lizenz auf, die das Tool als abgelehnt oder als MPL-2.0 gelesen hat. Ein Eintrag ohne Begründung lässt die Prüfung fehlschlagen, ebenso ein Eintrag, der
  zu keinem Paket mehr passt.
- **Fallstricke:** `MySql.Data` (GPL) wird anhand des Namens abgelehnt: Verwenden Sie `MySqlConnector`. Der Oracle-Treiber `Oracle.ManagedDataAccess.Core` und
  `Testcontainers.Oracle` werden nur in den Testprojekten unter `csharp/tests` akzeptiert, nie in einem Paket unter `csharp/src`.

## Demo {#demo}

Probieren Sie es online aus: [PostgreSQL](https://craticula-pg.pluries.dev) und [MongoDB](https://craticula-mongo.pluries.dev). Beide zeigen dieselben
synthetischen Bestellungen über dieselbe Seite mit AG Grid; sie sind schreibgeschützt und ratenbegrenzt.

[`examples/demo`](examples/demo/README.md) ist die App dahinter: eine Seite mit AG Grid, die dieselben Bestellungen aus PostgreSQL oder
MongoDB über eine auf der Bibliothek aufbauende C#-API liest. Um sie selbst auszuführen, brauchen Sie Docker, das .NET-10-SDK und Node 20.19 oder neuer. Sie ist ein
Schaufenster, das die veröffentlichten Pakete von nuget.org installiert, so wie es ein Anwender der Bibliothek tun würde.

## Kompatibilität {#compatibility}

| Spezifikationsversion | .NET-Ziel |
|---|---|
| 0.3.0 | net10.0 |

Die Spezifikationsversion ist die in [`spec/VERSION`](spec/VERSION); jedes Paket nennt sie in seinem eigenen README.
Wie Versionen gewählt werden, steht in [VERSIONING.md](VERSIONING.md).
Die Pakete deklarieren Versionsbereiche für die Bibliotheken, die sie umhüllen, nie eine einzelne exakte Version.

## Lizenz {#license}

Apache License 2.0 — siehe [LICENSE](LICENSE).
