---
translates: grouping-and-aggregation
title: Gruppierung und Aggregation
description: Wie ein gruppiertes Grid jeweils eine Ebene anfragt und wie sich Aggregationen verhalten.
source_fingerprint: 10e3bdf6eb7dc0f59a4e20738237bb2f9f7ebac06181756626f1c01f952450a5
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Gruppierung und Aggregation {#grouping-and-aggregation}

Diese Seite behandelt Zeilengruppierung und Aggregation: wie ein gruppiertes Grid jeweils eine Ebene anfragt, wie Craticula jede Ebene beantwortet und was das Schema erlauben muss. Sie richtet sich an Entwickler, deren Grid Zeilen gruppiert und Summen anzeigt. Zeilengruppierung und Aggregation sind Enterprise-Funktionen von AG Grid.

## Eine Ebene pro Anfrage {#one-level-per-request}

Ein gruppiertes Grid fragt nicht den ganzen Baum an. Es fragt jeweils eine Ebene an, und jede Anfrage trägt den bisherigen Pfad.

Zwei Listen in der Anfrage beschreiben diesen Pfad:

- `rowGroupCols` listet die Spalten auf, nach denen das Grid gruppiert, in der Reihenfolge.
- `groupKeys` listet die Gruppen auf, die der Benutzer bereits geöffnet hat, ein Schlüssel für jede Ebene.

Craticula vergleicht die beiden Längen:

- **Weniger Schlüssel als Spalten.** Die Anfrage verlangt eine gruppierte Ebene. Craticula gruppiert nach der nächsten Spalte, die noch keinen Schlüssel hat, und nur nach dieser. Es berechnet die Aggregationen für jede Gruppe.
- **Ebenso viele Schlüssel wie Spalten.** Jede Ebene ist geöffnet. Die Anfrage verlangt die Zeilen innerhalb der letzten Gruppe. Craticula gibt einfache Zeilen zurück und gruppiert nicht.
- **Mehr Schlüssel als Spalten.** Die Anfrage ist fehlerhaft und wird abgelehnt.

Der Pivot-Modus wird nicht unterstützt. Eine Anfrage mit `pivotMode` auf `true` oder mit beliebigen `pivotCols` wird abgelehnt.

## Ein Beispiel {#an-example}

Nehmen Sie ein Grid, das nach `region`, dann `segment`, dann `product` gruppiert ist, mit einer Summe von `amount`. Der Benutzer hat die Region `EMEA` geöffnet. Das Grid fragt nun die Segmente innerhalb von `EMEA` an.

Für PostgreSQL schreibt Craticula:

```sql
SELECT "segment" AS "segment", COALESCE(SUM("amount"), 0) AS "amount_sum" FROM "sales_fact" WHERE "region" = $1 GROUP BY "segment" ORDER BY "segment" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: 'EMEA', 100, 0
```

Die geöffnete Gruppe wurde zu `WHERE "region" = $1`. Die nächste Spalte, `segment`, wurde zum `GROUP BY`. Das Aggregat heißt `amount_sum`.

## Gruppenschlüssel kommen als typisierte Werte {#group-keys-arrive-as-typed-values}

Craticula liest jeden Eintrag in `groupKeys` als typisierten Wert, typisiert passend zum deklarierten Typ der Spalte, und nicht als einfachen String, den AG Grid sendet:

```json
"groupKeys": [ { "type": "string", "value": "EMEA" } ]
```

Ihre Seite muss die Schlüssel umwandeln, bevor sie die Anfrage abschickt. Die Demo tut das in `toWireRequest` in `examples/demo/web/src/datasource.ts`. Sie benennt außerdem auf dem Rückweg die Aggregatspalten um, weil die Antwort sie `amount_sum` nennt und das Grid `amount` liest. Wenn Sie die Demo kopieren, kopieren Sie beide Schritte.

## Welche Funktionen Sie verwenden können {#which-functions-you-can-use}

Craticula unterstützt fünf Aggregationsfunktionen: `sum`, `min`, `max`, `avg` und `count`. Eine andere Funktion, etwa `first`, wird abgelehnt. Ebenso ein Eintrag in `valueCols` ohne `aggFunc`.

Der Name jedes Aggregats im Ergebnis ist die Spalten-ID, wenn sie sich vom Feldnamen unterscheidet. Andernfalls ist es der Feldname, ein Unterstrich und die Funktion, etwa `amount_sum`.

Einige Einzelheiten, die für die Zahlen wichtig sind:

- `count` zählt die Zeilen, in denen das Feld nicht null ist. Es zählt keine Zeilen insgesamt. Um jede Zeile zu zählen, zählen Sie den stabilen Schlüssel, der nie null ist.
- Eine `sum` über eine Gruppe ohne Werte ist auf jedem Backend `0`. Die SQL-Compiler umhüllen `sum` so, dass es übereinstimmt.
- `avg`, `min` und `max` über eine Gruppe ohne Werte sind null.

## Was das Schema erlauben muss {#what-the-schema-must-allow}

Das Schema entscheidet, welche Spalten gruppiert und aggregiert werden dürfen. Beide Flags sind standardmäßig aus.

```json
"region": { "type": "string", "groupable": true, "physical": { "sql": { "column": "region" } } },
"amount": { "type": "decimal", "aggregatable": ["sum", "avg"], "physical": { "sql": { "column": "amount" } } }
```

- Eine Gruppenspalte muss im Schema stehen und als `groupable` markiert sein.
- Eine Aggregation muss eine Spalte im Schema und eine Funktion aus der Liste `aggregatable` dieser Spalte nennen.
- Eine Spalte, die geöffnet wurde, deren Schlüssel also in `groupKeys` steht, muss außerdem `filterable` sein. Eine Gruppe zu öffnen ist dasselbe wie nach einem einzelnen Wert zu filtern.

Jedes davon wird in beiden Modi abgelehnt, Strict wie Lenient. Würde man eine Gruppenspalte oder einen Schlüssel verwerfen, bekäme das Grid eine andere Antwort als die angefragte. Siehe [Strict und Lenient](strict-and-lenient.html).

## Eine Gruppe zu öffnen trifft exakt {#opening-a-group-matches-exactly}

Wenn eine Gruppe geöffnet wird, wird ihr Schlüssel zu einem exakten Treffer auf der Gruppenspalte. Gruppieren, eine Gruppe öffnen und die Gruppen ordnen verwenden alle den exakten Vergleich, daher sind `EMEA` und `emea` zwei Gruppen. Eine Gruppe, die nicht exakt träfe, würde sich nicht zu ihrer übergeordneten Gruppe aufsummieren.

Das gilt nur, wenn die Datenbank standardmäßig exakt vergleicht. PostgreSQL und SQLite tun das. SQL Server, MySQL und Oracle ignorieren meist die Groß-/Kleinschreibung, deshalb deklarieren Sie jede Spalte, nach der Sie gruppieren, mit einer binären Collation. Siehe [Index- und Datenbankleitfaden](index-guidance.html).

MongoDB hat eine Collation für die gesamte Abfrage. Eine Gruppierungsanfrage trägt keine, daher vergleicht ein Filter in derselben Anfrage dort unter Beachtung der Groß-/Kleinschreibung. Die SQL-Datenbanken ignorieren die Schreibweise in diesem Filter.

## Null-Gruppenschlüssel {#null-group-keys}

Zeilen mit einem Null-Gruppenwert bilden eine Gruppe. Um sie zu öffnen, senden Sie einen Schlüssel `{ "type": "null" }`. Craticula schreibt dafür einen Null-Test, etwa `"region" IS NULL`.

Der leere String ist eine andere Gruppe als null, seine Zeilen schließen sich also nicht der Null-Gruppe an. Oracle ist die Ausnahme, weil Oracle einen leeren String als null speichert.

## Sortieren und Zählen einer gruppierten Ebene {#sorting-and-counting-a-grouped-level}

Eine gruppierte Ebene kann nach ihrer Gruppenspalte oder nach einem ihrer Aggregate sortiert werden. Eine Sortierung nach jeder anderen Spalte wird abgelehnt. Die Gruppenspalte dient als stabiler Schlüssel, daher ist die Gruppenreihenfolge stabil. Ein Aggregat, das in der Sortierung nach der Gruppenspalte steht, hat keine Wirkung und wird verworfen.

Die Zeilenanzahl für eine gruppierte Ebene ist die Anzahl der Gruppen, nicht die Anzahl der Zeilen in ihnen.

OpenSearch und Elasticsearch haben hier zwei Einschränkungen:

- Sie können eine gruppierte Ebene nicht nach einem Aggregat ordnen. Eine solche Anfrage wird abgelehnt.
- Die Gruppe, die Nullwerte enthält, steht unabhängig von der Richtung immer zuerst.

## Exporte ignorieren Gruppierung {#exports-ignore-grouping}

Ein Export gibt einfache Zeilen zurück. Der Adapter verwirft `rowGroupCols`, `valueCols` und `groupKeys` aus einer Exportanfrage. Siehe [CSV-Export](csv-export.html).

## Woher das stammt {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/group-aggregation](../../spec/fixtures/group-aggregation/README.md)
- [csharp/src/Craticula.Core/Ir/Aggregation.cs](../../csharp/src/Craticula.Core/Ir/Aggregation.cs)
- [csharp/src/Craticula.Core/Ir/GroupingPlan.cs](../../csharp/src/Craticula.Core/Ir/GroupingPlan.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/src/Craticula.AgGrid/AgGridRequestParser.cs](../../csharp/src/Craticula.AgGrid/AgGridRequestParser.cs)
- [examples/demo/web/src/datasource.ts](../../examples/demo/web/src/datasource.ts)
- Verwandte Seiten: [Paging und Sortierung](paging-and-sorting.html), [Das GridSchema](the-gridschema.html), [Wie aus einer Anfrage eine Abfrage wird](request-to-query.html)
