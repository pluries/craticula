---
translates: dialects-and-providers
title: Dialectes et fournisseurs
description: En quoi chaque moteur de base de données diffère pour les guillemets d'identifiants, la pagination, l'ordre des valeurs nulles et la comparaison insensible à la casse.
source_fingerprint: e3cadc85fee286141cd8091c6103e2780064d51e19a1428afa783d8f20b83081
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Dialectes et fournisseurs {#dialects-and-providers}

Cette page énumère les bases de données pour lesquelles Craticula sait écrire des requêtes, en quoi ces requêtes diffèrent et quelles versions sont testées. Elle s'adresse au développeur qui choisit une base de données ou un dialecte, ou qui veut savoir pourquoi la même requête donne un texte différent sur chacune.

## Ce qu'est un dialecte {#what-a-dialect-is}

La même requête signifie la même chose sur chaque backend. Craticula décide une seule fois de ce qu'elle signifie, dans la forme canonique. Puis un écrivain par base de données l'exprime dans le langage de cette base.

Pour SQL, cet écrivain est un dialecte. Une classe de dialecte possède une unique `Instance` partagée, comme `PostgresDialect.Instance`. Vous la passez à `SqlQueryBuilder.Build`. Il y en a cinq :

| Base de données | Classe de dialecte |
|---|---|
| PostgreSQL | `PostgresDialect` |
| SQL Server | `MssqlDialect` |
| MySQL (MariaDB passe par le même dialecte mais n'a jamais été testée) | `MySqlDialect` |
| SQLite | `SqliteDialect` |
| Oracle | `OracleDialect` |

MongoDB et OpenSearch ont leurs propres compilateurs, `MongoPipelineBuilder` et `SearchQueryBuilder`. Ils ne prennent pas de dialecte. Voir [Adaptateurs MongoDB et OpenSearch](search-adapters.html).

## En quoi le SQL diffère {#how-the-sql-differs}

| Base de données | Paramètre substitutif | Guillemets d'identifiants | Pagination |
|---|---|---|---|
| PostgreSQL | `$1`, `$2` | `"name"` | `LIMIT` et `OFFSET` |
| SQL Server | `@p1`, `@p2` | `[name]` | `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` |
| MySQL | `?` | `` `name` `` | `LIMIT` et `OFFSET` |
| SQLite | `?` | `"name"` | `LIMIT` et `OFFSET` |
| Oracle | `:p1`, `:p2` | `"name"` | `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` |

Dans tous les cas, les valeurs sont des paramètres, listés dans l'ordre où apparaissent les paramètres substitutifs. Chaque nom de table et de colonne est entouré de guillemets, et un guillemet à l'intérieur d'un nom est doublé. Voir [Le modèle de sécurité](safety-model.html).

PostgreSQL passe une liste « in » sous la forme d'un seul paramètre tableau. Les autres bases écrivent un paramètre substitutif pour chaque valeur.

## L'ordre des valeurs nulles {#null-ordering}

Craticula indique où se placent les valeurs nulles dans chaque requête, de sorte que l'ordre ne dépend pas de la valeur par défaut de la base de données. La manière de le dire dépend de la base :

- PostgreSQL, SQLite et Oracle disposent de `NULLS FIRST` et `NULLS LAST`. SQLite exige la version 3.30.0 ou ultérieure.
- SQL Server n'a pas de telle syntaxe. La requête trie d'abord sur `CASE WHEN column IS NULL THEN 1 ELSE 0 END`, puis sur la colonne.
- MySQL n'en a pas non plus. La requête trie d'abord sur `ISNULL(column)`, puis sur la colonne.
- MongoDB trie sur un champ auxiliaire qui marque les valeurs nulles, que la requête retire ensuite.
- OpenSearch utilise `"missing": "_first"` ou `"_last"`.

Voir [Pagination et tri](paging-and-sorting.html).

## Comparaison insensible à la casse {#case-insensitive-comparison}

Un champ de texte se compare sans tenir compte de la casse, sauf indication contraire du schéma. Chaque base y parvient à sa façon :

| Base de données | Comment elle ignore la casse |
|---|---|
| PostgreSQL | `COLLATE craticula_ci` sur les comparaisons et les tris, que vous créez une seule fois. `ILIKE` pour `contains`, `startsWith` et `endsWith`. |
| SQL Server | `COLLATE Latin1_General_CI_AS` dans la requête. Un champ sensible à la casse reçoit `Latin1_General_CS_AS`. |
| MySQL | Rien dans la requête. C'est la collation propre à la colonne qui décide. Un champ sensible à la casse exige une colonne `_bin` ou `_as_cs`. |
| SQLite | `COLLATE NOCASE`, qui ne replie que les lettres ASCII. |
| Oracle | `COLLATE BINARY_CI`. Un champ sensible à la casse reçoit `COLLATE BINARY`. |
| MongoDB | Une collation sur l'ensemble de la requête, avec la locale `en` et la force 2. |
| OpenSearch et Elasticsearch | L'option `case_insensitive` sur les requêtes term et wildcard, et un sous-champ normalisé pour les tris et les intervalles. |

Deux cas sont silencieux : un champ sensible à la casse sur MySQL, et les colonnes de regroupement sur SQL Server, MySQL et Oracle. L'instruction s'exécute et renvoie de mauvaises lignes si la collation de la colonne n'est pas celle que suppose Craticula. Les conseils sur les index et les bases listent ce qu'il faut définir pour chacun : [Conseils sur les index et les bases](index-guidance.html).

## Versions {#versions}

Ce sont les versions les plus basses dont ont besoin les requêtes compilées, tirées de la spécification et de la documentation des éditeurs, et non d'une exécution de tests. Seule la colonne des versions testées a été exécutée. L'adaptateur Elasticsearch est documenté pour la version 8.x.

| Base de données | Minimum | Version sur laquelle les tests ont tourné |
|---|---|---|
| PostgreSQL | 12, avec ICU | 16 |
| SQL Server | aucun indiqué | 2022 |
| MySQL | aucun indiqué | 8.4 |
| SQLite | 3.30.0 | non consignée |
| Oracle | 12.2 | Database Free 23ai |
| MongoDB | 4.2 | 7.0 |
| OpenSearch | 1.0 | 2.19 |
| Elasticsearch | 7.10 | 8.17 |

« Aucun indiqué » signifie que le code et la spécification ne fixent aucun plancher, et non que chaque ancienne version a été essayée. MariaDB utilise le dialecte MySQL, mais aucun test ne tourne sur MariaDB.

Les tests exécutent les requêtes compilées sur de vraies bases de données dans des conteneurs. Cette exécution exige Docker et ne fait pas partie de l'exécution rapide des tests ; consultez donc le dépôt pour connaître l'état le plus récent.

## Le statut d'Oracle {#oracles-status}

Oracle est pris en charge comme dialecte testé par la communauté, et non comme dialecte central de la v1. Il est évalué de la même façon que les autres : chaque instruction est comparée à un texte attendu enregistré. La différence tient à la couverture. Il est vérifié sur un ensemble d'exemples plus petit que les quatre autres, 45 au total. Ces 45 exemples tournent aussi sur un vrai serveur Oracle Database Free 23ai.

Oracle 12.2 à 21c n'ont pas été exécutés. Le minimum 12.2 provient de la documentation d'Oracle, et non d'une mesure.

Trois faits propres à Oracle façonnent la sortie :

- **Un texte vide est nul.** Une valeur de texte `""` dans une comparaison correspondrait silencieusement aux mauvaises lignes ; le dialecte Oracle la refuse donc. Utilisez à la place les opérateurs « vide » et « non vide ».
- **Les noms doivent être entre guillemets.** Créez la table et ses colonnes avec des noms entre guillemets qui correspondent exactement au schéma.
- **Réglages de session.** Les formats de date, d'horodatage et de nombre proviennent de la session ; définissez-les donc comme le décrivent les [Conseils sur les index et les bases](index-guidance.html).

## Fournisseurs {#providers}

Un fournisseur désigne ici la bibliothèque qui parle réellement à la base de données. Craticula n'en choisit pas un pour vous.

- Pour SQL, `Craticula.Dapper` exécute n'importe quel dialecte sur une `IDbConnection` ouverte, quel que soit le fournisseur ADO.NET qui l'a créée.
- `Craticula.EntityFrameworkCore` utilise le fournisseur de votre `DbContext`. Il a besoin d'un `EfCoreProviderSemantics` qui décrit votre moteur, et seul celui de SQLite est fourni. Voir [Entity Framework Core et Dapper](relational-adapters.html).
- MongoDB s'exécute par le pilote .NET officiel de MongoDB, et OpenSearch par le client de bas niveau `OpenSearch.Client`.

Le dépôt contient une application de démonstration dans `examples/demo` que vous exécutez vous-même. Elle lit les mêmes commandes synthétiques dans plusieurs de ces bases de données et compare les réponses.

## D'où vient cette page {#where-this-comes-from}

- [csharp/src/Craticula.Sql/README.md](../../csharp/src/Craticula.Sql/README.md)
- [csharp/src/Craticula.Sql/OracleDialect.cs](../../csharp/src/Craticula.Sql/OracleDialect.cs)
- [csharp/src/Craticula.Sql/MssqlDialect.cs](../../csharp/src/Craticula.Sql/MssqlDialect.cs)
- [spec/fixtures/dialect-parity](../../spec/fixtures/dialect-parity/README.md)
- [spec/fixtures/README.md](../../spec/fixtures/README.md)
- [spec/semantics.md](../../spec/semantics.md)
- [csharp/tests/Craticula.Integration.Tests/Sql/SqlEngine.cs](../../csharp/tests/Craticula.Integration.Tests/Sql/SqlEngine.cs)
- [examples/demo/README.md](../../examples/demo/README.md)
- Pages liées : [Conseils sur les index et les bases](index-guidance.html), [Pagination et tri](paging-and-sorting.html), [Le GridSchema](the-gridschema.html)
