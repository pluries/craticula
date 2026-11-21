---
translates: paging-and-sorting
title: Paging und Sortierung
description: Wie Zeilen in Fenster gelegt und geordnet werden und warum das Paging deterministisch ist.
source_fingerprint: c01a09b912527d1a95923a5776c7b4abb3290f980e8c9111c4751565b710b445
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Paging und Sortierung {#paging-and-sorting}

Diese Seite behandelt, wie der Zeilenbereich und die Sortierreihenfolge einer Anfrage von AG Grid zu Paging und Ordnung in der Abfrage werden. Sie richtet sich an Entwickler, die wissen möchten, warum Zeilen in einer bestimmten Reihenfolge zurückkommen und was jedes Backend tut, um sie seitenweise zu durchlaufen.

## Von startRow und endRow zu einer Seite {#from-startrow-and-endrow-to-a-page}

AG Grid fragt einen Block von Zeilen mit `startRow` und `endRow` an. `endRow` ist exklusiv. Die Seitengröße ist `endRow - startRow`.

Craticula macht daraus eine Zeilenanzahl und einen Offset. Die Anzahl ist die Seitengröße. Der Offset ist `startRow`. Eine Anfrage für die Zeilen 50 bis 100 verlangt 50 Zeilen, nachdem 50 übersprungen wurden.

Der Adapter lehnt ein Fenster ab, das keinen Sinn ergibt:

- ein negatives `startRow`;
- ein `endRow` unterhalb von `startRow`;
- ein `endRow` gleich `startRow`, was ein leeres Fenster ist.

Eine Seite hat außerdem eine maximale Größe. Der Standard sind 1000 Zeilen. Siehe [Limits](limits.html).

## Eine Anfrage ohne Fenster {#a-request-with-no-window}

Manche Anfragen senden weder `startRow` noch `endRow`: ein eigener Client oder eine von Hand gebaute Anfrage. Seit Version 1.2.0 erhält eine solche Anfrage eine Standardseite von 100 Zeilen, `[0, 100)`. Die Größe ist `AgGridParseOptions.DefaultPageSize`, und das Limit für die Seitengröße prüft sie wie jedes andere Fenster. Vor 1.2.0 bedeutete eine Anfrage ohne Fenster jede passende Zeile.

Es gibt zwei Wege, jede Zeile anzufragen, und beide sind bewusst gewählt:

- **Ein Export von allem** (`exportScope` gesetzt auf `"all"`). Er hat keine Seite, und die Adapter streamen ihn Block für Block. Siehe [CSV-Export](csv-export.html).
- **Das Flag `ignorePageLimit: true`**, das nur wirkt, wenn Ihr Host `AgGridParseOptions.AllowUnboundedRows` eingeschaltet hat (standardmäßig aus). Ohne diesen Schalter wird die Anfrage mit dem Parse-Fehler `unbounded-not-allowed` abgelehnt; sie wird nie stillschweigend begrenzt. Eine Anfrage, die ein Fenster mitbringt, behält ihr Fenster, und das Flag ändert nichts.

Die Adapter lesen eine Anfrage nach allen Zeilen per Streaming. Das seitenweise `FetchPageAsync` der Adapter für MongoDB, Dapper, EF Core und OpenSearch lehnt die unpaginierte Seite ab, sodass kein Aufruf das gesamte Ergebnis in den Speicher lädt. Verwenden Sie für diese Anfragen den Export-Stream. Die Regeln stehen unter [Standardseitengröße](default-page-size.html).

## Was jedes Backend tut {#what-each-backend-does}

| Backend | Wie die Seite geschrieben wird |
|---|---|
| PostgreSQL, MySQL, SQLite | `LIMIT n OFFSET m` |
| SQL Server, Oracle | `OFFSET m ROWS FETCH NEXT n ROWS ONLY` |
| MongoDB | eine `$skip`-Stage, dann eine `$limit`-Stage |
| OpenSearch und Elasticsearch | `from` und `size` |

Bei SQL sind die beiden Zahlen Parameter und nicht Teil des Textes. SQL Server und Oracle binden den Offset vor der Zeilenanzahl. PostgreSQL, MySQL und SQLite binden zuerst die Zeilenanzahl. Darum müssen Sie sich nicht kümmern, denn die Parameterliste steht in der Reihenfolge, in der die Platzhalter erscheinen.

Ein Export von allem hat überhaupt keine Seite. Er verlangt jede passende Zeile und erhält keine Paging-Klausel. Siehe [CSV-Export](csv-export.html).

## Sortierreihenfolge {#sort-order}

Das Grid sendet in `sortModel` eine Liste von Sortierschlüsseln. Craticula behält sie in dieser Reihenfolge. Jeder Schlüssel hat eine Spalte und eine Richtung, `asc` oder `desc`.

Eine Sortierung auf eine Spalte, die das Schema nicht aufführt, wird abgelehnt, im Modus Strict wie im Modus Lenient. Die Ablehnung kommt vom Compiler, der seine eigene Kompilierungsausnahme wirft. Siehe [Strict und Lenient](strict-and-lenient.html).

Das Schema hat für jede Spalte ein Flag `sortable`. Nichts liest es (Stand dieser Version). Eine Spalte, die im Schema steht, kann sortiert werden, was auch immer ihr Flag sagt. Verlassen Sie sich nicht darauf, dass das Flag eine Spalte am Sortieren hindert.

## Wohin Nullwerte kommen {#where-nulls-go}

AG Grid sagt nicht, wo Nullwerte einsortiert werden sollen. Craticula entscheidet das, und zwar für jedes Backend gleich:

- eine aufsteigende Sortierung setzt Nullwerte ans Ende;
- eine absteigende Sortierung setzt Nullwerte an den Anfang.

Datenbanken sind sich hierbei standardmäßig uneins, deshalb überlässt Craticula es nie der Datenbank. Es schreibt die Position in jeden Sortierschlüssel.

PostgreSQL, SQLite und Oracle haben `NULLS FIRST` und `NULLS LAST`, und Craticula verwendet sie. SQLite braucht dafür Version 3.30.0 oder neuer. SQL Server und MySQL haben diese Syntax nicht, deshalb fügt Craticula einen vorangestellten Test hinzu, der Zeilen mit Nullwerten in einen eigenen Bereich legt: `CASE WHEN ... IS NULL` bei SQL Server und `ISNULL(...)` bei MySQL. MongoDB erhält pro Sortierschlüssel ein Hilfsfeld, das nach der Sortierung wieder entfernt wird. OpenSearch erhält `"missing": "_last"` oder `"_first"`.

## Text sortiert ohne Beachtung der Groß-/Kleinschreibung {#text-sorts-without-regard-to-case}

Eine Textspalte vergleicht standardmäßig ohne Beachtung der Groß-/Kleinschreibung. Die Sortierung folgt derselben Regel, sodass `apple` und `Apple` zusammen einsortiert werden. Eine Spalte kann im Schema exakte Schreibweise verlangen, indem `text.caseSensitivity` auf `sensitive` gesetzt wird.

Jede Engine erreicht dasselbe Ergebnis auf ihre Weise:

- PostgreSQL benennt eine Collation, `craticula_ci`, die Sie einmal anlegen.
- SQL Server und SQLite benennen eine Collation inline in der Abfrage.
- MySQL verwendet die Collation der Spalte selbst.
- MongoDB setzt eine Collation auf die gesamte Abfrage.
- OpenSearch sortiert nach einem normalisierten Unterfeld, das Sie im Index abbilden.

Was Sie für jede Datenbank einrichten müssen, steht unter [Index- und Datenbankleitfaden](index-guidance.html).

## Der stabile Schlüssel hält das Paging in Ordnung {#the-stable-key-keeps-paging-in-order}

Paging ist nur zuverlässig, wenn die Ordnung total ist. Wenn zwei Zeilen in jedem Sortierschlüssel gleichauf liegen, darf die Datenbank sie in beliebiger Reihenfolge zurückgeben, und eine Zeile kann auf zwei Seiten oder auf keiner erscheinen.

Um das zu verhindern, benennt das Schema einen `stableKey`, eine Spalte mit eindeutigen Werten. Wenn die Sortierung nicht bereits mit diesem Schlüssel endet, hängt Craticula ihn am Ende an, aufsteigend, Nullwerte zuletzt.

Die Anfrage der Schnellstartanleitung sortiert absteigend nach `amount`. Die Anweisung endet so:

```sql
ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST
```

Craticula bereinigt die Sortierung außerdem, bevor es etwas hinzufügt:

- eine Spalte, die zweimal genannt wird, behält nur ihr erstes Vorkommen;
- wenn der stabile Schlüssel exakt sortiert, wird jeder Schlüssel danach verworfen, weil kein Gleichstand mehr aufzulösen ist.

Eine Ausnahme ist ein stabiler Textschlüssel, der die Groß-/Kleinschreibung ignoriert. Zwei Schlüssel, die sich nur in der Schreibweise unterscheiden, vergleichen sich als gleich, daher bleiben die späteren Schlüssel erhalten, und es wird ein exakter Tiebreaker hinzugefügt.

Das funktioniert nur, wenn der stabile Schlüssel wirklich eindeutig ist. Die meisten Datenbanken erlauben in einer eindeutigen Spalte viele Nullwerte, was die Garantie bricht. Deklarieren Sie den Schlüssel als `NOT NULL`. Siehe [Index- und Datenbankleitfaden](index-guidance.html).

## Tiefes Paging {#deep-paging}

Grid-Seiten bei SQL und MongoDB verwenden einen Offset. Die Datenbank muss an jeder übersprungenen Zeile vorbeilaufen, daher ist eine Seite tief in einer großen Tabelle langsamer als eine Seite nahe dem Anfang. Indizieren Sie Ihre Filter und messen Sie.

OpenSearch lehnt reines `from` und `size` jenseits von 10,000 Zeilen ab. Der OpenSearch-Adapter übernimmt das für Sie. Ab diesem Punkt wechselt er zu einem Point in Time und `search_after` und hält zwischen den Anfragen einen Cursor. Daraus folgen drei Dinge:

- Sie müssen ihm einen Cursor-Cache geben, der so lange lebt wie die Grid-Sitzung. `InMemorySearchCursorCache` ist der mitgelieferte. Ein neuer Cache für jede Anfrage macht den Cursor wirkungslos.
- Die erste Anfrage, die den Schwellenwert überschreitet, läuft von Zeile null vorwärts. Die Blöcke danach sind schnell.
- Die Gesamtzahl der Zeilen oberhalb von 10,000 wird als unbekannt gemeldet, es sei denn, Sie verlangen die exakte Anzahl, was bei jeder ersten Anfrage eine vollständige Zählung kostet.

Siehe [MongoDB- und OpenSearch-Adapter](search-adapters.html).

## Woher das stammt {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/sort-paging](../../spec/fixtures/sort-paging/README.md)
- [csharp/src/Craticula.Core/Schema/SemanticsResolver.cs](../../csharp/src/Craticula.Core/Schema/SemanticsResolver.cs)
- [csharp/src/Craticula.Core/Ir/PageSpecValidator.cs](../../csharp/src/Craticula.Core/Ir/PageSpecValidator.cs)
- [csharp/src/Craticula.Sql](../../csharp/src/Craticula.Sql/README.md)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs)
- [site/pages/quickstart-csharp.md](quickstart-csharp.md)
- Verwandte Seiten: [Wie aus einer Anfrage eine Abfrage wird](request-to-query.html), [Gruppierung und Aggregation](grouping-and-aggregation.html), [Dialekte und Provider](dialects-and-providers.html)
