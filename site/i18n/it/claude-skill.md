---
translates: claude-skill
title: Skill per Claude
description: Una skill per Claude che insegna come aggiungere Craticula a un progetto C#, come installarla e che cosa aspettarsi.
source_fingerprint: 63b1738da63b9355a6d5c64ab072a81d4f2fa969df1e3817fc06403b6cb6dba0
drafter: claude
drafted_on: 2026-11-22
status: approved
---
# Skill per Claude {#claude-skill}

Craticula ha una skill per Claude. Una skill è una cartella di istruzioni in testo semplice che Claude legge prima di aiutarti. Questa insegna a Claude come aggiungere Craticula a un progetto C#.

Per usarla, installala con i due comandi qui sotto oppure copia la sua cartella a mano. Poi chiedi a Claude di aggiungere Craticula al tuo progetto. Quando hai finito, leggi [Il modello di sicurezza](safety-model.html) per vedere che cosa protegge Craticula.

## Due modi per installare {#two-ways-to-install}

Il primo modo è un plugin di Claude Code. Esegui entrambi i comandi in un terminale:

```text
claude plugin marketplace add pluries/craticula
claude plugin install craticula@craticula
```

Il primo comando aggiunge il marketplace di Craticula dal repository. Il secondo installa da esso la skill. I comandi sono gli stessi in ogni lingua di questo sito.

Il secondo modo è una copia. Prendi la cartella `skills/craticula` dal [repository di Craticula](https://github.com/pluries/craticula) e mettila in `~/.claude/skills/craticula/`. È la tua cartella personale delle skill, quindi la skill funziona in ogni progetto che apri. Per usarla in un solo progetto, metti invece la cartella nella cartella delle skill di quel progetto.

## Che cosa fa la skill {#what-the-skill-does}

- Dice a Claude di quali pacchetti Craticula ha bisogno il tuo progetto.
- Mostra come dichiarare uno schema, analizzare la richiesta della griglia e compilarla in una query.
- Tratta come opzionali gli adattatori che eseguono le query.
- Indirizza Claude verso gli stessi fatti di questo sito, in modo che i due non divergano.

La skill rispetta le regole di sicurezza e i limiti della libreria. Vedi [Il modello di sicurezza](safety-model.html) e [Limiti](limits.html).

## Che cosa non fa {#what-it-does-not-do}

La skill è testo. Non può eseguire codice, aprire una connessione né modificare un file. Claude apporta ogni modifica al tuo progetto nella tua sessione, con le tue impostazioni di autorizzazione.

La skill non indica una versione. Dice a Claude di usare l'ultimo pacchetto su nuget.org, oppure la versione che il tuo progetto usa già.

## Lingue {#languages}

La skill copre la libreria C#, che è l'implementazione di riferimento. Non esiste ancora alcuna implementazione in TypeScript, Python o Go. Le loro pagine di guida rapida lo dicono: [Python](quickstart-python.html), [Go](quickstart-go.html) e [TypeScript](quickstart-typescript.html). La skill propone invece la libreria C#.

## Quale copia è quella ufficiale {#which-copy-is-official}

La copia ufficiale è la cartella `skills/craticula` nel [repository di Craticula](https://github.com/pluries/craticula). Le release dei pacchetti portano tag che iniziano con `dotnet-v`. Segnala un problema di sicurezza come descrive [SECURITY.md](https://github.com/pluries/craticula/blob/main/SECURITY.md).

Un fork, o una copia presa altrove, non ha nulla di questa provenienza. Confrontalo con il repository prima di fare affidamento su di esso.

## Che cosa aspettarsi da Claude {#what-to-expect-from-claude}

Il comportamento di un agente non è garantito: la skill è testo, e la prova che un agente arrivi a un'esecuzione funzionante è una dimostrazione manuale, non un test automatizzato.

Leggi il codice che Claude scrive prima di eseguirlo, come faresti con qualsiasi codice.

## Approfondimenti {#further-reading}

- [Dialetti e provider](dialects-and-providers.html) indica per quali database Craticula compila e in che cosa differiscono.
- [Limiti](limits.html) elenca i tetti alla dimensione e alla complessità della richiesta.
- [Il modello di sicurezza](safety-model.html) elenca che cosa Craticula protegge e che cosa no.
- [La guida rapida C#](quickstart-csharp.html) mostra gli stessi passaggi a mano.
