---
translates: quickstart-typescript
title: TypeScript
description: Che cosa seguirà un port TypeScript.
source_fingerprint: 072ec77c552dd32b4086a7e68bb381e3e721e82ea24a817d6929470d27629ac2
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Guida rapida: TypeScript {#quickstart-typescript}

**Non esiste ancora un'implementazione TypeScript.** Questa pagina lo dice di proposito, per evitare di cercare un pacchetto che non c'è.

## Perché {#why}

Craticula parte dalla specifica: le regole e le fixture di conformità in `spec/` vengono per prime, e ogni implementazione in un linguaggio
deve superare le stesse fixture. Il port TypeScript è previsto **dopo il congelamento della specifica** (la specifica
si congela alla 1.0). Fino ad allora la specifica può ancora cambiare, e un port scritto adesso andrebbe riscritto.

Per TypeScript non è pubblicato nulla: nessun pacchetto, nessun comando di installazione.

## Che cosa si può fare oggi {#what-you-can-do-today}

- Usare la libreria C#, che è l'implementazione di riferimento: [Guida rapida: C#](quickstart-csharp.html).
- Leggere le regole che un port TypeScript dovrà rispettare: [semantica](semantics.html), e i
  riferimenti degli schemi ([GridSchema](grid-schema.html), [IR](ir-schema.html)).
- Guardare il test che un port deve superare: le fixture di conformità
  (`spec/fixtures`) e il runner indipendente dal linguaggio descritto in
  [`spec/conformance-runner.md`](../../spec/conformance-runner.md). Un driver in qualsiasi linguaggio risponde alle richieste del runner e il
  runner valuta le risposte.
