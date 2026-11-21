---
translates: csv-export
title: Esportazione CSV
description: Trasmettere in streaming le righe di una griglia in CSV con lo stesso modello di richiesta e gli stessi controlli.
source_fingerprint: fa1523a098455aba885855279c19504be3084b49be415b2a066c79e11c573ace
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Esportazione CSV {#csv-export}

Questa pagina descrive come Craticula esporta le righe mostrate da una griglia come file CSV o TSV: quale parte spetta a Craticula, quale spetta allo sviluppatore e quali impostazioni modificano il file. È rivolta allo sviluppatore che aggiunge un pulsante di esportazione a una griglia basata su Craticula.

## Due parti, un flusso tra loro {#two-parts-one-stream-between-them}

Un'esportazione si svolge in due passaggi, eseguiti da due componenti di Craticula.

1. **Lettura delle righe.** Un adattatore di esecuzione esegue la query e restituisce un flusso di righe. `DapperExportStream`, `EfCoreExportStream`, `MongoExportStream` e `OpenSearchExportStream` svolgono questo compito per i rispettivi backend. Vedere [Entity Framework Core e Dapper](relational-adapters.html) e [Adattatori MongoDB e OpenSearch](search-adapters.html).
2. **Scrittura del file.** Il pacchetto `Craticula.Export.Csv` prende quel flusso e scrive i byte. Non sa nulla del database. `CsvWriter` ne è il punto di ingresso.

Poiché il writer legge una riga alla volta e scrive ogni record man mano, un'esportazione di un milione di righe usa all'incirca la stessa memoria di una di dieci righe. Gli adattatori relazionali e quello OpenSearch leggono le righe a blocchi (5,000 per impostazione predefinita), l'adattatore MongoDB legge un unico cursore batch dopo batch, mai con un offset crescente, e le chiamate paginate `FetchPageAsync` rifiutano una richiesta di tutte le righe, in modo che solo il flusso di esportazione possa leggere l'intero risultato. Un download lento rallenta la lettura invece di riempire la memoria.

## Che cosa invia la griglia {#what-the-grid-sends}

Una richiesta di esportazione è una normale richiesta della griglia con fino a tre membri in più:

- `exportFormat`, che vale `"csv"` oppure `"tsv"`. Contrassegna la richiesta come esportazione. L'invio degli altri due membri senza di esso viene rifiutato.
- `exportScope`, che vale `"all"` oppure `"page"`. Il valore predefinito è `"all"`: tutte le righe che corrispondono al filtro e all'ordinamento, qualunque cosa indichino `startRow` e `endRow`. `"page"` mantiene l'intervallo di righe della richiesta. Una richiesta che non invia alcuna finestra e non è un'esportazione riceve invece una pagina predefinita di 100 righe; vedere [Paginazione e ordinamento](paging-and-sorting.html).
- `exportColumns`, un elenco facoltativo di voci `{ "colId": "...", "header": "..." }`.

Il filtro e l'ordinamento sono sempre rispettati.

## Quali colonne e che cosa dicono le intestazioni {#which-columns-and-what-the-headers-say}

Se la richiesta non contiene `exportColumns`, l'esportazione include ogni colonna che lo schema contrassegna come `exportable`, nell'ordine in cui lo schema le dichiara. Una colonna è esportabile a meno che lo schema non indichi `"exportable": false`.

Se la richiesta contiene `exportColumns`, l'esportazione include quelle colonne, in quell'ordine. Viene rifiutata una colonna non presente nello schema, non esportabile o elencata due volte, così come un elenco vuoto. Ciò vale sia in modalità Strict sia in modalità Lenient.

L'intestazione di una colonna proviene, in ordine, da:

1. l'`header` della richiesta;
2. la `label` dello schema;
3. l'id della colonna.

Il parser lo determina una sola volta e lo inserisce in `ExportSpec.Columns`.

## Il raggruppamento viene scartato {#grouping-is-dropped}

Un'esportazione è un elenco piatto di righe. L'adattatore scarta `rowGroupCols`, `valueCols` e `groupKeys` da una richiesta di esportazione, quindi l'esportazione di una griglia raggruppata restituisce righe semplici con il filtro e l'ordinamento correnti.

## Mettere tutto insieme {#putting-it-together}

Il parser ha bisogno dello schema per risolvere un'esportazione, quindi occorre passarlo in `AgGridParseOptions`. Questo esempio gestisce `exportScope` impostato su `"all"`. Per `"page"`, `parsed.Page` è un intervallo di righe e `StreamAsync` lo rifiuta. Usa Dapper e PostgreSQL. `connection` è un `IDbConnection` aperto e `destination` è uno `Stream`, come il corpo della risposta HTTP.

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

`CsvWriterOptions.ForFormat` è il modo in cui il formato richiesto arriva al file. Sceglie la virgola per CSV e la tabulazione per TSV. Il writer non vede mai la richiesta, quindi non potrebbe farlo da sé. Il risultato del task è il numero di righe di dati scritte, esclusa la riga di intestazione.

I flussi di esportazione degli adattatori accettano solo il risultato completo (`exportScope` impostato su `"all"`). Un'esportazione limitata a una pagina è un unico blocco delimitato, la stessa query che esegue un blocco della griglia. Recuperarla con il metodo di pagina dell'adattatore e scrivere quelle righe direttamente.

## Com'è fatto il file {#what-the-file-looks-like}

Per impostazione predefinita:

- una riga di intestazione viene per prima;
- i campi sono separati da una virgola e le righe terminano con un ritorno a capo e un avanzamento riga;
- un campo che contiene il delimitatore, un doppio apice o un'interruzione di riga è racchiuso tra doppi apici;
- il file inizia con un byte order mark, perché Excel interpreta male il testo Unicode in sua assenza;
- un valore nullo è un campo vuoto;
- i booleani sono `true` e `false`;
- le date sono scritte come `2026-01-05` e i valori di data e ora come `2026-01-05T14:30:45`, con l'offset quando il valore ne ha uno;
- un decimale mantiene il proprio numero di cifre dopo la virgola.

## Che cosa si può modificare {#what-you-can-change}

`CsvWriterOptions` offre queste impostazioni:

| Impostazione | Predefinito | Che cosa fa |
|---|---|---|
| `Delimiter` | `,` | Il separatore di campo. |
| `IncludeHeaderRow` | `true` | Se scrivere la riga di intestazione. |
| `WriteByteOrderMark` | `true` | Se iniziare il file con un byte order mark. |
| `DecimalSeparator` | `.` | Il separatore nei numeri frazionari. |
| `HardenFormulaInjection` | `true` | Vedere sotto. |

`CsvWriterOptions.SemicolonPreset` imposta il delimitatore su un punto e virgola, per le impostazioni locali in cui Excel ne prevede uno.

Lo schema può sovrascrivere il formato di una singola colonna con un blocco `format`:

```json
"orderDate": { "type": "date", "format": { "datePattern": "dd/MM/yyyy" } },
"amount": { "type": "decimal", "format": { "decimalSeparator": "," } }
```

Il writer rifiuta un separatore decimale uguale al delimitatore. Una virgola in entrambi i punti trasformerebbe ogni numero frazionario in testo tra apici. Rifiuta inoltre un modello di data che non è in grado di applicare. `GridSchema.Parse` verifica il modello al caricamento dello schema, quindi un modello errato fallisce all'avvio e non a metà di un download.

## Protezione contro le formule dei fogli di calcolo {#protection-against-spreadsheet-formulas}

Un foglio di calcolo tratta come formula una cella che inizia con `=`, `+`, `-`, `@`, una tabulazione o un ritorno a capo. Un valore digitato da un utente può quindi essere eseguito nel foglio di calcolo di chi apre l'esportazione.

Per impostazione predefinita il writer antepone un apostrofo a tale testo. Ciò riguarda ogni intestazione e ogni cella di testo. Non tocca i numeri, le date o i booleani che il writer ha formattato da sé, quindi un numero negativo resta un numero.

È possibile disattivare la protezione con `HardenFormulaInjection = false`. L'apostrofo non può poi essere rimosso, quindi disattivarla solo quando il file è letto da un programma e nessuna persona lo apre in un foglio di calcolo.

## Che cosa resta a carico dello sviluppatore {#what-stays-with-you}

- **Il limite di righe.** Né gli adattatori né il writer impongono un numero massimo di righe esportate. Aggiungere un proprio limite se l'esportazione è pubblica.
- **Il limite della dimensione di pagina.** Non si applica a un'esportazione dell'intero risultato (`exportScope` impostato su `"all"`), che non ha pagina. Un'esportazione limitata a una pagina mantiene il proprio intervallo di righe e il limite della dimensione di pagina si applica ad essa. Vedere [Limiti](limits.html).
- **Dapper rifiuta alcune esportazioni.** `DapperExportStream` rifiuta uno schema la cui chiave stabile è una colonna di testo e un'esportazione in cui una chiave di ordinamento di testo contiene una stringa vuota nelle righe esportate (ogni dialetto tranne Oracle). Usare una chiave stabile numerica o di data, oppure recuperare i dati pagina per pagina con `DapperGridQuery.FetchPageAsync`. `EfCoreExportStream` non ha un controllo di questo tipo.
- **Il download.** Il tipo di contenuto, il nome del file e la connessione spettano allo sviluppatore. La demo li imposta in `examples/demo/Api/Routes/GridRoutes.cs`.
- **L'elenco delle colonne di OpenSearch.** L'esportazione OpenSearch scrive sempre ogni colonna dello schema, nell'ordine di `schema.FieldOrder`. Passare a `CsvWriter` l'elenco completo, un `ExportColumn` per ogni campo in `schema.FieldOrder`. Un `export.Columns` più ristretto fa fallire `CsvWriter` con una `CsvWriterException`, perché il numero di celle non corrisponde.

## Da dove proviene questa pagina {#where-this-comes-from}

- [csharp/src/Craticula.Export.Csv/README.md](../../csharp/src/Craticula.Export.Csv/README.md)
- [csharp/src/Craticula.Export.Csv/CsvWriter.cs](../../csharp/src/Craticula.Export.Csv/CsvWriter.cs)
- [csharp/src/Craticula.Export.Csv/CsvWriterOptions.cs](../../csharp/src/Craticula.Export.Csv/CsvWriterOptions.cs)
- [csharp/src/Craticula.AgGrid/ExportSpec.cs](../../csharp/src/Craticula.AgGrid/ExportSpec.cs)
- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/page-export](../../spec/fixtures/page-export/README.md)
- [examples/demo/Api/Routes/GridRoutes.cs](../../examples/demo/Api/Routes/GridRoutes.cs)
- Pagine correlate: [Paginazione e ordinamento](paging-and-sorting.html), [Il GridSchema](the-gridschema.html), [Modello di sicurezza](safety-model.html)
