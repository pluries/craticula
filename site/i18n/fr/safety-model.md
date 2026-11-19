---
translates: safety-model
title: Le modèle de sécurité
description: Comment les valeurs, les identifiants et les limites protègent une requête compilée, et ce qui reste à votre charge.
source_fingerprint: cad40472e319059d27fe5a7517ac79ed14efb07866e1630c2883f9c7419a959c
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Le modèle de sécurité {#the-safety-model}

Cette page liste ce que fait Craticula pour empêcher une requête hostile de nuire à votre base de données, et ce qu'il ne fait pas. Elle s'adresse à un développeur ou à un relecteur qui doit juger si Craticula convient à un système exposé au public.

## Les valeurs sont des paramètres {#values-are-parameters}

Chaque valeur de la requête entre dans la requête compilée comme un paramètre. Elle n'est jamais collée dans le texte.

Pour SQL, l'instruction contient des marqueurs tels que `$1` et les valeurs voyagent dans une liste séparée. Pour la requête du guide de démarrage rapide, le texte ne contient ni "acme" ni 100. Voir [Comment une requête devient une requête](request-to-query.html).

La spécification applique la même idée à MongoDB et à OpenSearch. Là, les valeurs entrent dans le pipeline ou dans le document de requête comme des données. Une valeur de recherche de texte qui contient des caractères de motif est échappée. Les compilateurs ont des fonctions utilitaires pour cela.

Une valeur telle que `'; DROP TABLE users; --` envoyée dans un filtre de texte ordinaire est simplement une chaîne. Elle est comparée et ne fait rien d'autre. Les fixtures adversariales portent sur la forme de la requête, pas sur le contenu des chaînes.

## Les identifiants viennent de votre schéma {#identifiers-come-from-your-schema}

Les noms de table, de collection et de colonne viennent uniquement du schéma que vous avez écrit. La requête n'en fournit jamais.

La requête nomme les colonnes par leur identifiant de grille, par exemple `customer`. Craticula cherche cet identifiant dans le schéma et utilise le nom physique que vous avez déclaré. Pour SQL, le nom est entre guillemets selon le dialecte, et un guillemet à l'intérieur d'un nom est doublé.

## Les colonnes inconnues sont refusées {#unknown-columns-are-refused}

Une colonne qui n'est pas dans le schéma est refusée avant qu'une requête n'existe. Le guide de démarrage rapide montre le rejet d'un filtre sur `password`.

Une colonne qui n'est pas dans le schéma ne peut être utilisée ni pour regrouper, ni pour agréger, ni pour trier, dans aucun mode. Un filtre sur une telle colonne est refusé en mode Strict et abandonné en mode Lenient ; voir [Strict et Lenient](strict-and-lenient.html). Un schéma peut aussi marquer une colonne comme non filtrable, non groupable ou non exportable.

## Les entrées malformées sont refusées {#malformed-input-is-refused}

L'adaptateur et les contrôles rejettent les entrées qu'ils ne reconnaissent pas :

- un opérateur de filtre inconnu, y compris une faute de frappe ou `regex` ;
- une valeur de filtre envoyée sous forme d'objet ou de tableau là où une valeur simple est attendue ;
- des clés dupliquées dans le JSON ;
- une valeur qui ne convient pas au type de la colonne, par exemple du texte dans une colonne numérique ;
- des noms de sortie dupliqués pour les agrégations.

Chacun de ces cas a une fixture qui attend un rejet net.

## Limites de ressources {#resource-limits}

Une requête ne peut pas demander un travail illimité. Voici les valeurs par défaut dans `ResourceLimits` :

| Limite | Par défaut |
|---|---|
| Profondeur de l'arbre de filtres | 8 |
| Conditions dans l'ensemble du filtre | 64 |
| Valeurs dans une liste in ou not-in | 1000 |
| Lignes dans une page | 1000 |
| Lignes renvoyées par une requête de valeurs distinctes | au plus 10000 |
| Lignes dans une requête qui n'envoie aucune fenêtre de lignes | une page par défaut de 100 (toutes les lignes uniquement par un export, ou par un indicateur que vous activez) |
| Durée de la requête sur MongoDB et Search | non définie ; vous la définissez et la base de données la fait respecter |

Vous pouvez relever ou abaisser chacune d'elles. Vous ne pouvez pas désactiver une limite, sauf que la limite de durée de requête est facultative et non définie tant que vous ne la définissez pas. Zéro ou un nombre négatif est refusé lorsque vous le définissez. Voir [Limites](limits.html).

Les fixtures testent chaque limite un cran au-delà de la borne, et avec des valeurs extrêmes comme une liste de 5000 valeurs ou une page d'un million de lignes.

## Ce contre quoi Craticula ne protège pas {#what-craticula-does-not-protect-against}

- **Le compte de base de données.** Craticula ne contrôle pas ce que le compte peut faire. Donnez au compte qui exécute ces requêtes les droits minimaux dont il a besoin, par exemple en lecture seule sur la seule table concernée.
- **L'exécution de la requête.** Craticula ne l'exécute jamais. La gestion des connexions, les limites de coût et la manière d'exécuter l'instruction vous reviennent. Pour MongoDB et Search, vous pouvez faire porter à la requête compilée une limite de durée (`MaxQueryTimeMs`) que la base de données fait respecter ; pour SQL, définissez un délai d'expiration d'instruction sur la connexion ou sur le compte.
- **Qui peut utiliser la grille.** L'authentification et l'accès par utilisateur sont hors de son périmètre. Le schéma peut ajouter un filtre fixe à chaque requête, mais c'est à vous de décider ce que ce filtre doit être.
- **Un schéma erroné.** Si votre schéma liste une colonne qui devrait rester cachée, Craticula la servira.
- **Les requêtes lentes.** Une requête dans les limites peut quand même être lente si la colonne n'a pas d'index. Voir les [conseils sur les index](index-guidance.html).

## D'où cela provient {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
- [csharp/src/Craticula.Core/Schema/ResourceLimits.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimits.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/src/Craticula.Sql/PostgresDialect.cs](../../csharp/src/Craticula.Sql/PostgresDialect.cs)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
