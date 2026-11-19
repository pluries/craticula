---
translates: strict-and-lenient
title: Strict et Lenient
description: Ce que font les deux modes du schéma des colonnes que le schéma n'autorise pas.
source_fingerprint: 20ab3fa199820cb9e052565112f509257cd8428bafaf7eced343e56e4ea4c25a
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Strict et Lenient {#strict-and-lenient}

Cette page explique les deux modes dans lesquels un schéma peut fonctionner, et ce que fait chacun lorsqu'une requête nomme une colonne que le schéma n'autorise pas. Elle s'adresse à un développeur qui écrit un schéma et doit choisir un mode.

En bref : utilisez Strict sauf raison contraire. Strict est le mode par défaut.

## Où définir le mode {#where-you-set-the-mode}

Le mode est un paramètre du schéma, avec les valeurs `strict` et `lenient`.

```json
{
  "mode": "strict",
  "source": "orders",
  "stableKey": "id",
  "fields": { }
}
```

En C#, `GridSchema.Mode` vaut `Strict` par défaut. Le JSON Schema du fichier indique `mode` comme obligatoire : écrivez-le donc explicitement dans votre fichier de schéma.

## Strict {#strict}

En mode Strict, un filtre sur une colonne que le schéma ne liste pas est refusé. Craticula lève une `UnknownFieldException` qui nomme chaque colonne rejetée. Aucune requête n'est produite.

Il en va de même pour une colonne que le schéma liste mais marque `filterable: false`. Craticula la traite comme une colonne inconnue.

Les fixtures adversariales le montrent. Un filtre, un tri et un regroupement de lignes sur une colonne inconnue sont tous refusés. Le filtre et le regroupement de lignes lèvent `UnknownFieldException` ; le tri est refusé par le compilateur (voir le dernier point ci-dessous). Il en va de même pour un nom de colonne composé de SQL, tel que `amount'); DROP TABLE users; --`.

## Lenient {#lenient}

En mode Lenient, Craticula abandonne une condition de filtre portant sur une colonne inconnue ou non filtrable et poursuit avec le reste.

Abandonner une condition élargit la réponse. La grille peut recevoir plus de lignes que demandé. Ne choisissez Lenient que si vous l'acceptez.

Quelques précisions sur la façon dont une condition abandonnée est retirée :

- Un groupe AND ou OR qui perd toutes ses conditions disparaît.
- Un groupe qui n'a plus qu'une condition devient cette condition.
- Un NOT dont la condition disparaît disparaît aussi. Il ne devient ni "tout correspond" ni "rien ne correspond".

## Ce qu'aucun mode n'assouplit {#what-no-mode-relaxes}

Lenient ne pardonne qu'une condition de filtre. La spécification dit que tout ce qui détermine la forme de la réponse est refusé dans tous les modes :

- une colonne de groupe qui n'est pas dans le schéma, ou qui n'est pas marquée groupable ;
- une clé de groupe qui descend dans une colonne qui n'est pas filtrable ;
- une agrégation sur une colonne qui n'est pas dans le schéma, ou qui n'a pas le droit d'utiliser cette fonction ;
- la colonne d'une requête de valeurs distinctes pour un filtre d'ensemble ;
- une colonne d'export inconnue, non exportable, répétée, ou une liste vide.

La raison est que les abandonner donnerait à la grille une réponse différente de celle qu'elle a demandée, sans erreur. Une clé de groupe abandonnée pourrait renvoyer les lignes d'un autre groupe sous l'étiquette attendue par la grille.

Le mode n'a pas non plus d'effet sur les autres contrôles. Une requête trop profonde, trop large, qui demande trop de lignes, ou dont une valeur ne convient pas au type de la colonne est rejetée dans les deux modes. Voir [Le modèle de sécurité](safety-model.html).

Un dernier point : un tri sur une colonne que le schéma ne liste pas est refusé dans les deux modes. Le refus vient du compilateur, qui lève sa propre exception de compilation plutôt que `UnknownFieldException` ; interceptez donc les deux dans votre point d'accès et renvoyez une erreur client.

## Comment choisir {#how-to-choose}

- Choisissez **Strict** si la grille est la vôtre et qu'une colonne inconnue signifie un bug ou une attaque. Vous le découvrez immédiatement.
- Choisissez **Lenient** uniquement si vous acceptez qu'une requête nommant une colonne inconnue ou non filtrable renvoie davantage de lignes au lieu d'une erreur.

Si vous hésitez, utilisez Strict.

## D'où cela provient {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridSchemaMode.cs](../../csharp/src/Craticula.Core/Schema/GridSchemaMode.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
