---
translates: claude-skill
title: Compétence Claude
description: Une compétence pour Claude qui lui apprend à ajouter Craticula à un projet C#, comment l'installer et ce qu'elle fait.
source_fingerprint: 63b1738da63b9355a6d5c64ab072a81d4f2fa969df1e3817fc06403b6cb6dba0
drafter: claude
drafted_on: 2026-11-22
status: machine-drafted
---
# Compétence Claude {#claude-skill}

Craticula propose une compétence pour Claude. Une compétence est un dossier d'instructions en texte brut que Claude lit avant de vous aider. Celle-ci apprend à Claude à ajouter Craticula à un projet C#.

Pour l'utiliser, installez-la avec les deux commandes ci-dessous, ou copiez son dossier à la main. Demandez ensuite à Claude d'ajouter Craticula à votre projet. Quand vous avez terminé, lisez [Le modèle de sécurité](safety-model.html) pour voir ce que Craticula protège.

## Deux façons de l'installer {#two-ways-to-install}

La première façon est un plugin Claude Code. Exécutez les deux commandes dans un terminal :

```text
claude plugin marketplace add pluries/craticula
claude plugin install craticula@craticula
```

La première commande ajoute la place de marché Craticula depuis le dépôt. La seconde en installe la compétence. Les commandes sont les mêmes dans toutes les langues de ce site.

La seconde façon est une copie. Prenez le dossier `skills/craticula` du [dépôt Craticula](https://github.com/pluries/craticula) et placez-le dans `~/.claude/skills/craticula/`. C'est votre dossier personnel de compétences, donc la compétence fonctionne dans tous les projets que vous ouvrez. Pour l'utiliser dans un seul projet, placez plutôt le dossier dans le dossier de compétences de ce projet.

## Ce que fait la compétence {#what-the-skill-does}

- Elle indique à Claude quels paquets Craticula votre projet requiert.
- Elle montre comment déclarer un schéma, analyser la requête de la grille et la compiler en requête.
- Elle traite comme facultatifs les adaptateurs qui exécutent les requêtes.
- Elle oriente Claude vers les mêmes faits que ce site, pour que les deux ne divergent pas.

La compétence respecte les règles de sécurité et les limites de la bibliothèque. Voir [Le modèle de sécurité](safety-model.html) et [Limites](limits.html).

## Ce qu'elle ne fait pas {#what-it-does-not-do}

La compétence est du texte. Elle ne peut ni exécuter du code, ni ouvrir une connexion, ni modifier un fichier. Claude effectue toute modification de votre projet dans votre propre session, selon vos propres réglages d'autorisation.

La compétence ne nomme aucune version. Elle demande à Claude d'utiliser le dernier paquet sur nuget.org, ou la version que votre projet utilise déjà.

## Langages {#languages}

La compétence couvre la bibliothèque C#, qui est l'implémentation de référence. Aucune implémentation TypeScript, Python ou Go n'existe encore. Leurs pages de démarrage rapide le disent : [Python](quickstart-python.html), [Go](quickstart-go.html) et [TypeScript](quickstart-typescript.html). La compétence propose la bibliothèque C# à la place.

## Quelle copie est officielle {#which-copy-is-official}

La copie officielle est le dossier `skills/craticula` du [dépôt Craticula](https://github.com/pluries/craticula). Les versions des paquets portent des étiquettes qui commencent par `dotnet-v`. Signalez un problème de sécurité comme le décrit [SECURITY.md](https://github.com/pluries/craticula/blob/main/SECURITY.md).

Un fork, ou une copie venue d'ailleurs, n'a aucune de ces garanties de provenance. Comparez-le au dépôt avant de vous y fier.

## Ce qu'il faut attendre de Claude {#what-to-expect-from-claude}

Le comportement d'un agent n'est pas garanti : la compétence est du texte, et la preuve qu'un agent aboutit à une exécution qui fonctionne est une démonstration manuelle, pas un test automatisé.

Lisez le code que Claude écrit avant de l'exécuter, comme pour tout code.

## Pour aller plus loin {#further-reading}

- [Dialectes et fournisseurs](dialects-and-providers.html) indique pour quelles bases de données Craticula compile et en quoi elles diffèrent.
- [Limites](limits.html) énumère les plafonds de taille et de complexité d'une requête.
- [Le modèle de sécurité](safety-model.html) énumère ce que Craticula protège et ce qu'il ne protège pas.
- [Le guide de démarrage rapide C#](quickstart-csharp.html) montre les mêmes étapes à la main.
