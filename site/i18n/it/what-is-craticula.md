---
translates: what-is-craticula
title: Che cos'è Craticula
description: Che cosa compila Craticula, che cosa non fa mai e a che punto si trova.
source_fingerprint: 512000cfdae7ff06fd1d3cb96ba4f1892294a7fd2212e266fc84104c3017b36c
drafter: claude
drafted_on: 2026-11-22
status: machine-drafted
---
# Che cos'è Craticula {#what-craticula-is}

Questa pagina spiega che cosa fa Craticula, che cosa lascia a chi lo usa e a che punto si trova oggi il progetto. È destinata a uno sviluppatore che ha una griglia lato server AG Grid e non ha mai visto Craticula.

Craticula è una libreria .NET che trasforma una richiesta AG Grid Server-Side Row Model in una query per il database. Supporta SQL, MongoDB e OpenSearch.

## Il problema che risolve {#the-problem-it-solves}

Una griglia lato server AG Grid invia al server una richiesta JSON. La richiesta indica quali righe la griglia desidera, come ordinarle, come filtrarle e come raggrupparle.

Ogni team di backend finisce per scrivere lo stesso codice per trasformare quel JSON in una query. Questo codice è facile da sbagliare. Gestione dei valori null, distinzione tra maiuscole e minuscole, paginazione e protezione dalle injection richiedono tutte attenzione.

Craticula è questa traduzione, scritta una sola volta e verificata su esempi condivisi.

## Che cosa compila {#what-it-compiles}

A Craticula si forniscono due elementi:

- la richiesta esattamente come l'ha inviata AG Grid;
- uno schema che elenca le colonne che la griglia può toccare e il modo in cui corrispondono al database.

Craticula restituisce una query eseguibile:

- per SQL, un'istruzione e una lista di parametri;
- per MongoDB, una pipeline di aggregazione;
- per OpenSearch ed Elasticsearch, una query nel loro linguaggio di query JSON.

## Che cosa non fa mai {#what-it-never-does}

Craticula è un compilatore, non un client.

- Non apre mai una connessione a un database.
- Non esegue mai una query.
- Non legge mai i dati.

L'esecuzione della query spetta a chi usa la libreria. Pacchetti adattatori opzionali possono occuparsene, ma sono separati dal nucleo. I pacchetti del nucleo non dipendono mai da essi.

## Backend e versioni di AG Grid supportati {#supported-backends-and-ag-grid-versions}

La prima versione ha come obiettivo questi backend:

- PostgreSQL
- SQL Server
- MySQL e MariaDB
- SQLite
- MongoDB
- OpenSearch
- Elasticsearch

Oracle non è nell'elenco della v1 e il progetto lo considera una questione aperta. Il repository contiene un dialetto Oracle, ma non fa parte dell'impegno assunto.

Sul lato griglia, il README indica le versioni da 31 a 36 di AG Grid Server-Side Row Model. Supporta anche l'infinite row model della Community per le griglie piatte, cioè ordinamento, filtri di testo, numero e data, e paginazione. Raggruppamento di righe, aggregazione, pivot e filtro a insieme sono funzionalità Enterprise e non rientrano nell'impegno per la Community.

La modalità pivot non è supportata. Il parser delle richieste rifiuta una richiesta con la modalità pivot attiva.

## Stato attuale {#current-state}

I pacchetti C# sono pubblicati su nuget.org e nessuno gestisce una demo per i visitatori. Il repository contiene un'applicazione demo da eseguire in autonomia (`examples/demo`), che richiede Docker, l'SDK .NET 10 e Node.

Per provarlo, aggiungere i pacchetti da nuget.org. La [guida rapida C#](quickstart-csharp.html) mostra come. La libreria C# è l'implementazione di riferimento. Il repository descrive i port in TypeScript, Python e Go come previsti dopo il congelamento della specifica. Nessuno di essi esiste ancora.

## Come proseguire {#where-to-go-next}

- [Come una richiesta diventa una query](request-to-query.html) segue una richiesta attraverso la pipeline.
- [Strict e Lenient](strict-and-lenient.html) spiega i due modi di trattare le colonne sconosciute.
- [Il modello di sicurezza](safety-model.html) elenca ciò che Craticula protegge e ciò che non protegge.

## Da dove proviene {#where-this-comes-from}

- [README.md](../../README.md)
- [spec/README.md](../../spec/README.md)
- [csharp/src/Craticula.Core/README.md](../../csharp/src/Craticula.Core/README.md)
- [csharp/src/Craticula.AgGrid/AgGridRequestParser.cs](../../csharp/src/Craticula.AgGrid/AgGridRequestParser.cs)
