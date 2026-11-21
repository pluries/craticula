---
translates: the-gridschema
title: Das GridSchema
description: Das Schema, das auflistet, worauf eine Grid zugreifen darf, und welche seiner Flags heute durchgesetzt werden.
source_fingerprint: cdf6e47e0fa6a2ef7b974c3b2ac02ea7892b7f9a31ffa33a18595708e80d8a45
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Das GridSchema {#the-gridschema}

Diese Seite erklärt das Schema, das Sie für jede Grid schreiben: was es enthält, welche seiner Einstellungen Craticula heute durchsetzt und wie Sie eines beginnen. Sie richtet sich an Entwickler, die gleich eine Tabelle, eine Collection oder einen Index für Craticula beschreiben. Die vollständige Liste der Member finden Sie in der [GridSchema-Referenz](grid-schema.html).

## Wozu das Schema dient {#what-the-schema-is-for}

Das Schema ist die Grenze zwischen der Anfrage und Ihren Daten. Es ist ein JSON-Dokument, das Sie schreiben und auf dem Server aufbewahren. Es benennt die Tabelle, die Collection oder den Index. Es listet jede Spalte auf, auf die die Grid zugreifen darf. Für jede Spalte gibt es einen Typ und den physischen Namen in Ihrer Datenbank an.

Eine Spalte, die nicht im Schema steht, kann nie in eine Abfrage gelangen. Tabellennamen und Spaltennamen in einer Abfrage stammen aus dem Schema, nie aus der Anfrage. Siehe [Das Sicherheitsmodell](safety-model.html).

Keine Anfrage kann ein Schema mitbringen. Die Grid sendet Spalten über ihre Grid-ID, und Craticula schlägt jede einzelne nach.

## Ein kleines Beispiel {#a-small-example}

Dies ist das Schema aus dem Schnellstart. Es beschreibt eine Tabelle `orders`.

```json
{
  "mode": "strict",
  "source": "orders",
  "stableKey": "id",
  "fields": {
    "id":       { "type": "int64",    "sortable": true, "physical": { "sql": { "column": "id" } } },
    "customer": { "type": "string",   "filterable": true, "sortable": true, "physical": { "sql": { "column": "customer" } } },
    "amount":   { "type": "decimal",  "filterable": true, "sortable": true, "physical": { "sql": { "column": "amount" } } },
    "status":   { "type": "string",   "filterable": true, "sortable": true, "physical": { "sql": { "column": "status" } } }
  }
}
```

In C# laden Sie es mit `GridSchema.Parse(json)`.

## Die Member des gesamten Schemas {#the-members-of-the-whole-schema}

| Member | Wirkung |
|---|---|
| `mode` | `strict` oder `lenient`. Das JSON Schema verlangt ihn; der C#-Parser verwendet standardmäßig strict, wenn er fehlt. Siehe [Strict und Lenient](strict-and-lenient.html). |
| `source` | Die Tabelle oder View, die MongoDB-Collection oder der OpenSearch-Index. Er darf nicht leer sein. |
| `stableKey` | Eine Spalte mit eindeutigen Werten. Sie muss eines der `fields` sein. |
| `fields` | Die Allowlist, geordnet nach der Spalten-ID der Grid. Mindestens ein Feld ist erforderlich. |
| `staticFilter` | Ein Filter, der jeder Abfrage hinzugefügt wird. Optional. |

`GridSchema.Parse` lehnt ein Schema ab, das diese Regeln verletzt. Es lehnt außerdem unbekannte Member, doppelte Schlüssel und ein `physical.sql` ab, das nicht genau eines von `column`, `qualifiedColumn` und `expression` setzt.

## Die Member eines Feldes {#the-members-of-one-field}

| Member | Wirkung |
|---|---|
| `type` | `string`, `int64`, `decimal`, `double`, `boolean`, `date` oder `datetime`. Craticula wandelt jeden Wert der Anfrage in diesen Typ um. |
| `physical` | Wo die Spalte liegt: `sql`, `mongo`, `search` oder alle drei. |
| `text` | Für einen `string`: `caseSensitivity` (standardmäßig `insensitive`) und `searchMode`. |
| `filterable`, `sortable`, `groupable`, `aggregatable` | Was die Grid mit der Spalte tun darf. Siehe unten. |
| `exportable`, `label`, `format` | Wie die Spalte in einem CSV-Export erscheint. Siehe [CSV-Export](csv-export.html). |

Sie brauchen nur die Mappings für die Backends, die Sie verwenden. Ein SQL-Mapping ist eine einfache Spalte. Ein MongoDB-Mapping ist ein Dokumentpfad. Ein Such-Mapping benennt das Indexfeld und kann auch ein `keywordSubField` und ein `normalizedSubField` benennen. Ein Feld ganz ohne Mapping verwendet seine Spalten-ID als Namen.

## Was jedes Flag heute bewirkt {#what-each-flag-does-today}

Gehen Sie nicht davon aus, dass jedes Flag durchgesetzt wird. So verhält sich der Code heute:

| Flag | Standard | Durchgesetzt? |
|---|---|---|
| `filterable` | `true` | Ja. Ein Filter auf eine Spalte mit `false` wird im Strict-Modus abgelehnt und im Lenient-Modus verworfen. Die Spalte der Werteliste eines Set-Filters und ein Gruppenschlüssel, den der Benutzer geöffnet hat, müssen filterbar sein und werden in beiden Modi abgelehnt, wenn sie es nicht sind. |
| `groupable` | `false` | Ja. Eine Gruppenspalte muss gruppierbar sein. In beiden Modi abgelehnt. |
| `aggregatable` | keiner | Ja. Eine Aggregation muss eine Funktion aus dieser Liste verwenden. In beiden Modi abgelehnt. |
| `exportable` | `true` | Ja. Es bestimmt die Standard-Exportspalten, und eine Spalte mit `false` kann nicht in `exportColumns` genannt werden. |
| `sortable` | `true` | **Nein.** Heute liest nichts dieses Flag. Eine Spalte im Schema kann sortiert werden, unabhängig davon, was das Flag angibt. |

Die `aggregatable`-Liste enthält beliebige der Funktionen `sum`, `min`, `max`, `avg` und `count`. Siehe [Gruppierung und Aggregation](grouping-and-aggregation.html).

Wenn Sie verhindern müssen, dass eine Spalte sortiert wird, lassen Sie sie aus dem Schema weg oder verlassen Sie sich auf eine eigene Prüfung. Das Flag leistet das nicht.

## Der stabile Schlüssel {#the-stable-key}

Der `stableKey` sorgt dafür, dass das Paging in Reihenfolge bleibt. Craticula hängt ihn an das Ende jeder Sortierung an. Er muss eine Spalte mit eindeutigen Werten benennen. Deklarieren Sie die Spalte in Ihrer Datenbank als `NOT NULL`, denn die meisten Datenbanken erlauben in einer eindeutigen Spalte viele Nullwerte, und das hebt die Garantie auf. Siehe [Paging und Sortierung](paging-and-sorting.html).

## Der statische Filter {#the-static-filter}

`staticFilter` ist eine Bedingung, die Craticula jeder Abfrage mit AND hinzufügt. Hier gehört eine Mandanten-ID oder ein Soft-Delete-Flag hin. Die Anfrage kann ihn weder ändern noch entfernen.

```json
"staticFilter": {
  "type": "comparison",
  "op": "eq",
  "field": "tenantId",
  "value": { "type": "int64", "value": 42 }
}
```

Das Feld, das ein `staticFilter` benennt, muss auch in `fields` deklariert sein, damit der Compiler seine Spalte finden kann. Die Bedingung ist Teil des Schemas, daher kann die Anfrage sie nicht erreichen. Festzulegen, wie der Filter aussehen soll, ist Ihre Aufgabe. Craticula wendet ihn nur an. Siehe [Das Sicherheitsmodell](safety-model.html).

## Feldreihenfolge {#field-order}

Die Reihenfolge der Felder im Dokument zählt. Eine Export-Anfrage ohne Spaltenliste erhält die exportierbaren Felder in dieser Reihenfolge. Auch die Zeilen innerhalb einer geöffneten Gruppe werden in dieser Reihenfolge zurückgegeben.

## Woher diese Seite stammt {#where-this-comes-from}

- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridSchema.cs](../../csharp/src/Craticula.Core/Schema/GridSchema.cs)
- [csharp/src/Craticula.Core/Schema/FieldConfig.cs](../../csharp/src/Craticula.Core/Schema/FieldConfig.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
- [spec/fixtures/schemas](../../spec/fixtures/schemas)
- Verwandte Seiten: [Limits](limits.html), [Dialekte und Provider](dialects-and-providers.html), [Wie aus einer Anfrage eine Abfrage wird](request-to-query.html)
