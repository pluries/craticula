---
translates: odata-migration
title: Migrare da OData
description: Passare una griglia da OData alle query compilate e vedere che cosa cambia.
source_fingerprint: fd82735ea37c07ef6fc24c75d469d2a95817109d4cb1345e8240e4df38b66ee0
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Migrare da OData {#migrating-from-odata}

Questa pagina è per un team la cui griglia oggi dialoga con un servizio OData e che vuole passare a Craticula. Mostra, costrutto per
costrutto, che cosa si scriveva in OData e la richiesta che Craticula riceve al suo posto. Ogni esempio è un file che un test compila, quindi la
richiesta e l'istruzione sotto di essa sono reali e non possono diventare obsolete.

Due cose sono diverse fin dall'inizio:

- **Craticula riceve la richiesta che AG Grid già invia.** Non c'è alcuna stringa di query URL da costruire. Il Server-Side Row Model della griglia
  invia con POST un corpo JSON (`filterModel`, `sortModel`, `startRow`, `endRow`, `rowGroupCols`, `valueCols`, `groupKeys`), e Craticula
  lo compila. Il lato «OData» qui sotto è ciò che il vostro servizio riceveva; il lato «Craticula» è ciò che invia la griglia.
- **Craticula compila; non serve.** Restituisce un'istruzione e i suoi parametri. La si esegue con il proprio driver, e
  l'endpoint lo scrivete voi (vedere la [guida rapida C#](quickstart-csharp.html)).

Tutti gli esempi usano un piccolo schema sintetico, `orders` (id, customer, amount, active, status, region, country), e stampano l'istruzione
PostgreSQL. Gli altri database hanno una propria grafia della stessa richiesta.

````json
{
  "mode": "strict",
  "source": "orders",
  "stableKey": "id",
  "fields": {
    "id": {
      "type": "int64",
      "sortable": true,
      "physical": {
        "sql": {
          "column": "id"
        }
      },
      "aggregatable": [
        "count"
      ]
    },
    "customer": {
      "type": "string",
      "filterable": true,
      "sortable": true,
      "physical": {
        "sql": {
          "column": "customer"
        }
      }
    },
    "amount": {
      "type": "decimal",
      "filterable": true,
      "sortable": true,
      "aggregatable": [
        "sum",
        "avg",
        "min",
        "max",
        "count"
      ],
      "physical": {
        "sql": {
          "column": "amount"
        }
      }
    },
    "active": {
      "type": "boolean",
      "filterable": true,
      "sortable": true,
      "physical": {
        "sql": {
          "column": "active"
        }
      }
    },
    "status": {
      "type": "string",
      "filterable": true,
      "sortable": true,
      "physical": {
        "sql": {
          "column": "status"
        }
      }
    },
    "region": {
      "type": "string",
      "filterable": true,
      "sortable": true,
      "physical": {
        "sql": {
          "column": "region"
        }
      },
      "groupable": true
    },
    "country": {
      "type": "string",
      "filterable": true,
      "sortable": true,
      "groupable": true,
      "physical": {
        "sql": {
          "column": "country"
        }
      }
    }
  }
}
````

## `$filter` {#filter}

### Un confronto su una colonna {#a-comparison-on-one-column}

OData: `$filter=status eq 'active'`. Lo stesso vale per `ne`, `gt`, `ge`, `lt`, `le`: diventano i tipi di filtro `equals`,
`notEqual`, `greaterThan`, `greaterThanOrEqual`, `lessThan`, `lessThanOrEqual`.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "status": {
      "filterType": "text",
      "type": "equals",
      "filter": "active"
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE "status" COLLATE craticula_ci = $1 ORDER BY "id" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: 'active', 100, 0
````

Il confronto è `COLLATE craticula_ci`: **il testo si confronta per impostazione predefinita senza distinzione tra maiuscole e minuscole** ([Case sensitivity](semantics.html#sem-1)). In OData
il risultato dipende di solito dal servizio e dal suo database. Se gli utenti si affidavano alle maiuscole esatte, dichiarare il campo
`caseSensitivity: "sensitive"` nello schema.

### `contains`, `startswith`, `endswith` e `and` tra colonne {#contains-startswith-endswith-and-and-across-columns}

OData: `$filter=contains(customer,'acme') and amount gt 100`. Le funzioni di testo sono i tipi di filtro `contains`, `startsWith`
ed `endsWith`; `notContains` è l'unica negazione che il filtro di testo della griglia possiede. I filtri su colonne diverse sono uniti con AND,
una voce di `filterModel` per colonna.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "customer": {
      "filterType": "text",
      "type": "contains",
      "filter": "acme"
    },
    "amount": {
      "filterType": "number",
      "type": "greaterThan",
      "filter": 100
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE ("customer" ILIKE '%' || $1 || '%' ESCAPE '\' AND "amount" > $2::numeric) ORDER BY "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'acme', '100', 100, 0
````

La corrispondenza `contains` ha l'escape: i `%` e `_` dell'utente sono caratteri letterali, mai caratteri jolly ([Substring matching on OpenSearch](semantics.html#sem-7)).

### `or` su una colonna {#or-on-one-column}

OData: `$filter=amount gt 100 or amount lt 10`. Due condizioni sulla stessa colonna vanno nell'array `conditions` della colonna con
`operator: "OR"` (oppure `"AND"`).

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "amount": {
      "filterType": "number",
      "operator": "OR",
      "conditions": [
        {
          "filterType": "number",
          "type": "greaterThan",
          "filter": 100
        },
        {
          "filterType": "number",
          "type": "lessThan",
          "filter": 10
        }
      ]
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE ("amount" > $1::numeric OR "amount" < $2::numeric) ORDER BY "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: '100', '10', 100, 0
````

### `in` {#in}

OData (4.01): `$filter=status in ('active','pending')`. È il filtro a insieme della griglia.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "status": {
      "filterType": "set",
      "values": [
        "active",
        "pending"
      ]
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE "status" COLLATE craticula_ci = ANY($1) ORDER BY "id" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: ['active', 'pending'], 100, 0
````

### `ne` e `not` {#ne-and-not}

OData: `$filter=status ne 'blocked'` oppure `$filter=not (status eq 'blocked')`. Nella griglia è il tipo di filtro `notEqual`.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "status": {
      "filterType": "text",
      "type": "notEqual",
      "filter": "blocked"
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE ("status" COLLATE craticula_ci <> $1 OR "status" IS NULL) ORDER BY "id" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: 'blocked', 100, 0
````

Leggere con attenzione l'istruzione. `status ne 'blocked'` restituisce anche le righe in cui `status` è `NULL`. Gli operatori negativi di Craticula
includono di proposito le righe null ([Null handling](semantics.html#sem-2)), così la griglia si comporta come il filtro in memoria di AG Grid. La logica
a tre valori di SQL scarterebbe quelle righe, e un servizio OData potrebbe farlo o no. Verificare il comportamento precedente con un test prima di
migrare un filtro che esclude valori.

### `eq null` e `ne null` {#eq-null-and-ne-null}

OData: `$filter=region eq null`. Esistono due forme, e differiscono per le colonne di testo.

- Il tipo di filtro `blank` della griglia: null **oppure la stringa vuota** su una colonna di testo, solo `NULL` su una colonna numerica o di data.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "region": {
      "filterType": "text",
      "type": "blank"
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE ("region" IS NULL OR "region" = '') ORDER BY "id" ASC NULLS LAST LIMIT $1 OFFSET $2
-- parameters: 100, 0
````

- Un `eq` con un valore null, scritto nell'estensione `customFilters`: esattamente `NULL`, e nient'altro
  ([Grouping and drill-down](semantics.html#grp-7)). È l'`eq null` di OData.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {},
  "sortModel": [],
  "customFilters": {
    "type": "comparison",
    "field": "region",
    "op": "eq",
    "value": {
      "type": "null"
    }
  }
}
````

````sql
SELECT * FROM "orders" WHERE "region" IS NULL ORDER BY "id" ASC NULLS LAST LIMIT $1 OFFSET $2
-- parameters: 100, 0
````

`ne null` non ha una forma esatta su una colonna di testo. `notBlank` restituisce le righe che non sono né null né vuote. Non scrivere
`neq` con un valore null (restituisce solo le righe null, come risulta dalla combinazione della logica a tre valori di SQL e di SEM-2) né `not` attorno al test
di nullità (restituisce ogni riga).

### Intervalli e booleani {#ranges-and-booleans}

`$filter=amount ge 10 and amount le 20` sono due condizioni su una colonna unite da AND.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "amount": {
      "filterType": "number",
      "operator": "AND",
      "conditions": [
        {
          "filterType": "number",
          "type": "greaterThanOrEqual",
          "filter": 10
        },
        {
          "filterType": "number",
          "type": "lessThanOrEqual",
          "filter": 20
        }
      ]
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE ("amount" >= $1::numeric AND "amount" <= $2::numeric) ORDER BY "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: '10', '20', 100, 0
````

L'opzione di intervallo propria della griglia è rifiutata perché i suoi due estremi non portano alcuna inclusività; l'estensione `customFilters` ha un operatore `inRange`
con l'inclusività scritta esplicitamente. Una proprietà booleana, `$filter=active eq true`, è il filtro a insieme su una colonna booleana, che
si compila nell'operatore `true`.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "active": {
      "filterType": "set",
      "values": [
        "true"
      ]
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE "active" = $1 ORDER BY "id" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: true, 100, 0
````

### Date e date-time {#dates-and-date-times}

Un filtro su data accetta la forma di trasmissione della griglia: `yyyy-MM-dd`, oppure `yyyy-MM-dd HH:mm:ss` come ora locale letta nel fuso che la richiesta
porta (`requestContext.zone`) o che indicano le opzioni del parser, UTC per impostazione predefinita ([Dates and time zones](semantics.html#sem-4)). Un letterale OData come
`2026-01-01T00:00:00Z` o uno con offset non rientra in quella forma. Convertirlo nel fuso della richiesta, oppure inviare l'istante esatto
tramite `customFilters` come valore `datetime` tipizzato che indica il proprio fuso.

### Tutto il resto: un albero di `and`, `or`, `not` {#anything-else-a-tree-of-and-or-not}

I filtri di AG Grid coprono una colonna alla volta. Per un annidamento come `not startswith(customer,'test') and (status eq 'active' or
amount gt 1000)`, Craticula accetta un'estensione accanto a `filterModel`: `customFilters`, un albero di nodi `and`, `or`, `not` e
di confronto sull'insieme chiuso di 17 operatori: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `contains`, `notContains`,
`startsWith`, `endsWith`, `in`, `notIn`, `inRange`, `blank`, `notBlank`, `true`, `false`. È anche il luogo in cui vive un `startsWith` o
`endsWith` negato, perché la griglia non ha un tale tipo di filtro. L'albero è unito a `filterModel` con AND. La sua profondità e dimensione sono
limitate (i limiti di risorse di SEC-3), quindi un `$filter` enorme viene rifiutato anziché compilato.

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {},
  "sortModel": [],
  "customFilters": {
    "type": "and",
    "nodes": [
      {
        "type": "not",
        "node": {
          "type": "comparison",
          "field": "customer",
          "op": "startsWith",
          "value": {
            "type": "string",
            "value": "test"
          }
        }
      },
      {
        "type": "or",
        "nodes": [
          {
            "type": "comparison",
            "field": "status",
            "op": "eq",
            "value": {
              "type": "string",
              "value": "active"
            }
          },
          {
            "type": "comparison",
            "field": "amount",
            "op": "gt",
            "value": {
              "type": "decimal",
              "value": "1000"
            }
          }
        ]
      }
    ]
  }
}
````

````sql
SELECT * FROM "orders" WHERE ((NOT ("customer" ILIKE $1 || '%' ESCAPE '\') OR "customer" IS NULL) AND ("status" COLLATE craticula_ci = $2 OR "amount" > $3::numeric)) ORDER BY "id" ASC NULLS LAST LIMIT $4 OFFSET $5
-- parameters: 'test', 'active', '1000', 100, 0
````

## `$orderby`, `$top`, `$skip`, `$count` {#orderby-top-skip-count}

OData: `$orderby=amount desc,id&$top=20&$skip=40`. `$orderby` è `sortModel`, prima voce per prima. `$skip` è `startRow` e
`$skip + $top` è `endRow` (escluso), quindi `$skip=40&$top=20` è `startRow: 40`, `endRow: 60`.

````json
{
  "startRow": 40,
  "endRow": 60,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {},
  "sortModel": [
    {
      "colId": "amount",
      "sort": "desc"
    },
    {
      "colId": "id",
      "sort": "asc"
    }
  ]
}
````

````sql
SELECT * FROM "orders" ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST LIMIT $1 OFFSET $2
-- parameters: 20, 40
````

Due differenze:

- **Posizione dei null.** Lo standard OData ordina il null come il valore più basso: per primo in ordine crescente, per ultimo in ordine decrescente. La griglia
  non invia alcuna posizione dei null, quindi Craticula usa la regola opposta e fissa: **per ultimo in ordine crescente, per primo in ordine decrescente**
  ([Null ordering](semantics.html#sem-3)), mostrata sopra come `amount DESC NULLS FIRST`. Ogni ordinamento crescente su una colonna che contiene null
  restituisce quelle righe in una posizione diversa dopo la migrazione.
- **Un ordine stabile.** Un servizio deve mantenere stabili `$skip`/`$top` tra una richiesta e l'altra. Craticula lo garantisce qualunque sia il criterio di ordinamento della griglia:
  termina sempre l'ordinamento con la **chiave stabile** dello schema ([Deterministic paging](semantics.html#sem-6)), così due righe non si scambiano mai di posto tra
  le pagine.

`$count=true` (l'`@odata.count` della risposta) è il conteggio delle righe che gli adapter di esecuzione restituiscono accanto alla pagina quando lo si chiede
(`includeRowCount`: `RowCount`, e il `lastRow` di AG Grid). Su SQL e MongoDB è una seconda query. Su OpenSearch ed Elasticsearch è
limitato per impostazione predefinita e riportato come sconosciuto oltre 10,000 righe (vedere le [indicazioni sugli indici](index-guidance.html)).

## `$apply`: `groupby` e `aggregate` {#apply-groupby-and-aggregate}

OData: `$apply=groupby((country),aggregate(amount with sum as total))`. Il raggruppamento di righe della griglia invia `rowGroupCols` (le colonne di
gruppo, la più esterna per prima), `valueCols` (gli aggregati: `sum`, `min`, `max`, `avg`, `count`) e `groupKeys` (i gruppi che l'utente ha
aperto).

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [
    {
      "id": "country",
      "displayName": "Country",
      "field": "country"
    }
  ],
  "valueCols": [
    {
      "id": "amount",
      "displayName": "Amount",
      "field": "amount",
      "aggFunc": "sum"
    }
  ],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {},
  "sortModel": [
    {
      "colId": "country",
      "sort": "asc"
    }
  ]
}
````

````sql
SELECT "country" AS "country", COALESCE(SUM("amount"), 0) AS "amount_sum" FROM "orders" GROUP BY "country" ORDER BY "country" ASC NULLS LAST LIMIT $1 OFFSET $2
-- parameters: 100, 0
````

Una richiesta restituisce **un livello**. Con `groupby((country,region))` la griglia chiede prima i paesi. Quando l'utente apre la Germania
invia la chiave di gruppo `Germany` e ottiene le regioni della Germania:

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [
    {
      "id": "country",
      "displayName": "Country",
      "field": "country"
    },
    {
      "id": "region",
      "displayName": "Region",
      "field": "region"
    }
  ],
  "valueCols": [
    {
      "id": "amount",
      "displayName": "Amount",
      "field": "amount",
      "aggFunc": "sum"
    }
  ],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [
    {
      "type": "string",
      "value": "Germany"
    }
  ],
  "filterModel": {},
  "sortModel": [
    {
      "colId": "region",
      "sort": "asc"
    }
  ]
}
````

````sql
SELECT "region" AS "region", COALESCE(SUM("amount"), 0) AS "amount_sum" FROM "orders" WHERE "country" = $1 GROUP BY "region" ORDER BY "region" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: 'Germany', 100, 0
````

Un livello più in là, con entrambe le chiavi consumate, ottiene le righe:

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [
    {
      "id": "country",
      "displayName": "Country",
      "field": "country"
    },
    {
      "id": "region",
      "displayName": "Region",
      "field": "region"
    }
  ],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [
    {
      "type": "string",
      "value": "Germany"
    },
    {
      "type": "string",
      "value": "Bavaria"
    }
  ],
  "filterModel": {},
  "sortModel": [
    {
      "colId": "id",
      "sort": "asc"
    }
  ]
}
````

````sql
SELECT "id", "customer", "amount", "active", "status", "region", "country" FROM "orders" WHERE ("country" = $1 AND "region" = $2) ORDER BY "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'Germany', 'Bavaria', 100, 0
````

La richiesta propria di AG Grid porta le chiavi come semplici stringhe (`groupKeys: ["Germany"]`). Il parser fornito da Craticula riceve ogni chiave come
valore tipizzato (`{"type": "string", "value": "Germany"}`), quindi un piccolo passaggio nell'adapter del frontend tipizza le chiavi a partire dai tipi
delle colonne prima che la richiesta sia analizzata. Il `toWireRequest` della demo ([`datasource.ts`](../../examples/demo/web/src/datasource.ts)) è fatto di dieci righe che lo fanno, chiave null compresa.

Differenze da conoscere:

- `count` conta i valori non null di una colonna, non le righe ([AGG-1](semantics.html#agg-1)), e la colonna deve elencare `count` nella propria
  impostazione `aggregatable`. Per contare le righe, contare la chiave stabile.
- La somma di un gruppo senza valori è `0`, e `avg`, `min`, `max` sono `NULL` ([AGG-6](semantics.html#agg-6)).
- Il gruppo la cui chiave è null è un gruppo a sé, e lo si apre con una chiave di gruppo null ([Grouping and drill-down](semantics.html#grp-7)).
- L'aggregato torna con il nome `<field>_<function>` (`amount_sum`), a meno che l'id di colonna della griglia non dica altrimenti.
- Ordinare i gruppi per un aggregato non è disponibile sui motori di ricerca (un'aggregazione composite elenca i gruppi solo in ordine di chiave).

## Che cosa non ha equivalente {#what-has-no-equivalent}

| OData | Perché no, e che cosa fare |
|---|---|
| `$expand`, proprietà di navigazione, `$filter` attraverso una relazione | Uno schema legge una sola sorgente (una tabella, una collezione o un indice) e ogni colonna è un campo di essa. Costruire una vista o un indice che unisca i dati e dichiarare la vista come sorgente. |
| `$select` | Le colonne sono quelle dello schema. Una richiesta non può chiederne un sottoinsieme, e gli **adapter di esecuzione** restituiscono solo i campi dichiarati. Con il compilatore puro una normale query di righe è `SELECT *`, quindi una colonna non dichiarata è comunque nel risultato: lasciarla fuori dalla vista dichiarata come sorgente. Un'esportazione può nominare le proprie colonne. |
| `$search` | Non esiste una ricerca a testo libero tra i campi. Usare il filtro di testo su una colonna, oppure un indice di un motore di ricerca con il filtro `contains`. |
| `any` e `all` (operatori lambda) | Richiedono una proprietà di collezione, che una sorgente piatta non ha. Denormalizzare, oppure filtrare in una vista. |
| Aritmetica (`add`, `sub`, `mul`, `div`, `mod`) e `$compute` | L'insieme degli operatori è chiuso, così ogni operatore ha un significato testato su ogni database (AR-6 dei requisiti tecnici). Esporre il valore calcolato come colonna della sorgente. |
| Funzioni in `$filter` e `$orderby` (`tolower`, `toupper`, `trim`, `concat`, `substring`, `length`, `indexof`, `year`, `month`, `day`, `round`, `now`) | Lo stesso motivo. L'assenza di distinzione tra maiuscole e minuscole è già l'impostazione predefinita per il testo, e una parte di data è una colonna o un intervallo sulla data. |
| `$apply=filter(...)` **prima** di `groupby` | Metterlo in `filterModel` o `customFilters`: filtra le righe prima che siano raggruppate, come fa OData. |
| `$apply` con un filtro **dopo** `aggregate` (l'`HAVING` di SQL), `topcount`, `concat`, `join`, `compute`, `rollup` | Una richiesta di raggruppamento ha un livello e i cinque aggregati, e `filterModel` filtra sempre le righe prima che siano aggregate. Filtrare i gruppi dopo la query. |
| `countdistinct`, `$count` dentro `aggregate`, aggregati personalizzati | L'insieme degli aggregati è chiuso: `sum`, `min`, `max`, `avg`, `count`. |
| `$batch`, `$format`, `$metadata`, `$value`, azioni e funzioni | Riguardano il trasporto e il servizio, non la query. Craticula compila una query e non ha un livello di servizio. |

## Passi successivi {#next}

- Le regole su cui si basano questi esempi: [semantica](semantics.html).
- Ogni impostazione dello schema: il [riferimento GridSchema](grid-schema.html).
- Eseguire le stesse richieste su un database reale: la [guida rapida C#](quickstart-csharp.html).
