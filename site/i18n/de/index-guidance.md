---
translates: index-guidance
title: Hinweise zu Indizes und Datenbanken
description: Welche Datenbankindizes und -einstellungen kompilierte Abfragen schnell und exakt halten.
source_fingerprint: 3d3bf891b84587e5732e82a2bb52c06b0c2ee549efb1865d1fc2d889fe36ebf5
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Hinweise zu Indizes und Datenbanken {#index-and-database-guidance}

Craticula kompiliert Abfragen; es legt nie eine Tabelle, einen Index oder eine Collation an. Diese Seite listet für jede Datenbank auf, was **Sie**
einrichten müssen, damit kompilierte Abfragen die richtigen Zeilen liefern und schnell laufen. Die Regeln dahinter stehen in der
[Semantik](semantics.html); die datenbankspezifischen Fixtures, die die Anweisungen festschreiben, liegen in
[`spec/fixtures/dialect-parity`](../../spec/fixtures/dialect-parity/README.md).

Unten tauchen zwei Arten von Pflichten auf, und der Unterschied zählt:

- **Laut:** Die Datenbank weist die Anweisung zurück (fehlende Collation, zu alter Server). Sie bemerken es sofort.
- **Leise:** Die Anweisung läuft und liefert falsche Zeilen (eine Spalte, die die Groß- und Kleinschreibung ignoriert, obwohl sie es nicht sollte). Nichts warnt Sie; diese
  Pflichten lesen Sie deshalb zweimal.

## Auf einen Blick {#at-a-glance}

| Datenbank | Was Sie bereitstellen müssen | Wenn Sie es nicht tun |
|---|---|---|
| PostgreSQL | Version 12 oder neuer mit ICU; die Collation `craticula_ci`; `timestamptz` für Datum-Uhrzeit-Werte | laut bei den ersten beiden (jeder Vergleich ohne Beachtung der Groß- und Kleinschreibung schlägt fehl), leise bei `timestamp` |
| SQL Server | binäre oder groß-/kleinschreibungssensitive Collation auf Gruppierungsspalten; `datetime2` mit UTC | leise: `EMEA` und `emea` landen in einer Gruppe |
| MySQL / MariaDB | `_bin`- oder `_as_cs`-Collation auf groß-/kleinschreibungssensitiven Spalten und Gruppierungsspalten; `DATETIME` mit UTC | leise: die Deklaration wird ignoriert |
| SQLite | Version 3.30.0 oder neuer; Datum-Uhrzeit-Werte gespeichert als `yyyy-MM-ddTHH:mm:ss.fffZ` | laut bei der Version, leise beim Text des Datum-Uhrzeit-Werts |
| Oracle | 12.2 oder neuer; Bezeichner in Anführungszeichen; binäre Collation auf Gruppierungsspalten (die Standardeinstellung der Sitzung) | laut bei den ersten beiden, leise beim letzten |
| MongoDB | Server 4.2 oder neuer | laut: die Pipeline wird zurückgewiesen |
| OpenSearch / Elasticsearch | `keyword`-Unterfelder, ein Normalizer für Sortierung ohne Beachtung der Groß- und Kleinschreibung, ein präziser numerischer Typ für Dezimalzahlen | leise bei einem fehlenden `keyword`-Unterfeld in einem Filter (keine Zeile passt), laut in einer Sortierung; leise bei der Rundung |

Jede Engine verlangt außerdem, dass der **stabile Schlüssel des Schemas eindeutig ist, mit höchstens einem `NULL`**
([Deterministic paging](semantics.html#sem-6)). Die meisten Engines erlauben in einer Eindeutigkeitsbedingung mehrere `NULL`, was die Paging-Garantie bricht; deklarieren Sie den
Schlüssel als `NOT NULL`. Ein textbasierter stabiler Schlüssel ohne Beachtung der Groß- und Kleinschreibung verlangt zudem auf MySQL und SQL
Server eine binäre oder groß-/kleinschreibungssensitive Collation, sonst sind zwei Schlüssel, die sich nur in der Schreibweise unterscheiden, gleichrangig.

## Indizes für jede Datenbank {#indexes-for-every-database}

- **Filter.** Ein Textfeld wird standardmäßig ohne Beachtung der Groß- und Kleinschreibung verglichen ([Case sensitivity](semantics.html#sem-1)). Die Regel ist so gebaut, dass ein einfacher
  Index auf der Spalte für die Gleichheit nutzbar bleibt: Der Compiler gibt für den Vergleich eine Collation an, statt die
  Spalte in `lower()` einzuhüllen. Stimmen Sie den Index auf diese Collation ab (siehe unten). Teilzeichenfolgen-Suchen (`contains`, `endsWith`) beginnen mit einem
  Platzhalter, den kein gewöhnlicher B-Tree-Index bedient; siehe die einzelnen Engines.
- **Sortierung.** Jede sortierte Abfrage endet mit dem stabilen Schlüssel des Schemas, aufsteigend mit Nullwerten am Ende ([Deterministic paging](semantics.html#sem-6)),
  und Craticula schreibt die Position der Nullwerte selbst ([Null ordering](semantics.html#sem-3)). Ein Index bedient die Sortierung nur, wenn er genau dieser
  Reihenfolge entspricht. Auf PostgreSQL, SQLite und Oracle lautet die Reihenfolge des Schnellstarts `amount DESC NULLS FIRST, id ASC NULLS LAST`, der
  passende Index ist also `(amount DESC NULLS FIRST, id ASC NULLS LAST)`; ein einfacher Index `(amount, id)` passt nicht zu einer absteigenden Sortierung.
  Auf SQL Server und MySQL sortiert die Anweisung zuerst nach einem Null-Test (`CASE WHEN ... IS NULL`, `ISNULL(...)`), den kein Spaltenindex
  bedient, und auf MongoDB sortiert sie nach berechneten Hilfsfeldern. Indizieren Sie dort daher Ihre **Filter** und rechnen Sie damit, dass die Sortierung
  nach ihnen erfolgt. Prüfen Sie den Plan (`EXPLAIN`) auf Ihren eigenen Daten; Craticula kann die Größe Ihrer Tabellen nicht kennen.
- **Paging.** `OFFSET` wird in der Regel langsamer, je tiefer die Seite liegt. Der CSV-Export durchläuft das Ergebnis in der Reihenfolge des Schlüssels und verwendet kein
  `OFFSET`.

## PostgreSQL {#postgresql}

Verlangt PostgreSQL 12 oder neuer, mit ICU gebaut (eine nichtdeterministische Collation). Einmalige Einrichtung, in der Datenbank, die Ihre Tabellen enthält:

```sql
CREATE COLLATION craticula_ci (provider = icu, locale = 'und-u-ks-level2', deterministic = false);
```

Ohne sie schlägt jedes `=`, `IN`, jeder Bereich und jedes `ORDER BY` ohne Beachtung der Groß- und Kleinschreibung mit einer unbekannten Collation fehl
([Case sensitivity](semantics.html#sem-1)).

- **Gleichheit und Sortierung** auf einem Textfeld ohne Beachtung der Groß- und Kleinschreibung nennen `craticula_ci`. Ein mit dieser Collation angelegter Index
  (`CREATE INDEX ... ON orders (customer COLLATE craticula_ci)`) ist der passende; bestätigen Sie es mit `EXPLAIN`.
- **`contains`, `startsWith`, `endsWith`** werden zu `ILIKE` kompiliert. Stützen Sie sie auf einen Trigramm-Index: `CREATE EXTENSION pg_trgm;`
  und dann `CREATE INDEX ... USING gin (customer gin_trgm_ops);`.
- **Datumswerte:** Deklarieren Sie `datetime`-Spalten als `timestamptz`. Bei einem einfachen `timestamp` vergleicht der Server über die Zeitzone der Sitzung hinweg, und
  die Zeilen verschieben sich ohne Fehler ([Dates and time zones](semantics.html#sem-4)).
- Gruppierungsspalten brauchen keine Collation: Die Standard-Collation von PostgreSQL ist deterministisch, sodass `EMEA` und `emea` zwei Gruppen bilden, wie
  es [Grouping and drill-down](semantics.html#grp-2) verlangt.

## SQL Server {#sql-server}

Für Filter ist keine Collation einzurichten: Die Anweisung trägt `COLLATE Latin1_General_CI_AS` (oder `Latin1_General_CS_AS` für ein Feld, das Sie
als groß-/kleinschreibungssensitiv deklariert haben) inline, sodass keine der beiden Richtungen von der Collation der Datenbank selbst abhängt.

- **Gruppierungsspalten, leise Pflicht.** Ein `GROUP BY` und ein Drill-down müssen exakt sein ([Grouping and drill-down](semantics.html#grp-2)), und die
  Anweisung nennt an dieser Stelle keine Collation. Der übliche Standard von SQL Server (`SQL_Latin1_General_CP1_CI_AS`) ignoriert die Groß- und Kleinschreibung, sodass eine
  gruppierte Spalte, die ihn verwendet, `EMEA` und `emea` in eine Gruppe legt. Deklarieren Sie jede gruppierbare Spalte sowie den stabilen Schlüssel, falls er ein Text ist,
  mit einer binären oder groß-/kleinschreibungssensitiven Collation. Die Spaltendefinition lautet zum Beispiel:

  ```sql
  country nvarchar(100) COLLATE Latin1_General_100_BIN2 NULL
  ```

  Filter auf dieser Spalte vergleichen weiterhin ohne Beachtung der Groß- und Kleinschreibung, weil sie ihre eigene Collation inline angeben. Der Preis ist
  die Geschwindigkeit: Ein Vergleich, der eine andere Collation nennt als die der Spalte, kann in der Regel keine Index-Suche nutzen; messen Sie daher einen
  Filter ohne Beachtung der Groß- und Kleinschreibung auf einer Spalte, die Sie auch gruppieren.
- **Datumswerte.** `datetime2` hat keine Zeitzone. Speichern Sie den UTC-Wert; der Compiler vergleicht den UTC-Zeitpunkt direkt damit,
  und die Ergebnisse kommen in UTC zurück ([Dates and time zones](semantics.html#sem-4)).
- **Entity Framework Core:** Setzen Sie `PatternMatchFoldsCase = false` in der Provider-Semantik, es sei denn, die Collation jeder abfragbaren Spalte
  ignoriert die Groß- und Kleinschreibung; `true` sendet ein nacktes `LIKE`, das auf einer Spalte mit binärer Collation nur die exakte Schreibweise findet. Siehe die
  [README des Adapters](../../csharp/src/Craticula.EntityFrameworkCore/README.md).

## MySQL und MariaDB {#mysql-and-mariadb}

Dort ist die Groß- und Kleinschreibung eine Sache der Collation **der Spalte**, die eine Anweisung nicht portabel überschreiben kann.

- **Felder ohne Beachtung der Groß- und Kleinschreibung** (der Standard) funktionieren auf jeder `_ci`-Spalte, etwa `utf8mb4_0900_ai_ci`, und ein einfacher Index auf der
  Spalte bedient die Gleichheit auf ihnen (nicht eine Teilzeichenfolgen-Suche, die mit einem Platzhalter beginnt).
- **Groß-/kleinschreibungssensitive Felder, leise Pflicht.** Ein Feld, das als `caseSensitivity: "sensitive"` deklariert ist, verlangt eine Spalten-Collation `_bin` oder `_as_cs`
  (`utf8mb4_bin`, `utf8mb4_0900_as_cs`). Auf einer `_ci`-Spalte hat die Deklaration keine Wirkung, und Vergleiche bleiben
  ohne Beachtung der Groß- und Kleinschreibung; die kompilierte Anweisung sagt Ihnen das nicht.
- **Gruppierungsspalten** verlangen dieselbe binäre oder `_as_cs`-Collation für exakte Gruppen ([Grouping and drill-down](semantics.html#grp-2)):

  ```sql
  country varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin
  ```

  Eine Spalte hat nur eine Collation; eine gruppierbare Spalte, die binär gemacht wird, macht daher auch Filter und Präfixe ohne Beachtung der Groß- und Kleinschreibung auf
  genau dieser Spalte stillschweigend groß-/kleinschreibungssensitiv (die akzeptierte Abweichung Nr. 4 von GRP-2). Brauchen Sie beides auf einem Feld, entscheiden Sie, was
  wichtiger ist; der Compiler kann Ihnen nicht beides aus einer einzigen Spalte geben.
- **Entity Framework Core:** Wie bei SQL Server setzen Sie `PatternMatchFoldsCase = false`, es sei denn, die Collation jeder abfragbaren Spalte ignoriert die Groß- und Kleinschreibung.
- **Datumswerte.** `DATETIME` hat keine Zeitzone: Speichern Sie UTC. Wenn Sie MySqlConnector verwenden, lassen Sie `DateTimeKind` auf dem Standardwert oder setzen Sie es auf UTC;
  `Local` beschriftet den Wert nur und würde jeden Zeitpunkt um den Versatz des Servers verschieben ([Dates and time zones](semantics.html#sem-4)).

## SQLite {#sqlite}

- **Version 3.30.0 oder neuer**, für `NULLS FIRST` / `NULLS LAST`. Eine ältere Bibliothek weist die Anweisung zurück.
- **Felder ohne Beachtung der Groß- und Kleinschreibung** verwenden `COLLATE NOCASE`, das nur ASCII-Buchstaben faltet (`É` und `é` bleiben verschieden). Ein als
  `(customer COLLATE NOCASE)` deklarierter Index bedient sie.
- **Datum-Uhrzeit-Werte, leise Pflicht.** SQLite hat keinen Zeitstempel-Typ und vergleicht Text Zeichen für Zeichen. Speichern Sie jeden
  `datetime` genau in der Form `yyyy-MM-ddTHH:mm:ss.fffZ`, in UTC, mit drei Nachkommastellen ([Dates and time zones](semantics.html#sem-4)). Eine andere
  Breite (`...:00Z`, `yyyy-MM-dd HH:mm:ss`) liefert ohne Fehler falsche Zeilen.
- **Entity Framework Core** bindet einen `DateTime` in seiner eigenen Form `yyyy-MM-dd HH:mm:ss`; bilden Sie daher in Ihrem `DbContext` jeden Datum-Uhrzeit-Wert in beiden Richtungen auf den
  gespeicherten Text ab. Ohne diese Abbildung findet ein `eq` nichts, eine Bereichsgrenze zählt den ganzen Tag als später, und
  ein nach Datum-Uhrzeit sortierter Export kann Zeilen wiederholen. Die
  [README des Adapters](../../csharp/src/Craticula.EntityFrameworkCore/README.md) nennt
  die Einzelheiten.

## Oracle {#oracle}

- **Server 12.2 oder neuer.** Die Anweisungen verwenden `COLLATE BINARY_CI` und `COLLATE BINARY`; ein älterer Server weist sie zurück.
  Oracle dokumentiert `COMPATIBLE >= 12.2` und `MAX_STRING_SIZE = EXTENDED` als Voraussetzungen der datengebundenen Collation.
- **Was geprüft wurde.** Die kompilierten Anweisungen wurden auf Oracle Database Free 23.26.3 in einem Container ausgeführt
  (`gvenzl/oracle-free:23.26.3-slim-faststart`, `COMPATIBLE = 23.6.0`, `MAX_STRING_SIZE = STANDARD`): Die 45 Oracle-Fixtures
  liefern die erwarteten Zeilen, und die Parity-Eigenschaft zwischen den Backends besteht mit Oracle unter acht Engines. Auf diesem Server
  funktioniert der Operator `COLLATE` innerhalb einer Anweisung ohne `EXTENDED`; nur das **Deklarieren** einer Collation auf einer Spalte schlägt fehl
  (`ORA-43929`). Oracle 12.2 bis 21c wurden **nicht** getestet: Die Untergrenze oben stammt aus der Dokumentation von Oracle, nicht aus einer Messung.
- **Bezeichner in Anführungszeichen.** Legen Sie die Tabelle und jede Spalte mit Namen in Anführungszeichen an, die genau der Schreibweise von `source` und `column`
  im Schema entsprechen. Oracle setzt einen Namen ohne Anführungszeichen in Großbuchstaben, und die kompilierte Anweisung setzt jeden Bezeichner in Anführungszeichen
  (`ORA-00942`, wenn sie sich unterscheiden).
- **Sitzungseinstellungen.** Die kompilierten Anweisungen übergeben Datums-, Datum-Uhrzeit- und Dezimalwerte als Text und fügen keine Konvertierung hinzu; Oracle konvertiert sie daher
  nach den Einstellungen der Sitzung. Setzen Sie `NLS_DATE_FORMAT = 'YYYY-MM-DD'`,
  `NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD"T"HH24:MI:SS.FF"Z"'` und `NLS_NUMERIC_CHARACTERS = '.,'` auf der Verbindung; ohne sie schlägt
  jeder Filter auf Datum, Datum-Uhrzeit oder Dezimalzahl fehl (`ORA-01861`, `ORA-01722`), und eine Client-Kultur mit Dezimalkomma kann das nur
  auf manchen Rechnern auslösen.
- **Gruppierungsspalten, leise Pflicht.** Führen Sie die Sitzung mit `NLS_COMP = BINARY` und `NLS_SORT = BINARY` aus (die Standardwerte eines englischen Clients; die geprüfte Konfiguration) oder deklarieren Sie auf einem
  Server mit `MAX_STRING_SIZE = EXTENDED` jede gruppierbare Spalte und den stabilen Schlüssel mit `COLLATE BINARY`. Die Standard-Collation
  folgt der Sitzung und kann die Groß- und Kleinschreibung ignorieren. Die Spaltendefinition lautet zum Beispiel:

  ```sql
  "country" VARCHAR2(100) COLLATE BINARY
  ```

## MongoDB {#mongodb}

- **Server 4.2 oder neuer**, für die Stufe `$unset`, die jede sortierte Pipeline verwendet, um ihre Hilfsfelder für die Position der Nullwerte zu entfernen.
- **Felder ohne Beachtung der Groß- und Kleinschreibung** werden zu einer Collation auf Abfrageebene kompiliert (`locale: "en"`, `strength: 2`). Ein Index bedient eine Abfrage mit Collation
  nur, wenn er mit derselben Collation angelegt wurde: `createIndex({ customer: 1 }, { collation: { locale: "en", strength: 2 } })`.
- **`contains`, `startsWith`, `endsWith`** werden zu einem maskierten `$regex` kompiliert (MongoDB hat keinen Teilzeichenfolgen-Operator, der mit Collations zusammenarbeitet). Ein regulärer Ausdruck nutzt einen
  collationssensitiven Index nicht so wie eine Gleichheit; rechnen Sie daher auf einer großen Collection mit einem vollständigen Scan und
  messen Sie.
- **Sortierung.** Die Sortierung erfolgt nach berechneten Hilfsfeldern, die die Position der Nullwerte enthalten, sodass kein Index sie als Ganzes bedient; indizieren Sie Ihre
  Filter ([Null ordering](semantics.html#sem-3)).
- **Gruppierungsabfragen vergleichen unter Beachtung der Groß- und Kleinschreibung.** MongoDB hat nur eine Collation pro Abfrage. Eine Gruppierungsabfrage muss ihre
  Gruppen exakt halten; ihre Pipeline trägt daher keine Collation, und ein Benutzerfilter in derselben Abfrage vergleicht unter Beachtung der Groß- und Kleinschreibung
  (die akzeptierte Abweichung Nr. 3 von GRP-2). Die anderen Datenbanken ignorieren in diesem Filter die Groß- und Kleinschreibung.

## OpenSearch und Elasticsearch {#opensearch-and-elasticsearch}

Ein einziger Compiler bedient beide. Das Index-Mapping ist Ihre Sache, und die kompilierten Abfragen nennen die Unterfelder, die Ihr Schema deklariert.

- **Version:** Elasticsearch 7.10 oder neuer, OpenSearch 1.0 oder neuer (für `case_insensitive` auf `term` und `wildcard`).
- **`keyword`-Unterfeld, leise in einem Filter.** Jedes gefilterte, sortierte oder gruppierte Textfeld verlangt das `keyword`-Unterfeld,
  das Sie als `physical.search.keywordSubField` deklariert haben, ein Multi-Field im Index-Mapping. Fehlt es, findet ein Filter darauf
  **keine Zeile**, ohne Fehler; nur eine Sortierung darauf schlägt fehl.
- **Sortierung und Bereich ohne Beachtung der Groß- und Kleinschreibung.** Deklarieren Sie `physical.search.normalizedSubField` und bilden Sie es als `keyword` mit einem
  `normalizer` ab, der die Groß- und Kleinschreibung ignoriert. Das kostet Indexplatz und ist der einzige Weg, ein Textfeld ohne Beachtung der Groß- und Kleinschreibung zu sortieren oder zu vergleichen; der Compiler
  weigert sich, eine solche Abfrage für ein Feld zu kompilieren, das keines deklariert.
- **Dezimalzahlen.** Bilden Sie ein `decimal`-Feld als `scaled_float` mit ausreichendem `scaling_factor` ab, oder als `keyword`, wenn Sie es nur auf
  Gleichheit vergleichen. Ein `double`-Mapping rundet stillschweigend.
- **Tiefes Paging und Gesamtzahlen.** Jenseits von `max_result_window` (10,000 Zeilen) paginiert der Client mit einem Point-in-Time und `search_after`;
  setzen Sie `Flavour` auf `Elasticsearch` **sowohl** in den Optionen für tiefes Paging **als auch** in den Export-Optionen für Elasticsearch, sonst schlägt jeder Export
  mit einem HTTP-400-Fehler fehl. Die Gesamtzahl der Zeilen jenseits von 10,000 wird als unbekannt gemeldet, es sei denn,
  Sie wählen die exakte Zählung, die bei jeder ersten Abfrage jeden Treffer zählt.
- **`contains`** ist ein Platzhalter auf dem Feld `keyword`; ein führender Platzhalter durchläuft das Term-Wörterbuch, messen Sie ihn daher auf großen Indizes.

## Was diese Seite nicht behandelt {#what-stays-out-of-this-page}

Das engine-spezifische Tuning (Partitionen, abdeckende Indizes, Anzahl der Shards) hängt von Ihren Daten und Ihrer Last ab. Die kompilierten Anweisungen liegen in
den [Konformitäts-Fixtures](../../spec/fixtures/), ein Ordner pro Fall, mit dem
genauen Text, den jede Datenbank erhält; führen Sie `EXPLAIN` darauf auf Ihren eigenen Tabellen aus.
