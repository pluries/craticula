---
translates: strict-and-lenient
title: Strict und Lenient
description: Was die beiden Schemamodi mit Spalten tun, die das Schema nicht erlaubt.
source_fingerprint: 20ab3fa199820cb9e052565112f509257cd8428bafaf7eced343e56e4ea4c25a
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Strict und Lenient {#strict-and-lenient}

Diese Seite erklärt die beiden Modi, in denen ein Schema laufen kann, und was jeder tut, wenn eine Anfrage eine Spalte nennt, die das Schema nicht erlaubt. Sie richtet sich an Entwickler, die ein Schema schreiben und einen Modus wählen müssen.

Kurzfassung: Verwenden Sie Strict, sofern Sie keinen Grund dagegen haben. Strict ist der Standard.

## Wo Sie den Modus festlegen {#where-you-set-the-mode}

Der Modus ist eine Einstellung im Schema mit den Werten `strict` und `lenient`.

```json
{
  "mode": "strict",
  "source": "orders",
  "stableKey": "id",
  "fields": { }
}
```

In C# hat `GridSchema.Mode` den Standardwert `Strict`. Das JSON-Schema der Datei führt `mode` als Pflichtfeld, schreiben Sie es also in Ihre Schemadatei aus.

## Strict {#strict}

Im Modus Strict wird ein Filter auf eine Spalte, die das Schema nicht aufführt, abgelehnt. Craticula wirft eine `UnknownFieldException`, die jede abgelehnte Spalte nennt. Es wird keine Abfrage erzeugt.

Dasselbe gilt für eine Spalte, die das Schema aufführt, aber mit `filterable: false` markiert. Craticula behandelt sie wie eine unbekannte Spalte.

Die Adversarial-Fixtures zeigen das. Ein Filter, eine Sortierung und eine Zeilengruppe auf einer unbekannten Spalte werden alle abgelehnt. Der Filter und die Zeilengruppe werfen `UnknownFieldException`; die Sortierung wird vom Compiler abgelehnt (siehe den letzten Punkt weiter unten). Ebenso ein Spaltenname, der aus SQL besteht, etwa `amount'); DROP TABLE users; --`.

## Lenient {#lenient}

Im Modus Lenient verwirft Craticula eine Filterbedingung auf eine unbekannte oder nicht filterbare Spalte und macht mit dem Rest weiter.

Das Verwerfen einer Bedingung macht die Antwort breiter. Das Grid erhält möglicherweise mehr Zeilen, als es angefragt hat. Wählen Sie Lenient nur, wenn Sie das hinnehmen.

Einige Einzelheiten dazu, wie eine verworfene Bedingung entfernt wird:

- Eine AND- oder OR-Gruppe, die alle ihre Bedingungen verliert, verschwindet.
- Eine Gruppe, in der eine Bedingung übrig bleibt, wird zu dieser Bedingung.
- Ein NOT, dessen Bedingung verschwindet, verschwindet ebenfalls. Es wird nicht zu "alles passt" oder "nichts passt".

## Was kein Modus lockert {#what-no-mode-relaxes}

Lenient verzeiht nur eine Filterbedingung. Die Spezifikation legt fest, dass alles, was die Form der Antwort bestimmt, in jedem Modus abgelehnt wird:

- eine Gruppenspalte, die nicht im Schema steht oder nicht als gruppierbar markiert ist;
- ein Gruppenschlüssel, der in eine nicht filterbare Spalte vordringt;
- eine Aggregation auf einer Spalte, die nicht im Schema steht oder diese Funktion nicht verwenden darf;
- die Spalte einer Anfrage nach Einzelwerten (Distinct-Values) für einen Set-Filter;
- eine Exportspalte, die unbekannt, nicht exportierbar oder wiederholt ist, oder eine leere Liste.

Der Grund: Würde man diese verwerfen, bekäme das Grid ohne Fehler eine andere Antwort als die angefragte. Ein verworfener Gruppenschlüssel könnte die Zeilen einer anderen Gruppe unter dem Label zurückgeben, das das Grid erwartet.

Der Modus hat auch keinen Einfluss auf die übrigen Prüfungen. Eine Anfrage, die zu tief, zu breit ist, zu viele Zeilen verlangt oder einen Wert enthält, der nicht zum Spaltentyp passt, wird in beiden Modi abgelehnt. Siehe [Das Sicherheitsmodell](safety-model.html).

Noch ein Punkt: Eine Sortierung auf eine Spalte, die das Schema nicht aufführt, wird in beiden Modi abgelehnt. Die Ablehnung kommt vom Compiler, der seine eigene Kompilierungsausnahme wirft statt `UnknownFieldException`. Fangen Sie daher in Ihrem Endpunkt beide ab und geben Sie einen Clientfehler zurück.

## Wie Sie wählen {#how-to-choose}

- Wählen Sie **Strict**, wenn das Grid Ihnen gehört und eine unbekannte Spalte einen Fehler oder einen Angriff bedeutet. Sie erfahren es sofort.
- Wählen Sie **Lenient** nur, wenn Sie hinnehmen, dass eine Anfrage, die eine unbekannte oder nicht filterbare Spalte nennt, mehr Zeilen statt eines Fehlers zurückgibt.

Wenn Sie unsicher sind, verwenden Sie Strict.

## Woher das stammt {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridSchemaMode.cs](../../csharp/src/Craticula.Core/Schema/GridSchemaMode.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
