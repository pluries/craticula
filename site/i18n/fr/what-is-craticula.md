---
translates: what-is-craticula
title: Ce qu'est Craticula
description: Ce que Craticula compile, ce qu'il ne fait jamais, et où il en est.
source_fingerprint: e8f756cfd41d5e8621dce7f0e9a10a459e2c9061e1f4434abe57c82e8adc1664
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Ce qu'est Craticula {#what-craticula-is}

Cette page explique ce que fait Craticula, ce qu'il vous laisse et où en est le projet aujourd'hui. Elle s'adresse à un développeur qui a une grille côté serveur AG Grid et qui n'a jamais vu Craticula.

Craticula est une bibliothèque .NET qui transforme une requête AG Grid Server-Side Row Model en requête de base de données. Elle prend en charge SQL, MongoDB et OpenSearch.

## Le problème qu'il résout {#the-problem-it-solves}

Une grille côté serveur AG Grid envoie à votre serveur une requête JSON. La requête indique quelles lignes la grille veut, comment les trier, comment les filtrer et comment les regrouper.

Chaque équipe backend finit par écrire le même code pour transformer ce JSON en requête. Ce code est facile à rater. La gestion des valeurs nulles, la sensibilité à la casse, la pagination et la protection contre l'injection demandent toutes du soin.

Craticula est cette traduction, écrite une seule fois et testée sur des exemples communs.

## Ce qu'il compile {#what-it-compiles}

Vous donnez deux choses à Craticula :

- la requête exactement telle qu'AG Grid l'a envoyée ;
- un schéma qui liste les colonnes que la grille peut toucher et la façon dont elles correspondent à votre base de données.

Craticula vous renvoie une requête que vous pouvez exécuter :

- pour SQL, une instruction et une liste de paramètres ;
- pour MongoDB, un pipeline d'agrégation ;
- pour OpenSearch et Elasticsearch, une requête dans leur langage de requête JSON.

## Ce qu'il ne fait jamais {#what-it-never-does}

Craticula est un compilateur, pas un client.

- Il n'ouvre jamais de connexion à une base de données.
- Il n'exécute jamais de requête.
- Il ne lit jamais vos données.

L'exécution de la requête vous revient. Des paquets d'adaptateurs facultatifs peuvent s'en charger pour vous, mais ils sont séparés du cœur. Les paquets du cœur ne dépendent jamais d'eux.

## Backends et versions d'AG Grid pris en charge {#supported-backends-and-ag-grid-versions}

La première version cible ces backends :

- PostgreSQL
- SQL Server
- MySQL et MariaDB
- SQLite
- MongoDB
- OpenSearch
- Elasticsearch

Oracle ne figure pas dans la liste de la v1, et le projet le traite comme une question ouverte. Le dépôt contient un dialecte Oracle, mais il ne fait pas partie de l'engagement.

Côté grille, le README cite les versions 31 à 36 d'AG Grid Server-Side Row Model. Il prend aussi en charge l'Infinite Row Model de la Community pour les grilles à plat, c'est-à-dire le tri, les filtres de texte, de nombre et de date, et la pagination. Le regroupement de lignes, l'agrégation, le pivot et le filtre d'ensemble sont des fonctionnalités Enterprise et ne font pas partie de l'engagement pour la Community.

Le mode pivot n'est pas pris en charge. L'analyseur de requêtes refuse une requête dont le mode pivot est activé.

## État actuel {#current-state}

Craticula est en pré-version. Aucun paquet n'est encore publié, et personne n'héberge de démo pour les visiteurs. Le dépôt contient une application de démonstration que vous exécutez vous-même (`examples/demo`), qui demande Docker, le SDK .NET 10 et Node.

Pour l'essayer, compilez depuis les sources. Le [guide de démarrage rapide C#](quickstart-csharp.html) montre comment. La bibliothèque C# est l'implémentation de référence. Le dépôt décrit des portages TypeScript, Python et Go comme prévus après le gel de la spécification. Aucun n'existe encore.

## Pour aller plus loin {#where-to-go-next}

- [Comment une requête devient une requête](request-to-query.html) suit une requête à travers le pipeline.
- [Strict et Lenient](strict-and-lenient.html) explique les deux façons de traiter les colonnes inconnues.
- [Le modèle de sécurité](safety-model.html) liste ce que Craticula protège et ce qu'il ne protège pas.

## D'où cela provient {#where-this-comes-from}

- [README.md](../../README.md)
- [spec/README.md](../../spec/README.md)
- [csharp/src/Craticula.Core/README.md](../../csharp/src/Craticula.Core/README.md)
- [csharp/src/Craticula.AgGrid/AgGridRequestParser.cs](../../csharp/src/Craticula.AgGrid/AgGridRequestParser.cs)
