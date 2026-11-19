---
translates: limits
title: Limites
description: Les limites de ressources par défaut, ce que chacune fait et comment la modifier.
source_fingerprint: 4ebb0479bf2bf034db02fbe9221ed719f6f737678d26a8c1dee647b249dba066
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Limites {#limits}

Cette page énumère les limites de ressources que Craticula impose à chaque requête, ce que chacune protège et comment la modifier. Elle s'adresse au développeur qui exploite une grille publique, ou qui veut savoir pourquoi une requête volumineuse a été refusée.

## Pourquoi il y a des limites {#why-there-are-limits}

Une requête est une entrée venue d'un inconnu. Sans limites, une requête pourrait demander un arbre de filtres imbriqué sur mille niveaux, une liste d'un million de valeurs ou une page de dix millions de lignes. Chacune de ces demandes coûte beaucoup de travail à votre base de données.

Craticula refuse une telle requête avant de construire une requête de base de données.

## Les limites et leurs valeurs par défaut {#the-limits-and-their-defaults}

| Réglage | Valeur par défaut | Ce qu'il limite |
|---|---|---|
| `MaxDepth` | 8 | La profondeur d'imbrication des filtres. Une condition seule a la profondeur 1. |
| `MaxLeaves` | 64 | Le nombre de conditions dans l'ensemble du filtre, additionnées sur toutes les branches. |
| `MaxInValues` | 1000 | Le nombre de valeurs dans une liste « in » ou « not in ». |
| `MaxPageSize` | 1000 | Le nombre de lignes d'une page, soit `endRow - startRow`. |
| `MaxSetValuesResults` | 10000 | Le plus grand nombre de valeurs qu'une requête de valeurs distinctes peut renvoyer, quel que soit le nombre que demande la grille. |
| `DefaultSetValuesResults` | 1000 | Le nombre de valeurs que cette requête renvoie lorsque la grille ne le précise pas. |
| `MaxQueryTimeMs` | non défini | La durée pendant laquelle une requête MongoDB ou Search peut s'exécuter, en millisecondes. La seule limite facultative ; voir [La limite de temps de requête](#the-query-time-limit). |

Ce sont des propriétés de `ResourceLimits`.

Les quatre premières sont des contrôles : une requête au-delà de la limite est refusée. Les deux suivantes sont des plafonds. `MaxQueryTimeMs` n'est ni l'un ni l'autre : elle est transmise à la requête, et c'est la base de données qui l'applique. Une requête de valeurs distinctes pour un filtre d'ensemble n'est jamais refusée pour cause de taille excessive. Craticula la ramène au plafond, et utilise la valeur par défaut lorsque la grille n'envoie aucun nombre.

Une requête qui n'envoie ni `startRow` ni `endRow` n'est pas non plus illimitée : elle reçoit une page par défaut de 100 lignes (`AgGridParseOptions.DefaultPageSize`), et la limite de taille de page contrôle cette page comme n'importe quelle autre. Voir [Pagination et tri](paging-and-sorting.html).

La limite de taille de page ne s'applique pas à un export du résultat complet (`exportScope` défini à `"all"`), qui n'a pas de page. Un export limité à une page conserve sa plage de lignes, et la limite de taille de page s'y applique. Voir [Export CSV](csv-export.html).

Craticula compte ensemble les groupes que l'utilisateur a ouverts et les filtres. Chaque groupe ouvert est une condition de plus, et une requête groupée compte un niveau de plus que ce qu'elle écrit : sa limite de profondeur effective est donc de 7 avec la valeur par défaut.

## Les limites fixes {#limits-that-are-fixed}

Quelques bornes sont intégrées et ne peuvent pas être modifiées :

- au plus 64 colonnes de groupe dans une requête ;
- une valeur de texte dans un filtre d'au plus 8192 caractères ;
- une valeur décimale d'au plus 128 caractères ;
- un identifiant de colonne d'au plus 256 caractères, dans une clé de tri, une colonne de groupe, une agrégation ou la colonne d'un filtre d'ensemble.

## À quoi ressemble un refus {#what-a-refusal-looks-like}

Lorsqu'une requête enfreint une limite, `GridFilterPipeline.Process` lève une `ResourceLimitExceededException`. Sa liste `Violations` nomme chaque limite enfreinte, avec le nombre réel et le maximum. Interceptez-la dans votre point d'entrée et renvoyez une erreur client. Si une requête enfreint deux limites, vous voyez les deux.

## Comment modifier une limite {#how-to-change-a-limit}

Les limites ne font pas partie du fichier de schéma. Ce sont du code, et vous les transmettez. Voici comment la démo définit les siennes :

```csharp
public static ResourceLimits Default { get; } = new()
{
    MaxPageSize = 500,
    MaxDepth = 6,
    MaxLeaves = 32,
    MaxInValues = 200,
    MaxSetValuesResults = 1_000,
    DefaultSetValuesResults = 200
};
```

Passez ensuite la valeur aux appels qui en prennent une. Le guide de démarrage passe `new ResourceLimits()`, c'est-à-dire les valeurs par défaut.

```csharp
FilterNode? filter = GridFilterPipeline.Process(
    parsed.NativeFilter, parsed.CustomFilters, parsed.Page, schema, limits, parsed.Group, parsed.Aggregations);
```

Une requête de valeurs distinctes passe par `GridFilterPipeline.ProcessSetValues`, et son plafond provient de `ResourceLimitsValidator.ResolveSetValuesLimit`.

Vous pouvez relever une limite aussi haut que vous le voulez. Il n'y a aucun contrôle de borne supérieure. Choisissez des nombres que votre base de données peut supporter.

## La limite de temps de requête {#the-query-time-limit}

`MaxQueryTimeMs` s'adresse à un hôte dont la base de données est partagée ou publique. Les autres limites bornent la forme d'une requête ; celle-ci borne le travail que la base de données fournit pour elle. Définissez-la à un nombre entier de millisecondes, de 1 à 2,147,483,647, et les compilateurs l'inscrivent dans la requête :

| Moteur | Ce que porte la requête | Ce qui se passe lorsque le temps est écoulé |
|---|---|---|
| MongoDB | `maxTimeMS` sur la commande d'agrégation | MongoDB annule l'opération, et l'adaptateur lève `QueryTimeoutException`. |
| OpenSearch et Elasticsearch | un membre `timeout` du corps de recherche, par exemple `"2000ms"` | Le moteur s'arrête à son prochain contrôle (une limite souple) et répond avec `timed_out: true`. L'adaptateur lève `QueryTimeoutException` et ne renvoie jamais les résultats partiels comme une page. |

La limite provient uniquement de votre code. Une requête ne peut ni la définir, ni la relever, ni la retirer, et un `maxQueryTimeMs` dans une requête est ignoré. Un export ne porte aucune limite, car il est long par conception ; arrêtez un export avec le jeton d'annulation. Les moteurs SQL n'ont pas de limite compilée : définissez à la place un délai d'expiration d'instruction sur la connexion ou sur le compte de la base de données (la démo publique le fait, pour PostgreSQL).

Laissez-la non définie et rien ne change : les requêtes sont exactement ce qu'elles étaient. Une valeur nulle ou négative lève une exception lorsque vous construisez les `ResourceLimits`, et les compilateurs la refusent eux aussi si vous remplissez une requête à la main. Voir les règles dans [Limite de temps de requête](query-time-limit.html).

## Vous ne pouvez pas désactiver une limite {#you-cannot-turn-a-limit-off}

Toutes les limites sauf une sont de simples nombres positifs, et il n'existe pas de valeur « illimité ». Fixer une limite à zéro ou moins lève une `ArgumentOutOfRangeException` lorsque vous construisez les `ResourceLimits`. L'exception est `MaxQueryTimeMs`, non définie par défaut parce que la bibliothèque ne peut pas savoir à quel point votre base de données est lente ; la fixer à un nombre ne désactive jamais rien.

C'est voulu. Une limite de zéro ne signifierait pas « pas de limite ». Elle refuserait chaque requête, et un réglage laissé vide par erreur pourrait produire cet effet sans que personne le remarque.

## Où les contrôles s'exécutent {#where-the-checks-run}

Les limites sont contrôlées par `GridFilterPipeline.Process`. L'adaptateur qui lit la requête AG Grid ne les contrôle pas, et les compilateurs non plus. Si vous sautez le pipeline et appelez vous-même un compilateur, aucune limite n'est contrôlée. Le guide de démarrage appelle le pipeline pour cette raison. Voir [Comment une requête devient une requête de base de données](request-to-query.html).

## D'où vient cette page {#where-this-comes-from}

- [csharp/src/Craticula.Core/Schema/ResourceLimits.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimits.cs)
- [csharp/src/Craticula.Core/Schema/ResourceLimitsValidator.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimitsValidator.cs)
- [csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs](../../csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs)
- [csharp/src/Craticula.Core/Ir/GroupSpecValidator.cs](../../csharp/src/Craticula.Core/Ir/GroupSpecValidator.cs)
- [spec/semantics.md](../../spec/semantics.md), les addenda sur la limite de temps de requête et la taille de page par défaut
- [examples/demo/Api/Grid/DemoLimits.cs](../../examples/demo/Api/Grid/DemoLimits.cs)
- [spec/ir.schema.json](../../spec/ir.schema.json)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
- Pages liées : [Le modèle de sécurité](safety-model.html), [Pagination et tri](paging-and-sorting.html), [Le GridSchema](the-gridschema.html)
