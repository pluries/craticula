---
translates: overview
title: Vue d'ensemble
description: Ce qu'est Craticula, ce qu'il compile et où il en est.
source_fingerprint: 9e9db17bacc49cd5a84bc0635d310667b81d2516e78587d67158ad43b9e0c3f1
drafter: claude
drafted_on: 2026-11-27
status: approved
---
# Craticula {#craticula}

[![CI](https://github.com/pluries/craticula/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/pluries/craticula/actions/workflows/ci.yml)
[![coverage gate](https://img.shields.io/badge/coverage%20gate-%E2%89%A590%25%20per%20assembly-brightgreen)](https://github.com/pluries/craticula/actions/workflows/ci.yml)
[![license](https://img.shields.io/github/license/pluries/craticula)](LICENSE)
[![spec version](https://img.shields.io/badge/spec-1.0.0-blue)](spec/VERSION)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/pluries/craticula/badge)](https://scorecard.dev/viewer/?uri=github.com/pluries/craticula)

> Un compilateur, pas un client : traduire les requêtes AG Grid Server-Side Row Model en requêtes
> natives et sûres pour le backend — SQL, MongoDB, OpenSearch/Elasticsearch — à partir d'une seule IR
> canonique, dans quatre langages.

**Mainteneur :** Christian Stephan ([cstephan.dev](https://cstephan.dev), [LinkedIn](https://www.linkedin.com/in/christian-stephan), [GitHub](https://github.com/cstephan-dev)). Craticula est open source sous licence Apache-2.0 ;
le site du projet est [craticula.pluries.dev](https://craticula.pluries.dev).

**État :** conception initiale. Les mainteneurs tiennent en privé un document d'exigences techniques (TRD : architecture,
modèle de sécurité, feuille de route, questions ouvertes) ; ses identifiants d'exigences (AR-1, SEM-1, GRP-7, etc.)
sont cités dans tout ce dépôt, et les règles normatives se trouvent dans [`spec/semantics.md`](spec/semantics.md).

## Pourquoi {#why}

Chaque équipe backend réimplémente la traduction d'une requête AG Grid SSRM
(`filterModel`, `sortModel`, `rowGroupCols`, `groupKeys`, `valueCols`, `startRow`/`endRow`)
en requêtes de base de données, généralement avec des intermédiaires DSL sous forme de chaînes, des opérateurs manquants, une sémantique
des valeurs nulles et de la casse défaillante, une surface d'injection, et aucune prise en charge du regroupement ni des moteurs de recherche. Aucune
bibliothèque open source maintenue ne couvre cela de bout en bout.

## Comment ça marche {#how-it-works}

![Comment une requête devient une requête de base de données : une requête AG Grid passe par l'adaptateur de requêtes vers l'IR canonique, et le compilateur de requêtes la transforme en artefact de requête (SQL avec paramètres, pipeline d'agrégation MongoDB ou requête OpenSearch), le tout vérifié par rapport au GridSchema ; des adaptateurs d'exécution optionnels exécutent l'artefact et remettent les lignes en forme pour la réponse de la grille.](site/diagrams/how-it-works.svg)

Le cœur n'ouvre jamais de connexion : la compilation est une fonction pure qui prend une requête de grille et
une configuration de schéma (la frontière de sécurité et de typage) et produit un artefact de requête simple.
L'exécution — lancer l'artefact et remettre les résultats en forme pour la réponse de la grille — relève de
paquets d'adaptateurs distincts et optionnels, un par écosystème.

## Périmètre (v1) {#scope-v1}

- **Adaptateur de requêtes** (la spécification l'appelle *frontend adapter* ; c'est le côté entrée du compilateur, et il s'exécute dans votre serveur, pas dans le navigateur) : AG Grid SSRM (v31–v36). L'Infinite Row Model d'AG Grid Community est pris en charge pour les grilles à plat
  (tri, filtres de texte, de nombre et de date, pagination ; voir [`spec/fixtures/community-infinite`](spec/fixtures/community-infinite/README.md)).
  Le regroupement de lignes, l'agrégation, le pivot et le filtre d'ensemble sont des fonctionnalités Enterprise et ne font pas partie de cet engagement.
- **Compilateurs de requêtes** (les *backend compilers* de la spécification, eux aussi dans votre serveur) : PostgreSQL, SQL Server, MySQL/MariaDB, SQLite, MongoDB, OpenSearch,
  Elasticsearch. Oracle est testé par la communauté : le même pipeline SQL, avec une pagination `FETCH FIRST` (12c et suivantes).
- **Implémentation de référence :** C#/.NET, portée vers TypeScript, Python et Go après le gel
  de la spécification en 1.0.
- **La sémantique** (sensibilité à la casse, gestion et ordre des valeurs nulles, dates et fuseaux, pagination
  déterministe) est normative et appliquée par une suite de fixtures de conformité commune, indépendante du langage.
- L'export CSV/TSV en flux partage le même modèle d'entrée, uniquement compilé.

Le §2.2 du TRD (hors périmètre) et son §14 (feuille de route) disent ce qui est explicitement exclu de la v1.

## Organisation du dépôt (prévue) {#repository-layout-planned}

```
spec/         IR JSON Schema, semantics.md, conformance fixtures — the source of truth
csharp/       reference implementation (Core, AgGrid adapter, compilers, execution adapters)
typescript/   TypeScript port (after spec freeze)
python/       Python port (after spec freeze)
go/           Go port (after spec freeze)
docs/adr/     architecture decision records (why the design is the way it is)
examples/     demo app (React + AG Grid + one sample backend)
```

## Paquets {#packaging}

L'implémentation C# est répartie en dix paquets NuGet, tous publiés sur nuget.org :

[![NuGet](https://img.shields.io/nuget/v/Craticula.Core?label=nuget)](https://www.nuget.org/packages/Craticula.Core)

[`Craticula.Core`](https://www.nuget.org/packages/Craticula.Core),
[`Craticula.AgGrid`](https://www.nuget.org/packages/Craticula.AgGrid),
[`Craticula.Sql`](https://www.nuget.org/packages/Craticula.Sql),
[`Craticula.Mongo`](https://www.nuget.org/packages/Craticula.Mongo),
[`Craticula.Search`](https://www.nuget.org/packages/Craticula.Search),
[`Craticula.Export.Csv`](https://www.nuget.org/packages/Craticula.Export.Csv),
[`Craticula.EntityFrameworkCore`](https://www.nuget.org/packages/Craticula.EntityFrameworkCore),
[`Craticula.Dapper`](https://www.nuget.org/packages/Craticula.Dapper),
[`Craticula.MongoDB.Driver`](https://www.nuget.org/packages/Craticula.MongoDB.Driver) et
[`Craticula.OpenSearch.Client`](https://www.nuget.org/packages/Craticula.OpenSearch.Client).
Installez-en un avec `dotnet add package <name>`. Pour vérifier que les paquets se compilent et qu'un consommateur propre se compile contre eux, exécutez
`bash scripts/pack-smoke.sh` (Python 3.10+ et le SDK .NET 10 ; environ 3 minutes).

## Compétence Claude {#claude-skill}

Une compétence pour Claude vous guide de zéro jusqu'à une première requête de grille compilée et demande à Claude de refuser les raccourcis dangereux. Installez-la comme plugin Claude Code :

```text
claude plugin marketplace add pluries/craticula
claude plugin install craticula@craticula
```

Ou copiez le dossier [`skills/craticula`](skills/craticula/SKILL.md) dans `~/.claude/skills/craticula/`. La compétence est du texte : le comportement de Claude n'est pas garanti. Voir la [page de la compétence Claude](https://craticula.pluries.dev/claude-skill.html).

## Licences des dépendances {#dependency-licenses}

Chaque paquet NuGet sous `csharp/`, dépendances transitives et projets de test compris, doit porter une licence acceptée par le projet.
`python3 scripts/check-licenses.py` le vérifie (Python 3.10+, le SDK .NET 10 et nuget.org ; restaurez d'abord la solution avec
`dotnet restore Craticula.sln` dans `csharp/`, puis l'outil épinglé avec `dotnet tool restore` au même endroit). Le même script s'exécute dans le
job `license-check` de chaque pull request et prend quelques secondes avec un cache de paquets chaud.

- **Autorisées :** MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, 0BSD, Unlicense, PostgreSQL, Zlib
  ([`scripts/license-allowlist.json`](scripts/license-allowlist.json)).
- **Refusées :** GPL, LGPL, AGPL, SSPL, BUSL, Elastic, Commons Clause et toute licence non commerciale. La ligne d'échec nomme le
  paquet, sa version, la licence et le projet.
- **MPL-2.0 :** uniquement lorsqu'un ADR accepté (une ligne `Status: Accepted`) dans `docs/adr/` nomme MPL-2.0 et le paquet.
  Le contrôle refuse par défaut, par conception : sans un tel ADR, un paquet MPL-2.0 est refusé.
- **Dérogations :** lorsque l'outil ne peut pas lire une licence (un fichier de licence ou une simple URL au lieu d'un identifiant SPDX), ajoutez une entrée à
  [`scripts/license-overrides.json`](scripts/license-overrides.json) avec le paquet, sa version exacte, la vraie licence et une
  raison écrite. La licence doit être un identifiant SPDX autorisé (ou `"vendor_terms": true` pour les conditions propres à un éditeur, non SPDX). Une dérogation
  ne lève jamais une licence que l'outil a lue comme refusée ou comme MPL-2.0. Une entrée sans raison fait échouer le contrôle, de même qu'une entrée qui
  ne correspond plus à aucun paquet.
- **Pièges :** `MySql.Data` (GPL) est rejeté par son nom : utilisez `MySqlConnector`. Le pilote Oracle `Oracle.ManagedDataAccess.Core` et
  `Testcontainers.Oracle` ne sont acceptés que dans les projets de test sous `csharp/tests`, jamais dans un paquet sous `csharp/src`.

## Démo {#demo}

Essayez-la en ligne : [PostgreSQL](https://craticula-pg.pluries.dev) et [MongoDB](https://craticula-mongo.pluries.dev). Les deux affichent les mêmes
commandes synthétiques à travers la même page AG Grid ; elles sont en lecture seule et limitées en débit.

[`examples/demo`](examples/demo/README.md) est l'application qui se trouve derrière : une page AG Grid qui lit les mêmes commandes dans PostgreSQL ou
MongoDB à travers une API C# construite sur la bibliothèque. Pour l'exécuter vous-même, il faut Docker, le SDK .NET 10 et Node 20.19 ou plus récent. C'est une
vitrine qui installe les paquets publiés depuis nuget.org, comme le ferait un utilisateur de la bibliothèque.

## Compatibilité {#compatibility}

| Version de la spécification | Cible .NET |
|---|---|
| 1.0.0 | net10.0 |

La version de la spécification est celle de [`spec/VERSION`](spec/VERSION) ; chaque paquet l'indique dans son propre README.
La manière dont les versions sont choisies est décrite dans [VERSIONING.md](VERSIONING.md).
Les paquets déclarent des plages de versions pour les bibliothèques qu'ils enveloppent, jamais une version exacte unique.

## Licence {#license}

Apache License 2.0 — voir [LICENSE](LICENSE).
