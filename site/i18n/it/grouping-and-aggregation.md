---
translates: grouping-and-aggregation
title: Raggruppamento e aggregazione
description: Come una griglia raggruppata chiede un livello alla volta e come si comportano le aggregazioni.
source_fingerprint: 10e3bdf6eb7dc0f59a4e20738237bb2f9f7ebac06181756626f1c01f952450a5
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Raggruppamento e aggregazione {#grouping-and-aggregation}

Questa pagina tratta il raggruppamento di righe e l'aggregazione: come una griglia raggruppata chiede un livello alla volta, come Craticula risponde a ciascun livello e che cosa deve consentire lo schema. È destinata a uno sviluppatore la cui griglia raggruppa le righe e mostra dei totali. Il raggruppamento di righe e l'aggregazione sono funzionalità AG Grid Enterprise.

## Un livello per richiesta {#one-level-per-request}

Una griglia raggruppata non chiede l'intero albero. Chiede un livello alla volta e ogni richiesta porta con sé il percorso fin lì compiuto.

Due liste nella richiesta descrivono quel percorso:

- `rowGroupCols` elenca le colonne per cui la griglia raggruppa, in ordine.
- `groupKeys` elenca i gruppi che l'utente ha già aperto, una chiave per ogni livello.

Craticula confronta le due lunghezze:

- **Meno chiavi che colonne.** La richiesta chiede un livello raggruppato. Craticula raggruppa per la colonna successiva che non ha ancora una chiave, e solo per quella. Calcola le aggregazioni per ciascun gruppo.
- **Tante chiavi quante colonne.** Ogni livello è aperto. La richiesta chiede le righe all'interno dell'ultimo gruppo. Craticula restituisce righe semplici e non effettua alcun raggruppamento.
- **Più chiavi che colonne.** La richiesta è malformata e viene rifiutata.

La modalità pivot non è supportata. Una richiesta con `pivotMode` impostato su `true`, o con qualsiasi `pivotCols`, viene rifiutata.

## Un esempio {#an-example}

Si consideri una griglia raggruppata per `region`, poi `segment`, poi `product`, con una somma di `amount`. L'utente ha aperto la regione `EMEA`. La griglia chiede ora i segmenti all'interno di `EMEA`.

Per PostgreSQL, Craticula scrive:

```sql
SELECT "segment" AS "segment", COALESCE(SUM("amount"), 0) AS "amount_sum" FROM "sales_fact" WHERE "region" = $1 GROUP BY "segment" ORDER BY "segment" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: 'EMEA', 100, 0
```

Il gruppo aperto è diventato `WHERE "region" = $1`. La colonna successiva, `segment`, è diventata il `GROUP BY`. L'aggregato si chiama `amount_sum`.

## Le chiavi di gruppo arrivano come valori tipizzati {#group-keys-arrive-as-typed-values}

Craticula legge ogni voce di `groupKeys` come valore tipizzato, con il tipo corrispondente a quello dichiarato per la colonna, e non come la semplice stringa inviata da AG Grid:

```json
"groupKeys": [ { "type": "string", "value": "EMEA" } ]
```

La pagina deve convertire le chiavi prima di inviare la richiesta. La demo lo fa in `toWireRequest` in `examples/demo/web/src/datasource.ts`. Rinomina inoltre le colonne aggregate nel percorso di ritorno, perché la risposta le chiama `amount_sum` mentre la griglia legge `amount`. Se si copia la demo, vanno copiati entrambi i passaggi.

## Quali funzioni si possono usare {#which-functions-you-can-use}

Craticula supporta cinque funzioni di aggregazione: `sum`, `min`, `max`, `avg` e `count`. Un'altra funzione, come `first`, viene rifiutata. Lo stesso vale per una voce di `valueCols` priva di `aggFunc`.

Il nome di ciascun aggregato nel risultato è l'id della colonna quando differisce dal nome del campo. Altrimenti è il nome del campo, un underscore e la funzione, ad esempio `amount_sum`.

Alcuni dettagli importanti per i numeri:

- `count` conta le righe in cui il campo non è null. Non conta le righe. Per contare ogni riga, contare la chiave stabile, che non è mai null.
- Una `sum` su un gruppo privo di valori è `0` su ogni backend. I compilatori SQL avvolgono `sum` in modo che corrisponda.
- `avg`, `min` e `max` su un gruppo privo di valori sono null.

## Che cosa deve consentire lo schema {#what-the-schema-must-allow}

Lo schema decide quali colonne possono essere raggruppate e aggregate. Entrambi i flag sono disattivati per impostazione predefinita.

```json
"region": { "type": "string", "groupable": true, "physical": { "sql": { "column": "region" } } },
"amount": { "type": "decimal", "aggregatable": ["sum", "avg"], "physical": { "sql": { "column": "amount" } } }
```

- Una colonna di raggruppamento deve essere nello schema e contrassegnata come `groupable`.
- Un'aggregazione deve nominare una colonna dello schema e una funzione presente nell'elenco `aggregatable` di quella colonna.
- Una colonna che è stata aperta, così che la sua chiave è in `groupKeys`, deve essere anche `filterable`. Aprire un gruppo equivale a filtrare su un singolo valore.

Ognuno di questi casi viene rifiutato in entrambe le modalità, Strict e Lenient. Scartare una colonna di raggruppamento o una chiave darebbe alla griglia una risposta diversa da quella richiesta. Vedere [Strict e Lenient](strict-and-lenient.html).

## L'apertura di un gruppo è una corrispondenza esatta {#opening-a-group-matches-exactly}

Quando un gruppo viene aperto, la sua chiave diventa una corrispondenza esatta sulla colonna di raggruppamento. Raggruppamento, apertura di un gruppo e ordinamento dei gruppi usano tutti il confronto esatto, quindi `EMEA` ed `emea` sono due gruppi. Un gruppo che non corrispondesse esattamente non si sommerebbe al suo gruppo padre.

Questo è vero solo se il database confronta in modo esatto per impostazione predefinita. PostgreSQL e SQLite lo fanno. SQL Server, MySQL e Oracle di norma ignorano la distinzione tra maiuscole e minuscole, quindi ogni colonna per cui si raggruppa va dichiarata con una collation binaria. Vedere [Indicazioni su indici e database](index-guidance.html).

MongoDB ha un'unica collation per l'intera query. Una richiesta di raggruppamento non ne porta alcuna, quindi un filtro nella stessa richiesta confronta lì distinguendo tra maiuscole e minuscole. I database SQL, in quel filtro, ignorano la distinzione.

## Chiavi di gruppo null {#null-group-keys}

Le righe con un valore di gruppo null formano un unico gruppo. Per aprirlo, inviare una chiave `{ "type": "null" }`. Craticula scrive per esso un test di nullità, come `"region" IS NULL`.

La stringa vuota è un gruppo diverso dal null, quindi le sue righe non si uniscono al gruppo null. Fa eccezione Oracle, perché Oracle memorizza una stringa vuota come null.

## Ordinare e contare un livello raggruppato {#sorting-and-counting-a-grouped-level}

Un livello raggruppato può essere ordinato per la sua colonna di raggruppamento o per uno dei suoi aggregati. Un ordinamento su qualsiasi altra colonna viene rifiutato. La colonna di raggruppamento funge da chiave stabile, quindi l'ordine dei gruppi è stabile. Un aggregato elencato dopo la colonna di raggruppamento nell'ordinamento non ha effetto e viene eliminato.

Il conteggio delle righe per un livello raggruppato è il numero di gruppi, non il numero di righe al loro interno.

OpenSearch ed Elasticsearch hanno qui due limiti:

- Non possono ordinare un livello raggruppato per un aggregato. Una richiesta di questo tipo viene rifiutata.
- Il gruppo che contiene i valori null si ordina sempre per primo, qualunque sia la direzione.

## Le esportazioni ignorano il raggruppamento {#exports-ignore-grouping}

Un'esportazione restituisce righe semplici. L'adattatore elimina `rowGroupCols`, `valueCols` e `groupKeys` da una richiesta di esportazione. Vedere [Esportazione CSV](csv-export.html).

## Da dove proviene {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/group-aggregation](../../spec/fixtures/group-aggregation/README.md)
- [csharp/src/Craticula.Core/Ir/Aggregation.cs](../../csharp/src/Craticula.Core/Ir/Aggregation.cs)
- [csharp/src/Craticula.Core/Ir/GroupingPlan.cs](../../csharp/src/Craticula.Core/Ir/GroupingPlan.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/src/Craticula.AgGrid/AgGridRequestParser.cs](../../csharp/src/Craticula.AgGrid/AgGridRequestParser.cs)
- [examples/demo/web/src/datasource.ts](../../examples/demo/web/src/datasource.ts)
- Pagine correlate: [Paginazione e ordinamento](paging-and-sorting.html), [Il GridSchema](the-gridschema.html), [Come una richiesta diventa una query](request-to-query.html)
