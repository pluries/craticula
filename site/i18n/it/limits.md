---
translates: limits
title: Limiti
description: I limiti di risorse predefiniti, che cosa fa ciascuno e come modificarli.
source_fingerprint: 4ebb0479bf2bf034db02fbe9221ed719f6f737678d26a8c1dee647b249dba066
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Limiti {#limits}

Questa pagina elenca i limiti di risorse che Craticula applica a ogni richiesta, che cosa protegge ciascuno e come modificarlo. È rivolta allo sviluppatore che gestisce una griglia pubblica o che vuole sapere perché una richiesta di grandi dimensioni è stata rifiutata.

## Perché esistono i limiti {#why-there-are-limits}

Una richiesta è un input proveniente da uno sconosciuto. Senza limiti, una richiesta potrebbe chiedere un albero di filtri annidato per mille livelli, un elenco di un milione di valori o una pagina di dieci milioni di righe. Ognuna di queste richieste costa al database molto lavoro.

Craticula rifiuta una richiesta di questo tipo prima di costruire una query.

## I limiti e i loro valori predefiniti {#the-limits-and-their-defaults}

| Impostazione | Predefinito | Che cosa limita |
|---|---|---|
| `MaxDepth` | 8 | Quanto in profondità possono annidarsi i filtri. Una singola condizione ha profondità 1. |
| `MaxLeaves` | 64 | Il numero di condizioni nell'intero filtro, sommate su tutti i rami. |
| `MaxInValues` | 1000 | Il numero di valori in un singolo elenco "in" o "not in". |
| `MaxPageSize` | 1000 | Il numero di righe in una pagina, ovvero `endRow - startRow`. |
| `MaxSetValuesResults` | 10000 | Il massimo di valori che una richiesta di valori distinti può restituire, qualunque sia il numero richiesto dalla griglia. |
| `DefaultSetValuesResults` | 1000 | Quanti valori restituisce tale richiesta quando la griglia non lo indica. |
| `MaxQueryTimeMs` | non impostato | Per quanto tempo una query MongoDB o Search può essere eseguita, in millisecondi. L'unico limite facoltativo; vedere [Il limite di tempo delle query](#the-query-time-limit). |

Queste sono proprietà di `ResourceLimits`.

I primi quattro sono controlli: una richiesta che supera il limite viene rifiutata. I due successivi sono tetti massimi. `MaxQueryTimeMs` non è né l'uno né l'altro: viene trasportato nella query e il database lo applica. Una richiesta di valori distinti per un filtro a insieme non viene mai rifiutata perché troppo grande. Craticula la riduce al tetto massimo e usa il valore predefinito quando la griglia non invia alcun numero.

Anche una richiesta che non invia né `startRow` né `endRow` non è illimitata: riceve una pagina predefinita di 100 righe (`AgGridParseOptions.DefaultPageSize`) e il limite della dimensione di pagina controlla tale pagina come qualsiasi altra. Vedere [Paginazione e ordinamento](paging-and-sorting.html).

Il limite della dimensione di pagina non si applica a un'esportazione dell'intero risultato (`exportScope` impostato su `"all"`), che non ha pagina. Un'esportazione limitata a una pagina mantiene il proprio intervallo di righe e il limite della dimensione di pagina si applica ad essa. Vedere [Esportazione CSV](csv-export.html).

Craticula conta insieme ai filtri i gruppi che l'utente ha aperto. Ogni gruppo aperto è una condizione in più e una richiesta raggruppata conta un livello in più di quelli che scrive, quindi il suo limite di profondità effettivo è 7 con il valore predefinito.

## Limiti fissi {#limits-that-are-fixed}

Alcuni limiti sono incorporati e non possono essere modificati:

- al massimo 64 colonne di raggruppamento in una richiesta;
- un valore di testo in un filtro di al massimo 8192 caratteri;
- un valore decimale di al massimo 128 caratteri;
- un id di colonna di al massimo 256 caratteri, in una chiave di ordinamento, in una colonna di raggruppamento, in un'aggregazione o nella colonna di un filtro a insieme.

## Che aspetto ha un rifiuto {#what-a-refusal-looks-like}

Quando una richiesta viola un limite, `GridFilterPipeline.Process` solleva una `ResourceLimitExceededException`. Il suo elenco `Violations` indica ogni limite violato, con il numero effettivo e il massimo. Intercettarla nell'endpoint e restituire un errore client. Se una richiesta viola due limiti, vengono mostrati entrambi.

## Come modificare un limite {#how-to-change-a-limit}

I limiti non fanno parte del file dello schema. Sono codice e vanno passati dallo sviluppatore. Così li imposta la demo:

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

Passare poi il valore alle chiamate che ne accettano uno. La guida introduttiva passa `new ResourceLimits()`, che significa i valori predefiniti.

```csharp
FilterNode? filter = GridFilterPipeline.Process(
    parsed.NativeFilter, parsed.CustomFilters, parsed.Page, schema, limits, parsed.Group, parsed.Aggregations);
```

Una richiesta di valori distinti passa da `GridFilterPipeline.ProcessSetValues` e il suo tetto proviene da `ResourceLimitsValidator.ResolveSetValuesLimit`.

È possibile alzare un limite quanto si vuole. Non esiste alcun controllo di limite superiore. Scegliere numeri che il proprio database è in grado di sostenere.

## Il limite di tempo delle query {#the-query-time-limit}

`MaxQueryTimeMs` è pensato per un host il cui database è condiviso o pubblico. Gli altri limiti delimitano la forma di una richiesta; questo delimita il lavoro che il database svolge per essa. Impostarlo a un numero intero di millisecondi, da 1 a 2,147,483,647, e i compilatori lo inseriscono nella query:

| Motore | Che cosa contiene la query | Che cosa accade allo scadere del tempo |
|---|---|---|
| MongoDB | `maxTimeMS` nel comando aggregate | MongoDB annulla l'operazione e l'adattatore solleva `QueryTimeoutException`. |
| OpenSearch ed Elasticsearch | un membro `timeout` del corpo di ricerca, ad esempio `"2000ms"` | Il motore si ferma al controllo successivo (un limite soft) e risponde con `timed_out: true`. L'adattatore solleva `QueryTimeoutException` e non restituisce mai gli hit parziali come pagina. |

Il limite proviene solo dal codice dello sviluppatore. Una richiesta non può impostarlo, alzarlo né rimuoverlo e un `maxQueryTimeMs` in una richiesta viene ignorato. Un'esportazione non porta alcun limite, perché è lunga per natura; interrompere un'esportazione con il token di annullamento. I motori SQL non hanno alcun limite compilato: impostare invece un timeout delle istruzioni sulla connessione o sull'account del database (la demo pubblica lo fa, per PostgreSQL).

Lasciarlo non impostato e nulla cambia: le query sono esattamente quelle di prima. Uno zero o un valore negativo solleva un'eccezione quando si costruisce il `ResourceLimits` e anche i compilatori lo rifiutano se si compila una richiesta a mano. Vedere le regole in [Limite di tempo delle query](query-time-limit.html).

## Non è possibile disattivare un limite {#you-cannot-turn-a-limit-off}

Ogni limite tranne uno è un semplice numero positivo e non esiste alcun valore "illimitato". Impostare un limite a zero o meno solleva una `ArgumentOutOfRangeException` quando si costruisce il `ResourceLimits`. L'eccezione è `MaxQueryTimeMs`, che per impostazione predefinita non è impostato perché la libreria non può sapere quanto sia lento il database; impostarlo su un numero non disattiva mai nulla.

È una scelta voluta. Un limite pari a zero non significherebbe "nessun limite". Rifiuterebbe ogni richiesta e un'impostazione lasciata vuota per errore potrebbe farlo senza che nessuno se ne accorga.

## Dove vengono eseguiti i controlli {#where-the-checks-run}

I limiti sono controllati da `GridFilterPipeline.Process`. L'adattatore che legge la richiesta AG Grid non li controlla e nemmeno i compilatori. Se si salta la pipeline e si chiama direttamente un compilatore, nessun limite viene controllato. La guida introduttiva chiama la pipeline per questo motivo. Vedere [Come una richiesta diventa una query](request-to-query.html).

## Da dove proviene questa pagina {#where-this-comes-from}

- [csharp/src/Craticula.Core/Schema/ResourceLimits.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimits.cs)
- [csharp/src/Craticula.Core/Schema/ResourceLimitsValidator.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimitsValidator.cs)
- [csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs](../../csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs)
- [csharp/src/Craticula.Core/Ir/GroupSpecValidator.cs](../../csharp/src/Craticula.Core/Ir/GroupSpecValidator.cs)
- [spec/semantics.md](../../spec/semantics.md), gli addendum sul limite di tempo delle query e sulla dimensione di pagina predefinita
- [examples/demo/Api/Grid/DemoLimits.cs](../../examples/demo/Api/Grid/DemoLimits.cs)
- [spec/ir.schema.json](../../spec/ir.schema.json)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
- Pagine correlate: [Il modello di sicurezza](safety-model.html), [Paginazione e ordinamento](paging-and-sorting.html), [Il GridSchema](the-gridschema.html)
