---
translates: relational-adapters
title: Entity Framework Core e Dapper
description: Che cosa offrono i due adattatori relazionali, che cosa richiedono e che cosa non fanno mai.
source_fingerprint: c7c6226b52fe85563de296ccf30f4b6133346e53ef471b90257c33696e64481f
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Entity Framework Core e Dapper {#entity-framework-core-and-dapper}

Questa pagina descrive i due pacchetti facoltativi che eseguono le query di Craticula su un database relazionale: `Craticula.Dapper` e `Craticula.EntityFrameworkCore`. È rivolta allo sviluppatore che dispone di un database SQL e vuole che Craticula esegua la query oltre a scriverla.

## Perché esistono gli adattatori {#why-adapters-exist}

I pacchetti core si limitano a compilare. Non aprono mai una connessione e non eseguono mai nulla. Un adattatore colma questa lacuna per una specifica libreria di accesso ai dati: compila la richiesta, la esegue e restituisce le righe.

Gli adattatori sono facoltativi. I pacchetti core non dipendono mai da essi. È possibile farne a meno ed eseguire l'istruzione compilata con qualsiasi libreria.

Installarli da NuGet: `dotnet add package Craticula.Dapper` oppure `dotnet add package Craticula.EntityFrameworkCore`. Vedere [la guida introduttiva C#](quickstart-csharp.html).

## Dapper {#dapper}

`Craticula.Dapper` compila con `Craticula.Sql` ed esegue l'istruzione su una connessione fornita dal chiamante. Usarlo quando si vuole vedere e controllare l'SQL.

```csharp
DapperGridPage result = await DapperGridQuery.FetchPageAsync(
    openConnection,
    new SqlQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    PostgresDialect.Instance,
    includeRowCount: true);
```

Che cosa offre:

- `DapperGridQuery.FetchPageAsync` restituisce una pagina. `DapperGridPage` contiene `Columns`, `Rows` e un `RowCount` facoltativo.
- `DapperGridQuery.CountAsync` esegue solo il conteggio.
- `DapperExportStream.StreamAsync` trasmette in streaming ogni riga corrispondente per un'esportazione. Vedere [Esportazione CSV](csv-export.html).
- `FetchPageAsync` rifiuta la pagina non paginata (`NonePage`), così una chiamata non carica mai tutte le righe in memoria. Una richiesta di tutte le righe passa da `DapperExportStream`.

Che cosa richiede dallo sviluppatore:

- Un `IDbConnection` aperto. L'adattatore non lo apre né lo chiude mai.
- Il dialetto corrispondente al proprio database. Vedere [Dialetti e provider](dialects-and-providers.html).
- Dapper stesso, nell'intervallo `[2.1.89, 3.0)`.

Le richieste raggruppate funzionano con lo stesso metodo. Il compilatore SQL scrive già l'istruzione raggruppata, quindi l'adattatore si limita a eseguirla.

## Entity Framework Core {#entity-framework-core}

`Craticula.EntityFrameworkCore` non scrive testo SQL. Costruisce alberi di espressioni `IQueryable<T>`, che il provider EF Core traduce in SQL. Usarlo quando si dispone già di un `DbContext` e si vuole che si applichino i suoi filtri di query globali, come un filtro per tenant.

```csharp
var request = new EfCoreQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page };

EfCoreGridPage result = await EfCoreGridQuery.FetchPageAsync(
    source, request, EfCoreProviderSemantics.Sqlite, includeRowCount: true);
```

Che cosa offre:

- `EfCoreGridQuery.FetchPageAsync` restituisce una pagina, in un `EfCoreGridPage` con la stessa forma di quello di Dapper.
- `EfCoreGridQuery.CountAsync` esegue solo il conteggio.
- `EfCoreExportStream.StreamAsync` trasmette in streaming le righe per un'esportazione.
- `FetchPageAsync` rifiuta la pagina non paginata, come fa l'adattatore Dapper. Una richiesta di tutte le righe passa da `EfCoreExportStream`.

Che cosa richiede dallo sviluppatore:

- **Una query di origine.** Passare un `DbSet<T>`, oppure `GridSchemaPropertyBag.Query(context, schema)` se non si hanno classi di entità. Per la seconda forma, chiamare `GridSchemaPropertyBag.Configure` in `OnModelCreating`.
- **Nomi di proprietà corrispondenti.** Ogni campo è letto come una proprietà EF denominata come il suo `physical.sql.column`, oppure come l'id della colonna quando non c'è. Una classe che rinomina le proprie colonne con `HasColumnName` deve allinearsi a questa regola.
- **Un valore `EfCoreProviderSemantics`.** Dichiara cinque fatti sul database che EF non può comunicare a Craticula, come il nome della collation senza distinzione tra maiuscole e minuscole. Viene fornito solo `EfCoreProviderSemantics.Sqlite`, perché è l'unico che è stato misurato. Per un altro motore se ne dichiara uno proprio, una sola volta, accanto al `DbContext`.

I campi dello schema devono usare un semplice `physical.sql.column`. Un campo con `qualifiedColumn` o `expression` viene rifiutato, perché nessuno dei due ha una forma in un albero di espressioni.

Se un tipo `DbContext` può essere costruito a partire da più di uno schema, registrare `GridSchemaModelCacheKeyFactory` e implementare `IGridSchemaModel` sul contesto. Senza questo, EF riutilizza il modello del primo schema per lo schema successivo e fallisce con errori che non menzionano la cache.

### Due insidie silenziose {#two-silent-traps}

Entrambe producono righe errate senza alcun errore. L'adattatore non può vedere il modello né le collation, quindi non può proteggersi da esse.

- **Valori di data e ora in SQLite.** Memorizzare un `datetime` come testo `yyyy-MM-ddTHH:mm:ss.fffZ` e mappare ogni `DateTime` da e verso quel testo nel proprio `DbContext`. La mappatura propria di EF usa una forma diversa e SQLite confronta il testo carattere per carattere.
- **`PatternMatchFoldsCase`.** Indica se il `LIKE` del motore ignora la distinzione tra maiuscole e minuscole. Usare `true` per SQLite. Per SQL Server e MySQL usare `false`, a meno che ogni colonna ricercabile non abbia una collation che ignora tale distinzione. In caso contrario una colonna con collation binaria corrisponde solo alla stessa combinazione di maiuscole e minuscole.

Le celle di data e ora lasciano una pagina o un'esportazione come valori UTC, qualunque cosa abbia restituito il provider.

## Che cosa hanno in comune i due adattatori {#what-both-adapters-share}

- **I conteggi delle righe sono opt-in.** Il conteggio è un secondo round trip, quindi è disattivato a meno che non si passi `includeRowCount`. Una griglia ne ha bisogno una volta a ogni cambio di filtro, non una volta per blocco.
- **Le esportazioni non usano mai un offset.** Leggono le righe a blocchi di 5,000 percorrendo le chiavi di ordinamento, così un blocco tardivo costa quanto uno iniziale. `DapperExportOptions` e `EfCoreExportOptions` hanno un `ChunkSize` per modificarlo. L'esportazione richiede una chiave stabile davvero univoca. Un duplicato viene rilevato e solleva un'eccezione.
- **Dapper rifiuta alcune esportazioni.** `DapperExportStream` rifiuta uno schema la cui chiave stabile è una colonna di testo. Rifiuta inoltre un'esportazione in cui una chiave di ordinamento di testo contiene una stringa vuota nelle righe esportate, su ogni dialetto tranne Oracle. In entrambi i casi usare una chiave stabile numerica o di data, oppure recuperare i dati pagina per pagina con `DapperGridQuery.FetchPageAsync`. `EfCoreExportStream` non ha un controllo di questo tipo.
- **Un'esportazione limitata a una pagina viene rifiutata.** I flussi di esportazione accettano l'intero risultato. Una pagina delimitata passa dal metodo di pagina.
- **Un risultato neutro.** Ogni pagina ha un metodo di estensione `ToGridPageResult()`. Quello di OpenSearch accetta anche il `SearchQueryRequest` usato. `LoadSuccessParamsMapper.Map` in `Craticula.AgGrid` lo trasforma nella forma attesa da AG Grid.

## Che cosa non fanno mai {#what-they-never-do}

- Non aprono, non chiudono e non gestiscono mai in pool una connessione e non avviano mai una transazione.
- Non ripetono mai una query fallita e non impostano mai un timeout. La connessione e le impostazioni del comando spettano allo sviluppatore.
- Non impongono mai un numero massimo di righe esportate.
- Non applicano mai i limiti di risorse né i controlli sulle colonne dello schema. Eseguire prima `GridFilterPipeline.Process`, come fa la guida introduttiva. Vedere [Il modello di sicurezza](safety-model.html).

## Quale scegliere {#which-one-to-pick}

| Situazione | Usare |
|---|---|
| Un semplice `IDbConnection` e la volontà di vedere l'SQL | Dapper |
| Uno qualsiasi dei cinque dialetti SQL, senza codice aggiuntivo | Dapper |
| Un `DbContext` con filtri di query globali da mantenere | Entity Framework Core |

La demo esegue entrambi su PostgreSQL, così è possibile confrontarli sugli stessi dati.

## Da dove proviene questa pagina {#where-this-comes-from}

- [csharp/src/Craticula.Dapper/README.md](../../csharp/src/Craticula.Dapper/README.md)
- [csharp/src/Craticula.EntityFrameworkCore/README.md](../../csharp/src/Craticula.EntityFrameworkCore/README.md)
- [csharp/src/Craticula.Dapper/DapperGridQuery.cs](../../csharp/src/Craticula.Dapper/DapperGridQuery.cs)
- [csharp/src/Craticula.EntityFrameworkCore/EfCoreGridQuery.cs](../../csharp/src/Craticula.EntityFrameworkCore/EfCoreGridQuery.cs)
- [csharp/src/Craticula.EntityFrameworkCore/EfCoreProviderSemantics.cs](../../csharp/src/Craticula.EntityFrameworkCore/EfCoreProviderSemantics.cs)
- [csharp/src/Craticula.EntityFrameworkCore/GridSchemaPropertyBag.cs](../../csharp/src/Craticula.EntityFrameworkCore/GridSchemaPropertyBag.cs)
- [examples/demo/README.md](../../examples/demo/README.md)
- Pagine correlate: [Esportazione CSV](csv-export.html), [Adattatori MongoDB e OpenSearch](search-adapters.html), [Paginazione e ordinamento](paging-and-sorting.html)
