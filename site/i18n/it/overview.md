---
translates: overview
title: Panoramica
description: Che cos'è Craticula, che cosa compila e a che punto è.
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

> Un compilatore, non un client: tradurre le richieste AG Grid Server-Side Row Model in query
> native e sicure per il backend — SQL, MongoDB, OpenSearch/Elasticsearch — a partire da un'unica IR
> canonica, in quattro linguaggi.

**Manutentore:** Christian Stephan ([cstephan.dev](https://cstephan.dev), [LinkedIn](https://www.linkedin.com/in/christian-stephan), [GitHub](https://github.com/cstephan-dev)). Craticula è open source con licenza Apache-2.0;
il sito del progetto è [craticula.pluries.dev](https://craticula.pluries.dev).

**Stato:** progettazione iniziale. I manutentori conservano in privato un documento dei requisiti tecnici (TRD: architettura,
modello di sicurezza, roadmap, questioni aperte); i suoi identificatori di requisito (AR-1, SEM-1, GRP-7 e così via)
sono citati in tutto questo repository, e le regole normative si trovano in [`spec/semantics.md`](spec/semantics.md).

## Perché {#why}

Ogni team backend reimplementa la traduzione di una richiesta AG Grid SSRM
(`filterModel`, `sortModel`, `rowGroupCols`, `groupKeys`, `valueCols`, `startRow`/`endRow`)
in query di database, di solito con intermediari DSL basati su stringhe, operatori mancanti, una semantica
dei valori nulli e della distinzione tra maiuscole e minuscole difettosa, una superficie di injection e nessun supporto per il raggruppamento né per i motori di ricerca. Nessuna
libreria open source mantenuta copre tutto questo da un capo all'altro.

## Come funziona {#how-it-works}

![Come una richiesta diventa una query: una richiesta AG Grid attraversa l'adattatore di richieste e arriva all'IR canonica, e il compilatore di query la trasforma in un artefatto di query (SQL con parametri, una pipeline di aggregazione MongoDB o una query OpenSearch), il tutto verificato rispetto al GridSchema; adattatori di esecuzione opzionali eseguono l'artefatto e restituiscono le righe nella forma della risposta della griglia.](site/diagrams/how-it-works.svg)

Il nucleo non apre mai una connessione: la compilazione è una funzione pura che, a partire da una richiesta della griglia e da
una configurazione dello schema (il confine di sicurezza e di tipizzazione), produce un semplice artefatto di query.
L'esecuzione — eseguire l'artefatto e riportare i risultati nella forma della risposta della griglia — è affidata a
pacchetti di adattatori separati e opzionali, uno per ciascun ecosistema.

## Ambito (v1) {#scope-v1}

- **Adattatore di richieste** (la specifica lo chiama *frontend adapter*; è il lato di ingresso del compilatore e viene eseguito nel vostro server, non nel browser): AG Grid SSRM (v31–v36). L'Infinite Row Model di AG Grid Community è supportato per le griglie piatte
  (ordinamento, filtri di testo, numerici e di data, paginazione; vedere [`spec/fixtures/community-infinite`](spec/fixtures/community-infinite/README.md)).
  Raggruppamento di righe, aggregazione, pivot e filtro a insieme sono funzionalità Enterprise e non fanno parte di tale impegno.
- **Compilatori di query** (i *backend compilers* della specifica, anch'essi nel vostro server): PostgreSQL, SQL Server, MySQL/MariaDB, SQLite, MongoDB, OpenSearch,
  Elasticsearch. Oracle è testato dalla community: la stessa pipeline SQL, con paginazione `FETCH FIRST` (12c e successive).
- **Implementazione di riferimento:** C#/.NET, portata su TypeScript, Python e Go dopo il congelamento
  della specifica alla 1.0.
- **La semantica** (distinzione tra maiuscole e minuscole, gestione e ordinamento dei valori nulli, date e fusi orari, paginazione
  deterministica) è normativa e imposta da una suite condivisa di fixture di conformità, indipendente dal linguaggio.
- L'esportazione CSV/TSV in streaming condivide lo stesso modello di ingresso, solo compilato.

Il §2.2 del TRD (esclusioni) e il suo §14 (roadmap) indicano che cosa è esplicitamente escluso dalla v1.

## Struttura del repository (prevista) {#repository-layout-planned}

```
spec/         IR JSON Schema, semantics.md, conformance fixtures — the source of truth
csharp/       reference implementation (Core, AgGrid adapter, compilers, execution adapters)
typescript/   TypeScript port (after spec freeze)
python/       Python port (after spec freeze)
go/           Go port (after spec freeze)
docs/adr/     architecture decision records (why the design is the way it is)
examples/     demo app (React + AG Grid + one sample backend)
```

## Pacchetti {#packaging}

L'implementazione C# è suddivisa in dieci pacchetti NuGet, tutti pubblicati su nuget.org:

[![NuGet](https://img.shields.io/nuget/v/Craticula.Core?label=nuget)](https://www.nuget.org/packages/Craticula.Core)

[`Craticula.Core`](https://www.nuget.org/packages/Craticula.Core),
[`Craticula.AgGrid`](https://www.nuget.org/packages/Craticula.AgGrid),
[`Craticula.Sql`](https://www.nuget.org/packages/Craticula.Sql),
[`Craticula.Mongo`](https://www.nuget.org/packages/Craticula.Mongo),
[`Craticula.Search`](https://www.nuget.org/packages/Craticula.Search),
[`Craticula.Export.Csv`](https://www.nuget.org/packages/Craticula.Export.Csv),
[`Craticula.EntityFrameworkCore`](https://www.nuget.org/packages/Craticula.EntityFrameworkCore),
[`Craticula.Dapper`](https://www.nuget.org/packages/Craticula.Dapper),
[`Craticula.MongoDB.Driver`](https://www.nuget.org/packages/Craticula.MongoDB.Driver) e
[`Craticula.OpenSearch.Client`](https://www.nuget.org/packages/Craticula.OpenSearch.Client).
Se ne installa uno con `dotnet add package <name>`. Per verificare che i pacchetti si compilino e che un consumatore pulito si compili con essi, eseguire
`bash scripts/pack-smoke.sh` (Python 3.10+ e SDK .NET 10; circa 3 minuti).

## Skill per Claude {#claude-skill}

Una skill per Claude ti guida dal nulla alla prima richiesta di griglia compilata e dice a Claude di rifiutare le scorciatoie non sicure. Installala come plugin di Claude Code:

```text
claude plugin marketplace add pluries/craticula
claude plugin install craticula@craticula
```

Oppure copia la cartella [`skills/craticula`](skills/craticula/SKILL.md) in `~/.claude/skills/craticula/`. La skill è testo: il comportamento di Claude non è garantito. Vedi la [pagina della skill per Claude](https://craticula.pluries.dev/claude-skill.html).

## Licenze delle dipendenze {#dependency-licenses}

Ogni pacchetto NuGet sotto `csharp/`, comprese le dipendenze transitive e i progetti di test, deve avere una licenza accettata dal progetto.
Lo verifica `python3 scripts/check-licenses.py` (Python 3.10+, SDK .NET 10 e nuget.org; ripristinare prima la soluzione con
`dotnet restore Craticula.sln` in `csharp/`, e lo strumento fissato con `dotnet tool restore` nello stesso punto). Lo stesso script viene eseguito nel
job `license-check` di ogni pull request e richiede pochi secondi con una cache dei pacchetti già popolata.

- **Consentite:** MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, 0BSD, Unlicense, PostgreSQL, Zlib
  ([`scripts/license-allowlist.json`](scripts/license-allowlist.json)).
- **Rifiutate:** GPL, LGPL, AGPL, SSPL, BUSL, Elastic, Commons Clause e qualsiasi licenza non commerciale. La riga di errore indica il
  pacchetto, la sua versione, la licenza e il progetto.
- **MPL-2.0:** solo quando un ADR accettato (una riga `Status: Accepted`) in `docs/adr/` nomina MPL-2.0 e il pacchetto.
  Per progetto, il controllo nega per impostazione predefinita: senza un tale ADR, un pacchetto MPL-2.0 viene rifiutato.
- **Eccezioni:** quando lo strumento non riesce a leggere una licenza (un file di licenza o un semplice URL invece di un identificatore SPDX), aggiungere una voce a
  [`scripts/license-overrides.json`](scripts/license-overrides.json) con il pacchetto, la sua versione esatta, la licenza reale e un
  motivo scritto. La licenza deve essere un identificatore SPDX consentito (oppure `"vendor_terms": true` per i termini propri di un fornitore, non SPDX). Un'eccezione
  non annulla mai una licenza che lo strumento ha letto come rifiutata o come MPL-2.0. Una voce senza motivo fa fallire il controllo, così come una voce che
  non corrisponde più ad alcun pacchetto.
- **Insidie:** `MySql.Data` (GPL) viene rifiutato per nome: usare `MySqlConnector`. Il driver Oracle `Oracle.ManagedDataAccess.Core` e
  `Testcontainers.Oracle` sono accettati solo nei progetti di test sotto `csharp/tests`, mai in un pacchetto sotto `csharp/src`.

## Demo {#demo}

Provatela online: [PostgreSQL](https://craticula-pg.pluries.dev) e [MongoDB](https://craticula-mongo.pluries.dev). Entrambe mostrano gli stessi
ordini sintetici attraverso la stessa pagina AG Grid; sono in sola lettura e con limitazione della frequenza delle richieste.

[`examples/demo`](examples/demo/README.md) è l'applicazione che c'è dietro: una pagina AG Grid che legge gli stessi ordini da PostgreSQL o da
MongoDB attraverso un'API C# costruita sulla libreria. Per eseguirla in proprio servono Docker, l'SDK .NET 10 e Node 20.19 o successivo. È una
vetrina che installa i pacchetti pubblicati da nuget.org, come farebbe un utilizzatore della libreria.

## Compatibilità {#compatibility}

| Versione della specifica | Target .NET |
|---|---|
| 1.0.0 | net10.0 |

I pacchetti puntano a `net10.0`. Funzionano anche sul runtime .NET 11: la compilazione e i test offline passano con il .NET SDK 11.0.100 (verificato il 2026-11-27; il ragionamento è in ADR-0015).

La versione della specifica è quella di [`spec/VERSION`](spec/VERSION); ogni pacchetto la riporta nel proprio README.
Il modo in cui vengono scelte le versioni è descritto in [VERSIONING.md](VERSIONING.md).
I pacchetti dichiarano intervalli di versioni per le librerie che incapsulano, mai una singola versione esatta.

## Licenza {#license}

Apache License 2.0 — vedere [LICENSE](LICENSE).
