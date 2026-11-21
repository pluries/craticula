---
translates: dialects-and-providers
title: Dialetti e provider
description: Come ciascun motore di database differisce per quoting, paginazione, ordinamento dei null e confronto senza distinzione tra maiuscole e minuscole.
source_fingerprint: e3cadc85fee286141cd8091c6103e2780064d51e19a1428afa783d8f20b83081
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Dialetti e provider {#dialects-and-providers}

Questa pagina elenca i database per i quali Craticula può scrivere query, come differiscono le loro query e quali versioni sono testate. È rivolta allo sviluppatore che sceglie un database o un dialetto, oppure che vuole capire perché la stessa richiesta produce testi diversi su ciascuno.

## Che cos'è un dialetto {#what-a-dialect-is}

La stessa richiesta significa la stessa cosa su ogni backend. Craticula stabilisce una sola volta che cosa significa, nella forma canonica. Poi un writer per ciascun database la esprime nel linguaggio di quel database.

Per SQL, quel writer è un dialetto. Una classe di dialetto ha un'unica `Instance` condivisa, come `PostgresDialect.Instance`. La si passa a `SqlQueryBuilder.Build`. Ce ne sono cinque:

| Database | Classe del dialetto |
|---|---|
| PostgreSQL | `PostgresDialect` |
| SQL Server | `MssqlDialect` |
| MySQL (MariaDB passa dallo stesso dialetto ma non è mai stato testato) | `MySqlDialect` |
| SQLite | `SqliteDialect` |
| Oracle | `OracleDialect` |

MongoDB e OpenSearch hanno propri compilatori, `MongoPipelineBuilder` e `SearchQueryBuilder`. Non accettano un dialetto. Vedere [Adattatori MongoDB e OpenSearch](search-adapters.html).

## Come differisce l'SQL {#how-the-sql-differs}

| Database | Segnaposto | Quoting | Paginazione |
|---|---|---|---|
| PostgreSQL | `$1`, `$2` | `"name"` | `LIMIT` e `OFFSET` |
| SQL Server | `@p1`, `@p2` | `[name]` | `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` |
| MySQL | `?` | `` `name` `` | `LIMIT` e `OFFSET` |
| SQLite | `?` | `"name"` | `LIMIT` e `OFFSET` |
| Oracle | `:p1`, `:p2` | `"name"` | `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` |

In ogni caso i valori sono parametri, elencati nell'ordine in cui compaiono i segnaposto. Ogni nome di tabella e di colonna è racchiuso tra delimitatori e un carattere di delimitazione all'interno di un nome viene raddoppiato. Vedere [Il modello di sicurezza](safety-model.html).

PostgreSQL passa un elenco "in" come un unico parametro array. Gli altri database scrivono un segnaposto per ogni valore.

## Ordinamento dei null {#null-ordering}

Craticula indica in ogni query dove si collocano i null, quindi l'ordine non dipende dal comportamento predefinito del database. Il modo in cui lo indica dipende dal database:

- PostgreSQL, SQLite e Oracle dispongono di `NULLS FIRST` e `NULLS LAST`. SQLite richiede la versione 3.30.0 o successiva.
- SQL Server non ha una sintassi di questo tipo. La query ordina prima su `CASE WHEN column IS NULL THEN 1 ELSE 0 END`, poi sulla colonna.
- Nemmeno MySQL ne ha. La query ordina prima su `ISNULL(column)`, poi sulla colonna.
- MongoDB ordina su un campo ausiliario che contrassegna i null, e la query lo rimuove in seguito.
- OpenSearch usa `"missing": "_first"` oppure `"_last"`.

Vedere [Paginazione e ordinamento](paging-and-sorting.html).

## Confronto senza distinzione tra maiuscole e minuscole {#case-insensitive-comparison}

Un campo di testo viene confrontato senza considerare maiuscole e minuscole, a meno che lo schema non indichi diversamente. Ciascun database ci arriva in modo diverso:

| Database | Come ignora la distinzione tra maiuscole e minuscole |
|---|---|
| PostgreSQL | `COLLATE craticula_ci` nei confronti e negli ordinamenti, da creare una sola volta. `ILIKE` per `contains`, `startsWith` e `endsWith`. |
| SQL Server | `COLLATE Latin1_General_CI_AS` nella query. Un campo con distinzione tra maiuscole e minuscole riceve `Latin1_General_CS_AS`. |
| MySQL | Nulla nella query. Decide la collation della colonna stessa. Un campo con distinzione tra maiuscole e minuscole richiede una colonna `_bin` o `_as_cs`. |
| SQLite | `COLLATE NOCASE`, che uniforma solo le lettere ASCII. |
| Oracle | `COLLATE BINARY_CI`. Un campo con distinzione tra maiuscole e minuscole riceve `COLLATE BINARY`. |
| MongoDB | Una collation sull'intera query, con locale `en` e strength 2. |
| OpenSearch ed Elasticsearch | L'opzione `case_insensitive` sulle query term e wildcard e un sottocampo normalizzato per ordinamenti e intervalli. |

Due casi sono silenziosi: un campo con distinzione tra maiuscole e minuscole su MySQL e le colonne di raggruppamento su SQL Server, MySQL e Oracle. L'istruzione viene eseguita e restituisce righe errate se la collation della colonna non è quella che Craticula presume. Le indicazioni su indici e database elencano che cosa impostare in ciascun caso: [Indicazioni su indici e database](index-guidance.html).

## Versioni {#versions}

Queste sono le versioni minime necessarie alle query compilate, ricavate dalla specifica e dalla documentazione dei fornitori, non da un'esecuzione dei test. Solo la colonna dei test è stata eseguita. L'adattatore Elasticsearch è documentato per la versione 8.x.

| Database | Minimo | Su che cosa sono stati eseguiti i test |
|---|---|---|
| PostgreSQL | 12, con ICU | 16 |
| SQL Server | non indicato | 2022 |
| MySQL | non indicato | 8.4 |
| SQLite | 3.30.0 | non registrato |
| Oracle | 12.2 | Database Free 23ai |
| MongoDB | 4.2 | 7.0 |
| OpenSearch | 1.0 | 2.19 |
| Elasticsearch | 7.10 | 8.17 |

"Non indicato" significa che il codice e la specifica non fissano alcuna soglia minima, non che ogni vecchia versione sia stata provata. MariaDB usa il dialetto MySQL, ma nessun test viene eseguito su MariaDB.

I test eseguono le query compilate su database reali in container. Tale esecuzione richiede Docker e non fa parte dell'esecuzione rapida dei test, quindi consultare il repository per lo stato più recente.

## Lo stato di Oracle {#oracles-status}

Oracle è supportato come dialetto testato dalla community, non come dialetto core della v1. Viene valutato allo stesso modo degli altri: ogni istruzione è confrontata con un testo atteso memorizzato. La differenza sta nella copertura. È verificato su un insieme di esempi più ridotto rispetto agli altri quattro dialetti, 45 in tutto. Quei 45 vengono eseguiti anche su un vero server Oracle Database Free 23ai.

Le versioni da Oracle 12.2 a 21c non sono state eseguite. Il minimo 12.2 deriva dalla documentazione di Oracle, non da una misurazione.

Tre fatti su Oracle determinano l'output:

- **Il testo vuoto è null.** Un valore di testo `""` in un confronto corrisponderebbe silenziosamente alle righe sbagliate, quindi il dialetto Oracle lo rifiuta. Usare invece gli operatori blank e not-blank.
- **I nomi devono essere racchiusi tra delimitatori.** Creare la tabella e le sue colonne con nomi delimitati che corrispondano esattamente allo schema.
- **Impostazioni di sessione.** I formati di data, timestamp e numero provengono dalla sessione, quindi impostarli come descritto in [Indicazioni su indici e database](index-guidance.html).

## Provider {#providers}

Qui per provider si intende la libreria che comunica effettivamente con il database. Craticula non ne sceglie una al posto dello sviluppatore.

- Per SQL, `Craticula.Dapper` esegue qualsiasi dialetto su un `IDbConnection` aperto, qualunque sia il provider ADO.NET che l'ha creato.
- `Craticula.EntityFrameworkCore` usa il provider del `DbContext`. Richiede un `EfCoreProviderSemantics` che descriva il motore in uso e viene fornito solo quello per SQLite. Vedere [Entity Framework Core e Dapper](relational-adapters.html).
- MongoDB viene eseguito tramite il driver .NET ufficiale di MongoDB e OpenSearch tramite il client di basso livello `OpenSearch.Client`.

Il repository contiene un'app demo in `examples/demo` da eseguire autonomamente. Legge gli stessi ordini sintetici da diversi di questi database e confronta le risposte.

## Da dove proviene questa pagina {#where-this-comes-from}

- [csharp/src/Craticula.Sql/README.md](../../csharp/src/Craticula.Sql/README.md)
- [csharp/src/Craticula.Sql/OracleDialect.cs](../../csharp/src/Craticula.Sql/OracleDialect.cs)
- [csharp/src/Craticula.Sql/MssqlDialect.cs](../../csharp/src/Craticula.Sql/MssqlDialect.cs)
- [spec/fixtures/dialect-parity](../../spec/fixtures/dialect-parity/README.md)
- [spec/fixtures/README.md](../../spec/fixtures/README.md)
- [spec/semantics.md](../../spec/semantics.md)
- [csharp/tests/Craticula.Integration.Tests/Sql/SqlEngine.cs](../../csharp/tests/Craticula.Integration.Tests/Sql/SqlEngine.cs)
- [examples/demo/README.md](../../examples/demo/README.md)
- Pagine correlate: [Indicazioni su indici e database](index-guidance.html), [Paginazione e ordinamento](paging-and-sorting.html), [Il GridSchema](the-gridschema.html)
