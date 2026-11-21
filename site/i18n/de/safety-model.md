---
translates: safety-model
title: Das Sicherheitsmodell
description: Wie Werte, Bezeichner und Limits eine kompilierte Abfrage sicher halten und was bei Ihnen bleibt.
source_fingerprint: cad40472e319059d27fe5a7517ac79ed14efb07866e1630c2883f9c7419a959c
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Das Sicherheitsmodell {#the-safety-model}

Diese Seite listet auf, was Craticula tut, damit eine feindliche Anfrage Ihrer Datenbank nicht schaden kann, und was es nicht tut. Sie richtet sich an Entwickler oder Reviewer, die beurteilen müssen, ob Craticula zu einem öffentlich erreichbaren System passt.

## Werte sind Parameter {#values-are-parameters}

Jeder Wert aus der Anfrage geht als Parameter in die Abfrage ein. Er wird nie in den Text eingefügt.

Bei SQL enthält die Anweisung Platzhalter wie `$1`, und die Werte reisen in einer separaten Liste. Bei der Anfrage der Schnellstartanleitung enthält der Text weder "acme" noch 100. Siehe [Wie aus einer Anfrage eine Abfrage wird](request-to-query.html).

Die Spezifikation wendet denselben Gedanken auf MongoDB und OpenSearch an. Dort gehen Werte als Daten in das Pipeline- oder Abfragedokument ein. Ein Textsuchwert, der Musterzeichen enthält, wird maskiert. Die Compiler haben dafür Hilfsfunktionen.

Ein Wert wie `'; DROP TABLE users; --`, der in einem gewöhnlichen Textfilter gesendet wird, ist nur ein String. Er wird verglichen und bewirkt sonst nichts. Die Adversarial-Fixtures betreffen die Form der Anfrage, nicht den Inhalt von Strings.

## Bezeichner stammen aus Ihrem Schema {#identifiers-come-from-your-schema}

Tabellennamen, Collection-Namen und Spaltennamen stammen ausschließlich aus dem Schema, das Sie geschrieben haben. Die Anfrage liefert nie einen davon.

Die Anfrage benennt Spalten über ihre Grid-ID, etwa `customer`. Craticula schlägt diese ID im Schema nach und verwendet den physischen Namen, den Sie deklariert haben. Bei SQL wird der Name für den Dialekt in Anführungszeichen gesetzt, und ein Anführungszeichen innerhalb eines Namens wird verdoppelt.

## Unbekannte Spalten werden abgelehnt {#unknown-columns-are-refused}

Eine Spalte, die nicht im Schema steht, wird abgelehnt, bevor eine Abfrage existiert. Die Schnellstartanleitung zeigt, wie ein Filter auf `password` abgelehnt wird.

Eine Spalte, die nicht im Schema steht, kann in keinem Modus zum Gruppieren, Aggregieren oder Sortieren verwendet werden. Ein Filter auf eine solche Spalte wird im Modus Strict abgelehnt und im Modus Lenient verworfen; siehe [Strict und Lenient](strict-and-lenient.html). Ein Schema kann eine Spalte außerdem als nicht filterbar, nicht gruppierbar oder nicht exportierbar markieren.

## Fehlerhafte Eingaben werden abgelehnt {#malformed-input-is-refused}

Der Adapter und die Prüfungen weisen Eingaben ab, die sie nicht erkennen:

- einen unbekannten Filteroperator, auch einen Tippfehler oder `regex`;
- einen Filterwert, der als Objekt oder Array gesendet wird, wo ein einzelner Wert erwartet wird;
- doppelte Schlüssel im JSON;
- einen Wert, der nicht zum Spaltentyp passt, etwa Text in einer Zahlenspalte;
- doppelte Ausgabenamen bei Aggregationen.

Für jeden dieser Fälle gibt es ein Fixture, das eine saubere Ablehnung erwartet.

## Ressourcenlimits {#resource-limits}

Eine Anfrage kann nicht unbegrenzte Arbeit verlangen. Dies sind die Standardwerte in `ResourceLimits`:

| Limit | Standard |
|---|---|
| Tiefe des Filterbaums | 8 |
| Bedingungen im gesamten Filter | 64 |
| Werte in einer In- oder Not-in-Liste | 1000 |
| Zeilen in einer Seite | 1000 |
| Von einer Distinct-Values-Anfrage zurückgegebene Zeilen | höchstens 10000 |
| Zeilen in einer Anfrage ohne Zeilenfenster | eine Standardseite von 100 (alle Zeilen nur durch einen Export oder durch ein Flag, das Sie aktivieren) |
| Abfragezeit bei MongoDB und Search | nicht gesetzt; Sie setzen sie, und die Datenbank erzwingt sie |

Sie können jedes Limit höher oder niedriger setzen. Sie können ein Limit nicht abschalten, außer dass das Limit für die Abfragezeit optional ist und ungesetzt bleibt, bis Sie es setzen. Null oder eine negative Zahl wird beim Setzen abgelehnt. Siehe [Limits](limits.html).

Die Fixtures testen jedes Limit einen Schritt jenseits der Grenze und mit Extremwerten wie einer Liste mit 5000 Werten oder einer Seite von einer Million Zeilen.

## Wovor Craticula nicht schützt {#what-craticula-does-not-protect-against}

- **Das Datenbankkonto.** Craticula kontrolliert nicht, was das Konto darf. Geben Sie dem Konto, das diese Abfragen ausführt, nur die Rechte, die es mindestens braucht, etwa nur Lesezugriff auf die eine Tabelle.
- **Das Ausführen der Abfrage.** Craticula führt sie nie aus. Verbindungsverwaltung, Kostenlimits und die Art, wie Sie die Anweisung ausführen, liegen bei Ihnen. Bei MongoDB und Search können Sie die kompilierte Abfrage ein Zeitlimit (`MaxQueryTimeMs`) tragen lassen, das die Datenbank erzwingt; bei SQL setzen Sie ein Statement-Timeout auf der Verbindung oder dem Konto.
- **Wer das Grid nutzen darf.** Authentifizierung und Zugriff pro Benutzer liegen außerhalb seines Umfangs. Das Schema kann jeder Abfrage einen festen Filter hinzufügen, aber was dieser Filter sein soll, entscheiden Sie.
- **Ein falsches Schema.** Wenn Ihr Schema eine Spalte aufführt, die verborgen bleiben soll, liefert Craticula sie aus.
- **Langsame Abfragen.** Eine Anfrage innerhalb der Limits kann trotzdem langsam sein, wenn die Spalte keinen Index hat. Siehe den [Index-Leitfaden](index-guidance.html).

## Woher das stammt {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
- [csharp/src/Craticula.Core/Schema/ResourceLimits.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimits.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/src/Craticula.Sql/PostgresDialect.cs](../../csharp/src/Craticula.Sql/PostgresDialect.cs)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
