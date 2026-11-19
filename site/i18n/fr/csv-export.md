---
translates: csv-export
title: Export CSV
description: Diffusez les lignes d'une grille vers un fichier CSV avec le même modèle de requête et les mêmes contrôles.
source_fingerprint: fa1523a098455aba885855279c19504be3084b49be415b2a066c79e11c573ace
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Export CSV {#csv-export}

Cette page explique comment Craticula exporte les lignes qu'affiche une grille sous forme de fichier CSV ou TSV : ce qui relève de Craticula, ce qui relève de vous, et les réglages qui modifient le fichier. Elle s'adresse au développeur qui ajoute un bouton d'export à une grille reposant sur Craticula.

## Deux parties, un flux entre elles {#two-parts-one-stream-between-them}

Un export se fait en deux étapes, et deux éléments de Craticula les prennent en charge.

1. **Lire les lignes.** Un adaptateur d'exécution lance la requête et renvoie un flux de lignes. `DapperExportStream`, `EfCoreExportStream`, `MongoExportStream` et `OpenSearchExportStream` s'en chargent pour leurs backends respectifs. Voir [Entity Framework Core et Dapper](relational-adapters.html) et [Adaptateurs MongoDB et OpenSearch](search-adapters.html).
2. **Écrire le fichier.** Le paquet `Craticula.Export.Csv` prend ce flux et écrit les octets. Il ne sait rien de la base de données. `CsvWriter` en est le point d'entrée.

Comme l'écrivain lit une ligne à la fois et écrit chaque enregistrement au fur et à mesure, un export d'un million de lignes consomme à peu près la même mémoire qu'un export de dix lignes. Les adaptateurs relationnels et OpenSearch lisent les lignes par blocs (5,000 par défaut) et l'adaptateur MongoDB lit un seul curseur lot après lot, jamais avec un décalage croissant, et les appels paginés `FetchPageAsync` refusent une requête portant sur toutes les lignes afin que seul le flux d'export puisse lire le résultat complet. Un téléchargement lent ralentit la lecture au lieu de remplir la mémoire.

## Ce que la grille envoie {#what-the-grid-sends}

Une requête d'export est une requête de grille ordinaire accompagnée d'un maximum de trois membres supplémentaires :

- `exportFormat`, soit `"csv"`, soit `"tsv"`. Il marque la requête comme un export. Envoyer les deux autres membres sans lui est refusé.
- `exportScope`, soit `"all"`, soit `"page"`. La valeur par défaut est `"all"` : toutes les lignes qui correspondent au filtre et au tri, quoi que disent `startRow` et `endRow`. `"page"` conserve la plage de lignes de la requête. Une requête qui n'envoie aucune fenêtre et qui n'est pas un export reçoit à la place une page par défaut de 100 lignes ; voir [Pagination et tri](paging-and-sorting.html).
- `exportColumns`, une liste facultative d'entrées `{ "colId": "...", "header": "..." }`.

Le filtre et le tri sont toujours respectés.

## Quelles colonnes, et ce que disent les en-têtes {#which-columns-and-what-the-headers-say}

Si la requête n'a pas de `exportColumns`, l'export comprend toutes les colonnes que le schéma marque comme `exportable`, dans l'ordre où le schéma les déclare. Une colonne est exportable sauf si le schéma indique `"exportable": false`.

Si la requête a `exportColumns`, l'export comprend ces colonnes, dans cet ordre. Une colonne absente du schéma, non exportable ou citée deux fois, ainsi qu'une liste vide, sont refusées. Cela vaut en mode Strict comme en mode Lenient.

L'en-tête d'une colonne provient, dans l'ordre :

1. du `header` de la requête ;
2. du `label` du schéma ;
3. de l'identifiant de la colonne.

L'analyseur détermine cela une seule fois et le place dans `ExportSpec.Columns`.

## Le regroupement est abandonné {#grouping-is-dropped}

Un export est une liste de lignes à plat. L'adaptateur retire `rowGroupCols`, `valueCols` et `groupKeys` d'une requête d'export ; l'export d'une grille groupée renvoie donc des lignes simples sous le filtre et le tri courants.

## Mise en pratique {#putting-it-together}

L'analyseur a besoin du schéma pour résoudre un export ; passez-le donc dans `AgGridParseOptions`. Cet exemple traite `exportScope` défini à `"all"`. Pour `"page"`, `parsed.Page` est une plage de lignes et `StreamAsync` la refuse. Il utilise Dapper et PostgreSQL. `connection` est une `IDbConnection` ouverte et `destination` est un `Stream`, comme le corps de la réponse HTTP.

```csharp
// using Craticula.AgGrid; using Craticula.Core.Export; using Craticula.Core.Ir;
// using Craticula.Core.Schema; using Craticula.Dapper; using Craticula.Export.Csv; using Craticula.Sql;
AgGridParsedRequest parsed = AgGridRequestParser.Parse(requestJson, new AgGridParseOptions { Schema = schema });
ExportSpec export = parsed.Export!;

FilterNode? filter = GridFilterPipeline.Process(
    parsed.NativeFilter, parsed.CustomFilters, parsed.Page, schema, new ResourceLimits());

IAsyncEnumerable<ExportRow> rows = DapperExportStream.StreamAsync(
    connection,
    new SqlQueryRequest
    {
        Schema = schema,
        Filter = filter,
        Sort = parsed.Sort,
        Page = parsed.Page,
        Projection = export.ProjectionColumns
    },
    PostgresDialect.Instance);

long rowsWritten = await CsvWriter.WriteAsync(
    rows, export.Columns, CsvWriterOptions.ForFormat(export.Format), destination);
```

`CsvWriterOptions.ForFormat` est le moyen par lequel le format demandé parvient au fichier. Il choisit une virgule pour le CSV et une tabulation pour le TSV. L'écrivain ne voit jamais la requête : il ne peut donc pas le faire lui-même. Le résultat de la tâche est le nombre de lignes de données écrites, sans compter la ligne d'en-tête.

Les flux d'export des adaptateurs n'acceptent que le résultat complet (`exportScope` défini à `"all"`). Un export limité à une page est un seul bloc borné, la même requête qu'exécute un bloc de grille. Récupérez-le avec la méthode de page de l'adaptateur et écrivez vous-même ces lignes.

## À quoi ressemble le fichier {#what-the-file-looks-like}

Par défaut :

- une ligne d'en-tête vient en premier ;
- les champs sont séparés par une virgule, et les lignes se terminent par un retour chariot et un saut de ligne ;
- un champ qui contient le séparateur, un guillemet double ou un saut de ligne est entouré de guillemets doubles ;
- le fichier commence par une marque d'ordre des octets, car Excel interprète mal le texte Unicode qui n'en comporte pas ;
- une valeur nulle devient un champ vide ;
- les booléens sont `true` et `false` ;
- les dates sont écrites `2026-01-05`, et les valeurs de date et heure `2026-01-05T14:30:45`, avec le décalage lorsque la valeur en possède un ;
- un décimal conserve son propre nombre de chiffres après la virgule.

## Ce que vous pouvez modifier {#what-you-can-change}

`CsvWriterOptions` comporte ces réglages :

| Réglage | Valeur par défaut | Effet |
|---|---|---|
| `Delimiter` | `,` | Le séparateur de champs. |
| `IncludeHeaderRow` | `true` | Écrire ou non la ligne d'en-tête. |
| `WriteByteOrderMark` | `true` | Commencer ou non le fichier par une marque d'ordre des octets. |
| `DecimalSeparator` | `.` | Le séparateur des nombres fractionnaires. |
| `HardenFormulaInjection` | `true` | Voir ci-dessous. |

`CsvWriterOptions.SemicolonPreset` fixe le séparateur à un point-virgule, pour les paramètres régionaux où Excel en attend un.

Le schéma peut remplacer le format d'une seule colonne avec un bloc `format` :

```json
"orderDate": { "type": "date", "format": { "datePattern": "dd/MM/yyyy" } },
"amount": { "type": "decimal", "format": { "decimalSeparator": "," } }
```

L'écrivain refuse un séparateur décimal identique au séparateur de champs. Une virgule aux deux endroits transformerait chaque nombre fractionnaire en texte entre guillemets. Il refuse aussi un motif de date qu'il ne peut pas appliquer. `GridSchema.Parse` vérifie le motif au chargement du schéma : un motif invalide échoue donc au démarrage et non au milieu d'un téléchargement.

## Protection contre les formules de tableur {#protection-against-spreadsheet-formulas}

Un tableur traite comme une formule une cellule qui commence par `=`, `+`, `-`, `@`, une tabulation ou un retour chariot. Une valeur saisie par un utilisateur peut alors s'exécuter dans le tableur de celui qui ouvre l'export.

Par défaut, l'écrivain place une apostrophe devant un tel texte. Cela couvre chaque en-tête et chaque cellule de texte. Il ne touche pas aux nombres, dates ou booléens que l'écrivain a lui-même formatés : un nombre négatif reste donc un nombre.

Vous pouvez le désactiver avec `HardenFormulaInjection = false`. L'apostrophe ne peut plus être retirée ensuite : ne le désactivez donc que lorsqu'un programme lit le fichier et qu'aucune personne ne l'ouvre dans un tableur.

## Ce qui reste à votre charge {#what-stays-with-you}

- **Le plafond de lignes.** Ni les adaptateurs ni l'écrivain n'imposent un nombre maximal de lignes exportées. Ajoutez votre propre limite si l'export est public.
- **La limite de taille de page.** Elle ne s'applique pas à un export du résultat complet (`exportScope` défini à `"all"`), qui n'a pas de page. Un export limité à une page conserve sa plage de lignes, et la limite de taille de page s'y applique. Voir [Limites](limits.html).
- **Dapper refuse certains exports.** `DapperExportStream` refuse un schéma dont la clé stable est une colonne de texte, ainsi qu'un export où une clé de tri textuelle contient une chaîne vide dans les lignes exportées (sur tous les dialectes sauf Oracle). Utilisez une clé stable numérique ou de date, ou récupérez les données page par page avec `DapperGridQuery.FetchPageAsync`. `EfCoreExportStream` n'a pas de telle vérification.
- **Le téléchargement.** Le type de contenu, le nom du fichier et la connexion vous appartiennent. La démo les définit dans `examples/demo/Api/Routes/GridRoutes.cs`.
- **La liste des colonnes OpenSearch.** L'export OpenSearch écrit toujours chaque colonne du schéma, dans l'ordre de `schema.FieldOrder`. Passez à `CsvWriter` la liste complète, un `ExportColumn` par champ de `schema.FieldOrder`. Un `export.Columns` plus étroit fait échouer `CsvWriter` avec une `CsvWriterException`, car le nombre de cellules ne correspond pas.

## D'où vient cette page {#where-this-comes-from}

- [csharp/src/Craticula.Export.Csv/README.md](../../csharp/src/Craticula.Export.Csv/README.md)
- [csharp/src/Craticula.Export.Csv/CsvWriter.cs](../../csharp/src/Craticula.Export.Csv/CsvWriter.cs)
- [csharp/src/Craticula.Export.Csv/CsvWriterOptions.cs](../../csharp/src/Craticula.Export.Csv/CsvWriterOptions.cs)
- [csharp/src/Craticula.AgGrid/ExportSpec.cs](../../csharp/src/Craticula.AgGrid/ExportSpec.cs)
- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/page-export](../../spec/fixtures/page-export/README.md)
- [examples/demo/Api/Routes/GridRoutes.cs](../../examples/demo/Api/Routes/GridRoutes.cs)
- Pages liées : [Pagination et tri](paging-and-sorting.html), [Le GridSchema](the-gridschema.html), [Modèle de sécurité](safety-model.html)
