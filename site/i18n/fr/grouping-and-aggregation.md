---
translates: grouping-and-aggregation
title: Regroupement et agrégation
description: Comment une grille groupée demande un niveau à la fois et comment se comportent les agrégations.
source_fingerprint: 10e3bdf6eb7dc0f59a4e20738237bb2f9f7ebac06181756626f1c01f952450a5
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Regroupement et agrégation {#grouping-and-aggregation}

Cette page traite du regroupement de lignes et de l'agrégation : comment une grille groupée demande un niveau à la fois, comment Craticula répond à chaque niveau, et ce que le schéma doit autoriser. Elle s'adresse à un développeur dont la grille regroupe des lignes et affiche des totaux. Le regroupement de lignes et l'agrégation sont des fonctionnalités AG Grid Enterprise.

## Un niveau par requête {#one-level-per-request}

Une grille groupée ne demande pas l'arbre entier. Elle demande un niveau à la fois, et chaque requête porte le chemin parcouru jusque-là.

Deux listes de la requête décrivent ce chemin :

- `rowGroupCols` liste les colonnes par lesquelles la grille regroupe, dans l'ordre.
- `groupKeys` liste les groupes que l'utilisateur a déjà ouverts, une clé par niveau.

Craticula compare les deux longueurs :

- **Moins de clés que de colonnes.** La requête demande un niveau groupé. Craticula regroupe par la prochaine colonne qui n'a pas encore de clé, et seulement celle-là. Il calcule les agrégations pour chaque groupe.
- **Autant de clés que de colonnes.** Tous les niveaux sont ouverts. La requête demande les lignes à l'intérieur du dernier groupe. Craticula renvoie des lignes simples et ne regroupe pas.
- **Plus de clés que de colonnes.** La requête est malformée et est refusée.

Le mode pivot n'est pas pris en charge. Une requête avec `pivotMode` à `true`, ou avec des `pivotCols`, est refusée.

## Un exemple {#an-example}

Prenons une grille groupée par `region`, puis `segment`, puis `product`, avec une somme de `amount`. L'utilisateur a ouvert la région `EMEA`. La grille demande maintenant les segments à l'intérieur de `EMEA`.

Pour PostgreSQL, Craticula écrit :

```sql
SELECT "segment" AS "segment", COALESCE(SUM("amount"), 0) AS "amount_sum" FROM "sales_fact" WHERE "region" = $1 GROUP BY "segment" ORDER BY "segment" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: 'EMEA', 100, 0
```

Le groupe ouvert est devenu `WHERE "region" = $1`. La colonne suivante, `segment`, est devenue le `GROUP BY`. L'agrégat se nomme `amount_sum`.

## Les clés de groupe arrivent sous forme de valeurs typées {#group-keys-arrive-as-typed-values}

Craticula lit chaque entrée de `groupKeys` comme une valeur typée, du type déclaré de la colonne, et non comme la simple chaîne qu'envoie AG Grid :

```json
"groupKeys": [ { "type": "string", "value": "EMEA" } ]
```

Votre page doit convertir les clés avant d'envoyer la requête. La démo le fait dans `toWireRequest` dans `examples/demo/web/src/datasource.ts`. Elle renomme aussi les colonnes d'agrégat au retour, car la réponse les nomme `amount_sum` et la grille lit `amount`. Si vous copiez la démo, copiez les deux étapes.

## Les fonctions disponibles {#which-functions-you-can-use}

Craticula prend en charge cinq fonctions d'agrégation : `sum`, `min`, `max`, `avg` et `count`. Une autre fonction, telle que `first`, est refusée. Une entrée de `valueCols` sans `aggFunc` l'est aussi.

Le nom de chaque agrégat dans le résultat est l'identifiant de la colonne lorsqu'il diffère du nom du champ. Sinon, c'est le nom du champ, un tiret bas et la fonction, comme `amount_sum`.

Quelques détails qui comptent pour les chiffres :

- `count` compte les lignes où le champ n'est pas nul. Il ne compte pas les lignes. Pour compter toutes les lignes, comptez la clé stable, qui n'est jamais nulle.
- Une `sum` sur un groupe sans valeurs vaut `0` sur tous les backends. Les compilateurs SQL enveloppent `sum` pour que ce soit le cas.
- `avg`, `min` et `max` sur un groupe sans valeurs sont nuls.

## Ce que le schéma doit autoriser {#what-the-schema-must-allow}

Le schéma décide quelles colonnes peuvent être groupées et agrégées. Les deux indicateurs sont désactivés par défaut.

```json
"region": { "type": "string", "groupable": true, "physical": { "sql": { "column": "region" } } },
"amount": { "type": "decimal", "aggregatable": ["sum", "avg"], "physical": { "sql": { "column": "amount" } } }
```

- Une colonne de groupe doit être dans le schéma et marquée `groupable`.
- Une agrégation doit nommer une colonne du schéma et une fonction de la liste `aggregatable` de cette colonne.
- Une colonne qui a été ouverte, c'est-à-dire dont la clé figure dans `groupKeys`, doit aussi être `filterable`. Ouvrir un groupe revient à filtrer sur une seule valeur.

Chacun de ces cas est refusé dans les deux modes, Strict et Lenient. Abandonner une colonne de groupe ou une clé donnerait à la grille une réponse différente de celle qu'elle a demandée. Voir [Strict et Lenient](strict-and-lenient.html).

## Ouvrir un groupe correspond exactement {#opening-a-group-matches-exactly}

Lorsqu'un groupe est ouvert, sa clé devient une correspondance exacte sur la colonne de groupe. Le regroupement, l'ouverture d'un groupe et l'ordonnancement des groupes utilisent tous une comparaison exacte : `EMEA` et `emea` sont donc deux groupes. Un groupe qui ne correspondrait pas exactement ne s'additionnerait pas à son parent.

Cela n'est vrai que si la base de données compare exactement par défaut. C'est le cas de PostgreSQL et de SQLite. SQL Server, MySQL et Oracle ignorent généralement la casse : déclarez donc chaque colonne par laquelle vous regroupez avec un classement binaire. Voir [Conseils sur les index et les bases de données](index-guidance.html).

MongoDB a un seul classement pour toute la requête. Une requête de regroupement n'en porte aucun, de sorte qu'un filtre de la même requête y compare en tenant compte de la casse. Les bases SQL ignorent la casse dans ce filtre.

## Clés de groupe nulles {#null-group-keys}

Les lignes dont la valeur de groupe est nulle forment un seul groupe. Pour l'ouvrir, envoyez une clé `{ "type": "null" }`. Craticula écrit pour cela un test de nullité, tel que `"region" IS NULL`.

La chaîne vide est un groupe différent de null : ses lignes ne rejoignent donc pas le groupe nul. Oracle fait exception, car Oracle stocke une chaîne vide comme null.

## Trier et compter un niveau groupé {#sorting-and-counting-a-grouped-level}

Un niveau groupé peut être trié par sa colonne de groupe ou par l'un de ses agrégats. Un tri sur toute autre colonne est refusé. La colonne de groupe joue le rôle de clé stable, de sorte que l'ordre des groupes est stable. Un agrégat placé après la colonne de groupe dans le tri n'a aucun effet et est abandonné.

Le nombre de lignes d'un niveau groupé est le nombre de groupes, pas le nombre de lignes qu'ils contiennent.

OpenSearch et Elasticsearch ont ici deux limites :

- Ils ne peuvent pas ordonner un niveau groupé par un agrégat. Une telle requête est refusée.
- Le groupe qui contient les valeurs nulles se place toujours en premier, quelle que soit la direction.

## Les exports ignorent le regroupement {#exports-ignore-grouping}

Un export renvoie des lignes simples. L'adaptateur retire `rowGroupCols`, `valueCols` et `groupKeys` d'une requête d'export. Voir [Export CSV](csv-export.html).

## D'où cela provient {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/group-aggregation](../../spec/fixtures/group-aggregation/README.md)
- [csharp/src/Craticula.Core/Ir/Aggregation.cs](../../csharp/src/Craticula.Core/Ir/Aggregation.cs)
- [csharp/src/Craticula.Core/Ir/GroupingPlan.cs](../../csharp/src/Craticula.Core/Ir/GroupingPlan.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/src/Craticula.AgGrid/AgGridRequestParser.cs](../../csharp/src/Craticula.AgGrid/AgGridRequestParser.cs)
- [examples/demo/web/src/datasource.ts](../../examples/demo/web/src/datasource.ts)
- Pages liées : [Pagination et tri](paging-and-sorting.html), [Le GridSchema](the-gridschema.html), [Comment une requête devient une requête](request-to-query.html)
