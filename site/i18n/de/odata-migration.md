---
translates: odata-migration
title: Migration von OData
description: Ein Grid von OData auf kompilierte Abfragen umstellen und sehen, was sich ändert.
source_fingerprint: fd82735ea37c07ef6fc24c75d469d2a95817109d4cb1345e8240e4df38b66ee0
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Migration von OData {#migrating-from-odata}

Diese Seite richtet sich an ein Team, dessen Grid heute auf einem OData-Dienst aufsetzt und das auf Craticula umsteigen möchte. Sie zeigt Konstrukt für
Konstrukt, was Sie in OData geschrieben haben und welche Anfrage Craticula stattdessen entgegennimmt. Jedes Beispiel ist eine Datei, die ein Test kompiliert; die
Anfrage und die darauf folgende Anweisung sind also echt und können nicht veralten.

Zwei Dinge sind von Anfang an anders:

- **Craticula nimmt die Anfrage, die AG Grid ohnehin sendet.** Es gibt keinen URL-Abfragestring, den Sie bauen müssten. Das Server-Side Row Model des Grids
  sendet einen JSON-Body (`filterModel`, `sortModel`, `startRow`, `endRow`, `rowGroupCols`, `valueCols`, `groupKeys`), und Craticula
  kompiliert ihn. Die „OData“-Seite unten ist das, was Ihr Dienst erhielt; die „Craticula“-Seite ist das, was das Grid sendet.
- **Craticula kompiliert; es liefert nichts aus.** Es gibt eine Anweisung und ihre Parameter zurück. Sie führen sie mit Ihrem eigenen Treiber aus und
  schreiben den Endpunkt selbst (siehe den [C#-Schnellstart](quickstart-csharp.html)).

Alle Beispiele verwenden ein kleines synthetisches Schema, `orders` (id, customer, amount, active, status, region, country), und zeigen die
PostgreSQL-Anweisung. Die anderen Datenbanken erhalten ihre eigene Schreibweise derselben Abfrage.

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

### Ein Vergleich auf einer Spalte {#a-comparison-on-one-column}

OData: `$filter=status eq 'active'`. Dasselbe gilt für `ne`, `gt`, `ge`, `lt`, `le`: Sie werden zu den Filtertypen `equals`,
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

Der Vergleich lautet `COLLATE craticula_ci`: **Text wird standardmäßig ohne Beachtung der Groß- und Kleinschreibung verglichen** ([Case sensitivity](semantics.html#sem-1)). In OData
hängt das Ergebnis meist vom Dienst und seiner Datenbank ab. Wenn Ihre Benutzer auf die exakte Schreibweise angewiesen waren, deklarieren Sie das Feld im Schema als
`caseSensitivity: "sensitive"`.

### `contains`, `startswith`, `endswith` und `and` über Spalten {#contains-startswith-endswith-and-and-across-columns}

OData: `$filter=contains(customer,'acme') and amount gt 100`. Die Textfunktionen sind die Filtertypen `contains`, `startsWith`
und `endsWith`; `notContains` ist die einzige Negation, die der Textfilter des Grids kennt. Filter auf verschiedenen Spalten werden mit AND verknüpft,
ein Eintrag in `filterModel` pro Spalte.

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

Die Übereinstimmung `contains` wird maskiert: Die `%` und `_` des Benutzers sind literale Zeichen, nie Platzhalter ([Substring matching on OpenSearch](semantics.html#sem-7)).

### `or` auf einer Spalte {#or-on-one-column}

OData: `$filter=amount gt 100 or amount lt 10`. Zwei Bedingungen auf derselben Spalte kommen in das Array `conditions` der Spalte, mit
`operator: "OR"` (oder `"AND"`).

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

OData (4.01): `$filter=status in ('active','pending')`. Das ist der Mengenfilter des Grids.

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

### `ne` und `not` {#ne-and-not}

OData: `$filter=status ne 'blocked'` oder `$filter=not (status eq 'blocked')`. Im Grid ist das der Filtertyp `notEqual`.

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

Lesen Sie die Anweisung genau. `status ne 'blocked'` liefert auch die Zeilen, in denen `status` den Wert `NULL` hat. Die negativen Operatoren von Craticula
schließen Nullzeilen absichtlich ein ([Null handling](semantics.html#sem-2)), damit sich das Grid wie der In-Memory-Filter von AG Grid verhält. Die
dreiwertige Logik von SQL würde diese Zeilen verwerfen, und ein OData-Dienst kann das tun oder auch nicht. Prüfen Sie das alte Verhalten mit einem Test, bevor Sie
einen Filter migrieren, der Werte ausschließt.

### `eq null` und `ne null` {#eq-null-and-ne-null}

OData: `$filter=region eq null`. Es gibt zwei Formen, und sie unterscheiden sich bei Textspalten.

- Der Filtertyp `blank` des Grids: null **oder leere Zeichenfolge** auf einer Textspalte, nur `NULL` auf einer numerischen Spalte oder einer Datumsspalte.

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

- Ein `eq` mit einem Nullwert, geschrieben in der Erweiterung `customFilters`: genau `NULL` und sonst nichts
  ([Grouping and drill-down](semantics.html#grp-7)). Das ist das `eq null` von OData.

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

`ne null` hat auf einer Textspalte keine exakte Form. `notBlank` liefert die Zeilen, die weder null noch leer sind. Schreiben Sie nicht
`neq` mit einem Nullwert (es liefert nur die Nullzeilen, aus dem Zusammenspiel der dreiwertigen Logik von SQL mit SEM-2) und auch nicht `not` um den Null-Test
(es liefert alle Zeilen).

### Bereiche und boolesche Werte {#ranges-and-booleans}

`$filter=amount ge 10 and amount le 20` entspricht zwei mit AND verknüpften Bedingungen auf einer Spalte.

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

Die eigene Bereichsoption des Grids wird abgelehnt, weil ihre beiden Grenzen nicht angeben, ob sie eingeschlossen sind; die Erweiterung `customFilters` hat einen Operator `inRange`,
in dem der Einschluss ausdrücklich geschrieben wird. Eine boolesche Eigenschaft, `$filter=active eq true`, ist der Mengenfilter auf einer booleschen Spalte, der
zum Operator `true` kompiliert wird.

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

### Datumswerte und Datum-Uhrzeit-Werte {#dates-and-date-times}

Ein Datumsfilter nimmt die Übertragungsform des Grids: `yyyy-MM-dd` oder `yyyy-MM-dd HH:mm:ss` als Wandzeit, gelesen in der Zeitzone, die die Anfrage
trägt (`requestContext.zone`) oder die die Parser-Optionen nennen, standardmäßig UTC ([Dates and time zones](semantics.html#sem-4)). Ein OData-Literal wie
`2026-01-01T00:00:00Z` oder ein Literal mit Versatz entspricht dieser Form nicht. Rechnen Sie es in die Zeitzone der Anfrage um, oder senden Sie den exakten Zeitpunkt
über `customFilters` als typisierten `datetime`-Wert, der seine Zeitzone nennt.

### Alles andere: ein Baum aus `and`, `or`, `not` {#anything-else-a-tree-of-and-or-not}

Die Filter von AG Grid decken jeweils eine Spalte ab. Für eine Verschachtelung wie `not startswith(customer,'test') and (status eq 'active' or
amount gt 1000)` akzeptiert Craticula neben `filterModel` eine Erweiterung: `customFilters`, einen Baum aus den Knoten `and`, `or`, `not` und
Vergleichen über die geschlossene Menge von 17 Operatoren: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `contains`, `notContains`,
`startsWith`, `endsWith`, `in`, `notIn`, `inRange`, `blank`, `notBlank`, `true`, `false`. Dort lebt auch ein negiertes `startsWith` oder
`endsWith`, weil das Grid keinen solchen Filtertyp hat. Der Baum wird mit `filterModel` per AND zusammengeführt. Seine Tiefe und Größe sind
begrenzt (die Ressourcenlimits aus SEC-3), sodass ein riesiger `$filter` abgelehnt statt kompiliert wird.

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

OData: `$orderby=amount desc,id&$top=20&$skip=40`. `$orderby` entspricht `sortModel`, der erste Eintrag zuerst. `$skip` entspricht `startRow` und
`$skip + $top` entspricht `endRow` (exklusiv), sodass `$skip=40&$top=20` `startRow: 40`, `endRow: 60` ergibt.

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

Zwei Unterschiede:

- **Position der Nullwerte.** Der OData-Standard sortiert den Nullwert als den kleinsten: aufsteigend zuerst, absteigend zuletzt. Das Grid
  sendet keine Position für Nullwerte; Craticula wendet daher die umgekehrte feste Regel an: **aufsteigend zuletzt, absteigend zuerst**
  ([Null ordering](semantics.html#sem-3)), was oben `amount DESC NULLS FIRST` zeigt. Jede aufsteigende Sortierung auf einer Spalte, die Nullwerte enthält,
  liefert diese Zeilen nach der Migration an einer anderen Stelle.
- **Eine stabile Reihenfolge.** Ein Dienst muss `$skip`/`$top` von Anfrage zu Anfrage stabil halten. Craticula garantiert das unabhängig von der Sortierung des Grids:
  Es beendet die Sortierung immer mit dem **stabilen Schlüssel** des Schemas ([Deterministic paging](semantics.html#sem-6)), sodass zwei Zeilen nie zwischen
  den Seiten die Plätze tauschen.

`$count=true` (das `@odata.count` der Antwort) entspricht der Zeilenanzahl, die die Ausführungsadapter neben der Seite zurückgeben, wenn Sie sie anfordern
(`includeRowCount`: `RowCount` und das `lastRow` von AG Grid). Auf SQL und MongoDB ist das eine zweite Abfrage. Auf OpenSearch und Elasticsearch ist sie
standardmäßig begrenzt und wird jenseits von 10,000 Zeilen als unbekannt gemeldet (siehe die [Hinweise zu Indizes](index-guidance.html)).

## `$apply`: `groupby` und `aggregate` {#apply-groupby-and-aggregate}

OData: `$apply=groupby((country),aggregate(amount with sum as total))`. Die Zeilengruppierung des Grids sendet `rowGroupCols` (die Gruppenspalten,
von außen nach innen), `valueCols` (die Aggregate: `sum`, `min`, `max`, `avg`, `count`) und `groupKeys` (die Gruppen, die der Benutzer
geöffnet hat).

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

Eine Anfrage liefert **eine Ebene**. Bei `groupby((country,region))` fragt das Grid zuerst die Länder ab. Öffnet der Benutzer Germany,
sendet es den Gruppenschlüssel `Germany` und erhält die Regionen von Germany:

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

Eine Ebene weiter, wenn beide Schlüssel verbraucht sind, erhält es die Zeilen:

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

Die Anfrage von AG Grid trägt die Schlüssel als einfache Zeichenfolgen (`groupKeys: ["Germany"]`). Der Parser, den Craticula mitliefert, nimmt jeden Schlüssel als
typisierten Wert (`{"type": "string", "value": "Germany"}`); ein kleiner Schritt in Ihrem Frontend-Adapter typisiert die Schlüssel daher anhand der Spaltentypen,
bevor die Anfrage geparst wird. Das `toWireRequest` der Demo ([`datasource.ts`](../../examples/demo/web/src/datasource.ts)) erledigt das in zehn Zeilen, einschließlich des Nullschlüssels.

Unterschiede, die Sie kennen sollten:

- `count` zählt die Nicht-Null-Werte einer Spalte, nicht die Zeilen ([AGG-1](semantics.html#agg-1)), und die Spalte muss `count` in ihrer Einstellung
  `aggregatable` aufführen. Um Zeilen zu zählen, zählen Sie den stabilen Schlüssel.
- Die Summe einer Gruppe ohne Werte ist `0`, und `avg`, `min`, `max` sind `NULL` ([AGG-6](semantics.html#agg-6)).
- Die Gruppe mit dem Nullschlüssel bildet eine eigene Gruppe, und Sie öffnen sie mit einem Nullgruppenschlüssel ([Grouping and drill-down](semantics.html#grp-7)).
- Das Aggregat kommt unter dem Namen `<field>_<function>` zurück (`amount_sum`), es sei denn, die Spalten-ID des Grids besagt etwas anderes.
- Gruppen nach einem Aggregat zu sortieren ist auf den Suchmaschinen nicht möglich (eine zusammengesetzte Aggregation listet die Gruppen nur in der Reihenfolge der Schlüssel auf).

## Was keine Entsprechung hat {#what-has-no-equivalent}

| OData | Warum nicht, und was zu tun ist |
|---|---|
| `$expand`, Navigationseigenschaften, `$filter` über eine Beziehung hinweg | Ein Schema liest genau eine Quelle (eine Tabelle, eine Collection oder einen Index), und jede Spalte ist ein Feld dieser Quelle. Bauen Sie eine View oder einen Index, der die Daten verknüpft, und deklarieren Sie die View als Quelle. |
| `$select` | Die Spalten sind die des Schemas. Eine Anfrage kann keine Teilmenge anfordern, und die **Ausführungsadapter** liefern nur die deklarierten Felder zurück. Mit dem Compiler allein ist eine gewöhnliche Zeilenabfrage ein `SELECT *`; eine Spalte, die Sie nicht deklarieren, steht also trotzdem im Ergebnis: Lassen Sie sie in der View weg, die Sie als Quelle deklarieren. Ein Export kann seine Spalten benennen. |
| `$search` | Es gibt keine Freitextsuche über Felder hinweg. Verwenden Sie den Textfilter auf einer Spalte oder einen Suchmaschinenindex mit dem Filter `contains`. |
| `any` und `all` (Lambda-Operatoren) | Sie verlangen eine Collection-Eigenschaft, die eine flache Quelle nicht hat. Denormalisieren Sie, oder filtern Sie in einer View. |
| Arithmetik (`add`, `sub`, `mul`, `div`, `mod`) und `$compute` | Die Operatormenge ist geschlossen, damit jeder Operator auf jeder Datenbank eine getestete Bedeutung hat (AR-6 der technischen Anforderungen). Stellen Sie den berechneten Wert als Spalte der Quelle bereit. |
| Funktionen in `$filter` und `$orderby` (`tolower`, `toupper`, `trim`, `concat`, `substring`, `length`, `indexof`, `year`, `month`, `day`, `round`, `now`) | Aus demselben Grund. Die Missachtung der Groß- und Kleinschreibung ist für Text bereits der Standard, und ein Datumsteil ist eine Spalte oder ein Bereich auf dem Datum. |
| `$apply=filter(...)` **vor** `groupby` | Legen Sie es in `filterModel` oder `customFilters`: Es filtert die Zeilen, bevor sie gruppiert werden, wie es OData tut. |
| `$apply` mit einem Filter **nach** `aggregate` (das `HAVING` von SQL), `topcount`, `concat`, `join`, `compute`, `rollup` | Eine Gruppierungsabfrage hat nur eine Ebene und die fünf Aggregate, und `filterModel` filtert die Zeilen immer, bevor sie aggregiert werden. Filtern Sie die Gruppen nach der Abfrage. |
| `countdistinct`, `$count` in `aggregate`, benutzerdefinierte Aggregate | Die Menge der Aggregate ist geschlossen: `sum`, `min`, `max`, `avg`, `count`. |
| `$batch`, `$format`, `$metadata`, `$value`, Aktionen und Funktionen | Sie betreffen Transport und Dienst, nicht die Abfrage. Craticula kompiliert eine Abfrage und hat keine Dienstschicht. |

## Weiter {#next}

- Die Regeln, auf denen diese Beispiele beruhen: [Semantik](semantics.html).
- Jede Einstellung im Schema: die [GridSchema-Referenz](grid-schema.html).
- Dieselben Abfragen auf einer echten Datenbank ausführen: der [C#-Schnellstart](quickstart-csharp.html).
