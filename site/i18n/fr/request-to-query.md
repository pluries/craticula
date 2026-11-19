---
translates: request-to-query
title: Comment une requête devient une requête
description: Le chemin entre une requête AG Grid et une instruction avec paramètres.
source_fingerprint: 6c0315a52de692dbf39fc149aa86390474630dd3c2eb2282d8985f93da818dc0
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Comment une requête devient une requête {#how-a-request-becomes-a-query}

Cette page suit une requête AG Grid à travers Craticula, étape par étape, jusqu'à ce qu'elle devienne une requête avec paramètres. Elle s'adresse à un développeur qui veut savoir ce qui se passe entre la grille et la base de données, et pourquoi il y a plusieurs étapes.

## Le chemin {#the-path}

```text
request JSON -> adapter -> canonical form -> compiler -> query + parameters
```

1. **JSON de la requête.** La grille l'envoie. Craticula ne modifie pas ce que la grille envoie.
2. **Adaptateur.** L'adaptateur AG Grid lit le JSON et le transforme en forme canonique. Il rejette le JSON qu'il ne comprend pas.
3. **Forme canonique.** Le projet l'appelle l'IR, abréviation d'intermediate representation (représentation intermédiaire). C'est une description unique des filtres, du tri, du regroupement et de la pagination, qui ne dépend ni d'AG Grid ni d'une base de données.
4. **Contrôles.** Avant de compiler, Craticula vérifie la forme canonique par rapport à votre schéma et aux limites de ressources. Il convertit aussi chaque valeur vers le type que le schéma déclare.
5. **Compilateur.** Un compilateur par backend écrit la requête. Le compilateur SQL a un rédacteur par dialecte de base de données.
6. **Requête et paramètres.** Pour SQL, vous obtenez le texte de l'instruction plus une liste de valeurs. Les valeurs ne font jamais partie du texte.

Comme tous les backends lisent la même forme canonique, une même requête signifie la même chose partout. Les règles pour des détails tels que la gestion des valeurs nulles et la sensibilité à la casse sont écrites une seule fois, dans la spécification, et chaque compilateur les suit.

## Le schéma est la frontière {#the-schema-is-the-boundary}

Le schéma est un document JSON que vous écrivez. Il nomme la table ou la collection et les colonnes que la grille peut utiliser. Chaque colonne a un type et un nom physique dans la base de données. Il nomme aussi une clé stable, une colonne aux valeurs uniques que Craticula utilise pour garder la pagination dans un ordre fixe.

Une colonne qui n'est pas dans le schéma ne peut pas atteindre une requête. Voir [Le modèle de sécurité](safety-model.html) pour savoir comment cela fonctionne.

## Ce que la requête peut demander {#what-the-request-can-ask-for}

- **Pagination.** La grille demande une plage de lignes, par exemple les 50 premières. Craticula en fait une limite et un décalage, ou l'équivalent pour votre backend. Une page a une taille maximale.
- **Tri.** Le tri s'exécute dans l'ordre envoyé par la grille. Craticula ajoute la clé stable à la fin pour que les lignes de valeurs égales reviennent toujours dans le même ordre.
- **Filtrage.** Les filtres de texte, de nombre et de date deviennent des comparaisons reliées par AND ou OR. La correspondance insensible à la casse est le comportement par défaut pour le texte.
- **Regroupement.** Pour les grilles groupées, la requête porte les colonnes de groupe, les clés de groupe déjà ouvertes et les agrégations à calculer. Craticula construit la requête groupée pour le niveau demandé.

## Un petit exemple {#a-small-example}

Voici la requête du guide de démarrage rapide. Elle demande les clients contenant "acme" avec un montant supérieur à 100, les montants les plus élevés d'abord, lignes 0 à 50.

```json
{
  "startRow": 0,
  "endRow": 50,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "customer": { "filterType": "text", "type": "contains", "filter": "acme" },
    "amount": { "filterType": "number", "type": "greaterThan", "filter": 100 }
  },
  "sortModel": [ { "colId": "amount", "sort": "desc" } ]
}
```

Pour PostgreSQL, le programme du guide de démarrage rapide affiche cette instruction et ces paramètres :

```sql
SELECT * FROM "orders" WHERE ("customer" ILIKE '%' || $1 || '%' ESCAPE '\' AND "amount" > $2::numeric) ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'acme', '100', 50, 0
```

Regardez ce qui s'est passé :

- "acme" et 100 ne figurent pas dans le texte. Ce sont les paramètres.
- Les noms de table et de colonnes viennent du schéma, pas de la requête.
- Le tri se termine par `id`, la clé stable du schéma.
- La plage de la page est devenue `LIMIT 50 OFFSET 0`.

SQL Server obtient une instruction différente à partir de la même requête, parce qu'il écrit autrement la correspondance insensible à la casse et l'ordre des valeurs nulles. Le [guide de démarrage rapide C#](quickstart-csharp.html) montre les deux.

## Ce que vous écrivez en C# {#what-you-write-in-c}

Dans le guide de démarrage rapide, le code fait quatre choses dans cet ordre :

1. Analyser le schéma avec `GridSchema.Parse`.
2. Analyser la requête avec `AgGridRequestParser.Parse`.
3. Valider avec `GridFilterPipeline.Process`. Cela applique le contrôle des colonnes, les limites et la conversion de type.
4. Compiler avec `SqlQueryBuilder.Build` et un dialecte tel que `PostgresDialect.Instance`.

MongoDB et OpenSearch ont leurs propres constructeurs, `MongoPipelineBuilder` et `SearchQueryBuilder`.

Pour afficher le nombre total de lignes à côté d'une page, chaque compilateur a aussi `BuildCount`. Il utilise le même filtre mais ni tri ni fenêtre de lignes, car un comptage n'en a pas besoin. Donnez un `NonePage` à `GridFilterPipeline.Process` pour un comptage, afin qu'une grande taille de page ne puisse pas le faire échouer.

## D'où cela provient {#where-this-comes-from}

- [site/pages/quickstart-csharp.md](quickstart-csharp.md)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
- [spec/semantics.md](../../spec/semantics.md)
- [spec/ir.schema.json](../../spec/ir.schema.json)
- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs](../../csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs)
- [spec/fixtures/operators](../../spec/fixtures/operators/001-eq-string/description.md)
