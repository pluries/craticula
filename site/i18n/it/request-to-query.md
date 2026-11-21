---
translates: request-to-query
title: Come una richiesta diventa una query
description: Il percorso da una richiesta AG Grid a un'istruzione con parametri.
source_fingerprint: 6c0315a52de692dbf39fc149aa86390474630dd3c2eb2282d8985f93da818dc0
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Come una richiesta diventa una query {#how-a-request-becomes-a-query}

Questa pagina segue una richiesta AG Grid attraverso Craticula, passo dopo passo, fino a quando diventa una query con parametri. È destinata a uno sviluppatore che vuole sapere che cosa accade tra la griglia e il database e perché i passaggi sono più d'uno.

## Il percorso {#the-path}

```text
request JSON -> adapter -> canonical form -> compiler -> query + parameters
```

1. **Request JSON.** La invia la griglia. Craticula non modifica ciò che la griglia invia.
2. **Adapter.** L'adattatore AG Grid legge il JSON e lo trasforma nella forma canonica. Rifiuta il JSON che non comprende.
3. **Forma canonica.** Il progetto la chiama IR, abbreviazione di intermediate representation. È un'unica descrizione di filtri, ordinamento, raggruppamento e paginazione che non dipende da AG Grid né da alcun database.
4. **Controlli.** Prima di compilare, Craticula verifica la forma canonica rispetto allo schema e ai limiti di risorse. Converte inoltre ogni valore nel tipo dichiarato dallo schema.
5. **Compilatore.** Un compilatore per ciascun backend scrive la query. Il compilatore SQL ha un writer per ogni dialetto di database.
6. **Query e parametri.** Per SQL si ottengono il testo dell'istruzione e una lista di valori. I valori non fanno mai parte del testo.

Poiché ogni backend legge la stessa forma canonica, la stessa richiesta ha lo stesso significato ovunque. Le regole per dettagli come la gestione dei null e la distinzione tra maiuscole e minuscole sono scritte una sola volta, nella specifica, e ogni compilatore le segue.

## Lo schema è il confine {#the-schema-is-the-boundary}

Lo schema è un documento JSON scritto da chi usa la libreria. Nomina la tabella o la collezione e le colonne che la griglia può usare. Ogni colonna ha un tipo e un nome fisico nel database. Nomina anche una chiave stabile, una colonna con valori univoci che Craticula usa per mantenere la paginazione in un ordine fisso.

Una colonna che non è nello schema non può arrivare a una query. Vedere [Il modello di sicurezza](safety-model.html) per capire come.

## Che cosa può chiedere la richiesta {#what-the-request-can-ask-for}

- **Paginazione.** La griglia chiede un intervallo di righe, ad esempio le prime 50. Craticula lo trasforma in un limite e un offset, o nell'equivalente per il backend. Una pagina ha una dimensione massima.
- **Ordinamento.** L'ordinamento segue l'ordine inviato dalla griglia. Craticula aggiunge in fondo la chiave stabile, in modo che le righe con valori uguali tornino sempre nello stesso ordine.
- **Filtraggio.** I filtri di testo, numero e data diventano confronti uniti con AND o OR. Per il testo il confronto senza distinzione tra maiuscole e minuscole è il comportamento predefinito.
- **Raggruppamento.** Per le griglie raggruppate, la richiesta contiene le colonne di raggruppamento, le chiavi di gruppo già aperte e le aggregazioni da calcolare. Craticula costruisce la query raggruppata per il livello richiesto.

## Un piccolo esempio {#a-small-example}

Questa è la richiesta della guida rapida. Chiede i clienti contenenti "acme" con un importo superiore a 100, dagli importi maggiori, righe da 0 a 50.

```json
{
  "startRow": 0,
  "endRow": 50,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "customer": { "filterType": "text", "type": "contains", "filter": "acme" },
    "amount": { "filterType": "number", "type": "greaterThan", "filter": 100 }
  },
  "sortModel": [ { "colId": "amount", "sort": "desc" } ]
}
```

Per PostgreSQL, il programma della guida rapida stampa questa istruzione e questi parametri:

```sql
SELECT * FROM "orders" WHERE ("customer" ILIKE '%' || $1 || '%' ESCAPE '\' AND "amount" > $2::numeric) ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'acme', '100', 50, 0
```

Si osservi che cosa è successo:

- "acme" e 100 non sono nel testo. Sono i parametri.
- I nomi di tabella e di colonna provengono dallo schema, non dalla richiesta.
- L'ordinamento termina con `id`, la chiave stabile dello schema.
- L'intervallo di pagina è diventato `LIMIT 50 OFFSET 0`.

SQL Server riceve un'istruzione diversa dalla stessa richiesta, perché scrive in modo diverso il confronto senza distinzione tra maiuscole e minuscole e l'ordinamento dei null. La [guida rapida C#](quickstart-csharp.html) mostra entrambe.

## Che cosa si scrive in C# {#what-you-write-in-c}

Nella guida rapida, il codice compie quattro operazioni in quest'ordine:

1. Analizzare lo schema con `GridSchema.Parse`.
2. Analizzare la richiesta con `AgGridRequestParser.Parse`.
3. Validare con `GridFilterPipeline.Process`. Questo passaggio applica il controllo delle colonne, i limiti e la conversione dei tipi.
4. Compilare con `SqlQueryBuilder.Build` e un dialetto come `PostgresDialect.Instance`.

MongoDB e OpenSearch hanno i propri builder, `MongoPipelineBuilder` e `SearchQueryBuilder`.

Per mostrare il numero totale di righe accanto a una pagina, ogni compilatore dispone anche di `BuildCount`. Usa lo stesso filtro ma nessun ordinamento e nessuna finestra di righe, perché un conteggio non ne ha bisogno. Per un conteggio, passare a `GridFilterPipeline.Process` un `NonePage`, in modo che una dimensione di pagina elevata non possa farlo fallire.

## Da dove proviene {#where-this-comes-from}

- [site/pages/quickstart-csharp.md](quickstart-csharp.md)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
- [spec/semantics.md](../../spec/semantics.md)
- [spec/ir.schema.json](../../spec/ir.schema.json)
- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs](../../csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs)
- [spec/fixtures/operators](../../spec/fixtures/operators/001-eq-string/description.md)
