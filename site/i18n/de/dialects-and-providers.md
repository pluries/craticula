---
translates: dialects-and-providers
title: Dialekte und Provider
description: Wie sich die Datenbank-Engines bei Quoting, Paging, Null-Reihenfolge und Abgleich ohne Beachtung der Groß- und Kleinschreibung unterscheiden.
source_fingerprint: e3cadc85fee286141cd8091c6103e2780064d51e19a1428afa783d8f20b83081
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Dialekte und Provider {#dialects-and-providers}

Diese Seite listet die Datenbanken auf, für die Craticula Abfragen schreiben kann, wie sich deren Abfragen unterscheiden und welche Versionen getestet sind. Sie richtet sich an Entwickler, die eine Datenbank oder einen Dialekt auswählen oder wissen möchten, warum dieselbe Anfrage auf jeder Datenbank anderen Text ergibt.

## Was ein Dialekt ist {#what-a-dialect-is}

Dieselbe Anfrage bedeutet auf jedem Backend dasselbe. Craticula legt einmal in der kanonischen Form fest, was sie bedeutet. Danach formuliert ein Writer pro Datenbank sie in deren Sprache.

Für SQL ist dieser Writer ein Dialekt. Eine Dialektklasse hat eine einzige gemeinsame `Instance`, etwa `PostgresDialect.Instance`. Sie übergeben sie an `SqlQueryBuilder.Build`. Es gibt fünf:

| Datenbank | Dialektklasse |
|---|---|
| PostgreSQL | `PostgresDialect` |
| SQL Server | `MssqlDialect` |
| MySQL (MariaDB läuft über denselben Dialekt, wurde aber nie getestet) | `MySqlDialect` |
| SQLite | `SqliteDialect` |
| Oracle | `OracleDialect` |

MongoDB und OpenSearch haben eigene Compiler, `MongoPipelineBuilder` und `SearchQueryBuilder`. Sie nehmen keinen Dialekt entgegen. Siehe [MongoDB- und OpenSearch-Adapter](search-adapters.html).

## Wie sich das SQL unterscheidet {#how-the-sql-differs}

| Datenbank | Platzhalter | Quoting | Paging |
|---|---|---|---|
| PostgreSQL | `$1`, `$2` | `"name"` | `LIMIT` und `OFFSET` |
| SQL Server | `@p1`, `@p2` | `[name]` | `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` |
| MySQL | `?` | `` `name` `` | `LIMIT` und `OFFSET` |
| SQLite | `?` | `"name"` | `LIMIT` und `OFFSET` |
| Oracle | `:p1`, `:p2` | `"name"` | `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` |

In jedem Fall sind die Werte Parameter, aufgelistet in der Reihenfolge, in der die Platzhalter erscheinen. Jeder Tabellen- und Spaltenname wird in Anführungszeichen gesetzt, und ein Anführungszeichen innerhalb eines Namens wird verdoppelt. Siehe [Das Sicherheitsmodell](safety-model.html).

PostgreSQL übergibt eine „in“-Liste als einen einzigen Array-Parameter. Die anderen Datenbanken schreiben für jeden Wert einen eigenen Platzhalter.

## Null-Reihenfolge {#null-ordering}

Craticula legt in jeder Abfrage fest, wo Nullwerte einsortiert werden, sodass die Reihenfolge nicht vom Standard der Datenbank abhängt. Wie es das ausdrückt, hängt von der Datenbank ab:

- PostgreSQL, SQLite und Oracle kennen `NULLS FIRST` und `NULLS LAST`. SQLite benötigt Version 3.30.0 oder neuer.
- SQL Server hat keine solche Syntax. Die Abfrage sortiert zuerst nach `CASE WHEN column IS NULL THEN 1 ELSE 0 END`, dann nach der Spalte.
- MySQL hat ebenfalls keine. Die Abfrage sortiert zuerst nach `ISNULL(column)`, dann nach der Spalte.
- MongoDB sortiert nach einem Hilfsfeld, das Nullwerte markiert und das die Abfrage anschließend entfernt.
- OpenSearch verwendet `"missing": "_first"` oder `"_last"`.

Siehe [Paging und Sortierung](paging-and-sorting.html).

## Vergleich ohne Beachtung der Groß- und Kleinschreibung {#case-insensitive-comparison}

Ein Textfeld wird ohne Rücksicht auf die Groß- und Kleinschreibung verglichen, sofern das Schema nichts anderes angibt. Jede Datenbank erreicht das auf andere Weise:

| Datenbank | Wie die Groß- und Kleinschreibung ignoriert wird |
|---|---|
| PostgreSQL | `COLLATE craticula_ci` bei Vergleichen und Sortierungen, das Sie einmal anlegen. `ILIKE` für `contains`, `startsWith` und `endsWith`. |
| SQL Server | `COLLATE Latin1_General_CI_AS` in der Abfrage. Ein Feld mit Beachtung der Schreibweise erhält `Latin1_General_CS_AS`. |
| MySQL | Nichts in der Abfrage. Die eigene Collation der Spalte entscheidet. Ein Feld mit Beachtung der Schreibweise braucht eine Spalte mit `_bin` oder `_as_cs`. |
| SQLite | `COLLATE NOCASE`, das nur ASCII-Buchstaben angleicht. |
| Oracle | `COLLATE BINARY_CI`. Ein Feld mit Beachtung der Schreibweise erhält `COLLATE BINARY`. |
| MongoDB | Eine Collation für die gesamte Abfrage, mit der Locale `en` und Strength 2. |
| OpenSearch und Elasticsearch | Die Option `case_insensitive` bei Term- und Wildcard-Abfragen sowie ein normalisiertes Unterfeld für Sortierung und Bereiche. |

Zwei Fälle verlaufen stillschweigend: ein Feld mit Beachtung der Schreibweise auf MySQL und die Gruppierungsspalten auf SQL Server, MySQL und Oracle. Die Anweisung läuft und liefert falsche Zeilen, wenn die Collation der Spalte nicht diejenige ist, von der Craticula ausgeht. Der Leitfaden zu Index und Datenbank listet auf, was für jede Datenbank einzustellen ist: [Leitfaden zu Index und Datenbank](index-guidance.html).

## Versionen {#versions}

Dies sind die niedrigsten Versionen, die die kompilierten Abfragen benötigen, entnommen der Spezifikation und der Dokumentation der Hersteller, nicht aus einem Testlauf. Nur die Spalte „Wogegen die Tests liefen“ wurde tatsächlich ausgeführt. Der Elasticsearch-Adapter ist für 8.x dokumentiert.

| Datenbank | Minimum | Wogegen die Tests liefen |
|---|---|---|
| PostgreSQL | 12, mit ICU | 16 |
| SQL Server | keines angegeben | 2022 |
| MySQL | keines angegeben | 8.4 |
| SQLite | 3.30.0 | nicht erfasst |
| Oracle | 12.2 | Database Free 23ai |
| MongoDB | 4.2 | 7.0 |
| OpenSearch | 1.0 | 2.19 |
| Elasticsearch | 7.10 | 8.17 |

„Keines angegeben“ bedeutet, dass Code und Spezifikation keine Untergrenze festlegen, nicht dass jede alte Version ausprobiert wurde. MariaDB verwendet den MySQL-Dialekt, aber kein Test läuft auf MariaDB.

Die Tests führen die kompilierten Abfragen gegen echte Datenbanken in Containern aus. Dieser Lauf benötigt Docker und gehört nicht zum schnellen Testlauf; prüfen Sie daher im Repository den aktuellen Stand.

## Der Status von Oracle {#oracles-status}

Oracle wird als von der Community getesteter Dialekt unterstützt, nicht als Kerndialekt von v1. Es wird auf dieselbe Weise bewertet wie die anderen: Jede Anweisung wird mit einem gespeicherten erwarteten Text verglichen. Der Unterschied ist die Abdeckung. Es wird anhand einer kleineren Menge von Beispielen geprüft als die anderen vier, insgesamt 45. Diese 45 laufen auch gegen einen echten Oracle-Database-Free-23ai-Server.

Oracle 12.2 bis 21c wurden nicht ausgeführt. Das Minimum 12.2 stammt aus der Dokumentation von Oracle, nicht aus einer Messung.

Drei Oracle-Eigenheiten prägen die Ausgabe:

- **Leerer Text ist null.** Ein Textwert `""` in einem Vergleich würde stillschweigend die falschen Zeilen treffen, daher lehnt der Oracle-Dialekt ihn ab. Verwenden Sie stattdessen die Operatoren für leer und nicht leer.
- **Namen müssen in Anführungszeichen stehen.** Legen Sie die Tabelle und ihre Spalten mit Namen in Anführungszeichen an, die exakt zum Schema passen.
- **Sitzungseinstellungen.** Datums-, Zeitstempel- und Zahlenformate stammen aus der Sitzung; legen Sie sie daher so fest, wie es der [Leitfaden zu Index und Datenbank](index-guidance.html) beschreibt.

## Provider {#providers}

Ein Provider ist hier die Bibliothek, die tatsächlich mit der Datenbank spricht. Craticula wählt keine für Sie aus.

- Für SQL führt `Craticula.Dapper` jeden Dialekt auf einer geöffneten `IDbConnection` aus, gleichgültig, welcher ADO.NET-Provider sie erzeugt hat.
- `Craticula.EntityFrameworkCore` verwendet den Provider Ihres `DbContext`. Es benötigt eine `EfCoreProviderSemantics`, die Ihre Engine beschreibt, und nur die für SQLite wird mitgeliefert. Siehe [Entity Framework Core und Dapper](relational-adapters.html).
- MongoDB läuft über den offiziellen MongoDB-.NET-Treiber und OpenSearch über den Low-Level-Client von `OpenSearch.Client`.

Das Repository enthält eine Demo-App in `examples/demo`, die Sie selbst ausführen. Sie liest dieselben synthetischen Bestellungen aus mehreren dieser Datenbanken und vergleicht die Antworten.

## Woher diese Seite stammt {#where-this-comes-from}

- [csharp/src/Craticula.Sql/README.md](../../csharp/src/Craticula.Sql/README.md)
- [csharp/src/Craticula.Sql/OracleDialect.cs](../../csharp/src/Craticula.Sql/OracleDialect.cs)
- [csharp/src/Craticula.Sql/MssqlDialect.cs](../../csharp/src/Craticula.Sql/MssqlDialect.cs)
- [spec/fixtures/dialect-parity](../../spec/fixtures/dialect-parity/README.md)
- [spec/fixtures/README.md](../../spec/fixtures/README.md)
- [spec/semantics.md](../../spec/semantics.md)
- [csharp/tests/Craticula.Integration.Tests/Sql/SqlEngine.cs](../../csharp/tests/Craticula.Integration.Tests/Sql/SqlEngine.cs)
- [examples/demo/README.md](../../examples/demo/README.md)
- Verwandte Seiten: [Leitfaden zu Index und Datenbank](index-guidance.html), [Paging und Sortierung](paging-and-sorting.html), [Das GridSchema](the-gridschema.html)
