---
translates: quickstart-python
title: Python
description: Che cosa seguirà un port Python.
source_fingerprint: 1a16c930083a5f86f8097b39f7a061a955f53e1df4f9037186cd267905f2c2ba
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Guida rapida: Python {#quickstart-python}

**Non esiste ancora un'implementazione Python.** Questa pagina lo dice di proposito, per evitare di cercare un pacchetto che non c'è.

## Perché {#why}

Craticula parte dalla specifica: le regole e le fixture di conformità in `spec/` vengono per prime, e ogni implementazione in un linguaggio
deve superare le stesse fixture. Il port Python è previsto **dopo il congelamento della specifica** (la specifica
si congela alla 1.0). Fino ad allora la specifica può ancora cambiare, e un port scritto adesso andrebbe riscritto.

Per Python non è pubblicato nulla: nessun pacchetto, nessun comando di installazione.

## Che cosa si può fare oggi {#what-you-can-do-today}

- Usare la libreria C#, che è l'implementazione di riferimento: [Guida rapida: C#](quickstart-csharp.html).
- Leggere le regole che un port Python dovrà rispettare: [semantica](semantics.html), e i
  riferimenti degli schemi ([GridSchema](grid-schema.html), [IR](ir-schema.html)).
- Guardare il test che un port deve superare: le fixture di conformità
  (`spec/fixtures`) e il runner indipendente dal linguaggio descritto in
  [`spec/conformance-runner.md`](../../spec/conformance-runner.md). Un driver in qualsiasi linguaggio risponde alle richieste del runner e il
  runner valuta le risposte.
