---
translates: the-gridschema
title: Il GridSchema
description: Lo schema che elenca ciò che una griglia può toccare e quali dei suoi flag sono applicati oggi.
source_fingerprint: cdf6e47e0fa6a2ef7b974c3b2ac02ea7892b7f9a31ffa33a18595708e80d8a45
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Il GridSchema {#the-gridschema}

Questa pagina spiega lo schema da scrivere per ogni griglia: che cosa contiene, quali sue impostazioni Craticula applica oggi e come iniziare. È rivolta allo sviluppatore che sta per descrivere a Craticula una tabella, una collezione o un indice. Per l'elenco completo dei membri, vedere il [riferimento del GridSchema](grid-schema.html).

## A che cosa serve lo schema {#what-the-schema-is-for}

Lo schema è il confine tra la richiesta e i dati. È un documento JSON che lo sviluppatore scrive e conserva sul server. Indica la tabella, la collezione o l'indice. Elenca ogni colonna che la griglia può toccare. Per ogni colonna fornisce un tipo e il nome fisico nel database.

Una colonna che non è nello schema non può mai raggiungere una query. I nomi di tabella e di colonna in una query provengono dallo schema, mai dalla richiesta. Vedere [Il modello di sicurezza](safety-model.html).

Nessuna richiesta può trasportare uno schema. La griglia invia le colonne con il proprio id di griglia e Craticula cerca ciascuna di esse.

## Un piccolo esempio {#a-small-example}

Questo è lo schema della guida introduttiva. Descrive una tabella `orders`.

```json
{
  "mode": "strict",
  "source": "orders",
  "stableKey": "id",
  "fields": {
    "id":       { "type": "int64",    "sortable": true, "physical": { "sql": { "column": "id" } } },
    "customer": { "type": "string",   "filterable": true, "sortable": true, "physical": { "sql": { "column": "customer" } } },
    "amount":   { "type": "decimal",  "filterable": true, "sortable": true, "physical": { "sql": { "column": "amount" } } },
    "status":   { "type": "string",   "filterable": true, "sortable": true, "physical": { "sql": { "column": "status" } } }
  }
}
```

In C#, caricarlo con `GridSchema.Parse(json)`.

## I membri dell'intero schema {#the-members-of-the-whole-schema}

| Membro | Che cosa fa |
|---|---|
| `mode` | `strict` oppure `lenient`. Lo JSON Schema lo richiede; il parser C# usa strict per impostazione predefinita quando manca. Vedere [Strict e Lenient](strict-and-lenient.html). |
| `source` | La tabella o la vista, la collezione MongoDB o l'indice OpenSearch. Non può essere vuoto. |
| `stableKey` | Una colonna con valori univoci. Deve essere uno dei `fields`. |
| `fields` | L'allowlist, indicizzata per id di colonna della griglia. Richiede almeno un campo. |
| `staticFilter` | Un filtro aggiunto a ogni query. Facoltativo. |

`GridSchema.Parse` rifiuta uno schema che viola queste regole. Rifiuta inoltre membri sconosciuti, chiavi duplicate e un `physical.sql` che non imposta esattamente uno tra `column`, `qualifiedColumn` e `expression`.

## I membri di un singolo campo {#the-members-of-one-field}

| Membro | Che cosa fa |
|---|---|
| `type` | `string`, `int64`, `decimal`, `double`, `boolean`, `date` oppure `datetime`. Craticula converte ogni valore della richiesta in questo tipo. |
| `physical` | Dove risiede la colonna: `sql`, `mongo`, `search` oppure tutti e tre. |
| `text` | Per una `string`: `caseSensitivity` (`insensitive` per impostazione predefinita) e `searchMode`. |
| `filterable`, `sortable`, `groupable`, `aggregatable` | Che cosa la griglia può fare con la colonna. Vedere sotto. |
| `exportable`, `label`, `format` | Come la colonna appare in un'esportazione CSV. Vedere [Esportazione CSV](csv-export.html). |

Servono solo le mappature per i backend in uso. Una mappatura SQL è una semplice colonna. Una mappatura MongoDB è un percorso del documento. Una mappatura di ricerca indica il campo dell'indice e può indicare anche un `keywordSubField` e un `normalizedSubField`. Un campo senza alcuna mappatura usa il proprio id di colonna come nome.

## Che cosa fa oggi ciascun flag {#what-each-flag-does-today}

Non dare per scontato che ogni flag sia applicato. Questo è ciò che il codice fa oggi:

| Flag | Predefinito | Applicato? |
|---|---|---|
| `filterable` | `true` | Sì. Un filtro su una colonna contrassegnata `false` viene rifiutato in modalità Strict e scartato in modalità Lenient. La colonna dell'elenco di valori di un filtro a insieme e una chiave di gruppo che l'utente ha aperto devono essere filtrabili e vengono rifiutate in entrambe le modalità. |
| `groupable` | `false` | Sì. Una colonna di raggruppamento deve essere raggruppabile. Rifiutata in entrambe le modalità. |
| `aggregatable` | nessuno | Sì. Un'aggregazione deve usare una funzione di questo elenco. Rifiutata in entrambe le modalità. |
| `exportable` | `true` | Sì. Determina le colonne di esportazione predefinite e una colonna contrassegnata `false` non può essere indicata in `exportColumns`. |
| `sortable` | `true` | **No.** Oggi nulla lo legge. Una colonna dello schema può essere ordinata qualunque cosa indichi il flag. |

L'elenco `aggregatable` contiene una qualsiasi combinazione di `sum`, `min`, `max`, `avg` e `count`. Vedere [Raggruppamento e aggregazione](grouping-and-aggregation.html).

Se è necessario impedire l'ordinamento di una colonna, ometterla dallo schema oppure affidarsi a un controllo proprio. Il flag non lo farà.

## La chiave stabile {#the-stable-key}

La `stableKey` è ciò che mantiene l'ordine della paginazione. Craticula la aggiunge alla fine di ogni ordinamento. Deve indicare una colonna i cui valori sono univoci. Dichiarare la colonna `NOT NULL` nel database, perché la maggior parte dei database consente molti valori nulli in una colonna univoca e ciò compromette la garanzia. Vedere [Paginazione e ordinamento](paging-and-sorting.html).

## Il filtro statico {#the-static-filter}

`staticFilter` è una condizione che Craticula aggiunge a ogni query con AND. È il posto adatto per un id di tenant o un flag di eliminazione logica. La richiesta non può modificarla né rimuoverla.

```json
"staticFilter": {
  "type": "comparison",
  "op": "eq",
  "field": "tenantId",
  "value": { "type": "int64", "value": 42 }
}
```

Anche il campo indicato da un `staticFilter` deve essere dichiarato in `fields`, in modo che il compilatore possa trovarne la colonna. La condizione fa parte dello schema, quindi la richiesta non può raggiungerla. Decidere quale debba essere il filtro spetta allo sviluppatore. Craticula si limita ad applicarlo. Vedere [Il modello di sicurezza](safety-model.html).

## Ordine dei campi {#field-order}

L'ordine dei campi nel documento conta. Una richiesta di esportazione senza elenco di colonne ottiene i campi esportabili in quell'ordine. Anche le righe all'interno di un gruppo aperto sono restituite in quell'ordine.

## Da dove proviene questa pagina {#where-this-comes-from}

- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridSchema.cs](../../csharp/src/Craticula.Core/Schema/GridSchema.cs)
- [csharp/src/Craticula.Core/Schema/FieldConfig.cs](../../csharp/src/Craticula.Core/Schema/FieldConfig.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
- [spec/fixtures/schemas](../../spec/fixtures/schemas)
- Pagine correlate: [Limiti](limits.html), [Dialetti e provider](dialects-and-providers.html), [Come una richiesta diventa una query](request-to-query.html)
