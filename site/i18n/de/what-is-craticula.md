---
translates: what-is-craticula
title: Was Craticula ist
description: Was Craticula kompiliert, was es nie tut und wo es heute steht.
source_fingerprint: 512000cfdae7ff06fd1d3cb96ba4f1892294a7fd2212e266fc84104c3017b36c
drafter: claude
drafted_on: 2026-11-22
status: machine-drafted
---
# Was Craticula ist {#what-craticula-is}

Diese Seite erklärt, was Craticula tut, was es Ihnen überlässt und wo das Projekt heute steht. Sie richtet sich an Entwickler, die ein serverseitiges Grid von AG Grid betreiben und Craticula noch nie gesehen haben.

Craticula ist eine .NET-Bibliothek, die eine Anfrage des AG Grid Server-Side Row Model in eine Datenbankabfrage übersetzt. Sie unterstützt SQL, MongoDB und OpenSearch.

## Das Problem, das es löst {#the-problem-it-solves}

Ein serverseitiges Grid von AG Grid sendet Ihrem Server eine JSON-Anfrage. Die Anfrage legt fest, welche Zeilen das Grid haben möchte, wie sie sortiert, gefiltert und gruppiert werden sollen.

Jedes Backend-Team schreibt am Ende denselben Code, um dieses JSON in eine Abfrage zu überführen. Dieser Code ist leicht fehlerhaft. Null-Behandlung, Groß-/Kleinschreibung, Paging und Schutz vor Injection erfordern alle Sorgfalt.

Craticula ist diese Übersetzung, einmal geschrieben und gegen gemeinsame Beispiele getestet.

## Was es kompiliert {#what-it-compiles}

Sie geben Craticula zwei Dinge:

- die Anfrage genau so, wie AG Grid sie gesendet hat;
- ein Schema, das die Spalten auflistet, die das Grid ansprechen darf, und wie sie auf Ihre Datenbank abgebildet werden.

Craticula liefert eine Abfrage zurück, die Sie ausführen können:

- für SQL eine Anweisung und eine Liste von Parametern;
- für MongoDB eine Aggregation Pipeline;
- für OpenSearch und Elasticsearch eine Abfrage in deren JSON-Abfragesprache.

## Was es nie tut {#what-it-never-does}

Craticula ist ein Compiler, kein Client.

- Es öffnet nie eine Verbindung zu einer Datenbank.
- Es führt nie eine Abfrage aus.
- Es liest nie Ihre Daten.

Die Abfrage auszuführen ist Ihre Aufgabe. Optionale Adapterpakete können das für Sie übernehmen, sie sind aber vom Kern getrennt. Die Kernpakete hängen nie von ihnen ab.

## Unterstützte Backends und AG Grid Versionen {#supported-backends-and-ag-grid-versions}

Die erste Version zielt auf diese Backends:

- PostgreSQL
- SQL Server
- MySQL und MariaDB
- SQLite
- MongoDB
- OpenSearch
- Elasticsearch

Oracle steht nicht auf der Liste der v1, und das Projekt behandelt es als offene Frage. Das Repository enthält einen Oracle-Dialekt, er ist aber nicht Teil des Versprechens.

Auf der Grid-Seite nennt die README die Versionen 31 bis 36 des AG Grid Server-Side Row Model. Unterstützt wird außerdem das Infinite Row Model der Community für flache Grids. Das umfasst Sortierung, Text-, Zahlen- und Datumsfilter sowie Paging. Zeilengruppierung, Aggregation, Pivot und der Set-Filter sind Enterprise-Funktionen und nicht Teil des Versprechens für die Community.

Der Pivot-Modus wird nicht unterstützt. Der Anfrage-Parser lehnt eine Anfrage mit aktiviertem Pivot-Modus ab.

## Aktueller Stand {#current-state}

Die C#-Pakete sind auf nuget.org veröffentlicht, und niemand betreibt eine Demo für Besucher. Das Repository enthält eine Demo-Anwendung, die Sie selbst ausführen (`examples/demo`) und die Docker, das .NET 10 SDK und Node benötigt.

Um es auszuprobieren, fügen Sie die Pakete von nuget.org hinzu. Die [C#-Schnellstartanleitung](quickstart-csharp.html) zeigt, wie. Die C#-Bibliothek ist die Referenzimplementierung. Das Repository beschreibt Portierungen nach TypeScript, Python und Go als geplant für die Zeit nach dem Einfrieren der Spezifikation. Keine davon existiert bisher.

## Wie es weitergeht {#where-to-go-next}

- [Wie aus einer Anfrage eine Abfrage wird](request-to-query.html) verfolgt eine Anfrage durch die Pipeline.
- [Strict und Lenient](strict-and-lenient.html) erklärt die beiden Arten, mit unbekannten Spalten umzugehen.
- [Das Sicherheitsmodell](safety-model.html) listet auf, wovor Craticula schützt und wovor nicht.

## Woher das stammt {#where-this-comes-from}

- [README.md](../../README.md)
- [spec/README.md](../../spec/README.md)
- [csharp/src/Craticula.Core/README.md](../../csharp/src/Craticula.Core/README.md)
- [csharp/src/Craticula.AgGrid/AgGridRequestParser.cs](../../csharp/src/Craticula.AgGrid/AgGridRequestParser.cs)
