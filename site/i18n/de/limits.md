---
translates: limits
title: Limits
description: Die standardmäßigen Ressourcenlimits, was jedes bewirkt und wie man es ändert.
source_fingerprint: 4ebb0479bf2bf034db02fbe9221ed719f6f737678d26a8c1dee647b249dba066
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Limits {#limits}

Diese Seite listet die Ressourcenlimits auf, die Craticula jeder Anfrage auferlegt, was jedes davon schützt und wie Sie es ändern. Sie richtet sich an Entwickler, die eine öffentliche Grid betreiben oder wissen möchten, warum eine große Anfrage abgelehnt wurde.

## Warum es Limits gibt {#why-there-are-limits}

Eine Anfrage ist Eingabe von einem Fremden. Ohne Limits könnte eine Anfrage einen Filterbaum verlangen, der tausend Ebenen tief verschachtelt ist, eine Liste mit einer Million Werten oder eine Seite mit zehn Millionen Zeilen. Jedes davon verursacht Ihrer Datenbank viel Arbeit.

Craticula lehnt eine solche Anfrage ab, bevor es eine Abfrage baut.

## Die Limits und ihre Standardwerte {#the-limits-and-their-defaults}

| Einstellung | Standard | Was sie begrenzt |
|---|---|---|
| `MaxDepth` | 8 | Wie tief Filter verschachtelt sein können. Eine einzelne Bedingung hat die Tiefe 1. |
| `MaxLeaves` | 64 | Die Anzahl der Bedingungen im gesamten Filter, über alle Zweige hinweg summiert. |
| `MaxInValues` | 1000 | Die Anzahl der Werte in einer einzelnen „in“- oder „not in“-Liste. |
| `MaxPageSize` | 1000 | Die Anzahl der Zeilen in einer Seite, also `endRow - startRow`. |
| `MaxSetValuesResults` | 10000 | Die meisten Werte, die eine Anfrage nach eindeutigen Werten zurückgeben kann, wie viele die Grid auch anfordert. |
| `DefaultSetValuesResults` | 1000 | Wie viele Werte diese Anfrage zurückgibt, wenn die Grid dazu nichts angibt. |
| `MaxQueryTimeMs` | nicht gesetzt | Wie lange eine MongoDB- oder Search-Abfrage laufen darf, in Millisekunden. Das einzige optionale Limit; siehe [Das Abfragezeitlimit](#the-query-time-limit). |

Dies sind Eigenschaften von `ResourceLimits`.

Die ersten vier sind Prüfungen: Eine Anfrage über dem Limit wird abgelehnt. Die nächsten beiden sind Obergrenzen. `MaxQueryTimeMs` ist keines von beiden: Es wird in die Abfrage übernommen, und die Datenbank setzt es durch. Eine Anfrage nach eindeutigen Werten für einen Set-Filter wird nie abgelehnt, weil sie zu groß wäre. Craticula begrenzt sie auf die Obergrenze und verwendet den Standardwert, wenn die Grid keine Zahl sendet.

Eine Anfrage, die weder `startRow` noch `endRow` sendet, ist ebenfalls nicht unbegrenzt: Sie erhält eine Standardseite von 100 Zeilen (`AgGridParseOptions.DefaultPageSize`), und das Limit der Seitengröße prüft diese Seite wie jede andere. Siehe [Paging und Sortierung](paging-and-sorting.html).

Das Limit der Seitengröße gilt nicht für einen Export des gesamten Ergebnisses (`exportScope` mit dem Wert `"all"`), der keine Seite hat. Ein seitenbezogener Export behält seinen Zeilenbereich, und das Limit der Seitengröße gilt für ihn. Siehe [CSV-Export](csv-export.html).

Craticula zählt die Gruppen, die ein Benutzer geöffnet hat, zusammen mit den Filtern. Jede geöffnete Gruppe ist eine weitere Bedingung, und eine gruppierte Anfrage zählt eine Ebene mehr, als sie schreibt; ihr wirksames Tiefenlimit beträgt daher mit dem Standardwert 7.

## Limits, die fest sind {#limits-that-are-fixed}

Einige Grenzen sind fest eingebaut und lassen sich nicht ändern:

- höchstens 64 Gruppenspalten in einer Anfrage;
- ein Textwert in einem Filter von höchstens 8192 Zeichen;
- ein Dezimalwert von höchstens 128 Zeichen;
- eine Spalten-ID von höchstens 256 Zeichen, in einem Sortierschlüssel, einer Gruppenspalte, einer Aggregation oder der Spalte eines Set-Filters.

## Wie eine Ablehnung aussieht {#what-a-refusal-looks-like}

Verletzt eine Anfrage ein Limit, wirft `GridFilterPipeline.Process` eine `ResourceLimitExceededException`. Ihre Liste `Violations` nennt jedes verletzte Limit, mit der tatsächlichen Zahl und dem Maximum. Fangen Sie sie in Ihrem Endpunkt ab und geben Sie einen Client-Fehler zurück. Verletzt eine Anfrage zwei Limits, sehen Sie beide.

## Wie man ein Limit ändert {#how-to-change-a-limit}

Die Limits gehören nicht zur Schemadatei. Sie sind Code, und Sie übergeben sie. So legt die Demo ihre eigenen fest:

```csharp
public static ResourceLimits Default { get; } = new()
{
    MaxPageSize = 500,
    MaxDepth = 6,
    MaxLeaves = 32,
    MaxInValues = 200,
    MaxSetValuesResults = 1_000,
    DefaultSetValuesResults = 200
};
```

Übergeben Sie den Wert dann an die Aufrufe, die einen entgegennehmen. Der Schnellstart übergibt `new ResourceLimits()`, was die Standardwerte bedeutet.

```csharp
FilterNode? filter = GridFilterPipeline.Process(
    parsed.NativeFilter, parsed.CustomFilters, parsed.Page, schema, limits, parsed.Group, parsed.Aggregations);
```

Eine Anfrage nach eindeutigen Werten läuft über `GridFilterPipeline.ProcessSetValues`, und ihre Obergrenze stammt aus `ResourceLimitsValidator.ResolveSetValuesLimit`.

Sie können ein Limit beliebig hoch setzen. Es gibt keine Prüfung auf eine Obergrenze. Wählen Sie Zahlen, die Ihre Datenbank tragen kann.

## Das Abfragezeitlimit {#the-query-time-limit}

`MaxQueryTimeMs` ist für einen Host gedacht, dessen Datenbank geteilt oder öffentlich ist. Die anderen Limits begrenzen die Form einer Anfrage; dieses begrenzt die Arbeit, die die Datenbank dafür leistet. Setzen Sie es auf eine ganze Zahl von Millisekunden, von 1 bis 2,147,483,647, und die Compiler übernehmen es in die Abfrage:

| Engine | Was die Abfrage trägt | Was passiert, wenn die Zeit abgelaufen ist |
|---|---|---|
| MongoDB | `maxTimeMS` am Aggregate-Befehl | MongoDB bricht die Operation ab, und der Adapter wirft `QueryTimeoutException`. |
| OpenSearch und Elasticsearch | ein `timeout`-Member des Such-Bodys, zum Beispiel `"2000ms"` | Die Engine stoppt bei ihrer nächsten Prüfung (ein weiches Limit) und antwortet mit `timed_out: true`. Der Adapter wirft `QueryTimeoutException` und gibt die Teiltreffer nie als Seite zurück. |

Das Limit stammt nur aus Ihrem Code. Eine Anfrage kann es weder setzen noch erhöhen noch entfernen, und ein `maxQueryTimeMs` in einer Anfrage wird ignoriert. Ein Export trägt kein Limit, weil er von Natur aus lang ist; beenden Sie einen Export mit dem Cancellation Token. Die SQL-Engines haben kein kompiliertes Limit: Setzen Sie stattdessen ein Statement-Timeout auf der Verbindung oder dem Datenbankkonto (die öffentliche Demo tut das für PostgreSQL).

Lassen Sie es ungesetzt, ändert sich nichts: Die Abfragen sind genau das, was sie waren. Ein Wert von null oder ein negativer Wert wirft eine Ausnahme, wenn Sie die `ResourceLimits` bauen, und die Compiler lehnen ihn ebenfalls ab, wenn Sie eine Anfrage von Hand füllen. Siehe die Regeln unter [Abfragezeitlimit](query-time-limit.html).

## Sie können ein Limit nicht abschalten {#you-cannot-turn-a-limit-off}

Jedes Limit bis auf eines ist eine einfache positive Zahl, und es gibt keinen Wert „unbegrenzt“. Ein Limit auf null oder weniger zu setzen, wirft eine `ArgumentOutOfRangeException`, wenn Sie die `ResourceLimits` bauen. Die Ausnahme ist `MaxQueryTimeMs`, das standardmäßig nicht gesetzt ist, weil die Bibliothek nicht wissen kann, wie langsam Ihre Datenbank ist; es auf eine Zahl zu setzen, schaltet nie etwas ab.

Das ist Absicht. Ein Limit von null würde nicht „kein Limit“ bedeuten. Es würde jede Anfrage ablehnen, und eine Einstellung, die versehentlich leer geblieben ist, könnte das tun, ohne dass es jemand bemerkt.

## Wo die Prüfungen laufen {#where-the-checks-run}

Die Limits werden von `GridFilterPipeline.Process` geprüft. Der Adapter, der die AG Grid-Anfrage liest, prüft sie nicht, und die Compiler auch nicht. Wenn Sie die Pipeline überspringen und einen Compiler selbst aufrufen, wird kein Limit geprüft. Der Schnellstart ruft die Pipeline aus diesem Grund auf. Siehe [Wie aus einer Anfrage eine Abfrage wird](request-to-query.html).

## Woher diese Seite stammt {#where-this-comes-from}

- [csharp/src/Craticula.Core/Schema/ResourceLimits.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimits.cs)
- [csharp/src/Craticula.Core/Schema/ResourceLimitsValidator.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimitsValidator.cs)
- [csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs](../../csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs)
- [csharp/src/Craticula.Core/Ir/GroupSpecValidator.cs](../../csharp/src/Craticula.Core/Ir/GroupSpecValidator.cs)
- [spec/semantics.md](../../spec/semantics.md), die Nachträge zum Abfragezeitlimit und zur Standardseitengröße
- [examples/demo/Api/Grid/DemoLimits.cs](../../examples/demo/Api/Grid/DemoLimits.cs)
- [spec/ir.schema.json](../../spec/ir.schema.json)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
- Verwandte Seiten: [Das Sicherheitsmodell](safety-model.html), [Paging und Sortierung](paging-and-sorting.html), [Das GridSchema](the-gridschema.html)
