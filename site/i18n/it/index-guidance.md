---
translates: index-guidance
title: Indicazioni sugli indici
description: Quali indici e impostazioni del database mantengono le query compilate veloci ed esatte.
source_fingerprint: 3d3bf891b84587e5732e82a2bb52c06b0c2ee549efb1865d1fc2d889fe36ebf5
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Indicazioni su indici e database {#index-and-database-guidance}

Craticula compila query; non crea mai una tabella, un indice o una collation. Questa pagina elenca, per ciascun database, che cosa
**spetta a voi** predisporre perché le query compilate restituiscano le righe giuste e siano veloci. Le regole alla base sono in
[semantica](semantics.html); le fixture per database che fissano le istruzioni sono in
[`spec/fixtures/dialect-parity`](../../spec/fixtures/dialect-parity/README.md).

Qui sotto compaiono due tipi di obbligo, e la differenza conta:

- **Rumoroso:** il database rifiuta l'istruzione (una collation mancante, un server vecchio). Ce ne si accorge subito.
- **Silenzioso:** l'istruzione viene eseguita e restituisce righe sbagliate (una colonna che ignora la differenza tra maiuscole e minuscole quando non dovrebbe). Nulla lo segnala, perciò
  sono quelli da leggere due volte.

## In sintesi {#at-a-glance}

| Database | Cosa si deve fornire | Se non lo si fa |
|---|---|---|
| PostgreSQL | versione 12 o successiva con ICU; la collation `craticula_ci`; `timestamptz` per i datetime | rumoroso per i primi due (ogni confronto senza distinzione tra maiuscole e minuscole fallisce), silenzioso per `timestamp` |
| SQL Server | collation binaria o con distinzione tra maiuscole e minuscole sulle colonne di raggruppamento; `datetime2` che contiene UTC | silenzioso: `EMEA` e `emea` condividono un gruppo |
| MySQL / MariaDB | collation `_bin` o `_as_cs` sulle colonne con distinzione tra maiuscole e minuscole e su quelle di raggruppamento; `DATETIME` che contiene UTC | silenzioso: la dichiarazione viene ignorata |
| SQLite | versione 3.30.0 o successiva; datetime memorizzati come `yyyy-MM-ddTHH:mm:ss.fffZ` | rumoroso per la versione, silenzioso per il testo del datetime |
| Oracle | 12.2 o successiva; identificatori tra virgolette; collation binaria sulle colonne di raggruppamento (l'impostazione predefinita della sessione) | rumoroso per i primi due, silenzioso per l'ultimo |
| MongoDB | server 4.2 o successivo | rumoroso: la pipeline viene rifiutata |
| OpenSearch / Elasticsearch | sotto-campi `keyword`, un normalizer per l'ordinamento senza distinzione tra maiuscole e minuscole, un tipo numerico preciso per i decimali | silenzioso per un sotto-campo `keyword` mancante in un filtro (nessuna riga corrisponde), rumoroso in un ordinamento; silenzioso per gli arrotondamenti |

Ogni motore richiede inoltre che la **chiave stabile dello schema sia univoca, con al massimo un `NULL`**
([Deterministic paging](semantics.html#sem-6)). La maggior parte dei motori consente a un vincolo di unicità di contenere molti `NULL`, il che rompe la garanzia di paginazione; dichiarare la
chiave `NOT NULL`. Una chiave stabile di tipo testo senza distinzione tra maiuscole e minuscole richiede anche una collation binaria o con distinzione tra maiuscole e minuscole su MySQL e SQL
Server, altrimenti due chiavi che differiscono solo per le maiuscole risultano pari.

## Indici per ogni database {#indexes-for-every-database}

- **Filtri.** Un campo di testo si confronta per impostazione predefinita senza distinzione tra maiuscole e minuscole ([Case sensitivity](semantics.html#sem-1)). La regola è costruita in modo che un normale
  indice sulla colonna possa comunque essere usato per l'uguaglianza: il compilatore indica una collation nel confronto invece di racchiudere la
  colonna in `lower()`. Fare in modo che l'indice corrisponda a quella collation (vedi sotto). Le corrispondenze di sottostringa (`contains`, `endsWith`) iniziano con un
  carattere jolly, che nessun normale indice B-tree serve; vedere ciascun motore.
- **Ordinamento.** Ogni query ordinata termina con la chiave stabile dello schema, in ordine crescente con i null per ultimi ([Deterministic paging](semantics.html#sem-6)),
  e Craticula stabilisce da sé la posizione dei null ([Null ordering](semantics.html#sem-3)). Un indice serve l'ordinamento solo se corrisponde a quell'
  ordine esatto. Su PostgreSQL, SQLite e Oracle l'ordine della guida rapida è `amount DESC NULLS FIRST, id ASC NULLS LAST`, quindi
  l'indice corrispondente è `(amount DESC NULLS FIRST, id ASC NULLS LAST)`; un normale indice `(amount, id)` non corrisponde a un ordinamento decrescente.
  Su SQL Server e MySQL l'istruzione ordina prima per un test di nullità (`CASE WHEN ... IS NULL`, `ISNULL(...)`), che nessun indice di colonna
  serve, e su MongoDB l'ordinamento lavora su campi ausiliari calcolati. Quindi lì si indicizzano i **filtri** e ci si aspetta che l'ordinamento
  avvenga dopo di essi. Controllare il piano (`EXPLAIN`) sui propri dati; Craticula non può conoscere le dimensioni delle vostre tabelle.
- **Paginazione.** `OFFSET` in genere rallenta quanto più è profonda la pagina. L'esportazione CSV percorre il risultato in ordine di chiave e non usa
  `OFFSET`.

## PostgreSQL {#postgresql}

Richiede PostgreSQL 12 o successivo compilato con ICU (una collation non deterministica). Configurazione una tantum, nel database che contiene le tabelle:

```sql
CREATE COLLATION craticula_ci (provider = icu, locale = 'und-u-ks-level2', deterministic = false);
```

Senza di essa ogni `=`, `IN`, intervallo e `ORDER BY` senza distinzione tra maiuscole e minuscole fallisce con una collation sconosciuta
([Case sensitivity](semantics.html#sem-1)).

- **Uguaglianza e ordinamento** su un campo di testo senza distinzione tra maiuscole e minuscole citano `craticula_ci`. Un indice creato con quella collation
  (`CREATE INDEX ... ON orders (customer COLLATE craticula_ci)`) è quello che corrisponde; confermare con `EXPLAIN`.
- **`contains`, `startsWith`, `endsWith`** si compilano in `ILIKE`. Sostenerli con un indice trigram: `CREATE EXTENSION pg_trgm;`
  poi `CREATE INDEX ... USING gin (customer gin_trgm_ops);`.
- **Date:** dichiarare le colonne `datetime` come `timestamptz`. Con un semplice `timestamp` il server confronta attraverso il fuso orario della sessione e
  le righe si spostano senza alcun errore ([Dates and time zones](semantics.html#sem-4)).
- Le colonne di raggruppamento non richiedono collation: la collation predefinita di PostgreSQL è deterministica, quindi `EMEA` e `emea` sono due gruppi, come
  richiede [Grouping and drill-down](semantics.html#grp-2).

## SQL Server {#sql-server}

Nessuna configurazione di collation per i filtri: l'istruzione porta `COLLATE Latin1_General_CI_AS` (oppure `Latin1_General_CS_AS` per un campo dichiarato
con distinzione tra maiuscole e minuscole) in linea, quindi nessuna delle due direzioni dipende dalla collation propria del database.

- **Colonne di raggruppamento, obbligo silenzioso.** Un `GROUP BY` e un drill-down devono essere esatti ([Grouping and drill-down](semantics.html#grp-2)), e l'
  istruzione non indica alcuna collation in quel punto. La collation predefinita abituale di SQL Server (`SQL_Latin1_General_CP1_CI_AS`) ignora la differenza tra maiuscole e minuscole, quindi una colonna
  raggruppata dichiarata con essa mette `EMEA` e `emea` in un solo gruppo. Dichiarare ogni colonna raggruppabile, e la chiave stabile se è di testo,
  con una collation binaria o con distinzione tra maiuscole e minuscole. La definizione della colonna è, ad esempio:

  ```sql
  country nvarchar(100) COLLATE Latin1_General_100_BIN2 NULL
  ```

  I filtri su quella colonna continuano a confrontare senza distinzione tra maiuscole e minuscole, perché indicano una propria collation in linea. Il prezzo è la
  velocità: un confronto che nomina una collation diversa da quella della colonna di solito non può usare un seek su di essa, quindi misurare un
  filtro senza distinzione tra maiuscole e minuscole su una colonna per cui si raggruppa anche.
- **Date.** `datetime2` non ha fuso orario. Memorizzare la lettura UTC; il compilatore confronta direttamente l'istante UTC con essa,
  e i risultati tornano in UTC ([Dates and time zones](semantics.html#sem-4)).
- **Entity Framework Core:** impostare `PatternMatchFoldsCase = false` sulla semantica del provider, a meno che la collation di ogni colonna ricercabile
  non ignori la differenza tra maiuscole e minuscole; `true` invia un semplice `LIKE`, che su una colonna con collation binaria corrisponde solo alle maiuscole esatte. Vedere il
  [README dell'adapter](../../csharp/src/Craticula.EntityFrameworkCore/README.md).

## MySQL e MariaDB {#mysql-and-mariadb}

Lì la distinzione tra maiuscole e minuscole appartiene alla collation **della colonna**, che un'istruzione non può sovrascrivere in modo portabile.

- **I campi senza distinzione tra maiuscole e minuscole** (l'impostazione predefinita) funzionano su qualsiasi colonna `_ci`, come `utf8mb4_0900_ai_ci`, e un normale indice sulla
  colonna serve l'uguaglianza su di essi (non una corrispondenza di sottostringa, che inizia con un carattere jolly).
- **Campi con distinzione tra maiuscole e minuscole, obbligo silenzioso.** Un campo dichiarato `caseSensitivity: "sensitive"` richiede una collation di colonna `_bin` o `_as_cs`
  (`utf8mb4_bin`, `utf8mb4_0900_as_cs`). Su una colonna `_ci` la dichiarazione non ha effetto e i confronti restano
  senza distinzione tra maiuscole e minuscole; l'istruzione compilata non lo segnala.
- **Le colonne di raggruppamento** richiedono la stessa collation binaria o `_as_cs` per gruppi esatti ([Grouping and drill-down](semantics.html#grp-2)):

  ```sql
  country varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin
  ```

  Una colonna ha una sola collation, quindi una colonna raggruppabile resa binaria rende anche i filtri e i prefissi senza distinzione tra maiuscole e minuscole su quella
  stessa colonna con distinzione tra maiuscole e minuscole, in silenzio (la divergenza accettata n. 4 di GRP-2). Se servono entrambi su un campo, decidere quale conta
  di più; il compilatore non può darvi entrambi da una sola colonna.
- **Entity Framework Core:** come per SQL Server, impostare `PatternMatchFoldsCase = false` a meno che la collation di ogni colonna ricercabile non ignori la differenza tra maiuscole e minuscole.
- **Date.** `DATETIME` non ha fuso orario: memorizzare UTC. Se si usa MySqlConnector, lasciare `DateTimeKind` al valore predefinito oppure impostare UTC;
  `Local` si limita a etichettare il valore e sposterebbe ogni istante dell'offset del server ([Dates and time zones](semantics.html#sem-4)).

## SQLite {#sqlite}

- **Versione 3.30.0 o successiva**, per `NULLS FIRST` / `NULLS LAST`. Una libreria più vecchia rifiuta l'istruzione.
- **I campi senza distinzione tra maiuscole e minuscole** usano `COLLATE NOCASE`, che ignora la differenza solo per le lettere ASCII (`É` e `é` restano diverse). Un indice
  dichiarato `(customer COLLATE NOCASE)` li serve.
- **Datetime, obbligo silenzioso.** SQLite non ha un tipo timestamp e confronta il testo carattere per carattere. Memorizzare ogni
  `datetime` esattamente come `yyyy-MM-ddTHH:mm:ss.fffZ`, in UTC, con tre cifre frazionarie ([Dates and time zones](semantics.html#sem-4)). Un'altra
  larghezza (`...:00Z`, `yyyy-MM-dd HH:mm:ss`) restituisce righe sbagliate senza alcun errore.
- **Entity Framework Core** associa un `DateTime` nella propria forma `yyyy-MM-dd HH:mm:ss`, quindi mappare ogni datetime verso e dal
  testo memorizzato nel proprio `DbContext`. Senza la mappatura un `eq` non trova nulla, un limite di intervallo considera l'intera data come successiva e
  un'esportazione ordinata per datetime può ripetere righe. Il
  [README dell'adapter](../../csharp/src/Craticula.EntityFrameworkCore/README.md) ne dà
  i dettagli.

## Oracle {#oracle}

- **Server 12.2 o successivo.** Le istruzioni usano `COLLATE BINARY_CI` e `COLLATE BINARY`; un server più vecchio le rifiuta.
  Oracle documenta `COMPATIBLE >= 12.2` e `MAX_STRING_SIZE = EXTENDED` come prerequisito della collation legata ai dati.
- **Che cosa è stato verificato.** Le istruzioni compilate sono state eseguite su Oracle Database Free 23.26.3 in un container
  (`gvenzl/oracle-free:23.26.3-slim-faststart`, `COMPATIBLE = 23.6.0`, `MAX_STRING_SIZE = STANDARD`): tutte le 45 fixture Oracle
  restituiscono le righe attese, e la proprietà di parità tra backend è superata con Oracle tra otto motori. Su quel server l'
  operatore `COLLATE` all'interno di un'istruzione funziona senza `EXTENDED`; fallisce solo il **dichiarare** una collation su una colonna
  (`ORA-43929`). Oracle da 12.2 a 21c **non** è stato provato: la soglia indicata sopra è la documentazione di Oracle, non una misurazione.
- **Identificatori tra virgolette.** Creare la tabella e ogni colonna con nomi tra virgolette che corrispondano esattamente alla grafia di `source` e `column`
  dello schema. Oracle converte in maiuscolo un nome senza virgolette, e l'istruzione compilata mette tra virgolette ogni identificatore
  (`ORA-00942` se differiscono).
- **Impostazioni di sessione.** Le istruzioni compilate passano date, datetime e decimali come testo e non aggiungono alcun cast, quindi Oracle li converte
  secondo le impostazioni della sessione. Impostare sulla connessione `NLS_DATE_FORMAT = 'YYYY-MM-DD'`,
  `NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD"T"HH24:MI:SS.FF"Z"'` e `NLS_NUMERIC_CHARACTERS = '.,'`; senza di esse
  ogni filtro su data, datetime o decimale fallisce (`ORA-01861`, `ORA-01722`), e una cultura del client con la virgola decimale può causarlo
  solo su alcune macchine.
- **Colonne di raggruppamento, obbligo silenzioso.** Eseguire la sessione con `NLS_COMP = BINARY` e `NLS_SORT = BINARY` (i valori predefiniti per un client inglese; la configurazione verificata) oppure, su un
  server con `MAX_STRING_SIZE = EXTENDED`, dichiarare ogni colonna raggruppabile e la chiave stabile con `COLLATE BINARY`. La collation
  predefinita segue la sessione e può ignorare la differenza tra maiuscole e minuscole. La definizione della colonna è, ad esempio:

  ```sql
  "country" VARCHAR2(100) COLLATE BINARY
  ```

## MongoDB {#mongodb}

- **Server 4.2 o successivo**, per lo stage `$unset` che ogni pipeline ordinata usa per eliminare i propri campi ausiliari di posizionamento dei null.
- **I campi senza distinzione tra maiuscole e minuscole** si compilano in una collation a livello di query (`locale: "en"`, `strength: 2`). Un indice serve una query
  con collation solo se è stato creato con la stessa collation: `createIndex({ customer: 1 }, { collation: { locale: "en", strength: 2 } })`.
- **`contains`, `startsWith`, `endsWith`** si compilano in un `$regex` con escape (in
  MongoDB non esiste un operatore di sottostringa compatibile con le collation). Una regex non usa un indice sensibile alla collation come invece fa un'uguaglianza, quindi aspettarsi una scansione su una collezione grande e
  misurare.
- **Ordinamento.** L'ordinamento lavora su campi ausiliari calcolati che contengono la posizione dei null, quindi nessun indice lo serve nel suo complesso; indicizzare i
  filtri ([Null ordering](semantics.html#sem-3)).
- **Le richieste di raggruppamento confrontano con distinzione tra maiuscole e minuscole.** MongoDB ha una sola collation per query. Una richiesta di raggruppamento deve mantenere esatti i propri
  bucket, quindi la sua pipeline non porta alcuna collation e un filtro utente nella stessa richiesta confronta **con** distinzione tra maiuscole e minuscole
  (la divergenza accettata n. 3 di GRP-2). Gli altri database ignorano la differenza tra maiuscole e minuscole in quel filtro.

## OpenSearch ed Elasticsearch {#opensearch-and-elasticsearch}

Un solo compilatore serve entrambi. Il mapping dell'indice è vostro, e le query compilate nominano i sotto-campi che il vostro schema dichiara.

- **Versione:** Elasticsearch 7.10 o successiva, OpenSearch 1.0 o successiva (per `case_insensitive` su `term` e `wildcard`).
- **Sotto-campo `keyword`, silenzioso in un filtro.** Ogni campo di testo filtrato, ordinato o raggruppato richiede il sotto-campo `keyword`
  dichiarato come `physical.search.keywordSubField`, un multi-field nel mapping dell'indice. Se manca, un filtro su di esso
  non corrisponde a **nessuna riga** senza alcun errore; solo un ordinamento su di esso fallisce.
- **Ordinamento e intervallo senza distinzione tra maiuscole e minuscole.** Dichiarare `physical.search.normalizedSubField` e mapparlo come `keyword` con un
  `normalizer` che ignora la differenza tra maiuscole e minuscole. Ciò costa spazio nell'indice ed è l'unico modo per ordinare o confrontare un campo di testo senza distinzione tra maiuscole e minuscole; il compilatore
  rifiuta di compilare una richiesta di questo tipo per un campo che non ne dichiara uno.
- **Decimali.** Mappare un campo `decimal` come `scaled_float` con un `scaling_factor` sufficiente, oppure come `keyword` se si confronta solo per
  uguaglianza. Un mapping `double` arrotonda in silenzio.
- **Paginazione profonda e conteggi.** Oltre `max_result_window` (10,000 righe) il client pagina con un point-in-time e `search_after`;
  impostare `Flavour` su `Elasticsearch` **sia** nelle opzioni di paginazione profonda **sia** in quelle di esportazione per Elasticsearch, altrimenti ogni esportazione
  fallisce con HTTP 400. Il conteggio totale delle righe oltre 10,000 è riportato come sconosciuto, a meno che
  non si scelga il conteggio esatto, che conta ogni corrispondenza a ogni prima richiesta.
- **`contains`** è un carattere jolly sul campo `keyword`; un carattere jolly iniziale percorre il dizionario dei termini, quindi misurarlo su indici grandi.

## Che cosa resta fuori da questa pagina {#what-stays-out-of-this-page}

L'ottimizzazione per motore (partizioni, indici di copertura, numero di shard) dipende dai dati e dal carico di lavoro. Le istruzioni compilate si trovano nelle
[fixture di conformità](../../spec/fixtures/), una cartella per caso, con il testo
esatto che riceve ciascun database; eseguire `EXPLAIN` su di esse contro le proprie tabelle.
