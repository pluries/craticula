---
translates: strict-and-lenient
title: Strict e Lenient
description: Che cosa fanno le due modalità dello schema con le colonne che lo schema non consente.
source_fingerprint: 20ab3fa199820cb9e052565112f509257cd8428bafaf7eced343e56e4ea4c25a
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Strict e Lenient {#strict-and-lenient}

Questa pagina spiega le due modalità in cui può operare uno schema e che cosa fa ciascuna quando una richiesta nomina una colonna che lo schema non consente. È destinata a uno sviluppatore che sta scrivendo uno schema e deve scegliere una modalità.

In breve: usare Strict, salvo ragioni contrarie. Strict è il valore predefinito.

## Dove si imposta la modalità {#where-you-set-the-mode}

La modalità è un'impostazione dello schema, con i valori `strict` e `lenient`.

```json
{
  "mode": "strict",
  "source": "orders",
  "stableKey": "id",
  "fields": { }
}
```

In C#, `GridSchema.Mode` ha come valore predefinito `Strict`. Lo schema JSON del file indica `mode` come obbligatorio, quindi va scritto esplicitamente nel file dello schema.

## Strict {#strict}

In modalità Strict, un filtro su una colonna che lo schema non elenca viene rifiutato. Craticula lancia una `UnknownFieldException` che nomina ogni colonna rifiutata. Non viene prodotta alcuna query.

Lo stesso accade per una colonna che lo schema elenca ma contrassegna con `filterable: false`. Craticula la tratta come una colonna sconosciuta.

Le fixture avversariali lo mostrano. Un filtro, un ordinamento e un raggruppamento di righe su una colonna sconosciuta vengono tutti rifiutati. Il filtro e il raggruppamento lanciano `UnknownFieldException`; l'ordinamento è rifiutato dal compilatore (vedere l'ultimo punto più sotto). Lo stesso vale per un nome di colonna composto da SQL, come `amount'); DROP TABLE users; --`.

## Lenient {#lenient}

In modalità Lenient, Craticula scarta una condizione di filtro su una colonna sconosciuta o non filtrabile e prosegue con il resto.

Scartare una condizione rende la risposta più ampia. La griglia può ricevere più righe di quelle richieste. Scegliere Lenient solo se si accetta questa conseguenza.

Alcuni dettagli su come viene rimossa una condizione scartata:

- Un gruppo AND o OR che perde tutte le sue condizioni scompare.
- Un gruppo rimasto con una sola condizione diventa quella condizione.
- Un NOT la cui condizione scompare scompare a sua volta. Non diventa "corrispondi a tutto" né "non corrispondere a nulla".

## Ciò che nessuna modalità attenua {#what-no-mode-relaxes}

Lenient perdona soltanto una condizione di filtro. La specifica stabilisce che tutto ciò che determina la forma della risposta viene rifiutato in ogni modalità:

- una colonna di raggruppamento che non è nello schema o non è contrassegnata come raggruppabile;
- una chiave di gruppo che approfondisce una colonna non filtrabile;
- un'aggregazione su una colonna che non è nello schema o a cui non è consentito usare quella funzione;
- la colonna di una richiesta di valori distinti per un filtro a insieme;
- una colonna di esportazione sconosciuta, non esportabile, ripetuta, oppure un elenco vuoto.

Il motivo è che scartare questi elementi darebbe alla griglia una risposta diversa da quella richiesta, senza alcun errore. Una chiave di gruppo scartata potrebbe restituire le righe di un altro gruppo sotto l'etichetta che la griglia si aspetta.

La modalità non ha effetto nemmeno sugli altri controlli. Una richiesta troppo profonda, troppo ampia, che chiede troppe righe o che contiene un valore non compatibile con il tipo della colonna viene rifiutata in entrambe le modalità. Vedere [Il modello di sicurezza](safety-model.html).

Un ultimo punto: un ordinamento su una colonna che lo schema non elenca viene rifiutato in entrambe le modalità. Il rifiuto proviene dal compilatore, che lancia una propria eccezione di compilazione anziché `UnknownFieldException`; per questo nell'endpoint vanno intercettate entrambe, restituendo un errore client.

## Come scegliere {#how-to-choose}

- Scegliere **Strict** se la griglia è propria e una colonna sconosciuta indica un bug o un attacco. Lo si scopre subito.
- Scegliere **Lenient** solo se si accetta che una richiesta che nomina una colonna sconosciuta o non filtrabile restituisca più righe invece di un errore.

In caso di dubbio, usare Strict.

## Da dove proviene {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridSchemaMode.cs](../../csharp/src/Craticula.Core/Schema/GridSchemaMode.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
