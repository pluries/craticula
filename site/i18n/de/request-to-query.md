---
translates: request-to-query
title: Wie aus einer Anfrage eine Abfrage wird
description: Der Weg von einer Anfrage von AG Grid zu einer Anweisung mit Parametern.
source_fingerprint: 6c0315a52de692dbf39fc149aa86390474630dd3c2eb2282d8985f93da818dc0
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Wie aus einer Anfrage eine Abfrage wird {#how-a-request-becomes-a-query}

Diese Seite verfolgt eine Anfrage von AG Grid Schritt für Schritt durch Craticula, bis sie zu einer Abfrage mit Parametern wird. Sie richtet sich an Entwickler, die wissen möchten, was zwischen Grid und Datenbank geschieht und warum es mehrere Schritte gibt.

## Der Weg {#the-path}

```text
request JSON -> adapter -> canonical form -> compiler -> query + parameters
```

1. **Anfrage-JSON.** Das Grid sendet es. Craticula verändert nicht, was das Grid sendet.
2. **Adapter.** Der Adapter für AG Grid liest das JSON und überführt es in die kanonische Form. Er weist JSON ab, das er nicht versteht.
3. **Kanonische Form.** Das Projekt nennt sie IR, kurz für Intermediate Representation (Zwischendarstellung). Sie ist eine einzige Beschreibung von Filtern, Sortierung, Gruppierung und Paging, die weder von AG Grid noch von einer Datenbank abhängt.
4. **Prüfungen.** Vor dem Kompilieren prüft Craticula die kanonische Form gegen Ihr Schema und die Ressourcenlimits. Außerdem wandelt es jeden Wert in den Typ um, den das Schema deklariert.
5. **Compiler.** Pro Backend schreibt ein Compiler die Abfrage. Der SQL-Compiler hat für jeden Datenbankdialekt einen eigenen Writer.
6. **Abfrage und Parameter.** Für SQL erhalten Sie den Text der Anweisung plus eine Liste von Werten. Die Werte sind nie Teil des Textes.

Weil jedes Backend dieselbe kanonische Form liest, bedeutet dieselbe Anfrage überall dasselbe. Die Regeln für Details wie Null-Behandlung und Groß-/Kleinschreibung sind einmal in der Spezifikation festgehalten, und jeder Compiler folgt ihnen.

## Das Schema ist die Grenze {#the-schema-is-the-boundary}

Das Schema ist ein JSON-Dokument, das Sie schreiben. Es benennt die Tabelle oder Collection und die Spalten, die das Grid verwenden darf. Jede Spalte hat einen Typ und einen physischen Namen in der Datenbank. Außerdem benennt es einen stabilen Schlüssel, eine Spalte mit eindeutigen Werten, mit der Craticula das Paging in fester Reihenfolge hält.

Eine Spalte, die nicht im Schema steht, kann keine Abfrage erreichen. Wie das funktioniert, steht unter [Das Sicherheitsmodell](safety-model.html).

## Was die Anfrage verlangen kann {#what-the-request-can-ask-for}

- **Paging.** Das Grid fragt einen Zeilenbereich an, etwa die ersten 50. Craticula macht daraus ein Limit und einen Offset oder das Äquivalent für Ihr Backend. Eine Seite hat eine maximale Größe.
- **Sortierung.** Die Sortierung läuft in der Reihenfolge, in der das Grid sie gesendet hat. Craticula hängt am Ende den stabilen Schlüssel an, damit Zeilen mit gleichen Werten immer in derselben Reihenfolge zurückkommen.
- **Filterung.** Text-, Zahlen- und Datumsfilter werden zu Vergleichen, die mit AND oder OR verknüpft sind. Bei Text ist der Vergleich standardmäßig ohne Beachtung der Groß-/Kleinschreibung.
- **Gruppierung.** Bei gruppierten Grids enthält die Anfrage die Gruppenspalten, die bereits geöffneten Gruppenschlüssel und die zu berechnenden Aggregationen. Craticula baut die gruppierte Abfrage für die Ebene, nach der gefragt wird.

## Ein kleines Beispiel {#a-small-example}

Dies ist die Anfrage aus der Schnellstartanleitung. Sie verlangt Kunden, deren Name "acme" enthält und deren Betrag über 100 liegt, größte Beträge zuerst, Zeilen 0 bis 50.

```json
{
  "startRow": 0,
  "endRow": 50,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "customer": { "filterType": "text", "type": "contains", "filter": "acme" },
    "amount": { "filterType": "number", "type": "greaterThan", "filter": 100 }
  },
  "sortModel": [ { "colId": "amount", "sort": "desc" } ]
}
```

Für PostgreSQL gibt das Programm der Schnellstartanleitung diese Anweisung und diese Parameter aus:

```sql
SELECT * FROM "orders" WHERE ("customer" ILIKE '%' || $1 || '%' ESCAPE '\' AND "amount" > $2::numeric) ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'acme', '100', 50, 0
```

Beachten Sie, was geschehen ist:

- "acme" und 100 stehen nicht im Text. Sie sind die Parameter.
- Die Namen von Tabelle und Spalten stammen aus dem Schema, nicht aus der Anfrage.
- Die Sortierung endet mit `id`, dem stabilen Schlüssel des Schemas.
- Der Seitenbereich wurde zu `LIMIT 50 OFFSET 0`.

SQL Server erhält aus derselben Anfrage eine andere Anweisung, weil es den Vergleich ohne Beachtung der Groß-/Kleinschreibung und die Anordnung von Nullwerten anders ausdrückt. Die [C#-Schnellstartanleitung](quickstart-csharp.html) zeigt beides.

## Was Sie in C# schreiben {#what-you-write-in-c}

In der Schnellstartanleitung tut der Code vier Dinge in dieser Reihenfolge:

1. Das Schema mit `GridSchema.Parse` parsen.
2. Die Anfrage mit `AgGridRequestParser.Parse` parsen.
3. Mit `GridFilterPipeline.Process` validieren. Das wendet die Spaltenprüfung, die Limits und die Typumwandlung an.
4. Mit `SqlQueryBuilder.Build` und einem Dialekt wie `PostgresDialect.Instance` kompilieren.

MongoDB und OpenSearch haben eigene Builder, `MongoPipelineBuilder` und `SearchQueryBuilder`.

Um die Gesamtzahl der Zeilen neben einer Seite anzuzeigen, hat jeder Compiler außerdem `BuildCount`. Es nutzt denselben Filter, aber keine Sortierung und kein Zeilenfenster, denn eine Zählung braucht sie nicht. Übergeben Sie `GridFilterPipeline.Process` für eine Zählung eine `NonePage`, damit eine große Seitengröße sie nicht scheitern lassen kann.

## Woher das stammt {#where-this-comes-from}

- [site/pages/quickstart-csharp.md](quickstart-csharp.md)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
- [spec/semantics.md](../../spec/semantics.md)
- [spec/ir.schema.json](../../spec/ir.schema.json)
- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs](../../csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs)
- [spec/fixtures/operators](../../spec/fixtures/operators/001-eq-string/description.md)
