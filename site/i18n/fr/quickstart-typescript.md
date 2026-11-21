---
translates: quickstart-typescript
title: TypeScript
description: Ce que suivra un portage TypeScript.
source_fingerprint: 072ec77c552dd32b4086a7e68bb381e3e721e82ea24a817d6929470d27629ac2
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Démarrage rapide : TypeScript {#quickstart-typescript}

**Il n'existe pas encore d'implémentation TypeScript.** Cette page le dit volontairement, pour que vous ne cherchiez pas un paquet qui n'existe pas.

## Pourquoi {#why}

Craticula part de la spécification : les règles et les fixtures de conformité de `spec/` viennent en premier, et chaque
implémentation dans un langage doit réussir les mêmes fixtures. Le portage TypeScript est prévu **après le gel de la spécification** (la
spécification est gelée à la version 1.0). D'ici là, la spécification peut encore changer, et un portage écrit maintenant devrait être réécrit.

Rien n'est publié pour TypeScript : ni paquet, ni commande d'installation.

## Ce que vous pouvez faire aujourd'hui {#what-you-can-do-today}

- Utilisez la bibliothèque C#, qui est l'implémentation de référence : [Démarrage rapide : C#](quickstart-csharp.html).
- Lisez les règles qu'un portage TypeScript devra suivre : [sémantique](semantics.html), et les
  références de schémas ([GridSchema](grid-schema.html), [IR](ir-schema.html)).
- Regardez le test qu'un portage doit réussir : les fixtures de conformité
  (`spec/fixtures`) et le lanceur indépendant du langage décrit dans
  [`spec/conformance-runner.md`](../../spec/conformance-runner.md). Un pilote écrit dans n'importe quel langage répond aux requêtes du lanceur et le
  lanceur note les réponses.
