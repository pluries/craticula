---
translates: claude-skill
title: Claude-Skill
description: Was der Craticula-Skill für Claude ist, wie Sie ihn installieren und was er tut und nicht tut.
source_fingerprint: 63b1738da63b9355a6d5c64ab072a81d4f2fa969df1e3817fc06403b6cb6dba0
drafter: claude
drafted_on: 2026-11-22
status: approved
---
# Claude-Skill {#claude-skill}

Craticula hat einen Skill für Claude. Ein Skill ist ein Ordner mit Klartext-Anweisungen, die Claude liest, bevor es Ihnen hilft. Dieser bringt Claude bei, wie man Craticula in ein C#-Projekt einbindet.

Um ihn zu nutzen, installieren Sie ihn mit den beiden Befehlen unten oder kopieren Sie seinen Ordner von Hand. Bitten Sie dann Claude, Craticula in Ihr Projekt einzubinden. Wenn Sie fertig sind, lesen Sie [Das Sicherheitsmodell](safety-model.html), um zu sehen, was Craticula schützt.

## Zwei Wege zur Installation {#two-ways-to-install}

Der erste Weg ist ein Claude-Code-Plugin. Führen Sie beide Befehle in einem Terminal aus:

```text
claude plugin marketplace add pluries/craticula
claude plugin install craticula@craticula
```

Der erste Befehl fügt den Craticula-Marketplace aus dem Repository hinzu. Der zweite installiert daraus den Skill. Die Befehle sind in jeder Sprache dieser Website dieselben.

Der zweite Weg ist eine Kopie. Nehmen Sie den Ordner `skills/craticula` aus dem [Craticula-Repository](https://github.com/pluries/craticula) und legen Sie ihn in `~/.claude/skills/craticula/` ab. Das ist Ihr persönlicher Skills-Ordner, der Skill funktioniert also in jedem Projekt, das Sie öffnen. Um ihn nur in einem Projekt zu verwenden, legen Sie den Ordner stattdessen in den eigenen Skills-Ordner dieses Projekts.

## Was der Skill tut {#what-the-skill-does}

- Er sagt Claude, welche Craticula-Pakete Ihr Projekt braucht.
- Er zeigt, wie man ein Schema deklariert, die Grid-Anfrage parst und sie zu einer Abfrage kompiliert.
- Er behandelt die Adapter, die Abfragen ausführen, als optional.
- Er verweist Claude auf dieselben Fakten wie diese Website, damit beide nicht auseinanderlaufen.

Der Skill hält sich an die Sicherheitsregeln und Limits der Bibliothek. Siehe [Das Sicherheitsmodell](safety-model.html) und [Limits](limits.html).

## Was er nicht tut {#what-it-does-not-do}

Der Skill ist Text. Er kann keinen Code ausführen, keine Verbindung öffnen und keine Datei ändern. Claude nimmt jede Änderung an Ihrem Projekt in Ihrer eigenen Sitzung vor, unter Ihren eigenen Berechtigungseinstellungen.

Der Skill nennt keine Version. Er weist Claude an, das neueste Paket auf nuget.org zu verwenden oder die Version, die Ihr Projekt bereits nutzt.

## Sprachen {#languages}

Der Skill deckt die C#-Bibliothek ab, die Referenzimplementierung. Eine Implementierung in TypeScript, Python oder Go gibt es noch nicht. Ihre Schnellstartseiten sagen das auch: [Python](quickstart-python.html), [Go](quickstart-go.html) und [TypeScript](quickstart-typescript.html). Der Skill bietet stattdessen die C#-Bibliothek an.

## Welche Kopie offiziell ist {#which-copy-is-official}

Die offizielle Kopie ist der Ordner `skills/craticula` im [Craticula-Repository](https://github.com/pluries/craticula). Releases der Pakete tragen Tags, die mit `dotnet-v` beginnen. Melden Sie ein Sicherheitsproblem so, wie [SECURITY.md](https://github.com/pluries/craticula/blob/main/SECURITY.md) es beschreibt.

Ein Fork oder eine Kopie von anderer Stelle hat nichts von dieser Herkunft. Vergleichen Sie sie mit dem Repository, bevor Sie sich darauf verlassen.

## Was Sie von Claude erwarten können {#what-to-expect-from-claude}

Das Verhalten eines Agenten ist nicht garantiert: Der Skill ist Text, und der Nachweis, dass ein Agent zu einem funktionierenden Lauf kommt, ist eine manuelle Demonstration, kein automatisierter Test.

Lesen Sie den Code, den Claude schreibt, bevor Sie ihn ausführen, wie bei jedem Code.

## Weiterführende Lektüre {#further-reading}

- [Dialekte und Provider](dialects-and-providers.html) sagt, für welche Datenbanken Craticula kompiliert und wie sie sich unterscheiden.
- [Limits](limits.html) listet die Obergrenzen für Größe und Komplexität einer Anfrage auf.
- [Das Sicherheitsmodell](safety-model.html) listet auf, was Craticula schützt und was nicht.
- [Der C#-Schnellstart](quickstart-csharp.html) zeigt dieselben Schritte von Hand.
