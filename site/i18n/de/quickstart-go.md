---
translates: quickstart-go
title: Go
description: Was ein Go-Port umsetzen wird.
source_fingerprint: 99c3a5a56c06d2a70375387b75d972430756a414510521cfe4542daa3fea3e3a
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Schnellstart: Go {#quickstart-go}

**Es gibt noch keine Go-Implementierung.** Diese Seite sagt das absichtlich, damit Sie nicht nach einem Paket suchen, das es nicht gibt.

## Warum {#why}

Craticula folgt dem Prinzip „Spezifikation zuerst“: Die Regeln und die Konformitäts-Fixtures in `spec/` entstehen zuerst, und jede
Implementierung in einer Sprache muss dieselben Fixtures bestehen. Der Go-Port ist für die Zeit **nach dem Einfrieren der Spezifikation** geplant (die
Spezifikation wird mit 1.0 eingefroren). Bis dahin kann sich die Spezifikation noch ändern, und ein jetzt geschriebener Port müsste neu geschrieben werden.

Für Go ist nichts veröffentlicht: kein Paket, kein Installationsbefehl.

## Was Sie heute tun können {#what-you-can-do-today}

- Verwenden Sie die C#-Bibliothek, die Referenzimplementierung: [Schnellstart: C#](quickstart-csharp.html).
- Lesen Sie die Regeln, die ein Go-Port einhalten muss: [Semantik](semantics.html) sowie die
  Schema-Referenzen ([GridSchema](grid-schema.html), [IR](ir-schema.html)).
- Sehen Sie sich den Test an, den ein Port bestehen muss: die Konformitäts-Fixtures
  (`spec/fixtures`) und den sprachunabhängigen Runner, der in
  [`spec/conformance-runner.md`](../../spec/conformance-runner.md) beschrieben ist. Ein Treiber in beliebiger Sprache beantwortet die Anfragen des Runners, und der
  Runner bewertet die Antworten.
