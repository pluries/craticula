---
translates: the-gridschema
title: Le GridSchema
description: Le schéma qui énumère ce qu'une grille peut toucher, et lesquels de ses indicateurs sont appliqués aujourd'hui.
source_fingerprint: cdf6e47e0fa6a2ef7b974c3b2ac02ea7892b7f9a31ffa33a18595708e80d8a45
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Le GridSchema {#the-gridschema}

Cette page explique le schéma que vous écrivez pour chaque grille : ce qu'il contient, lesquels de ses réglages Craticula applique aujourd'hui, et comment en démarrer un. Elle s'adresse au développeur sur le point de décrire à Craticula une table, une collection ou un index. Pour la liste complète des membres, voir la [référence du GridSchema](grid-schema.html).

## À quoi sert le schéma {#what-the-schema-is-for}

Le schéma est la frontière entre la requête et vos données. C'est un document JSON que vous écrivez et conservez sur le serveur. Il nomme la table, la collection ou l'index. Il énumère chaque colonne que la grille peut toucher. Pour chaque colonne, il donne un type et le nom physique dans votre base de données.

Une colonne absente du schéma ne peut jamais atteindre une requête. Les noms de tables et de colonnes d'une requête proviennent du schéma, jamais de la requête reçue. Voir [Le modèle de sécurité](safety-model.html).

Aucune requête ne peut transporter un schéma. La grille envoie les colonnes par leur identifiant de grille, et Craticula recherche chacune d'elles.

## Un petit exemple {#a-small-example}

Voici le schéma du guide de démarrage. Il décrit une table `orders`.

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

En C#, chargez-le avec `GridSchema.Parse(json)`.

## Les membres du schéma entier {#the-members-of-the-whole-schema}

| Membre | Rôle |
|---|---|
| `mode` | `strict` ou `lenient`. Le JSON Schema l'exige ; l'analyseur C# prend strict par défaut lorsqu'il manque. Voir [Strict et Lenient](strict-and-lenient.html). |
| `source` | La table ou la vue, la collection MongoDB ou l'index OpenSearch. Il ne peut pas être vide. |
| `stableKey` | Une colonne aux valeurs uniques. Ce doit être l'un des `fields`. |
| `fields` | La liste d'autorisation, indexée par l'identifiant de colonne de la grille. Il lui faut au moins un champ. |
| `staticFilter` | Un filtre ajouté à chaque requête. Facultatif. |

`GridSchema.Parse` refuse un schéma qui enfreint ces règles. Il refuse aussi les membres inconnus, les clés en double, et un `physical.sql` qui ne définit pas exactement un seul de `column`, `qualifiedColumn` et `expression`.

## Les membres d'un champ {#the-members-of-one-field}

| Membre | Rôle |
|---|---|
| `type` | `string`, `int64`, `decimal`, `double`, `boolean`, `date` ou `datetime`. Craticula convertit chaque valeur de la requête vers ce type. |
| `physical` | L'endroit où la colonne se trouve : `sql`, `mongo`, `search`, ou les trois. |
| `text` | Pour un `string` : `caseSensitivity` (`insensitive` par défaut) et `searchMode`. |
| `filterable`, `sortable`, `groupable`, `aggregatable` | Ce que la grille peut faire de la colonne. Voir ci-dessous. |
| `exportable`, `label`, `format` | La façon dont la colonne apparaît dans un export CSV. Voir [Export CSV](csv-export.html). |

Vous n'avez besoin que des mappages des backends que vous utilisez. Un mappage SQL est une colonne simple. Un mappage MongoDB est un chemin de document. Un mappage de recherche nomme le champ de l'index, et peut aussi nommer un `keywordSubField` et un `normalizedSubField`. Un champ sans aucun mappage utilise son identifiant de colonne comme nom.

## Ce que fait chaque indicateur aujourd'hui {#what-each-flag-does-today}

Ne partez pas du principe que chaque indicateur est appliqué. Voici ce que fait le code aujourd'hui :

| Indicateur | Valeur par défaut | Appliqué ? |
|---|---|---|
| `filterable` | `true` | Oui. Un filtre sur une colonne marquée `false` est refusé en mode Strict et abandonné en mode Lenient. La colonne de la liste de valeurs d'un filtre d'ensemble, et une clé de groupe que l'utilisateur a ouverte, doivent être filtrables et sont refusées dans les deux modes. |
| `groupable` | `false` | Oui. Une colonne de groupe doit être groupable. Refusé dans les deux modes. |
| `aggregatable` | aucune | Oui. Une agrégation doit utiliser une fonction de cette liste. Refusé dans les deux modes. |
| `exportable` | `true` | Oui. Il détermine les colonnes d'export par défaut, et une colonne marquée `false` ne peut pas être nommée dans `exportColumns`. |
| `sortable` | `true` | **Non.** Rien ne le lit aujourd'hui. Une colonne du schéma peut être triée quoi que dise l'indicateur. |

La liste `aggregatable` contient n'importe lesquelles des valeurs `sum`, `min`, `max`, `avg` et `count`. Voir [Regroupement et agrégation](grouping-and-aggregation.html).

Si vous devez empêcher le tri d'une colonne, laissez-la en dehors du schéma, ou appuyez-vous sur un contrôle de votre cru. L'indicateur ne le fera pas.

## La clé stable {#the-stable-key}

La `stableKey` est ce qui maintient la pagination dans l'ordre. Craticula l'ajoute à la fin de chaque tri. Elle doit nommer une colonne dont les valeurs sont uniques. Déclarez la colonne `NOT NULL` dans votre base de données, car la plupart des bases autorisent de nombreuses valeurs nulles dans une colonne unique, ce qui brise la garantie. Voir [Pagination et tri](paging-and-sorting.html).

## Le filtre statique {#the-static-filter}

`staticFilter` est une condition que Craticula ajoute à chaque requête avec AND. C'est l'endroit pour un identifiant de locataire ou un indicateur de suppression logique. La requête ne peut ni la modifier ni la retirer.

```json
"staticFilter": {
  "type": "comparison",
  "op": "eq",
  "field": "tenantId",
  "value": { "type": "int64", "value": 42 }
}
```

Le champ que nomme un `staticFilter` doit aussi être déclaré dans `fields`, afin que le compilateur trouve sa colonne. La condition fait partie du schéma : la requête ne peut donc pas l'atteindre. Décider de ce que doit être le filtre est votre travail. Craticula ne fait que l'appliquer. Voir [Le modèle de sécurité](safety-model.html).

## L'ordre des champs {#field-order}

L'ordre des champs dans le document compte. Une requête d'export sans liste de colonnes reçoit les champs exportables dans cet ordre. Les lignes d'un groupe ouvert sont elles aussi renvoyées dans cet ordre.

## D'où vient cette page {#where-this-comes-from}

- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridSchema.cs](../../csharp/src/Craticula.Core/Schema/GridSchema.cs)
- [csharp/src/Craticula.Core/Schema/FieldConfig.cs](../../csharp/src/Craticula.Core/Schema/FieldConfig.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
- [spec/fixtures/schemas](../../spec/fixtures/schemas)
- Pages liées : [Limites](limits.html), [Dialectes et fournisseurs](dialects-and-providers.html), [Comment une requête devient une requête de base de données](request-to-query.html)
