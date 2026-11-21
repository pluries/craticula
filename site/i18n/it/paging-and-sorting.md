---
translates: paging-and-sorting
title: Paginazione e ordinamento
description: Come le righe vengono finestrate e ordinate e perché la paginazione è deterministica.
source_fingerprint: c01a09b912527d1a95923a5776c7b4abb3290f980e8c9111c4751565b710b445
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Paginazione e ordinamento {#paging-and-sorting}

Questa pagina descrive come l'intervallo di righe e l'ordinamento di una richiesta AG Grid diventano paginazione e ordinamento nella query. È destinata a uno sviluppatore che vuole sapere perché le righe tornano in un certo ordine e che cosa fa ciascun backend per scorrerle.

## Da startRow e endRow a una pagina {#from-startrow-and-endrow-to-a-page}

AG Grid chiede un blocco di righe con `startRow` e `endRow`. `endRow` è escluso. La dimensione della pagina è `endRow - startRow`.

Craticula lo trasforma in un numero di righe e un offset. Il numero di righe è la dimensione della pagina. L'offset è `startRow`. Una richiesta per le righe da 50 a 100 chiede 50 righe dopo averne saltate 50.

L'adattatore rifiuta una finestra priva di senso:

- un `startRow` negativo;
- un `endRow` inferiore a `startRow`;
- un `endRow` uguale a `startRow`, cioè una finestra vuota.

Anche una pagina ha una dimensione massima. Il valore predefinito è 1000 righe. Vedere [Limiti](limits.html).

## Una richiesta senza finestra {#a-request-with-no-window}

Alcune richieste non inviano né `startRow` né `endRow`: un client personalizzato o una richiesta costruita a mano. Dalla versione 1.2.0 una richiesta di questo tipo riceve una pagina predefinita di 100 righe, `[0, 100)`. La dimensione è `AgGridParseOptions.DefaultPageSize` e il limite della dimensione di pagina la verifica come qualsiasi altra finestra. Prima della versione 1.2.0 una richiesta senza finestra significava tutte le righe corrispondenti.

Ci sono due modi per chiedere tutte le righe, ed entrambi sono deliberati:

- **Un'esportazione di tutto** (`exportScope` impostato su `"all"`). Non ha pagina e gli adattatori la trasmettono in streaming blocco per blocco. Vedere [Esportazione CSV](csv-export.html).
- **Il flag `ignorePageLimit: true`**, che funziona solo se l'host ha attivato `AgGridParseOptions.AllowUnboundedRows` (disattivato per impostazione predefinita). Senza questo interruttore la richiesta viene rifiutata con l'errore di parsing `unbounded-not-allowed`; non viene mai limitata silenziosamente. Una richiesta che contiene una finestra la mantiene e il flag non cambia nulla.

Gli adattatori leggono in streaming una richiesta di tutte le righe. Il `FetchPageAsync` paginato degli adattatori MongoDB, Dapper, EF Core e OpenSearch rifiuta la pagina non paginata, così nessuna chiamata carica l'intero risultato in memoria. Per queste richieste usare lo stream di esportazione. Le regole sono in [Dimensione di pagina predefinita](default-page-size.html).

## Che cosa fa ciascun backend {#what-each-backend-does}

| Backend | Come viene scritta la pagina |
|---|---|
| PostgreSQL, MySQL, SQLite | `LIMIT n OFFSET m` |
| SQL Server, Oracle | `OFFSET m ROWS FETCH NEXT n ROWS ONLY` |
| MongoDB | uno stage `$skip`, poi uno stage `$limit` |
| OpenSearch ed Elasticsearch | `from` e `size` |

Per SQL, i due numeri sono parametri, non parte del testo. SQL Server e Oracle associano l'offset prima del numero di righe. PostgreSQL, MySQL e SQLite associano prima il numero di righe. Non occorre preoccuparsene, perché la lista dei parametri segue l'ordine in cui compaiono i segnaposto.

Un'esportazione di tutto non ha alcuna pagina. Chiede ogni riga corrispondente e non riceve alcuna clausola di paginazione. Vedere [Esportazione CSV](csv-export.html).

## Ordine di ordinamento {#sort-order}

La griglia invia in `sortModel` una lista di chiavi di ordinamento. Craticula le mantiene in quell'ordine. Ogni chiave ha una colonna e una direzione, `asc` o `desc`.

Un ordinamento su una colonna che lo schema non elenca viene rifiutato, sia in modalità Strict sia in modalità Lenient. Il rifiuto proviene dal compilatore, che lancia una propria eccezione di compilazione. Vedere [Strict e Lenient](strict-and-lenient.html).

Lo schema ha un flag `sortable` per ogni colonna. Nessuno lo legge (in questa versione). Una colonna presente nello schema può essere ordinata qualunque sia il suo flag. Non fare affidamento sul flag per impedire l'ordinamento di una colonna.

## Dove vanno i null {#where-nulls-go}

AG Grid non dice dove debbano essere ordinati i valori null. Lo decide Craticula, e lo decide allo stesso modo per ogni backend:

- un ordinamento crescente pone i null in fondo;
- un ordinamento decrescente pone i null all'inizio.

I database non concordano su questo per impostazione predefinita, quindi Craticula non lo lascia mai al database. Scrive la posizione in ogni chiave di ordinamento.

PostgreSQL, SQLite e Oracle dispongono di `NULLS FIRST` e `NULLS LAST` e Craticula li usa. SQLite richiede a tal fine la versione 3.30.0 o successiva. SQL Server e MySQL non hanno una sintassi simile, quindi Craticula aggiunge in testa un test che pone le righe null in un gruppo a sé: `CASE WHEN ... IS NULL` su SQL Server e `ISNULL(...)` su MySQL. Per MongoDB viene aggiunto un campo di supporto per ogni chiave di ordinamento, rimosso di nuovo dopo l'ordinamento. Per OpenSearch si ottiene `"missing": "_last"` oppure `"_first"`.

## L'ordinamento del testo ignora maiuscole e minuscole {#text-sorts-without-regard-to-case}

Per impostazione predefinita una colonna di testo viene confrontata senza distinguere tra maiuscole e minuscole. L'ordinamento segue la stessa regola, quindi `apple` e `Apple` si ordinano insieme. Una colonna può richiedere la distinzione esatta nello schema con `text.caseSensitivity` impostato su `sensitive`.

Ogni motore raggiunge lo stesso risultato a modo suo:

- PostgreSQL nomina una collation, `craticula_ci`, da creare una sola volta.
- SQL Server e SQLite nominano una collation direttamente nella query.
- MySQL usa la collation della colonna stessa.
- MongoDB imposta una collation sull'intera query.
- OpenSearch ordina su un sottocampo normalizzato che va mappato nell'indice.

Ciò che occorre configurare per ciascun database è descritto in [Indicazioni su indici e database](index-guidance.html).

## La chiave stabile mantiene l'ordine della paginazione {#the-stable-key-keeps-paging-in-order}

La paginazione è affidabile solo se l'ordine è totale. Se due righe sono in parità su ogni chiave di ordinamento, il database può restituirle in uno qualsiasi dei due ordini e una riga può comparire in due pagine o in nessuna.

Per evitarlo, lo schema nomina una `stableKey`, una colonna i cui valori sono univoci. Quando l'ordinamento non termina già con quella chiave, Craticula la aggiunge in fondo, in ordine crescente, con i null in fondo.

La richiesta della guida rapida ordina per `amount` in ordine decrescente. L'istruzione termina così:

```sql
ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST
```

Craticula riordina anche l'ordinamento prima di aggiungere qualcosa:

- una colonna nominata due volte mantiene solo la prima occorrenza;
- se la chiave stabile ordina in modo esatto, ogni chiave successiva viene eliminata, perché non resta alcuna parità da risolvere.

Fa eccezione una chiave stabile di testo che ignora maiuscole e minuscole. Due chiavi che differiscono solo per le maiuscole risultano uguali al confronto, quindi le chiavi successive restano e viene aggiunto uno spareggio esatto.

Tutto questo funziona solo se la chiave stabile è davvero univoca. La maggior parte dei database consente a una colonna univoca di contenere molti null, il che rompe la garanzia. Dichiarare la chiave `NOT NULL`. Vedere [Indicazioni su indici e database](index-guidance.html).

## Paginazione profonda {#deep-paging}

Le pagine della griglia per SQL e MongoDB usano un offset. Il database deve scorrere ogni riga saltata, quindi una pagina in profondità in una tabella grande è più lenta di una pagina vicina all'inizio. Indicizzare i filtri e misurare.

OpenSearch rifiuta `from` e `size` semplici oltre 10,000 righe. L'adattatore OpenSearch se ne occupa. Oltre quel punto passa a un point in time e a `search_after` e conserva un cursore tra le richieste. Ne derivano tre conseguenze:

- Bisogna fornirgli un'unica cache di cursori che duri quanto la sessione della griglia. `InMemorySearchCursorCache` è quella fornita. Una nuova cache per ogni richiesta vanifica il cursore.
- La prima richiesta che supera la soglia avanza dalla riga zero. I blocchi successivi sono rapidi.
- Il numero totale di righe oltre 10,000 viene riportato come sconosciuto, a meno che non si chieda il conteggio esatto, che costa un conteggio completo a ogni prima richiesta.

Vedere [Adattatori MongoDB e OpenSearch](search-adapters.html).

## Da dove proviene {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/sort-paging](../../spec/fixtures/sort-paging/README.md)
- [csharp/src/Craticula.Core/Schema/SemanticsResolver.cs](../../csharp/src/Craticula.Core/Schema/SemanticsResolver.cs)
- [csharp/src/Craticula.Core/Ir/PageSpecValidator.cs](../../csharp/src/Craticula.Core/Ir/PageSpecValidator.cs)
- [csharp/src/Craticula.Sql](../../csharp/src/Craticula.Sql/README.md)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs)
- [site/pages/quickstart-csharp.md](quickstart-csharp.md)
- Pagine correlate: [Come una richiesta diventa una query](request-to-query.html), [Raggruppamento e aggregazione](grouping-and-aggregation.html), [Dialetti e provider](dialects-and-providers.html)
