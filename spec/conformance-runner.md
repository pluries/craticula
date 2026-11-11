# Conformance runner — the contract between the fixture suite and an implementation

This file defines how any implementation of this spec — the C# reference today, the TypeScript, Python and Go ports
later (ML-1) — is graded against [`fixtures/`](fixtures/README.md). It is the operational form of TRD **T-1** tier (a),
*artifact equality*, and of **ML-3**'s requirement that every implementation produce byte-comparable artifacts.

It defines **two programs and the protocol between them**:

- **the runner** — one program for every language. It reads the fixture tree, sends each case to a driver, compares
  the answer with the expected artifact, and reports. It lives in `conformance/` at the repository root.
- **a driver** — one small program per implementation. It compiles what it is sent and prints the result. It never
  reads the fixture tree, never compares anything, and knows nothing about the fixture layout.

Adding a language means writing a driver. The runner does not change.

## 1. What this tier grades, and what it does not

**Graded:** every `expected/<backend>.artifact.json` in the fixture tree, for the backends the driver declares (§6).

**Not graded here**, and listed by the runner as *out of tier* so that nobody mistakes silence for a pass:

| Fixture content | Why not | Graded by |
|---|---|---|
| `expected/rejection.json` (SEC-6) | a rejection is not a compiled artifact; it has its own shape and stage | the implementation's own tests today; a later tier |
| `rowStream.json` + `expected/export.csv` / `.tsv` (EXP-4) | compares writer output bytes, not a compiled query | the implementation's own tests today; a later tier |
| `dataset.json` / `expectedRows.json` (T-1b, `semantics.md` XEQ-1..XEQ-4) | execution equality needs a seeded database to run | Feature #1624, integration tier |

The listing goes by content, not by directory: a fixture that carries both an expected artifact and writer output has
its artifact graded and its writer output listed. A fixture directory with none of the graded files is reported as out
of tier; `schemas/` is not a category and is skipped.

## 2. The protocol

The runner starts the driver as a child process (the command is given to the runner, never hard-coded) and talks to it
over **JSON Lines**: UTF-8, one JSON object per line, `\n`-terminated, on the driver's stdin and stdout. Anything a
driver wants to log goes to **stderr**, which the runner passes through and never parses.

### 2.1 Hello — the driver speaks first

The driver's first stdout line declares what it is and what it can compile:

```json
{"hello":{"impl":"csharp","specVersion":"0.1.0","backends":["postgres","mssql","mysql","oracle","sqlite","mongo","search"]}}
```

- `impl` — a free label shown in the report.
- `specVersion` — the version of this spec the implementation claims (TRD P-2). Echoed in the report, not validated:
  the suite has no version number yet. The version of this spec lives in `spec/VERSION`, and that is the value implementations claim.
- `backends` — a non-empty subset of the closed set `postgres`, `mssql`, `mysql`, `oracle`, `sqlite`, `mongo`, `search`
  (the file stems under `expected/`). `search` is the one shared OpenSearch/Elasticsearch artifact (OQ-7).

### 2.2 Requests and responses

After the hello, the runner writes one request per line and reads one response per line, **one at a time, in order**:

```json
{"id":"operators/001-eq-string#postgres","backend":"postgres","schema":{…},"agGridRequest":{…}}
```

- `id` — `<category>/<NNN-slug>#<backend>`, unique in the session. The driver echoes it and must not interpret it.
- `schema` — the parsed content of the fixture's `schema.json`.
- `agGridRequest` — the parsed content of the fixture's `agGridRequest.json`, unchanged.

The driver answers with exactly one of:

```json
{"id":"operators/001-eq-string#postgres","artifact":{…}}
{"id":"operators/001-eq-string#postgres","error":{"kind":"<free label>","message":"<text>"}}
```

`artifact` is the compiled artifact in the shape `fixtures/schemas/<…>-artifact.schema.json` defines for that backend —
the same JSON the expected file holds. `error` means the implementation refused or failed to compile; for a graded case
that is a failure (§6), never a skip.

### 2.3 End of session

When every request is answered, the runner closes the driver's stdin. The driver exits with status 0.

### 2.4 Protocol failures

Each of these stops the run with **exit status 2** (§7) and lists the requests left unanswered (none after a failed
hello: the graded set depends on the backends the hello declares):

1. no hello, or a first line that is not a valid hello;
2. a stdout line that is not a single JSON object;
3. a response whose `id` is not the one the runner is waiting for (unknown, repeated, or out of order);
4. no hello within the **timeout** of the driver starting, or no response within the timeout of the request being
   written — **30 seconds** unless the runner is given another (§9);
5. the driver exiting before the session ends, or with a non-zero status.

When a run stops, the runner ends the driver **and every process the driver started**: a driver command is often a
launcher (`dotnet run`, `npx`, `go run`, a wrapper script) whose child must not outlive the run.

## 3. What a driver does with a request

A driver compiles the request exactly as a host application would, with the following inputs pinned so that every
implementation compiles the same thing:

- **Schema** — `schema` is the host's `GridSchema` (`grid-schema.schema.json`), applied as is.
- **Resource limits** — the SEC-3 defaults of the TRD, and for a set-values request the default and maximum value
  counts of **GRP-6**(d). A driver does not raise or lower them.
- **Clock** — when `agGridRequest.requestContext.now` is present, the driver pins its clock to that instant. This is the
  harness rule of **SEM-4**: `now` is a harness instruction that a production adapter must never read from the wire; the
  driver is the harness, so it does. When `now` is absent the driver keeps its normal clock: a fixture whose artifact
  depends on the current instant always carries `now`.
- **Query time limit** — when `agGridRequest.requestContext.maxQueryTimeMs` is present, the driver sets the host's maximum
  query time to that many milliseconds (TL-4). Like `now`, it is a harness instruction that a production parser never
  reads; a top-level `maxQueryTimeMs` on the request is not the harness input and is ignored. Absent, no limit is configured.
- **Page defaults** — `agGridRequest.requestContext.defaultPageSize` (a whole number) sets the host's default page size, and
  `requestContext.allowUnboundedRows: true` sets the host's switch for `ignorePageLimit` (PG-1, PG-3). Like `now`, they are
  harness instructions that a production parser never reads from the wire. Absent, the defaults are 100 and off.
- **Zone** — `requestContext.zone`, when present, is read as SEM-4 prescribes for any request.
- **Entry point** — a request with a top-level `setValuesRequest` member is a set-values request (BM-3) and goes through
  that entry point; every other request is a row request.
- **Export** — a request carrying the export wire members (`exportFormat`, with `exportScope` and `exportColumns`,
  EXP-1) compiles with the unpaginated page (EXP-2) and names its output columns (EXP-1(b)), as it would in a host.
- **Backend** — `backend` picks the compiler and, for SQL, the dialect.

The driver then prints the artifact for that backend. It does not normalise, sort or pretty-print it to look like the
expected file; the runner's comparison (§4) decides what is significant.

## 4. Equality

The runner parses both sides keeping **object key order** and **the literal text of every number**, then compares by
backend. The rules below are not new: each one points at the rule that already pins the artifact's form.

| Backend | Compared | Pinned by |
|---|---|---|
| `postgres`, `mssql`, `mysql`, `oracle`, `sqlite` | the three members `dialect`, `sql` and `params`, each by value: `sql` character for character, `params` element by element in order; the order of the three members in the wrapper object is not significant | the canonical SQL rendering, SQL-0..SQL-8 in `semantics.md` |
| `mongo` | the whole artifact exactly, **object key order included** | MDB-7 and the MongoDB addendum (a `$sort` document's key order is its tiebreak order) |
| `search` | objects compared as **unordered maps** (the same keys, each with an equal value, in any order); arrays element by element **in order** | OSE-0 |

**Numbers compare by their text.** `19.99` and `"19.99"` differ (a JSON number is not a string, whatever it spells),
and so do `1` and `1.0`. An implementation prints the value its compiler produced, in the type the expected artifact
uses; it does not reformat it.

**ML-3's "modulo parameter naming style"** has no effect on this suite: the canonical rendering fixes each dialect's
placeholder spelling (`$1`, `@p1`, `:p1`, `?`), so a different spelling is a different `sql` string and fails.

## 5. Report

For each failure the runner prints the `id`, the first JSON path where the two sides differ (e.g.
`$.pipeline[2].$match.status`), and the expected and actual values at that path. It then prints totals per backend:
passed, failed, not graded, and the out-of-tier count. `--json <file>` writes the same content as JSON for tools.

## 6. Coverage — what counts as a pass

- The **graded set** is every expected artifact whose backend the driver declared.
- A graded case **fails** if the artifact differs (§4) or the driver answered `error`.
- A backend the driver did not declare is reported as **not graded**, with its case count. It is never counted as passed.
- The runner only sends cases that have an expected artifact, so an implementation cannot be graded on a case the
  suite does not define.
- A run whose graded set is **empty** never passes: nothing selected (an empty tree, or an `--only` that matches no
  expected artifact, §9), or no selected case in a backend the driver declared. It exits 2 (§7).

## 7. Exit status

| Status | Meaning |
|---|---|
| 0 | every graded case passed |
| 1 | at least one graded case failed |
| 2 | protocol failure (§2.4), usage error (bad arguments, unreadable fixture tree), or an empty graded set (§6) |

## 8. Writing a driver

In any language, a driver is this loop:

```text
print {"hello": {impl, specVersion, backends}}
for each line on stdin:
    req = parse(line)
    try:
        artifact = compile(req.schema, req.agGridRequest, req.backend)   # §3 inputs pinned
        print {"id": req.id, "artifact": artifact}
    except any failure as e:
        print {"id": req.id, "error": {"kind": name(e), "message": text(e)}}
    flush stdout
exit 0
```

A session, abridged (`→` runner to driver, `←` driver to runner):

```text
← {"hello":{"impl":"csharp","specVersion":"0.1.0","backends":["postgres","mongo","search"]}}
→ {"id":"operators/001-eq-string#postgres","backend":"postgres","schema":{…},"agGridRequest":{…}}
← {"id":"operators/001-eq-string#postgres","artifact":{"dialect":"postgres","sql":"SELECT …","params":["Alice"]}}
→ {"id":"operators/001-eq-string#mongo","backend":"mongo","schema":{…},"agGridRequest":{…}}
← {"id":"operators/001-eq-string#mongo","artifact":[{"$match":{…}},…]}
  (stdin closed; driver exits 0)
```

Flush after every response: a buffered driver looks hung and hits the timeout (§2.4).

## 9. Running the runner

```text
python3 conformance/run.py --driver "<command>" [--fixtures <dir>] [--only <glob>]… [--json <file>] [--timeout <seconds>]
```

| Option | Meaning |
|---|---|
| `--driver` | Required. The command that starts the driver. No shell is involved: on POSIX the runner splits it like a shell line, on Windows it hands it to the operating system as is (so `C:\…\driver.exe` keeps its backslashes). |
| `--fixtures` | The fixture tree. Default: `spec/fixtures` of the repository the runner sits in. |
| `--only` | Narrows the run to the cases whose id matches the glob — `<category>/<NNN-slug>` selects a fixture, `<category>/<NNN-slug>#<backend>` one case. Repeatable. A narrowed run is a debugging aid, not a conformance claim: conformance is the run over the whole tree. |
| `--json` | Writes the report of §5 as JSON as well. |
| `--timeout` | The limit of §2.4 item 4, in seconds. Default 30. |
