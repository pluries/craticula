---
translates: odata-migration
title: Migrer depuis OData
description: Faire passer une grille d'OData à des requêtes compilées et voir ce qui change.
source_fingerprint: fd82735ea37c07ef6fc24c75d469d2a95817109d4cb1345e8240e4df38b66ee0
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Migrer depuis OData {#migrating-from-odata}

Cette page s'adresse à une équipe dont la grille s'appuie aujourd'hui sur un service OData et qui veut passer à Craticula. Elle montre, construction par
construction, ce que vous écriviez en OData et la requête que Craticula prend à la place. Chaque exemple est un fichier qu'un test compile ; la
requête et l'énoncé qui la suit sont donc réels et ne peuvent pas devenir obsolètes.

Deux choses sont différentes dès le départ :

- **Craticula prend la requête qu'AG Grid envoie déjà.** Il n'y a aucune chaîne de requête d'URL à construire. Le Server-Side Row Model de la grille
  poste un corps JSON (`filterModel`, `sortModel`, `startRow`, `endRow`, `rowGroupCols`, `valueCols`, `groupKeys`), et Craticula le
  compile. Le côté « OData » ci-dessous est ce que votre service recevait ; le côté « Craticula » est ce que la grille envoie.
- **Craticula compile ; il ne sert pas.** Il renvoie un énoncé et ses paramètres. Vous l'exécutez avec votre propre pilote, et vous
  écrivez le point d'accès (voir le [démarrage rapide C#](quickstart-csharp.html)).

Tous les exemples utilisent un petit schéma synthétique, `orders` (id, customer, amount, active, status, region, country), et affichent l'énoncé
PostgreSQL. Les autres bases de données obtiennent leur propre écriture de la même requête.

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

### Une comparaison sur une colonne {#a-comparison-on-one-column}

OData : `$filter=status eq 'active'`. Il en va de même pour `ne`, `gt`, `ge`, `lt`, `le` : ils deviennent les types de filtre `equals`,
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

La comparaison est `COLLATE craticula_ci` : **le texte se compare sans tenir compte de la casse par défaut** ([Case sensitivity](semantics.html#sem-1)). En OData,
le résultat dépend généralement du service et de sa base de données. Si vos utilisateurs comptaient sur la casse exacte, déclarez le champ
`caseSensitivity: "sensitive"` dans le schéma.

### `contains`, `startswith`, `endswith` et `and` sur plusieurs colonnes {#contains-startswith-endswith-and-and-across-columns}

OData : `$filter=contains(customer,'acme') and amount gt 100`. Les fonctions de texte sont les types de filtre `contains`, `startsWith`
et `endsWith` ; `notContains` est la seule négation que possède le filtre de texte de la grille. Les filtres sur des colonnes différentes sont reliés par AND,
une entrée de `filterModel` par colonne.

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

La correspondance `contains` est échappée : les `%` et `_` de l'utilisateur sont des caractères littéraux, jamais des jokers ([Substring matching on OpenSearch](semantics.html#sem-7)).

### `or` sur une colonne {#or-on-one-column}

OData : `$filter=amount gt 100 or amount lt 10`. Deux conditions sur la même colonne vont dans le tableau `conditions` de la colonne avec
`operator: "OR"` (ou `"AND"`).

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

OData (4.01) : `$filter=status in ('active','pending')`. C'est le filtre d'ensemble de la grille.

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

### `ne` et `not` {#ne-and-not}

OData : `$filter=status ne 'blocked'` ou `$filter=not (status eq 'blocked')`. Dans la grille, c'est le type de filtre `notEqual`.

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

Lisez l'énoncé de près. `status ne 'blocked'` renvoie aussi les lignes où `status` vaut `NULL`. Les opérateurs négatifs de Craticula
incluent les lignes nulles volontairement ([Null handling](semantics.html#sem-2)), de sorte que la grille se comporte comme le filtre en mémoire d'AG Grid. La
logique à trois valeurs de SQL écarterait ces lignes, et un service OData peut le faire ou non. Vérifiez l'ancien comportement par un test avant de
migrer un filtre qui exclut des valeurs.

### `eq null` et `ne null` {#eq-null-and-ne-null}

OData : `$filter=region eq null`. Il existe deux formes, et elles diffèrent pour les colonnes de texte.

- Le type de filtre `blank` de la grille : nul **ou chaîne vide** sur une colonne de texte, seulement `NULL` sur une colonne numérique ou de date.

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

- Un `eq` avec une valeur nulle, écrit dans l'extension `customFilters` : exactement `NULL`, et rien d'autre
  ([Grouping and drill-down](semantics.html#grp-7)). C'est le `eq null` d'OData.

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

`ne null` n'a pas de forme exacte sur une colonne de texte. `notBlank` renvoie les lignes qui ne sont ni nulles ni vides. N'écrivez pas
`neq` avec une valeur nulle (il ne renvoie que les lignes nulles, par la combinaison de la logique à trois valeurs de SQL et de SEM-2) ni `not` autour du test
de nullité (il renvoie toutes les lignes).

### Intervalles et booléens {#ranges-and-booleans}

`$filter=amount ge 10 and amount le 20` correspond à deux conditions sur une colonne reliées par AND.

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

L'option d'intervalle propre à la grille est refusée parce que ses deux bornes ne précisent pas si elles sont incluses ; l'extension `customFilters` a un opérateur `inRange`
où l'inclusion est écrite explicitement. Une propriété booléenne, `$filter=active eq true`, est le filtre d'ensemble sur une colonne booléenne, qui
se compile en l'opérateur `true`.

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

### Dates et dates-heures {#dates-and-date-times}

Un filtre de date prend la forme de transmission de la grille : `yyyy-MM-dd`, ou `yyyy-MM-dd HH:mm:ss` comme heure murale lue dans le fuseau que la requête
porte (`requestContext.zone`) ou que nomment les options de l'analyseur, UTC par défaut ([Dates and time zones](semantics.html#sem-4)). Un littéral OData tel que
`2026-01-01T00:00:00Z`, ou un littéral avec décalage, ne correspond pas à cette forme. Convertissez-le dans le fuseau de la requête, ou envoyez l'instant exact
par `customFilters` comme une valeur `datetime` typée qui nomme son fuseau.

### Tout le reste : un arbre de `and`, `or`, `not` {#anything-else-a-tree-of-and-or-not}

Les filtres d'AG Grid couvrent une colonne à la fois. Pour une imbrication comme `not startswith(customer,'test') and (status eq 'active' or
amount gt 1000)`, Craticula accepte une extension à côté de `filterModel` : `customFilters`, un arbre de nœuds `and`, `or`, `not` et
de comparaison sur l'ensemble fermé de 17 opérateurs : `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `contains`, `notContains`,
`startsWith`, `endsWith`, `in`, `notIn`, `inRange`, `blank`, `notBlank`, `true`, `false`. C'est aussi là que vit un `startsWith` ou
`endsWith` négatif, parce que la grille n'a pas de tel type de filtre. L'arbre est fusionné avec `filterModel` par AND. Sa profondeur et sa taille sont
limitées (les limites de ressources de SEC-3), de sorte qu'un `$filter` gigantesque est refusé au lieu d'être compilé.

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

OData : `$orderby=amount desc,id&$top=20&$skip=40`. `$orderby` correspond à `sortModel`, première entrée en premier. `$skip` correspond à `startRow` et
`$skip + $top` à `endRow` (exclusif), de sorte que `$skip=40&$top=20` donne `startRow: 40`, `endRow: 60`.

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

Deux différences :

- **Position des valeurs nulles.** Le standard d'OData trie la valeur nulle comme la plus basse : en premier en ordre ascendant, en dernier en ordre descendant. La grille
  n'envoie aucune position pour les valeurs nulles ; Craticula applique donc la règle fixe inverse : **en dernier en ordre ascendant, en premier en ordre descendant**
  ([Null ordering](semantics.html#sem-3)), ce que montre ci-dessus `amount DESC NULLS FIRST`. Chaque tri ascendant sur une colonne qui contient des valeurs nulles
  renvoie ces lignes à un autre endroit après la migration.
- **Un ordre stable.** Un service doit garder `$skip`/`$top` stables d'une requête à l'autre. Craticula le garantit quel que soit le tri de la grille :
  il termine toujours le tri par la **clé stable** du schéma ([Deterministic paging](semantics.html#sem-6)), de sorte que deux lignes n'échangent jamais leur place entre
  les pages.

`$count=true` (le `@odata.count` de la réponse) correspond au nombre de lignes que les adaptateurs d'exécution renvoient à côté de la page quand vous le demandez
(`includeRowCount` : `RowCount`, et le `lastRow` d'AG Grid). Sur SQL et MongoDB, c'est une seconde requête. Sur OpenSearch et Elasticsearch, il est
plafonné par défaut et signalé comme inconnu au-delà de 10,000 lignes (voir les [conseils sur les index](index-guidance.html)).

## `$apply` : `groupby` et `aggregate` {#apply-groupby-and-aggregate}

OData : `$apply=groupby((country),aggregate(amount with sum as total))`. Le regroupement de lignes de la grille envoie `rowGroupCols` (les colonnes de
groupe, de l'extérieur vers l'intérieur), `valueCols` (les agrégats : `sum`, `min`, `max`, `avg`, `count`) et `groupKeys` (les groupes que l'utilisateur a
ouverts).

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

Une requête renvoie **un niveau**. Avec `groupby((country,region))`, la grille demande d'abord les pays. Quand l'utilisateur ouvre Germany,
elle envoie la clé de groupe `Germany` et obtient les régions de Germany :

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

Un niveau plus loin, les deux clés étant consommées, elle obtient les lignes :

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

La requête d'AG Grid porte les clés sous forme de simples chaînes (`groupKeys: ["Germany"]`). L'analyseur que fournit Craticula prend chaque clé comme une
valeur typée (`{"type": "string", "value": "Germany"}`) ; une petite étape dans votre adaptateur frontend type donc les clés d'après les types de colonnes
avant l'analyse de la requête. Le `toWireRequest` de la démo ([`datasource.ts`](../../examples/demo/web/src/datasource.ts)) tient en dix lignes pour cela, clé nulle comprise.

Différences à connaître :

- `count` compte les valeurs non nulles d'une colonne, pas les lignes ([AGG-1](semantics.html#agg-1)), et la colonne doit lister `count` dans son réglage
  `aggregatable`. Pour compter les lignes, comptez la clé stable.
- La somme d'un groupe sans valeurs est `0`, et `avg`, `min`, `max` valent `NULL` ([AGG-6](semantics.html#agg-6)).
- Le groupe dont la clé est nulle forme un groupe à part, et vous l'ouvrez avec une clé de groupe nulle ([Grouping and drill-down](semantics.html#grp-7)).
- L'agrégat revient nommé `<field>_<function>` (`amount_sum`), sauf si l'identifiant de colonne de la grille dit autre chose.
- Ordonner les groupes par un agrégat n'est pas possible sur les moteurs de recherche (une agrégation composite ne liste les groupes que dans l'ordre des clés).

## Ce qui n'a pas d'équivalent {#what-has-no-equivalent}

| OData | Pourquoi pas, et que faire |
|---|---|
| `$expand`, propriétés de navigation, `$filter` à travers une relation | Un schéma lit une seule source (une table, une collection ou un index) et chaque colonne est un champ de celle-ci. Construisez une vue ou un index qui joint les données et déclarez la vue comme source. |
| `$select` | Les colonnes sont celles du schéma. Une requête ne peut pas en demander un sous-ensemble, et les **adaptateurs d'exécution** ne renvoient que les champs déclarés. Avec le compilateur seul, une requête de lignes ordinaire est un `SELECT *` ; une colonne que vous ne déclarez pas figure donc quand même dans le résultat : laissez-la de côté dans la vue que vous déclarez comme source. Un export peut nommer ses colonnes. |
| `$search` | Il n'y a pas de recherche en texte libre à travers les champs. Utilisez le filtre de texte sur une colonne, ou un index de moteur de recherche avec le filtre `contains`. |
| `any` et `all` (opérateurs lambda) | Ils exigent une propriété de collection, qu'une source plate n'a pas. Dénormalisez, ou filtrez dans une vue. |
| Arithmétique (`add`, `sub`, `mul`, `div`, `mod`) et `$compute` | L'ensemble d'opérateurs est fermé pour que chaque opérateur ait un sens testé sur chaque base de données (AR-6 des exigences techniques). Exposez la valeur calculée comme une colonne de la source. |
| Fonctions dans `$filter` et `$orderby` (`tolower`, `toupper`, `trim`, `concat`, `substring`, `length`, `indexof`, `year`, `month`, `day`, `round`, `now`) | Même raison. L'insensibilité à la casse est déjà le défaut pour le texte, et une partie de date est une colonne ou un intervalle sur la date. |
| `$apply=filter(...)` **avant** `groupby` | Mettez-le dans `filterModel` ou `customFilters` : il filtre les lignes avant leur regroupement, comme le fait OData. |
| `$apply` avec un filtre **après** `aggregate` (le `HAVING` de SQL), `topcount`, `concat`, `join`, `compute`, `rollup` | Une requête de regroupement a un seul niveau et les cinq agrégats, et `filterModel` filtre toujours les lignes avant leur agrégation. Filtrez les groupes après la requête. |
| `countdistinct`, `$count` dans `aggregate`, agrégats personnalisés | L'ensemble des agrégats est fermé : `sum`, `min`, `max`, `avg`, `count`. |
| `$batch`, `$format`, `$metadata`, `$value`, actions et fonctions | Ils concernent le transport et le service, pas la requête. Craticula compile une requête et n'a pas de couche de service. |

## Suite {#next}

- Les règles sur lesquelles s'appuient ces exemples : [sémantique](semantics.html).
- Chaque paramètre du schéma : la [référence GridSchema](grid-schema.html).
- Exécuter les mêmes requêtes sur une vraie base de données : le [démarrage rapide C#](quickstart-csharp.html).
