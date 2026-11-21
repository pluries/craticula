---
translates: quickstart-typescript
title: TypeScript
description: Was ein TypeScript-Port umsetzen wird.
source_fingerprint: 072ec77c552dd32b4086a7e68bb381e3e721e82ea24a817d6929470d27629ac2
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Schnellstart: TypeScript {#quickstart-typescript}

**Es gibt noch keine TypeScript-Implementierung.** Diese Seite sagt das absichtlich, damit Sie nicht nach einem Paket suchen, das es nicht gibt.

## Warum {#why}

Craticula folgt dem Prinzip „Spezifikation zuerst“: Die Regeln und die Konformitäts-Fixtures in `spec/` entstehen zuerst, und jede
Implementierung in einer Sprache muss dieselben Fixtures bestehen. Der TypeScript-Port ist für die Zeit **nach dem Einfrieren der Spezifikation** geplant (die
Spezifikation wird mit 1.0 eingefroren). Bis dahin kann sich die Spezifikation noch ändern, und ein jetzt geschriebener Port müsste neu geschrieben werden.

Für TypeScript ist nichts veröffentlicht: kein Paket, kein Installationsbefehl.

## Was Sie heute tun können {#what-you-can-do-today}

- Verwenden Sie die C#-Bibliothek, die Referenzimplementierung: [Schnellstart: C#](quickstart-csharp.html).
- Lesen Sie die Regeln, die ein TypeScript-Port einhalten muss: [Semantik](semantics.html) sowie die
  Schema-Referenzen ([GridSchema](grid-schema.html), [IR](ir-schema.html)).
- Sehen Sie sich den Test an, den ein Port bestehen muss: die Konformitäts-Fixtures
  (`spec/fixtures`) und den sprachunabhängigen Runner, der in
  [`spec/conformance-runner.md`](../../spec/conformance-runner.md) beschrieben ist. Ein Treiber in beliebiger Sprache beantwortet die Anfragen des Runners, und der
  Runner bewertet die Antworten.
