---
translates: index-guidance
title: Conseils sur les index et les bases de données
description: Les index et les réglages de base de données qui gardent les requêtes compilées rapides et exactes.
source_fingerprint: 3d3bf891b84587e5732e82a2bb52c06b0c2ee549efb1865d1fc2d889fe36ebf5
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Conseils sur les index et les bases de données {#index-and-database-guidance}

Craticula compile des requêtes ; il ne crée jamais de table, d'index ni de collation. Cette page liste, pour chaque base de données, ce que **vous**
devez mettre en place pour que les requêtes compilées renvoient les bonnes lignes et s'exécutent vite. Les règles qui le fondent se trouvent dans la
[sémantique](semantics.html) ; les fixtures par base de données qui figent les énoncés se trouvent dans
[`spec/fixtures/dialect-parity`](../../spec/fixtures/dialect-parity/README.md).

Deux sortes d'obligations apparaissent ci-dessous, et la différence compte :

- **Bruyante :** la base de données rejette l'énoncé (collation absente, serveur trop ancien). Vous le remarquez tout de suite.
- **Silencieuse :** l'énoncé s'exécute et renvoie de mauvaises lignes (une colonne qui ignore la casse alors qu'elle ne devrait pas). Rien ne vous prévient ; ce
  sont donc celles à lire deux fois.

## En un coup d'œil {#at-a-glance}

| Base de données | Ce que vous devez fournir | Si vous ne le faites pas |
|---|---|---|
| PostgreSQL | version 12 ou ultérieure avec ICU ; la collation `craticula_ci` ; `timestamptz` pour les dates-heures | bruyant pour les deux premiers (chaque comparaison insensible à la casse échoue), silencieux pour `timestamp` |
| SQL Server | collation binaire ou sensible à la casse sur les colonnes de regroupement ; `datetime2` contenant de l'UTC | silencieux : `EMEA` et `emea` partagent un groupe |
| MySQL / MariaDB | collation `_bin` ou `_as_cs` sur les colonnes sensibles à la casse et de regroupement ; `DATETIME` contenant de l'UTC | silencieux : la déclaration est ignorée |
| SQLite | version 3.30.0 ou ultérieure ; dates-heures stockées sous la forme `yyyy-MM-ddTHH:mm:ss.fffZ` | bruyant pour la version, silencieux pour le texte de la date-heure |
| Oracle | 12.2 ou ultérieur ; identifiants entre guillemets ; collation binaire sur les colonnes de regroupement (le réglage de session par défaut) | bruyant pour les deux premiers, silencieux pour le dernier |
| MongoDB | serveur 4.2 ou ultérieur | bruyant : le pipeline est rejeté |
| OpenSearch / Elasticsearch | sous-champs `keyword`, un normalizer pour le tri insensible à la casse, un type numérique précis pour les décimaux | silencieux pour un sous-champ `keyword` manquant dans un filtre (aucune ligne ne correspond), bruyant dans un tri ; silencieux pour l'arrondi |

Chaque moteur exige aussi que la **clé stable du schéma soit unique, avec au plus un `NULL`**
([Deterministic paging](semantics.html#sem-6)). La plupart des moteurs laissent une contrainte d'unicité contenir plusieurs `NULL`, ce qui brise la garantie de pagination ; déclarez la
clé `NOT NULL`. Une clé stable textuelle insensible à la casse exige en outre une collation binaire ou sensible à la casse sur MySQL et SQL
Server, faute de quoi deux clés qui ne diffèrent que par la casse sont à égalité.

## Index pour toutes les bases de données {#indexes-for-every-database}

- **Filtres.** Un champ texte se compare sans tenir compte de la casse par défaut ([Case sensitivity](semantics.html#sem-1)). La règle est construite pour qu'un simple
  index sur la colonne reste utilisable pour l'égalité : le compilateur indique une collation sur la comparaison au lieu d'envelopper la
  colonne dans `lower()`. Faites correspondre l'index à cette collation (voir plus bas). Les recherches de sous-chaîne (`contains`, `endsWith`) commencent par un
  caractère générique, qu'aucun index B-tree ordinaire ne sert ; voyez chaque moteur.
- **Tri.** Chaque requête ordonnée se termine par la clé stable du schéma, ascendante avec les valeurs nulles en dernier ([Deterministic paging](semantics.html#sem-6)),
  et Craticula écrit lui-même la position des valeurs nulles ([Null ordering](semantics.html#sem-3)). Un index ne sert le tri que s'il correspond à cet
  ordre exact. Sur PostgreSQL, SQLite et Oracle, l'ordre du démarrage rapide est `amount DESC NULLS FIRST, id ASC NULLS LAST`, donc
  l'index correspondant est `(amount DESC NULLS FIRST, id ASC NULLS LAST)` ; un index simple `(amount, id)` ne correspond pas à un tri descendant.
  Sur SQL Server et MySQL, l'énoncé trie d'abord sur un test de nullité (`CASE WHEN ... IS NULL`, `ISNULL(...)`), qu'aucun index de colonne
  ne sert, et sur MongoDB le tri porte sur des champs auxiliaires calculés. Là, indexez donc vos **filtres** et attendez-vous à ce que le tri
  s'effectue après eux. Vérifiez le plan (`EXPLAIN`) sur vos propres données ; Craticula ne peut pas connaître la taille de vos tables.
- **Pagination.** `OFFSET` devient en général plus lent à mesure que la page est profonde. L'export CSV parcourt le résultat dans l'ordre de la clé et n'utilise pas
  `OFFSET`.

## PostgreSQL {#postgresql}

Exige PostgreSQL 12 ou ultérieur compilé avec ICU (une collation non déterministe). Mise en place unique, dans la base de données qui contient vos tables :

```sql
CREATE COLLATION craticula_ci (provider = icu, locale = 'und-u-ks-level2', deterministic = false);
```

Sans elle, chaque `=`, `IN`, intervalle et `ORDER BY` insensible à la casse échoue avec une collation inconnue
([Case sensitivity](semantics.html#sem-1)).

- **L'égalité et le tri** sur un champ texte insensible à la casse nomment `craticula_ci`. Un index créé avec cette collation
  (`CREATE INDEX ... ON orders (customer COLLATE craticula_ci)`) est celui qui correspond ; confirmez avec `EXPLAIN`.
- **`contains`, `startsWith`, `endsWith`** se compilent en `ILIKE`. Appuyez-les sur un index trigramme : `CREATE EXTENSION pg_trgm;`
  puis `CREATE INDEX ... USING gin (customer gin_trgm_ops);`.
- **Dates :** déclarez les colonnes `datetime` en `timestamptz`. Avec un simple `timestamp`, le serveur compare à travers le fuseau horaire de la session et
  les lignes se décalent sans erreur ([Dates and time zones](semantics.html#sem-4)).
- Les colonnes de regroupement n'ont besoin d'aucune collation : la collation par défaut de PostgreSQL est déterministe, donc `EMEA` et `emea` forment deux groupes, comme
  l'exige [Grouping and drill-down](semantics.html#grp-2).

## SQL Server {#sql-server}

Aucune mise en place de collation pour les filtres : l'énoncé porte `COLLATE Latin1_General_CI_AS` (ou `Latin1_General_CS_AS` pour un champ que vous
avez déclaré sensible à la casse) en ligne, de sorte que ni l'un ni l'autre sens ne dépend de la collation propre à la base de données.

- **Colonnes de regroupement, obligation silencieuse.** Un `GROUP BY` et un forage vers le détail doivent être exacts ([Grouping and drill-down](semantics.html#grp-2)), et l'
  énoncé ne nomme aucune collation à cet endroit. La valeur par défaut habituelle de SQL Server (`SQL_Latin1_General_CP1_CI_AS`) ignore la casse, donc une colonne
  groupée qui l'utilise met `EMEA` et `emea` dans un seul groupe. Déclarez chaque colonne regroupable, ainsi que la clé stable si elle est textuelle,
  avec une collation binaire ou sensible à la casse. La définition de colonne est, par exemple :

  ```sql
  country nvarchar(100) COLLATE Latin1_General_100_BIN2 NULL
  ```

  Les filtres sur cette colonne comparent toujours sans tenir compte de la casse, parce qu'ils indiquent leur propre collation en ligne. Le prix est
  la vitesse : une comparaison qui nomme une collation différente de celle de la colonne ne peut généralement pas faire de recherche dans l'index, donc mesurez un
  filtre insensible à la casse sur une colonne que vous regroupez aussi.
- **Dates.** `datetime2` n'a pas de fuseau horaire. Stockez la lecture UTC ; le compilateur compare directement l'instant UTC à celle-ci,
  et les résultats reviennent en UTC ([Dates and time zones](semantics.html#sem-4)).
- **Entity Framework Core :** réglez `PatternMatchFoldsCase = false` dans la sémantique du fournisseur, sauf si la collation de chaque colonne interrogeable
  ignore la casse ; `true` envoie un `LIKE` nu, qui sur une colonne à collation binaire ne trouve que la casse exacte. Voir le
  [README de l'adaptateur](../../csharp/src/Craticula.EntityFrameworkCore/README.md).

## MySQL et MariaDB {#mysql-and-mariadb}

Là, la sensibilité à la casse relève de la collation **de la colonne**, qu'un énoncé ne peut pas remplacer de façon portable.

- **Les champs insensibles à la casse** (le défaut) fonctionnent sur toute colonne `_ci`, comme `utf8mb4_0900_ai_ci`, et un simple index sur la
  colonne sert l'égalité sur eux (pas une recherche de sous-chaîne, qui commence par un caractère générique).
- **Champs sensibles à la casse, obligation silencieuse.** Un champ déclaré `caseSensitivity: "sensitive"` exige une collation de colonne `_bin` ou `_as_cs`
  (`utf8mb4_bin`, `utf8mb4_0900_as_cs`). Sur une colonne `_ci`, la déclaration n'a aucun effet et les comparaisons restent
  insensibles à la casse ; l'énoncé compilé ne vous le dit pas.
- **Les colonnes de regroupement** exigent la même collation binaire ou `_as_cs` pour des groupes exacts ([Grouping and drill-down](semantics.html#grp-2)) :

  ```sql
  country varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin
  ```

  Une colonne n'a qu'une collation ; une colonne regroupable rendue binaire rend donc aussi les filtres et préfixes insensibles à la casse sur cette
  même colonne sensibles à la casse, silencieusement (la divergence acceptée n° 4 de GRP-2). Si vous avez besoin des deux sur un champ, décidez ce qui compte le
  plus ; le compilateur ne peut pas vous donner les deux à partir d'une seule colonne.
- **Entity Framework Core :** comme pour SQL Server, réglez `PatternMatchFoldsCase = false` sauf si la collation de chaque colonne interrogeable ignore la casse.
- **Dates.** `DATETIME` n'a pas de fuseau horaire : stockez de l'UTC. Si vous utilisez MySqlConnector, laissez `DateTimeKind` à sa valeur par défaut ou réglez-le sur UTC ;
  `Local` ne fait qu'étiqueter la valeur et décalerait chaque instant du décalage du serveur ([Dates and time zones](semantics.html#sem-4)).

## SQLite {#sqlite}

- **Version 3.30.0 ou ultérieure**, pour `NULLS FIRST` / `NULLS LAST`. Une bibliothèque plus ancienne rejette l'énoncé.
- **Les champs insensibles à la casse** utilisent `COLLATE NOCASE`, qui ne remplace que les lettres ASCII (`É` et `é` restent différents). Un index
  déclaré `(customer COLLATE NOCASE)` les sert.
- **Dates-heures, obligation silencieuse.** SQLite n'a pas de type d'horodatage et compare le texte caractère par caractère. Stockez chaque
  `datetime` exactement sous la forme `yyyy-MM-ddTHH:mm:ss.fffZ`, en UTC, avec trois chiffres de fraction ([Dates and time zones](semantics.html#sem-4)). Une autre
  largeur (`...:00Z`, `yyyy-MM-dd HH:mm:ss`) renvoie de mauvaises lignes sans erreur.
- **Entity Framework Core** lie un `DateTime` sous sa propre forme `yyyy-MM-dd HH:mm:ss` ; faites donc correspondre chaque date-heure au texte
  stocké, dans les deux sens, dans votre `DbContext`. Sans ce mappage, un `eq` ne trouve rien, une borne d'intervalle compte toute la date comme postérieure et
  un export trié par date-heure peut répéter des lignes. Le
  [README de l'adaptateur](../../csharp/src/Craticula.EntityFrameworkCore/README.md) donne
  les détails.

## Oracle {#oracle}

- **Serveur 12.2 ou ultérieur.** Les énoncés utilisent `COLLATE BINARY_CI` et `COLLATE BINARY` ; un serveur plus ancien les rejette.
  Oracle documente `COMPATIBLE >= 12.2` et `MAX_STRING_SIZE = EXTENDED` comme prérequis de la collation liée aux données.
- **Ce qui a été vérifié.** Les énoncés compilés ont été exécutés sur Oracle Database Free 23.26.3 dans un conteneur
  (`gvenzl/oracle-free:23.26.3-slim-faststart`, `COMPATIBLE = 23.6.0`, `MAX_STRING_SIZE = STANDARD`) : les 45 fixtures Oracle
  renvoient les lignes attendues, et la propriété de parité entre backends réussit avec Oracle parmi huit moteurs. Sur ce serveur,
  l'opérateur `COLLATE` à l'intérieur d'un énoncé fonctionne sans `EXTENDED` ; seule la **déclaration** d'une collation sur une colonne échoue
  (`ORA-43929`). Oracle 12.2 à 21c n'ont **pas** été testés : le plancher ci-dessus vient de la documentation d'Oracle, pas d'une mesure.
- **Identifiants entre guillemets.** Créez la table et chaque colonne avec des noms entre guillemets qui correspondent exactement à l'orthographe de `source` et `column`
  du schéma. Oracle met en majuscules un nom sans guillemets, et l'énoncé compilé met chaque identifiant entre guillemets
  (`ORA-00942` s'ils diffèrent).
- **Réglages de session.** Les énoncés compilés passent les dates, les dates-heures et les décimaux sous forme de texte et n'ajoutent aucune conversion ; Oracle les convertit donc
  selon les réglages de la session. Réglez `NLS_DATE_FORMAT = 'YYYY-MM-DD'`,
  `NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD"T"HH24:MI:SS.FF"Z"'` et `NLS_NUMERIC_CHARACTERS = '.,'` sur la connexion ; sans eux,
  chaque filtre de date, de date-heure ou de décimal échoue (`ORA-01861`, `ORA-01722`), et une culture cliente à virgule décimale peut ne le provoquer
  que sur certaines machines.
- **Colonnes de regroupement, obligation silencieuse.** Exécutez la session avec `NLS_COMP = BINARY` et `NLS_SORT = BINARY` (les valeurs par défaut d'un client anglais ; la configuration vérifiée), ou, sur un
  serveur avec `MAX_STRING_SIZE = EXTENDED`, déclarez chaque colonne regroupable et la clé stable avec `COLLATE BINARY`. La collation
  par défaut suit la session et peut ignorer la casse. La définition de colonne est, par exemple :

  ```sql
  "country" VARCHAR2(100) COLLATE BINARY
  ```

## MongoDB {#mongodb}

- **Serveur 4.2 ou ultérieur**, pour l'étape `$unset` que chaque pipeline trié utilise afin de supprimer ses champs auxiliaires de position des valeurs nulles.
- **Les champs insensibles à la casse** se compilent en une collation au niveau de la requête (`locale: "en"`, `strength: 2`). Un index ne sert une requête avec collation
  que s'il a été créé avec la même collation : `createIndex({ customer: 1 }, { collation: { locale: "en", strength: 2 } })`.
- **`contains`, `startsWith`, `endsWith`** se compilent en un `$regex` échappé (MongoDB n'a pas d'opérateur de sous-chaîne compatible avec les collations). Une expression régulière n'utilise pas un index
  sensible à la collation comme le fait une égalité ; attendez-vous donc à un parcours complet sur une grande collection et
  mesurez.
- **Tri.** Le tri porte sur des champs auxiliaires calculés qui contiennent la position des valeurs nulles, de sorte qu'aucun index ne le sert dans son ensemble ; indexez vos
  filtres ([Null ordering](semantics.html#sem-3)).
- **Les requêtes de regroupement comparent en respectant la casse.** MongoDB n'a qu'une collation par requête. Une requête de regroupement doit garder ses
  groupes exacts ; son pipeline ne porte donc aucune collation et un filtre utilisateur dans la même requête compare en respectant la casse
  (la divergence acceptée n° 3 de GRP-2). Les autres bases de données ignorent la casse dans ce filtre.

## OpenSearch et Elasticsearch {#opensearch-and-elasticsearch}

Un seul compilateur sert les deux. Le mappage d'index est le vôtre, et les requêtes compilées nomment les sous-champs que votre schéma déclare.

- **Version :** Elasticsearch 7.10 ou ultérieur, OpenSearch 1.0 ou ultérieur (pour `case_insensitive` sur `term` et `wildcard`).
- **Sous-champ `keyword`, silencieux dans un filtre.** Chaque champ texte filtré, trié ou regroupé exige le sous-champ `keyword`
  que vous avez déclaré comme `physical.search.keywordSubField`, un multi-champ dans le mappage d'index. S'il manque, un filtre dessus
  ne trouve **aucune ligne** sans erreur ; seul un tri dessus échoue.
- **Tri et intervalle insensibles à la casse.** Déclarez `physical.search.normalizedSubField` et mappez-le comme un `keyword` avec un
  `normalizer` qui ignore la casse. Cela coûte de l'espace d'index et c'est le seul moyen de trier ou de comparer un champ texte sans tenir compte de la casse ; le compilateur
  refuse de compiler une telle requête pour un champ qui n'en déclare pas.
- **Décimaux.** Mappez un champ `decimal` comme `scaled_float` avec un `scaling_factor` suffisant, ou comme `keyword` si vous ne le comparez que pour
  l'égalité. Un mappage `double` arrondit silencieusement.
- **Pagination profonde et totaux.** Au-delà de `max_result_window` (10,000 lignes), le client pagine avec un point-in-time et `search_after` ;
  réglez `Flavour` sur `Elasticsearch` **à la fois** dans les options de pagination profonde et dans les options d'export pour Elasticsearch, sinon chaque export
  échoue avec une erreur HTTP 400. Le nombre total de lignes au-delà de 10,000 est signalé comme inconnu, sauf si
  vous choisissez le décompte exact, qui compte chaque correspondance à chaque première requête.
- **`contains`** est un caractère générique sur le champ `keyword` ; un caractère générique en tête parcourt le dictionnaire de termes, donc mesurez-le sur de grands index.

## Ce que cette page ne couvre pas {#what-stays-out-of-this-page}

Le réglage propre à chaque moteur (partitions, index couvrants, nombre de shards) dépend de vos données et de votre charge. Les énoncés compilés se trouvent dans
les [fixtures de conformité](../../spec/fixtures/), un dossier par cas, avec le
texte exact que reçoit chaque base de données ; exécutez `EXPLAIN` dessus sur vos propres tables.
