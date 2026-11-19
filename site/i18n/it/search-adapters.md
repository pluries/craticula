---
translates: search-adapters
title: Adattatori MongoDB e OpenSearch
description: Eseguire le query MongoDB e OpenSearch compilate con gli adattatori facoltativi, inclusa la paginazione profonda.
source_fingerprint: 48d257e31e0add276e9f93959d7b0b4c8302bb0209dc059498cdbe72961005ce
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Adattatori MongoDB e OpenSearch {#mongodb-and-opensearch-adapters}

Questa pagina descrive i due pacchetti facoltativi che eseguono le query di Craticula su un document store: `Craticula.MongoDB.Driver` per MongoDB e `Craticula.OpenSearch.Client` per OpenSearch ed Elasticsearch. È rivolta allo sviluppatore che usa uno di questi store e vuole che Craticula esegua la query oltre a scriverla.

## Che cosa offre il core e che cosa aggiungono gli adattatori {#what-the-core-gives-you-and-what-the-adapters-add}

I compilatori scrivono la query e si fermano lì.

- `Craticula.Mongo` trasforma una richiesta in una pipeline di aggregazione. `MongoPipelineBuilder.Build` restituisce un `MongoQuery` con il nome della collezione e gli stadi della pipeline.
- `Craticula.Search` trasforma una richiesta in un corpo di ricerca. `SearchQueryBuilder.Build` restituisce un `SearchQuery` con il nome dell'indice e il corpo, che `ToArtifact()` fornisce come JSON.

Nessuno dei due compilatori dipende da una libreria client e nessuno apre una connessione. È possibile eseguirne l'output direttamente.

Gli adattatori lo eseguono al posto dello sviluppatore. Installarli da NuGet: `dotnet add package Craticula.MongoDB.Driver` oppure `dotnet add package Craticula.OpenSearch.Client`. Vedere [la guida introduttiva C#](quickstart-csharp.html).

## MongoDB {#mongodb}

`Craticula.MongoDB.Driver` compila con `Craticula.Mongo` ed esegue la pipeline tramite il driver ufficiale di MongoDB, nell'intervallo `[3.13.0, 4.0)`.

```csharp
MongoGridPage result = await MongoGridQuery.FetchPageAsync(
    database,
    new MongoQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    includeRowCount: true);
```

Che cosa offre:

- `MongoGridQuery.FetchPageAsync` restituisce un `MongoGridPage` con `Columns`, `Rows` e un `RowCount` facoltativo.
- `MongoGridQuery.CountAsync` esegue solo il conteggio. Il conteggio è un'aggregazione separata che scarta l'ordinamento e la finestra di pagina, perché un conteggio non ha bisogno né dell'uno né dell'altra.
- `MongoExportStream.StreamAsync` trasmette in streaming ogni documento corrispondente per un'esportazione. Legge il cursore del driver batch dopo batch, senza alcun offset da percorrere. Vedere [Esportazione CSV](csv-export.html).
- Un limite di tempo, se ne viene impostato uno. Con `ResourceLimits.MaxQueryTimeMs` l'aggregazione compilata contiene `maxTimeMS`, MongoDB annulla una query che dura più a lungo e l'adattatore solleva `QueryTimeoutException`. Anche il conteggio riceve il limite, mentre l'esportazione no. Vedere [Limiti](limits.html).
- `FetchPageAsync` rifiuta la pagina non paginata. Una richiesta di tutte le righe passa da `MongoExportStream`, che non mantiene mai in memoria l'intero risultato.

Che cosa richiede dallo sviluppatore:

- Un `IMongoDatabase` aperto. L'adattatore non lo apre né lo chiude mai.
- Uno schema che associa ogni campo a un percorso del documento, come `"physical": { "mongo": { "path": "address.city" } }`, e una `source` che indica la collezione.
- MongoDB 4.2 o successivo. Vedere [Dialetti e provider](dialects-and-providers.html).

## OpenSearch ed Elasticsearch {#opensearch-and-elasticsearch}

`Craticula.OpenSearch.Client` compila con `Craticula.Search` ed esegue il corpo tramite il client di basso livello di `OpenSearch.Client`, nell'intervallo `[2.2.0, 3.0)`. Invia il JSON compilato così com'è. Non costruisce la richiesta una seconda volta con il client tipizzato.

```csharp
OpenSearchGridPage result = await OpenSearchGridQuery.FetchPageAsync(
    client,
    new SearchQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    gridSessionId,
    cache);
```

Qui `client` è un `IOpenSearchLowLevelClient`, `gridSessionId` è una stringa scelta dallo sviluppatore per la sessione della griglia e `cache` è un `ISearchCursorCache`.

Che cosa offre:

- `OpenSearchGridQuery.FetchPageAsync` restituisce un `OpenSearchGridPage` con `Columns`, `Rows`, un `RowCount` che può essere nullo e un flag `LastRow`.
- `OpenSearchExportStream.StreamAsync` trasmette in streaming ogni hit corrispondente per un'esportazione. Scrive sempre ogni colonna dello schema, nell'ordine di `schema.FieldOrder`, perché il compilatore di ricerca non ha proiezione delle colonne. Passare a `CsvWriter` un `ExportColumn` per ogni campo in `schema.FieldOrder`; un elenco più ristretto lo fa fallire per un numero di celle non corrispondente.
- Un limite di tempo, se ne viene impostato uno. Con `ResourceLimits.MaxQueryTimeMs` ogni corpo di ricerca contiene `timeout`. Una ricerca che esaurisce il tempo risponde comunque con gli hit trovati e `timed_out: true`; l'adattatore lo trasforma in una `QueryTimeoutException` e non restituisce mai gli hit parziali come pagina, né in una pagina della griglia né in un blocco di esportazione. Le richieste proprie di un'esportazione non contengono `timeout`. `FetchPageAsync` rifiuta la pagina non paginata; usare `OpenSearchExportStream`.

Che cosa richiede dallo sviluppatore:

- Un client aperto. L'adattatore non lo costruisce né lo chiude mai.
- Un mapping dell'indice corrispondente allo schema. Le query compilate nominano i sottocampi che lo schema dichiara, come un campo `keyword`. Se ne manca uno, un filtro può non corrispondere ad alcuna riga senza alcun errore. Vedere [Indicazioni su indici e database](index-guidance.html).
- Una cache dei cursori che duri quanto la sessione della griglia. Vedere sotto.

### La cache dei cursori {#the-cursor-cache}

OpenSearch rifiuta la paginazione semplice oltre 10,000 righe. L'adattatore passa a un point in time e a `search_after` e ricorda dove è terminato l'ultimo blocco. Quella memoria è l'`ISearchCursorCache` passato in ingresso.

`InMemorySearchCursorCache` è quella fornita. Crearla una sola volta per il processo e condividerla. Una nuova cache per ogni richiesta fa ripartire da zero ogni pagina profonda. `InMemorySearchCursorCache` conserva le proprie voci in un unico processo. Se le richieste di una sessione della griglia possono raggiungere più server, una pagina profonda su un altro server non trova alcun cursore e ripercorre di nuovo le righe dall'inizio. Una cache condivisa da tutti i server eviterebbe il problema, ma non ne viene fornita alcuna.

Lo stesso cursore serve i livelli raggruppati. Un livello raggruppato usa un'aggregazione composite, che non può iniziare da una riga diversa da zero. L'adattatore conserva la chiave dell'ultimo gruppo e la rinvia per richiedere il blocco successivo.

### Opzioni {#options}

`OpenSearchDeepPagingOptions` modifica la paginazione:

| Impostazione | Predefinito | Che cosa fa |
|---|---|---|
| `MaxResultWindow` | 10,000 | Il numero di righe oltre il quale l'adattatore passa al cursore. |
| `WalkBatchSize` | 1,000 | Di quante righe avanza un singolo passo di recupero. |
| `PitKeepAlive` | 5 minuti | Per quanto tempo un cursore inattivo resta valido. |
| `ExactRowCount` | `false` | Chiedere al motore il conteggio esatto quando si richiede un conteggio di righe. |
| `Flavour` | `OpenSearch` | Il motore, `OpenSearch` oppure `Elasticsearch`. |

Senza `ExactRowCount`, un conteggio superiore alla finestra viene riportato come sconosciuto, il che è economico. Con essa, il motore conta ogni corrispondenza a ogni prima richiesta.

### Elasticsearch {#elasticsearch}

La richiesta compilata è la stessa per entrambi i motori. Differiscono solo le chiamate che aprono e chiudono un point in time. Impostare il flavour su entrambi i record di opzioni quando il cluster è Elasticsearch:

```csharp
var paging = new OpenSearchDeepPagingOptions { Flavour = SearchEngineFlavour.Elasticsearch };
var export = new OpenSearchExportOptions { Flavour = SearchEngineFlavour.Elasticsearch };
```

Con il flavour predefinito su Elasticsearch, una finestra oltre 10,000 righe e ogni esportazione falliscono con HTTP 400.

## Che cosa non fanno mai {#what-they-never-do}

- Non aprono, non chiudono e non configurano mai una connessione o un client.
- Non ripetono mai una richiesta fallita e non impostano mai un timeout.
- Non impongono mai un numero massimo di righe esportate.
- Non applicano mai i limiti di risorse né i controlli sulle colonne dello schema. Eseguire prima `GridFilterPipeline.Process`. Vedere [Il modello di sicurezza](safety-model.html).
- Non esportano mai un risultato raggruppato. Un'esportazione è un elenco piatto di righe e i flussi di esportazione rifiutano una richiesta che contiene un gruppo.

## Da dove proviene questa pagina {#where-this-comes-from}

- [csharp/src/Craticula.MongoDB.Driver/README.md](../../csharp/src/Craticula.MongoDB.Driver/README.md)
- [csharp/src/Craticula.OpenSearch.Client/README.md](../../csharp/src/Craticula.OpenSearch.Client/README.md)
- [csharp/src/Craticula.MongoDB.Driver/MongoGridQuery.cs](../../csharp/src/Craticula.MongoDB.Driver/MongoGridQuery.cs)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchDeepPagingOptions.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchDeepPagingOptions.cs)
- [csharp/src/Craticula.Mongo/README.md](../../csharp/src/Craticula.Mongo/README.md)
- [csharp/src/Craticula.Search/README.md](../../csharp/src/Craticula.Search/README.md)
- Pagine correlate: [Entity Framework Core e Dapper](relational-adapters.html), [Paginazione e ordinamento](paging-and-sorting.html), [Raggruppamento e aggregazione](grouping-and-aggregation.html)
