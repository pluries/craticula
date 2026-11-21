---
translates: csv-export
title: CSV-Export
description: Die Zeilen einer Grid als Stream in eine CSV-Datei schreiben, mit demselben Anfragemodell und denselben Prüfungen.
source_fingerprint: fa1523a098455aba885855279c19504be3084b49be415b2a066c79e11c573ace
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# CSV-Export {#csv-export}

Diese Seite beschreibt, wie Craticula die Zeilen, die eine Grid anzeigt, als CSV- oder TSV-Datei exportiert: welcher Teil Aufgabe von Craticula ist, welcher Teil Ihre Aufgabe ist und welche Einstellungen die Datei verändern. Sie richtet sich an Entwickler, die einer Grid auf Craticula-Basis eine Export-Schaltfläche hinzufügen.

## Zwei Teile, ein Stream dazwischen {#two-parts-one-stream-between-them}

Ein Export besteht aus zwei Schritten, und zwei Bausteine von Craticula erledigen sie.

1. **Die Zeilen lesen.** Ein Ausführungsadapter führt die Abfrage aus und liefert einen Stream von Zeilen zurück. `DapperExportStream`, `EfCoreExportStream`, `MongoExportStream` und `OpenSearchExportStream` übernehmen das für ihre jeweiligen Backends. Siehe [Entity Framework Core und Dapper](relational-adapters.html) und [MongoDB- und OpenSearch-Adapter](search-adapters.html).
2. **Die Datei schreiben.** Das Paket `Craticula.Export.Csv` nimmt diesen Stream und schreibt die Bytes. Es weiß nichts über die Datenbank. `CsvWriter` ist sein Einstiegspunkt.

Da der Writer jeweils eine Zeile liest und jeden Datensatz sofort schreibt, braucht ein Export mit einer Million Zeilen etwa genauso viel Speicher wie einer mit zehn Zeilen. Die relationalen Adapter und der OpenSearch-Adapter lesen die Zeilen in Blöcken (standardmäßig 5,000), der MongoDB-Adapter liest einen einzigen Cursor Batch für Batch, nie mit wachsendem Offset, und die seitenweisen `FetchPageAsync`-Aufrufe lehnen eine Anfrage nach allen Zeilen ab, sodass nur der Export-Stream das vollständige Ergebnis lesen kann. Ein langsamer Download bremst das Lesen, anstatt den Speicher zu füllen.

## Was die Grid sendet {#what-the-grid-sends}

Eine Export-Anfrage ist eine gewöhnliche Grid-Anfrage mit bis zu drei weiteren Membern:

- `exportFormat`, entweder `"csv"` oder `"tsv"`. Es kennzeichnet die Anfrage als Export. Werden die beiden anderen Member ohne ihn gesendet, wird die Anfrage abgelehnt.
- `exportScope`, entweder `"all"` oder `"page"`. Der Standardwert ist `"all"`: alle Zeilen, die zu Filter und Sortierung passen, unabhängig von `startRow` und `endRow`. `"page"` behält den Zeilenbereich der Anfrage bei. Eine Anfrage, die kein Fenster sendet und kein Export ist, erhält stattdessen eine Standardseite von 100 Zeilen; siehe [Paging und Sortierung](paging-and-sorting.html).
- `exportColumns`, eine optionale Liste von Einträgen der Form `{ "colId": "...", "header": "..." }`.

Filter und Sortierung werden immer beachtet.

## Welche Spalten, und was die Kopfzeilen sagen {#which-columns-and-what-the-headers-say}

Hat die Anfrage kein `exportColumns`, enthält der Export alle Spalten, die das Schema als `exportable` kennzeichnet, in der Reihenfolge, in der das Schema sie deklariert. Eine Spalte ist exportierbar, es sei denn, das Schema gibt `"exportable": false` an.

Hat die Anfrage `exportColumns`, enthält der Export genau diese Spalten in dieser Reihenfolge. Abgelehnt werden eine Spalte, die nicht im Schema steht, nicht exportierbar ist oder doppelt aufgeführt wird, sowie eine leere Liste. Das gilt im Strict- wie im Lenient-Modus.

Die Kopfzeile einer Spalte stammt der Reihe nach aus:

1. dem `header` der Anfrage;
2. dem `label` des Schemas;
3. der Spalten-ID.

Der Parser ermittelt das einmal und legt es in `ExportSpec.Columns` ab.

## Gruppierung entfällt {#grouping-is-dropped}

Ein Export ist eine flache Liste von Zeilen. Der Adapter entfernt `rowGroupCols`, `valueCols` und `groupKeys` aus einer Export-Anfrage; der Export einer gruppierten Grid liefert daher einfache Zeilen unter dem aktuellen Filter und der aktuellen Sortierung.

## Alles zusammen {#putting-it-together}

Der Parser benötigt das Schema, um einen Export aufzulösen; übergeben Sie es daher in `AgGridParseOptions`. Dieses Beispiel behandelt `exportScope` mit dem Wert `"all"`. Bei `"page"` ist `parsed.Page` ein Zeilenbereich, und `StreamAsync` lehnt ihn ab. Es verwendet Dapper und PostgreSQL. `connection` ist eine geöffnete `IDbConnection`, und `destination` ist ein `Stream`, etwa der Body der HTTP-Antwort.

```csharp
// using Craticula.AgGrid; using Craticula.Core.Export; using Craticula.Core.Ir;
// using Craticula.Core.Schema; using Craticula.Dapper; using Craticula.Export.Csv; using Craticula.Sql;
AgGridParsedRequest parsed = AgGridRequestParser.Parse(requestJson, new AgGridParseOptions { Schema = schema });
ExportSpec export = parsed.Export!;

FilterNode? filter = GridFilterPipeline.Process(
    parsed.NativeFilter, parsed.CustomFilters, parsed.Page, schema, new ResourceLimits());

IAsyncEnumerable<ExportRow> rows = DapperExportStream.StreamAsync(
    connection,
    new SqlQueryRequest
    {
        Schema = schema,
        Filter = filter,
        Sort = parsed.Sort,
        Page = parsed.Page,
        Projection = export.ProjectionColumns
    },
    PostgresDialect.Instance);

long rowsWritten = await CsvWriter.WriteAsync(
    rows, export.Columns, CsvWriterOptions.ForFormat(export.Format), destination);
```

`CsvWriterOptions.ForFormat` ist der Weg, auf dem das angeforderte Format in die Datei gelangt. Es wählt ein Komma für CSV und einen Tabulator für TSV. Der Writer sieht die Anfrage nie und kann das daher nicht selbst tun. Das Ergebnis der Task ist die Anzahl der geschriebenen Datenzeilen, ohne die Kopfzeile.

Die Export-Streams der Adapter akzeptieren nur das gesamte Ergebnis (`exportScope` mit dem Wert `"all"`). Ein seitenbezogener Export ist ein einzelner begrenzter Block, also dieselbe Abfrage, die ein Grid-Block ausführt. Rufen Sie ihn mit der Seitenmethode des Adapters ab und schreiben Sie diese Zeilen selbst.

## Wie die Datei aussieht {#what-the-file-looks-like}

Standardmäßig gilt:

- eine Kopfzeile steht am Anfang;
- Felder werden durch ein Komma getrennt, und Zeilen enden mit einem Wagenrücklauf und einem Zeilenvorschub;
- ein Feld, das das Trennzeichen, ein doppeltes Anführungszeichen oder einen Zeilenumbruch enthält, wird in doppelte Anführungszeichen gesetzt;
- die Datei beginnt mit einer Byte-Order-Mark, weil Excel Unicode-Text ohne sie falsch interpretiert;
- ein Nullwert wird zu einem leeren Feld;
- Boolesche Werte lauten `true` und `false`;
- Datumswerte werden als `2026-01-05` geschrieben und Datums-Zeit-Werte als `2026-01-05T14:30:45`, mit dem Offset, wenn der Wert einen hat;
- ein Dezimalwert behält seine eigene Anzahl von Nachkommastellen.

## Was Sie ändern können {#what-you-can-change}

`CsvWriterOptions` bietet diese Einstellungen:

| Einstellung | Standard | Wirkung |
|---|---|---|
| `Delimiter` | `,` | Das Feldtrennzeichen. |
| `IncludeHeaderRow` | `true` | Ob die Kopfzeile geschrieben wird. |
| `WriteByteOrderMark` | `true` | Ob die Datei mit einer Byte-Order-Mark beginnt. |
| `DecimalSeparator` | `.` | Das Trennzeichen in Dezimalzahlen. |
| `HardenFormulaInjection` | `true` | Siehe unten. |

`CsvWriterOptions.SemicolonPreset` setzt das Trennzeichen auf ein Semikolon, für Gebietsschemas, in denen Excel eines erwartet.

Das Schema kann das Format einer einzelnen Spalte mit einem `format`-Block überschreiben:

```json
"orderDate": { "type": "date", "format": { "datePattern": "dd/MM/yyyy" } },
"amount": { "type": "decimal", "format": { "decimalSeparator": "," } }
```

Der Writer lehnt ein Dezimaltrennzeichen ab, das dem Feldtrennzeichen entspricht. Ein Komma an beiden Stellen würde jede Dezimalzahl in Text in Anführungszeichen verwandeln. Er lehnt auch ein Datumsmuster ab, das er nicht anwenden kann. `GridSchema.Parse` prüft das Muster beim Laden des Schemas; ein fehlerhaftes Muster schlägt daher beim Start fehl und nicht mitten in einem Download.

## Schutz vor Tabellenkalkulationsformeln {#protection-against-spreadsheet-formulas}

Eine Tabellenkalkulation behandelt eine Zelle, die mit `=`, `+`, `-`, `@`, einem Tabulator oder einem Wagenrücklauf beginnt, als Formel. Ein von einem Benutzer eingegebener Wert kann dann als Formel in der Tabellenkalkulation derjenigen Person ausgeführt werden, die den Export öffnet.

Standardmäßig setzt der Writer vor solchen Text ein Apostroph. Das gilt für jede Kopfzeile und jede Textzelle. Zahlen, Datumswerte oder Boolesche Werte, die der Writer selbst formatiert hat, bleiben unberührt; eine negative Zahl bleibt also eine Zahl.

Mit `HardenFormulaInjection = false` können Sie das abschalten. Das Apostroph lässt sich danach nicht mehr entfernen; schalten Sie die Funktion daher nur ab, wenn ein Programm die Datei liest und niemand sie in einer Tabellenkalkulation öffnet.

## Was in Ihrer Verantwortung bleibt {#what-stays-with-you}

- **Die Zeilenobergrenze.** Weder die Adapter noch der Writer erzwingen eine maximale Anzahl exportierter Zeilen. Fügen Sie ein eigenes Limit hinzu, wenn der Export öffentlich ist.
- **Das Limit der Seitengröße.** Es gilt nicht für einen Export des gesamten Ergebnisses (`exportScope` mit dem Wert `"all"`), der keine Seite hat. Ein seitenbezogener Export behält seinen Zeilenbereich, und das Limit der Seitengröße gilt für ihn. Siehe [Limits](limits.html).
- **Dapper lehnt manche Exporte ab.** `DapperExportStream` lehnt ein Schema ab, dessen stabiler Schlüssel eine Textspalte ist, und einen Export, bei dem ein Text-Sortierschlüssel in den exportierten Zeilen eine leere Zeichenfolge enthält (auf allen Dialekten außer Oracle). Verwenden Sie einen numerischen Schlüssel oder einen Datumsschlüssel als stabilen Schlüssel, oder rufen Sie die Daten seitenweise mit `DapperGridQuery.FetchPageAsync` ab. `EfCoreExportStream` hat keine solche Prüfung.
- **Der Download.** Inhaltstyp, Dateiname und Verbindung liegen bei Ihnen. Die Demo legt sie in `examples/demo/Api/Routes/GridRoutes.cs` fest.
- **Die OpenSearch-Spaltenliste.** Der OpenSearch-Export schreibt immer jede Schemaspalte, in der Reihenfolge von `schema.FieldOrder`. Übergeben Sie `CsvWriter` die vollständige Liste, je ein `ExportColumn` pro Feld in `schema.FieldOrder`. Ein schmaleres `export.Columns` lässt `CsvWriter` mit einer `CsvWriterException` fehlschlagen, weil die Zellenzahl nicht übereinstimmt.

## Woher diese Seite stammt {#where-this-comes-from}

- [csharp/src/Craticula.Export.Csv/README.md](../../csharp/src/Craticula.Export.Csv/README.md)
- [csharp/src/Craticula.Export.Csv/CsvWriter.cs](../../csharp/src/Craticula.Export.Csv/CsvWriter.cs)
- [csharp/src/Craticula.Export.Csv/CsvWriterOptions.cs](../../csharp/src/Craticula.Export.Csv/CsvWriterOptions.cs)
- [csharp/src/Craticula.AgGrid/ExportSpec.cs](../../csharp/src/Craticula.AgGrid/ExportSpec.cs)
- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/page-export](../../spec/fixtures/page-export/README.md)
- [examples/demo/Api/Routes/GridRoutes.cs](../../examples/demo/Api/Routes/GridRoutes.cs)
- Verwandte Seiten: [Paging und Sortierung](paging-and-sorting.html), [Das GridSchema](the-gridschema.html), [Sicherheitsmodell](safety-model.html)
