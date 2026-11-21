---
translates: relational-adapters
title: Entity Framework Core und Dapper
description: Was die beiden relationalen Adapter leisten, was sie benötigen und was sie nie tun.
source_fingerprint: c7c6226b52fe85563de296ccf30f4b6133346e53ef471b90257c33696e64481f
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Entity Framework Core und Dapper {#entity-framework-core-and-dapper}

Diese Seite beschreibt die beiden optionalen Pakete, die Craticula-Abfragen auf einer relationalen Datenbank ausführen: `Craticula.Dapper` und `Craticula.EntityFrameworkCore`. Sie richtet sich an Entwickler, die eine SQL-Datenbank haben und möchten, dass Craticula die Abfrage nicht nur schreibt, sondern auch ausführt.

## Warum es Adapter gibt {#why-adapters-exist}

Die Kernpakete kompilieren nur. Sie öffnen nie eine Verbindung und führen nie etwas aus. Ein Adapter schließt diese Lücke für eine Datenzugriffsbibliothek. Er kompiliert die Anfrage, führt sie aus und liefert Ihnen Zeilen.

Adapter sind optional. Die Kernpakete hängen nie von ihnen ab. Sie können sie weglassen und die kompilierte Anweisung selbst mit einer beliebigen Bibliothek ausführen.

Installieren Sie sie über NuGet: `dotnet add package Craticula.Dapper` oder `dotnet add package Craticula.EntityFrameworkCore`. Siehe [den C#-Schnellstart](quickstart-csharp.html).

## Dapper {#dapper}

`Craticula.Dapper` kompiliert mit `Craticula.Sql` und führt die Anweisung auf einer Verbindung aus, die Sie übergeben. Verwenden Sie es, wenn Sie das SQL sehen und steuern möchten.

```csharp
DapperGridPage result = await DapperGridQuery.FetchPageAsync(
    openConnection,
    new SqlQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    PostgresDialect.Instance,
    includeRowCount: true);
```

Was es Ihnen bietet:

- `DapperGridQuery.FetchPageAsync` liefert eine Seite. `DapperGridPage` enthält die `Columns`, die `Rows` und ein optionales `RowCount`.
- `DapperGridQuery.CountAsync` führt nur die Zählung aus.
- `DapperExportStream.StreamAsync` streamt für einen Export jede passende Zeile. Siehe [CSV-Export](csv-export.html).
- `FetchPageAsync` lehnt die Seite ohne Paginierung (`NonePage`) ab, sodass ein Aufruf nie alle Zeilen in den Speicher lädt. Eine Anfrage nach allen Zeilen läuft über `DapperExportStream`.

Was es von Ihnen benötigt:

- Eine geöffnete `IDbConnection`. Der Adapter öffnet oder schließt sie nie.
- Den Dialekt, der zu Ihrer Datenbank passt. Siehe [Dialekte und Provider](dialects-and-providers.html).
- Dapper selbst, im Bereich `[2.1.89, 3.0)`.

Gruppierte Anfragen funktionieren über dieselbe Methode. Der SQL-Compiler schreibt die gruppierte Anweisung bereits, der Adapter führt sie also nur aus.

## Entity Framework Core {#entity-framework-core}

`Craticula.EntityFrameworkCore` schreibt keinen SQL-Text. Es baut `IQueryable<T>`-Ausdrucksbäume, und der EF-Core-Provider übersetzt sie in SQL. Verwenden Sie es, wenn Sie bereits einen `DbContext` haben und möchten, dass dessen globale Abfragefilter, etwa ein Mandantenfilter, gelten.

```csharp
var request = new EfCoreQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page };

EfCoreGridPage result = await EfCoreGridQuery.FetchPageAsync(
    source, request, EfCoreProviderSemantics.Sqlite, includeRowCount: true);
```

Was es Ihnen bietet:

- `EfCoreGridQuery.FetchPageAsync` liefert eine Seite, in einer `EfCoreGridPage`, die wie die von Dapper aufgebaut ist.
- `EfCoreGridQuery.CountAsync` führt nur die Zählung aus.
- `EfCoreExportStream.StreamAsync` streamt Zeilen für einen Export.
- `FetchPageAsync` lehnt die Seite ohne Paginierung ab, wie es auch der Dapper-Adapter tut. Eine Anfrage nach allen Zeilen läuft über `EfCoreExportStream`.

Was es von Ihnen benötigt:

- **Eine Quellabfrage.** Übergeben Sie ein `DbSet<T>` oder, wenn Sie keine Entitätsklassen haben, `GridSchemaPropertyBag.Query(context, schema)`. Für die zweite Form rufen Sie `GridSchemaPropertyBag.Configure` in `OnModelCreating` auf.
- **Übereinstimmende Eigenschaftsnamen.** Jedes Feld wird als EF-Eigenschaft gelesen, die nach seinem `physical.sql.column` benannt ist, oder nach der Spalten-ID, wenn es keines gibt. Eine Klasse, die ihre Spalten mit `HasColumnName` umbenennt, muss dazu passen.
- **Einen `EfCoreProviderSemantics`-Wert.** Er nennt fünf Fakten über Ihre Datenbank, die EF Craticula nicht mitteilen kann, etwa den Namen der Collation ohne Beachtung der Groß- und Kleinschreibung. Es wird nur `EfCoreProviderSemantics.Sqlite` mitgeliefert, weil nur dieser Wert gemessen wurde. Für eine andere Engine deklarieren Sie Ihren eigenen, einmal, neben Ihrem `DbContext`.

Die Felder des Schemas müssen ein einfaches `physical.sql.column` verwenden. Ein Feld mit `qualifiedColumn` oder `expression` wird abgelehnt, weil keines von beiden eine Entsprechung in einem Ausdrucksbaum hat.

Kann ein `DbContext`-Typ aus mehr als einem Schema aufgebaut werden, registrieren Sie `GridSchemaModelCacheKeyFactory` und implementieren Sie `IGridSchemaModel` auf dem Kontext. Ohne das verwendet EF das Modell des ersten Schemas für das nächste Schema weiter und schlägt mit Fehlern fehl, die das Caching nicht erwähnen.

### Zwei stille Fallen {#two-silent-traps}

Beide liefern falsche Zeilen ohne Fehlermeldung. Der Adapter sieht weder Ihr Modell noch Ihre Collations und kann sich daher nicht dagegen absichern.

- **SQLite-Datums- und Zeitwerte.** Speichern Sie ein `datetime` als Text der Form `yyyy-MM-ddTHH:mm:ss.fffZ` und bilden Sie in Ihrem `DbContext` jedes `DateTime` auf diesen Text und von ihm ab. Das eigene Mapping von EF verwendet eine andere Form, und SQLite vergleicht Text Zeichen für Zeichen.
- **`PatternMatchFoldsCase`.** Es gibt an, ob das `LIKE` der Engine die Groß- und Kleinschreibung ignoriert. Verwenden Sie `true` für SQLite. Für SQL Server und MySQL verwenden Sie `false`, es sei denn, jede durchsuchbare Spalte hat eine Collation, die Groß- und Kleinschreibung ignoriert. Eine Spalte mit binärer Collation findet sonst nur die exakte Schreibweise.

Datums- und Zeitzellen verlassen eine Seite oder einen Export als UTC-Werte, unabhängig davon, was der Provider zurückgegeben hat.

## Was beide Adapter gemeinsam haben {#what-both-adapters-share}

- **Zeilenzählungen sind Opt-in.** Die Zählung ist ein zweiter Roundtrip und daher aus, es sei denn, Sie übergeben `includeRowCount`. Eine Grid braucht sie einmal pro Filteränderung, nicht einmal pro Block.
- **Exporte verwenden nie einen Offset.** Sie lesen die Zeilen in Blöcken von 5,000, indem sie die Sortierschlüssel durchlaufen, sodass ein später Block genauso viel kostet wie ein früher. `DapperExportOptions` und `EfCoreExportOptions` haben ein `ChunkSize`, um das zu ändern. Der Export benötigt einen wirklich eindeutigen stabilen Schlüssel. Ein Duplikat wird erkannt und löst eine Ausnahme aus.
- **Dapper lehnt manche Exporte ab.** `DapperExportStream` lehnt ein Schema ab, dessen stabiler Schlüssel eine Textspalte ist. Es lehnt auch einen Export ab, bei dem ein Text-Sortierschlüssel in den exportierten Zeilen eine leere Zeichenfolge enthält, auf allen Dialekten außer Oracle. Verwenden Sie in beiden Fällen einen numerischen Schlüssel oder einen Datumsschlüssel als stabilen Schlüssel, oder rufen Sie die Daten seitenweise mit `DapperGridQuery.FetchPageAsync` ab. `EfCoreExportStream` hat keine solche Prüfung.
- **Ein seitenbezogener Export wird abgelehnt.** Die Export-Streams nehmen das gesamte Ergebnis. Eine begrenzte Seite läuft über die Seitenmethode.
- **Ein neutrales Ergebnis.** Jede Seite hat eine `ToGridPageResult()`-Erweiterung. Die von OpenSearch nimmt zusätzlich die `SearchQueryRequest`, die Sie verwendet haben. `LoadSuccessParamsMapper.Map` in `Craticula.AgGrid` wandelt das in die Form um, die AG Grid erwartet.

## Was sie nie tun {#what-they-never-do}

- Sie öffnen, schließen oder poolen nie eine Verbindung und starten nie eine Transaktion.
- Sie wiederholen nie eine fehlgeschlagene Abfrage und setzen nie ein Timeout. Die Verbindung und die Befehlseinstellungen liegen bei Ihnen.
- Sie erzwingen nie eine maximale Anzahl exportierter Zeilen.
- Sie wenden nie Ihre Ressourcenlimits oder die Spaltenprüfungen Ihres Schemas an. Führen Sie zuerst `GridFilterPipeline.Process` aus, wie es der Schnellstart tut. Siehe [Das Sicherheitsmodell](safety-model.html).

## Welchen Adapter wählen {#which-one-to-pick}

| Sie haben | Verwenden Sie |
|---|---|
| Eine einfache `IDbConnection` und möchten das SQL sehen | Dapper |
| Einen der fünf SQL-Dialekte, ohne zusätzlichen Code | Dapper |
| Einen `DbContext` mit globalen Abfragefiltern, die Sie behalten möchten | Entity Framework Core |

Die Demo führt beide auf PostgreSQL aus, sodass Sie sie an denselben Daten vergleichen können.

## Woher diese Seite stammt {#where-this-comes-from}

- [csharp/src/Craticula.Dapper/README.md](../../csharp/src/Craticula.Dapper/README.md)
- [csharp/src/Craticula.EntityFrameworkCore/README.md](../../csharp/src/Craticula.EntityFrameworkCore/README.md)
- [csharp/src/Craticula.Dapper/DapperGridQuery.cs](../../csharp/src/Craticula.Dapper/DapperGridQuery.cs)
- [csharp/src/Craticula.EntityFrameworkCore/EfCoreGridQuery.cs](../../csharp/src/Craticula.EntityFrameworkCore/EfCoreGridQuery.cs)
- [csharp/src/Craticula.EntityFrameworkCore/EfCoreProviderSemantics.cs](../../csharp/src/Craticula.EntityFrameworkCore/EfCoreProviderSemantics.cs)
- [csharp/src/Craticula.EntityFrameworkCore/GridSchemaPropertyBag.cs](../../csharp/src/Craticula.EntityFrameworkCore/GridSchemaPropertyBag.cs)
- [examples/demo/README.md](../../examples/demo/README.md)
- Verwandte Seiten: [CSV-Export](csv-export.html), [MongoDB- und OpenSearch-Adapter](search-adapters.html), [Paging und Sortierung](paging-and-sorting.html)
