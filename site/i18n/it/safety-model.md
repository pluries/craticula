---
translates: safety-model
title: Il modello di sicurezza
description: Come valori, identificatori e limiti mantengono sicura una query compilata e che cosa resta a carico di chi usa la libreria.
source_fingerprint: cad40472e319059d27fe5a7517ac79ed14efb07866e1630c2883f9c7419a959c
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Il modello di sicurezza {#the-safety-model}

Questa pagina elenca ciò che Craticula fa per impedire che una richiesta ostile danneggi il database e ciò che non fa. È destinata a uno sviluppatore o a un revisore che deve valutare se Craticula si adatta a un sistema esposto al pubblico.

## I valori sono parametri {#values-are-parameters}

Ogni valore della richiesta entra nella query come parametro. Non viene mai incollato nel testo.

Per SQL, l'istruzione contiene segnaposto come `$1` e i valori viaggiano in una lista separata. Per la richiesta della guida rapida, il testo non contiene né "acme" né 100. Vedere [Come una richiesta diventa una query](request-to-query.html).

La specifica applica la stessa idea a MongoDB e OpenSearch. In questi casi i valori entrano nella pipeline o nel documento di query come dati. Un valore di ricerca testuale che contiene caratteri di pattern viene sottoposto a escape. I compilatori dispongono di funzioni di supporto per questo.

Un valore come `'; DROP TABLE users; --` inviato in un normale filtro di testo è soltanto una stringa. Viene confrontato e non fa nient'altro. Le fixture avversariali riguardano la forma della richiesta, non il contenuto delle stringhe.

## Gli identificatori provengono dallo schema {#identifiers-come-from-your-schema}

I nomi di tabella, di collezione e di colonna provengono soltanto dallo schema scritto da chi usa la libreria. La richiesta non ne fornisce mai alcuno.

La richiesta nomina le colonne con il loro id di griglia, ad esempio `customer`. Craticula cerca quell'id nello schema e usa il nome fisico dichiarato. Per SQL, il nome viene racchiuso tra delimitatori secondo il dialetto e un carattere di virgolette all'interno di un nome viene raddoppiato.

## Le colonne sconosciute vengono rifiutate {#unknown-columns-are-refused}

Una colonna che non è nello schema viene rifiutata prima che esista una query. La guida rapida mostra il rifiuto di un filtro su `password`.

Una colonna che non è nello schema non può essere usata per raggruppare, aggregare o ordinare, in nessuna modalità. Un filtro su una colonna di questo tipo viene rifiutato in modalità Strict e scartato in modalità Lenient; vedere [Strict e Lenient](strict-and-lenient.html). Uno schema può anche contrassegnare una colonna come non filtrabile, non raggruppabile o non esportabile.

## L'input malformato viene rifiutato {#malformed-input-is-refused}

L'adattatore e i controlli rifiutano l'input che non riconoscono:

- un operatore di filtro sconosciuto, compreso un errore di battitura o `regex`;
- un valore di filtro inviato come oggetto o array dove è atteso un valore singolo;
- chiavi duplicate nel JSON;
- un valore non compatibile con il tipo della colonna, ad esempio testo in una colonna numerica;
- nomi di output duplicati per le aggregazioni.

Per ciascuno di questi casi esiste una fixture che prevede un rifiuto pulito.

## Limiti di risorse {#resource-limits}

Una richiesta non può chiedere un lavoro illimitato. Questi sono i valori predefiniti in `ResourceLimits`:

| Limite | Valore predefinito |
|---|---|
| Profondità dell'albero dei filtri | 8 |
| Condizioni nell'intero filtro | 64 |
| Valori in una lista in o not-in | 1000 |
| Righe in una pagina | 1000 |
| Righe restituite da una richiesta di valori distinti | al massimo 10000 |
| Righe in una richiesta che non invia una finestra di righe | una pagina predefinita di 100 (tutte le righe solo con un'esportazione o con un flag da attivare) |
| Tempo di query su MongoDB e Search | non impostato; lo si imposta e lo applica il database |

Ciascun limite può essere alzato o abbassato. Nessun limite può essere disattivato, tranne il limite di tempo di query, che è facoltativo e resta non impostato finché non lo si imposta. Zero o un numero negativo viene rifiutato al momento dell'impostazione. Vedere [Limiti](limits.html).

Le fixture verificano ogni limite a un passo oltre il confine e con valori estremi, come una lista di 5000 valori o una pagina di un milione di righe.

## Da che cosa Craticula non protegge {#what-craticula-does-not-protect-against}

- **L'account del database.** Craticula non controlla ciò che l'account può fare. All'account che esegue queste query vanno assegnati i diritti minimi necessari, ad esempio sola lettura su quella sola tabella.
- **L'esecuzione della query.** Craticula non la esegue mai. La gestione delle connessioni, i limiti di costo e il modo di eseguire l'istruzione spettano a chi usa la libreria. Per MongoDB e Search è possibile far portare alla query compilata un limite di tempo (`MaxQueryTimeMs`) applicato dal database; per SQL, impostare un timeout dell'istruzione sulla connessione o sull'account.
- **Chi può usare la griglia.** Autenticazione e accesso per utente sono al di fuori del suo ambito. Lo schema può aggiungere un filtro fisso a ogni query, ma spetta a chi lo usa decidere quale debba essere.
- **Uno schema errato.** Se lo schema elenca una colonna che dovrebbe restare nascosta, Craticula la servirà.
- **Query lente.** Una richiesta entro i limiti può comunque essere lenta se la colonna non ha un indice. Vedere le [indicazioni sugli indici](index-guidance.html).

## Da dove proviene {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
- [csharp/src/Craticula.Core/Schema/ResourceLimits.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimits.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/src/Craticula.Sql/PostgresDialect.cs](../../csharp/src/Craticula.Sql/PostgresDialect.cs)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
