---
translates: search-adapters
title: MongoDB- und OpenSearch-Adapter
description: Kompilierte MongoDB- und OpenSearch-Abfragen mit den optionalen Adaptern ausführen, einschließlich Deep Paging.
source_fingerprint: 48d257e31e0add276e9f93959d7b0b4c8302bb0209dc059498cdbe72961005ce
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# MongoDB- und OpenSearch-Adapter {#mongodb-and-opensearch-adapters}

Diese Seite beschreibt die beiden optionalen Pakete, die Craticula-Abfragen auf einem Dokumentenspeicher ausführen: `Craticula.MongoDB.Driver` für MongoDB und `Craticula.OpenSearch.Client` für OpenSearch und Elasticsearch. Sie richtet sich an Entwickler, die einen dieser Speicher verwenden und möchten, dass Craticula die Abfrage nicht nur schreibt, sondern auch ausführt.

## Was der Kern bietet und was die Adapter hinzufügen {#what-the-core-gives-you-and-what-the-adapters-add}

Die Compiler schreiben die Abfrage und hören dort auf.

- `Craticula.Mongo` wandelt eine Anfrage in eine Aggregations-Pipeline um. `MongoPipelineBuilder.Build` liefert eine `MongoQuery` mit dem Collection-Namen und den Pipeline-Stufen.
- `Craticula.Search` wandelt eine Anfrage in einen Such-Body um. `SearchQueryBuilder.Build` liefert eine `SearchQuery` mit dem Indexnamen und dem Body, den `ToArtifact()` als JSON bereitstellt.

Keiner der Compiler hängt von einer Client-Bibliothek ab, und keiner öffnet eine Verbindung. Sie können ihre Ausgabe selbst ausführen.

Die Adapter führen sie für Sie aus. Installieren Sie sie über NuGet: `dotnet add package Craticula.MongoDB.Driver` oder `dotnet add package Craticula.OpenSearch.Client`. Siehe [den C#-Schnellstart](quickstart-csharp.html).

## MongoDB {#mongodb}

`Craticula.MongoDB.Driver` kompiliert mit `Craticula.Mongo` und führt die Pipeline über den offiziellen MongoDB-Treiber aus, im Bereich `[3.13.0, 4.0)`.

```csharp
MongoGridPage result = await MongoGridQuery.FetchPageAsync(
    database,
    new MongoQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    includeRowCount: true);
```

Was er Ihnen bietet:

- `MongoGridQuery.FetchPageAsync` liefert eine `MongoGridPage` mit `Columns`, `Rows` und einem optionalen `RowCount`.
- `MongoGridQuery.CountAsync` führt nur die Zählung aus. Die Zählung ist eine eigene Aggregation, die Sortierung und Seitenfenster weglässt, da eine Zählung beides nicht braucht.
- `MongoExportStream.StreamAsync` streamt für einen Export jedes passende Dokument. Er liest den Cursor des Treibers Batch für Batch, ohne einen Offset durchlaufen zu müssen. Siehe [CSV-Export](csv-export.html).
- Ein Zeitlimit, falls Sie eines setzen. Mit `ResourceLimits.MaxQueryTimeMs` trägt die kompilierte Aggregation `maxTimeMS`, MongoDB bricht eine Abfrage ab, die länger läuft, und der Adapter wirft `QueryTimeoutException`. Auch die Zählung erhält das Limit, ein Export nicht. Siehe [Limits](limits.html).
- `FetchPageAsync` lehnt die Seite ohne Paginierung ab. Eine Anfrage nach allen Zeilen läuft über `MongoExportStream`, der nie das gesamte Ergebnis im Speicher hält.

Was er von Ihnen benötigt:

- Eine geöffnete `IMongoDatabase`. Der Adapter öffnet oder schließt sie nie.
- Ein Schema, das jedes Feld auf einen Dokumentpfad abbildet, etwa `"physical": { "mongo": { "path": "address.city" } }`, und ein `source`, das die Collection benennt.
- MongoDB 4.2 oder neuer. Siehe [Dialekte und Provider](dialects-and-providers.html).

## OpenSearch und Elasticsearch {#opensearch-and-elasticsearch}

`Craticula.OpenSearch.Client` kompiliert mit `Craticula.Search` und führt den Body über den Low-Level-Client von `OpenSearch.Client` aus, im Bereich `[2.2.0, 3.0)`. Es sendet das kompilierte JSON unverändert. Es baut die Anfrage nicht ein zweites Mal mit dem typisierten Client auf.

```csharp
OpenSearchGridPage result = await OpenSearchGridQuery.FetchPageAsync(
    client,
    new SearchQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    gridSessionId,
    cache);
```

Dabei ist `client` ein `IOpenSearchLowLevelClient`, `gridSessionId` ein String, den Sie für die Grid-Sitzung wählen, und `cache` ein `ISearchCursorCache`.

Was es Ihnen bietet:

- `OpenSearchGridQuery.FetchPageAsync` liefert eine `OpenSearchGridPage` mit `Columns`, `Rows`, einem `RowCount`, der null sein kann, und einem `LastRow`-Flag.
- `OpenSearchExportStream.StreamAsync` streamt für einen Export jeden passenden Treffer. Es schreibt immer jede Schemaspalte, in der Reihenfolge von `schema.FieldOrder`, weil der Such-Compiler keine Spaltenprojektion kennt. Übergeben Sie `CsvWriter` je ein `ExportColumn` pro Feld in `schema.FieldOrder`; eine schmalere Liste lässt ihn wegen einer abweichenden Zellenzahl fehlschlagen.
- Ein Zeitlimit, falls Sie eines setzen. Mit `ResourceLimits.MaxQueryTimeMs` trägt jeder Such-Body `timeout`. Eine Suche, der die Zeit ausgeht, antwortet dennoch mit den bis dahin gefundenen Treffern und `timed_out: true`; der Adapter macht daraus eine `QueryTimeoutException` und gibt die Teiltreffer nie als Seite zurück, weder in einer Grid-Seite noch in einem Export-Block. Die eigenen Anfragen eines Exports tragen kein `timeout`. `FetchPageAsync` lehnt die Seite ohne Paginierung ab; verwenden Sie `OpenSearchExportStream`.

Was es von Ihnen benötigt:

- Einen geöffneten Client. Der Adapter baut oder schließt ihn nie.
- Ein Index-Mapping, das zu Ihrem Schema passt. Die kompilierten Abfragen benennen die Unterfelder, die Ihr Schema deklariert, etwa ein `keyword`-Feld. Ein fehlendes Unterfeld kann dazu führen, dass ein Filter ohne Fehlermeldung keine Zeilen findet. Siehe [Leitfaden zu Index und Datenbank](index-guidance.html).
- Einen Cursor-Cache, der so lange lebt wie die Grid-Sitzung. Siehe unten.

### Der Cursor-Cache {#the-cursor-cache}

OpenSearch lehnt einfaches Paging jenseits von 10,000 Zeilen ab. Der Adapter wechselt zu einem Point in Time und `search_after` und merkt sich, wo der letzte Block endete. Dieses Gedächtnis ist der `ISearchCursorCache`, den Sie übergeben.

`InMemorySearchCursorCache` wird mitgeliefert. Erstellen Sie ihn einmal pro Prozess und teilen Sie ihn. Ein neuer Cache pro Anfrage führt dazu, dass jede tiefe Seite wieder bei Zeile null beginnt. `InMemorySearchCursorCache` hält seine Einträge in einem einzigen Prozess. Können die Anfragen einer Grid-Sitzung mehrere Server erreichen, findet eine tiefe Seite auf einem anderen Server keinen Cursor und läuft erneut ab Zeile null. Ein Cache, den alle Server gemeinsam nutzen, würde das vermeiden, doch es wird keiner mitgeliefert.

Derselbe Cursor bedient gruppierte Ebenen. Eine gruppierte Ebene verwendet eine Composite Aggregation, die nicht bei einer Zeile ungleich null beginnen kann. Der Adapter merkt sich den Schlüssel der letzten Gruppe und sendet ihn zurück, um den nächsten Block anzufordern.

### Optionen {#options}

`OpenSearchDeepPagingOptions` ändert das Paging:

| Einstellung | Standard | Wirkung |
|---|---|---|
| `MaxResultWindow` | 10,000 | Die Zeilenzahl, ab der der Adapter zum Cursor wechselt. |
| `WalkBatchSize` | 1,000 | Um wie viele Zeilen ein Aufholschritt vorrückt. |
| `PitKeepAlive` | 5 Minuten | Wie lange ein ungenutzter Cursor gültig bleibt. |
| `ExactRowCount` | `false` | Die Engine nach der exakten Zählung fragen, wenn Sie eine Zeilenzählung anfordern. |
| `Flavour` | `OpenSearch` | Die Engine, `OpenSearch` oder `Elasticsearch`. |

Ohne `ExactRowCount` wird eine Zählung oberhalb des Fensters als unbekannt gemeldet, was günstig ist. Mit der Option zählt die Engine bei jeder ersten Anfrage alle Treffer.

### Elasticsearch {#elasticsearch}

Die kompilierte Anfrage ist für beide Engines dieselbe. Nur die Aufrufe, die einen Point in Time öffnen und schließen, unterscheiden sich. Setzen Sie die Variante in beiden Options-Records, wenn der Cluster Elasticsearch ist:

```csharp
var paging = new OpenSearchDeepPagingOptions { Flavour = SearchEngineFlavour.Elasticsearch };
var export = new OpenSearchExportOptions { Flavour = SearchEngineFlavour.Elasticsearch };
```

Mit der Standardvariante gegen Elasticsearch schlagen ein Fenster jenseits von 10,000 Zeilen und jeder Export mit HTTP 400 fehl.

## Was sie nie tun {#what-they-never-do}

- Sie öffnen, schließen oder konfigurieren nie eine Verbindung oder einen Client.
- Sie wiederholen nie eine fehlgeschlagene Anfrage und setzen nie ein Timeout.
- Sie erzwingen nie eine maximale Anzahl exportierter Zeilen.
- Sie wenden nie Ihre Ressourcenlimits oder die Spaltenprüfungen Ihres Schemas an. Führen Sie zuerst `GridFilterPipeline.Process` aus. Siehe [Das Sicherheitsmodell](safety-model.html).
- Sie exportieren nie ein gruppiertes Ergebnis. Ein Export ist eine flache Liste von Zeilen, und die Export-Streams lehnen eine Anfrage ab, die eine Gruppe enthält.

## Woher diese Seite stammt {#where-this-comes-from}

- [csharp/src/Craticula.MongoDB.Driver/README.md](../../csharp/src/Craticula.MongoDB.Driver/README.md)
- [csharp/src/Craticula.OpenSearch.Client/README.md](../../csharp/src/Craticula.OpenSearch.Client/README.md)
- [csharp/src/Craticula.MongoDB.Driver/MongoGridQuery.cs](../../csharp/src/Craticula.MongoDB.Driver/MongoGridQuery.cs)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchDeepPagingOptions.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchDeepPagingOptions.cs)
- [csharp/src/Craticula.Mongo/README.md](../../csharp/src/Craticula.Mongo/README.md)
- [csharp/src/Craticula.Search/README.md](../../csharp/src/Craticula.Search/README.md)
- Verwandte Seiten: [Entity Framework Core und Dapper](relational-adapters.html), [Paging und Sortierung](paging-and-sorting.html), [Gruppierung und Aggregation](grouping-and-aggregation.html)
