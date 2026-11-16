# Performance

These are measurements of Craticula on one machine, not promises. Nothing here changes how Craticula behaves: the only hard limit on the demos is the two second query cut-off. Every number links to the raw result it came from, and each run lists the command that repeats it.

Measured on bench-vm-10c-34g.

## Compile time

Compiling a request means parsing it, checking it against the schema and building the query. Nothing is executed. The specification sets a target of under 50 µs per typical request (PERF-1). The target is benchmarked, not enforced, and the results below say plainly whether it is met.

The table has two paths. **Full compile** parses the schema from JSON on every call, as the conformance driver does, because it receives the schema as text with each request. **Prepared schema** uses a schema built once, which is what a host does: it builds its schema once and compiles every request against it. The second is what a host pays per request. On the full compile path, 3 of 12 measured compile times are not under the target. On the prepared schema path, every measured compile time is under the target.

| Backend | Request shape | Full compile | Allocated | PERF-1 | Prepared schema | Allocated | PERF-1 |
|---|---|---|---|---|---|---|---|
| mongo | deep-filter | [37.5 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [17.7 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 | [26.8 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [15.0 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| postgres | deep-filter | [35.2 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [13.4 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 | [23.3 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [10.7 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| search | deep-filter | [37.5 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [17.8 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 | [25.5 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [15.1 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| mongo | filter-tree | [42.6 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [17.7 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 | [18.8 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [12.4 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| postgres | filter-tree | [38.9 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [13.9 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 | [15.8 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [8.6 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| search | filter-tree | [40.7 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [15.2 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 | [16.6 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [9.9 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| mongo | group-aggregate | [53.1 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [17.2 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | does not meet PERF-1 | [13.9 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [10.0 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| postgres | group-aggregate | [51.9 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [15.1 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | does not meet PERF-1 | [12.3 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [7.8 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| search | group-aggregate | [52.3 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [15.0 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | does not meet PERF-1 | [12.5 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [7.8 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| mongo | plain-page | [20.5 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [10.7 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 | [9.7 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [8.0 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| postgres | plain-page | [17.2 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [6.9 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 | [7.3 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [4.1 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| search | plain-page | [17.0 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [6.6 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 | [7.0 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [3.8 KiB](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |

## Load on the demo API

A load test posts a mix of grid requests to the demo API on a local stack, without the public rate limit. The table shows latency percentiles and requests per second for each engine and data size.

| Engine | Rows | p50 | p95 | p99 | Throughput | Failed |
|---|---|---|---|---|---|---|
| PostgreSQL through EF Core | 10k | [22.0 ms](../../perf/results/2026-11-16-p/manifest-ef-10k.json) | [42.3 ms](../../perf/results/2026-11-16-p/manifest-ef-10k.json) | [59.8 ms](../../perf/results/2026-11-16-p/manifest-ef-10k.json) | [330.6 /s](../../perf/results/2026-11-16-p/manifest-ef-10k.json) | [0](../../perf/results/2026-11-16-p/manifest-ef-10k.json) |
| MongoDB | 10k | [57.9 ms](../../perf/results/2026-11-16-p/manifest-mongo-10k.json) | [108.0 ms](../../perf/results/2026-11-16-p/manifest-mongo-10k.json) | [149.4 ms](../../perf/results/2026-11-16-p/manifest-mongo-10k.json) | [126.0 /s](../../perf/results/2026-11-16-p/manifest-mongo-10k.json) | [0](../../perf/results/2026-11-16-p/manifest-mongo-10k.json) |
| PostgreSQL | 10k | [18.5 ms](../../perf/results/2026-11-16-p/manifest-postgres-10k.json) | [39.0 ms](../../perf/results/2026-11-16-p/manifest-postgres-10k.json) | [52.7 ms](../../perf/results/2026-11-16-p/manifest-postgres-10k.json) | [381.1 /s](../../perf/results/2026-11-16-p/manifest-postgres-10k.json) | [0](../../perf/results/2026-11-16-p/manifest-postgres-10k.json) |
| PostgreSQL through EF Core | 1m | [1209.3 ms](../../perf/results/2026-11-16-p/manifest-ef-1m.json) | [2639.7 ms](../../perf/results/2026-11-16-p/manifest-ef-1m.json) | [3512.5 ms](../../perf/results/2026-11-16-p/manifest-ef-1m.json) | [5.6 /s](../../perf/results/2026-11-16-p/manifest-ef-1m.json) | [0](../../perf/results/2026-11-16-p/manifest-ef-1m.json) |
| MongoDB | 1m | [4183.5 ms](../../perf/results/2026-11-16-p/manifest-mongo-1m.json) | [7860.7 ms](../../perf/results/2026-11-16-p/manifest-mongo-1m.json) | [7970.5 ms](../../perf/results/2026-11-16-p/manifest-mongo-1m.json) | [1.5 /s](../../perf/results/2026-11-16-p/manifest-mongo-1m.json) | [0](../../perf/results/2026-11-16-p/manifest-mongo-1m.json) |
| PostgreSQL | 1m | [1148.3 ms](../../perf/results/2026-11-16-p/manifest-postgres-1m.json) | [2532.0 ms](../../perf/results/2026-11-16-p/manifest-postgres-1m.json) | [3480.9 ms](../../perf/results/2026-11-16-p/manifest-postgres-1m.json) | [6.2 /s](../../perf/results/2026-11-16-p/manifest-postgres-1m.json) | [0](../../perf/results/2026-11-16-p/manifest-postgres-1m.json) |

## One client at a time

The table above has 8 clients sending requests at once on the same machine, so at 1 million rows it includes waiting. These runs use one client, so each number is what a single request costs on an otherwise idle server.

| Engine | Rows | p50 | p95 | p99 | Throughput | Failed |
|---|---|---|---|---|---|---|
| PostgreSQL through EF Core | 10k | [11.8 ms](../../perf/results/2026-11-16-p-single/manifest-ef-10k.json) | [16.6 ms](../../perf/results/2026-11-16-p-single/manifest-ef-10k.json) | [19.6 ms](../../perf/results/2026-11-16-p-single/manifest-ef-10k.json) | [85.5 /s](../../perf/results/2026-11-16-p-single/manifest-ef-10k.json) | [0](../../perf/results/2026-11-16-p-single/manifest-ef-10k.json) |
| MongoDB | 10k | [26.0 ms](../../perf/results/2026-11-16-p-single/manifest-mongo-10k.json) | [43.4 ms](../../perf/results/2026-11-16-p-single/manifest-mongo-10k.json) | [52.1 ms](../../perf/results/2026-11-16-p-single/manifest-mongo-10k.json) | [34.8 /s](../../perf/results/2026-11-16-p-single/manifest-mongo-10k.json) | [0](../../perf/results/2026-11-16-p-single/manifest-mongo-10k.json) |
| PostgreSQL | 10k | [9.3 ms](../../perf/results/2026-11-16-p-single/manifest-postgres-10k.json) | [23.5 ms](../../perf/results/2026-11-16-p-single/manifest-postgres-10k.json) | [32.9 ms](../../perf/results/2026-11-16-p-single/manifest-postgres-10k.json) | [83.2 /s](../../perf/results/2026-11-16-p-single/manifest-postgres-10k.json) | [0](../../perf/results/2026-11-16-p-single/manifest-postgres-10k.json) |
| PostgreSQL through EF Core | 1m | [294.5 ms](../../perf/results/2026-11-16-p-single/manifest-ef-1m.json) | [428.9 ms](../../perf/results/2026-11-16-p-single/manifest-ef-1m.json) | [483.5 ms](../../perf/results/2026-11-16-p-single/manifest-ef-1m.json) | [3.3 /s](../../perf/results/2026-11-16-p-single/manifest-ef-1m.json) | [0](../../perf/results/2026-11-16-p-single/manifest-ef-1m.json) |
| MongoDB | 1m | [1949.4 ms](../../perf/results/2026-11-16-p-single/manifest-mongo-1m.json) | [3422.1 ms](../../perf/results/2026-11-16-p-single/manifest-mongo-1m.json) | [3429.6 ms](../../perf/results/2026-11-16-p-single/manifest-mongo-1m.json) | [0.4 /s](../../perf/results/2026-11-16-p-single/manifest-mongo-1m.json) | [0](../../perf/results/2026-11-16-p-single/manifest-mongo-1m.json) |
| PostgreSQL | 1m | [366.8 ms](../../perf/results/2026-11-16-p-single/manifest-postgres-1m.json) | [633.0 ms](../../perf/results/2026-11-16-p-single/manifest-postgres-1m.json) | [763.4 ms](../../perf/results/2026-11-16-p-single/manifest-postgres-1m.json) | [2.5 /s](../../perf/results/2026-11-16-p-single/manifest-postgres-1m.json) | [0](../../perf/results/2026-11-16-p-single/manifest-postgres-1m.json) |

## Repeatability

Every measurement was taken twice on the same machine, in two runs one after the other. The target is that the second run lands within 10% of the first.

27 of 48 measurements of the repeat run are within 10% of this run. These 21 are not, so read them with that spread in mind:

- compile mongo/group-aggregate mean: [53.1 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) then [62.4 µs](../../perf/results/2026-11-16-p-repeat/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json), 17.6% apart
- compile mongo/group-aggregate prepared mean: [13.9 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) then [16.4 µs](../../perf/results/2026-11-16-p-repeat/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json), 18.1% apart
- compile postgres/group-aggregate mean: [51.9 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) then [58.8 µs](../../perf/results/2026-11-16-p-repeat/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json), 13.3% apart
- compile postgres/group-aggregate prepared mean: [12.3 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) then [13.9 µs](../../perf/results/2026-11-16-p-repeat/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json), 13.1% apart
- compile postgres/plain-page prepared mean: [7.3 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) then [8.0 µs](../../perf/results/2026-11-16-p-repeat/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json), 10.5% apart
- compile search/filter-tree prepared mean: [16.6 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) then [19.5 µs](../../perf/results/2026-11-16-p-repeat/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json), 17.1% apart
- compile search/group-aggregate prepared mean: [12.5 µs](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) then [13.9 µs](../../perf/results/2026-11-16-p-repeat/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json), 11.5% apart
- load ef 10k p50: [22.0 ms](../../perf/results/2026-11-16-p/manifest-ef-10k.json) then [30.2 ms](../../perf/results/2026-11-16-p-repeat/manifest-ef-10k.json), 37.0% apart
- load ef 10k p95: [42.3 ms](../../perf/results/2026-11-16-p/manifest-ef-10k.json) then [65.4 ms](../../perf/results/2026-11-16-p-repeat/manifest-ef-10k.json), 54.6% apart
- load ef 10k p99: [59.8 ms](../../perf/results/2026-11-16-p/manifest-ef-10k.json) then [118.3 ms](../../perf/results/2026-11-16-p-repeat/manifest-ef-10k.json), 98.1% apart
- load ef 10k requests per second: [330.6 /s](../../perf/results/2026-11-16-p/manifest-ef-10k.json) then [229.6 /s](../../perf/results/2026-11-16-p-repeat/manifest-ef-10k.json), 30.6% apart
- load mongo 10k p50: [57.9 ms](../../perf/results/2026-11-16-p/manifest-mongo-10k.json) then [64.4 ms](../../perf/results/2026-11-16-p-repeat/manifest-mongo-10k.json), 11.3% apart
- load mongo 10k p95: [108.0 ms](../../perf/results/2026-11-16-p/manifest-mongo-10k.json) then [127.1 ms](../../perf/results/2026-11-16-p-repeat/manifest-mongo-10k.json), 17.7% apart
- load mongo 10k p99: [149.4 ms](../../perf/results/2026-11-16-p/manifest-mongo-10k.json) then [190.7 ms](../../perf/results/2026-11-16-p-repeat/manifest-mongo-10k.json), 27.6% apart
- load mongo 10k requests per second: [126.0 /s](../../perf/results/2026-11-16-p/manifest-mongo-10k.json) then [112.5 /s](../../perf/results/2026-11-16-p-repeat/manifest-mongo-10k.json), 10.8% apart
- load mongo 1m p95: [7860.7 ms](../../perf/results/2026-11-16-p/manifest-mongo-1m.json) then [9126.0 ms](../../perf/results/2026-11-16-p-repeat/manifest-mongo-1m.json), 16.1% apart
- load mongo 1m p99: [7970.5 ms](../../perf/results/2026-11-16-p/manifest-mongo-1m.json) then [9608.1 ms](../../perf/results/2026-11-16-p-repeat/manifest-mongo-1m.json), 20.5% apart
- load postgres 10k p50: [18.5 ms](../../perf/results/2026-11-16-p/manifest-postgres-10k.json) then [20.8 ms](../../perf/results/2026-11-16-p-repeat/manifest-postgres-10k.json), 12.4% apart
- load postgres 10k p95: [39.0 ms](../../perf/results/2026-11-16-p/manifest-postgres-10k.json) then [48.3 ms](../../perf/results/2026-11-16-p-repeat/manifest-postgres-10k.json), 23.7% apart
- load postgres 10k p99: [52.7 ms](../../perf/results/2026-11-16-p/manifest-postgres-10k.json) then [74.4 ms](../../perf/results/2026-11-16-p-repeat/manifest-postgres-10k.json), 41.2% apart
- load postgres 10k requests per second: [381.1 /s](../../perf/results/2026-11-16-p/manifest-postgres-10k.json) then [328.5 /s](../../perf/results/2026-11-16-p-repeat/manifest-postgres-10k.json), 13.8% apart

## How each result was produced

### Compile benchmark

- Machine: bench-vm-10c-34g
- Tool: BenchmarkDotNet 0.15.8 on .NET 10.0.404
- Date: 2026-11-16, commit 2e9c4d67
- Raw result: [BenchmarkDotNet report](../../perf/results/2026-11-16-p/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json)

To repeat it:

```
bash scripts/perf-compile.sh perf/results/2026-11-16-p/compile
```

### PostgreSQL through EF Core, 10k rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: postgres (PostgreSQL) 16.16 (Debian 16.16-1.pgdg13+1) through Npgsql.EntityFrameworkCore.PostgreSQL 10.0.3
- Load: 8 threads for 60 seconds, after 5 seconds of warm-up that were not measured
- Date: 2026-11-16, commit 2e9c4d67
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16-p/manifest-ef-10k.json), [every request](../../perf/results/2026-11-16-p/load-ef-10k.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_WARMUP=5 PERF_OUT=perf/results/2026-11-16-p bash scripts/perf-load.sh ef 10k
```

### MongoDB, 10k rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: MongoDB 7.0.48
- Load: 8 threads for 60 seconds, after 5 seconds of warm-up that were not measured
- Date: 2026-11-16, commit 2e9c4d67
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16-p/manifest-mongo-10k.json), [every request](../../perf/results/2026-11-16-p/load-mongo-10k.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_WARMUP=5 PERF_OUT=perf/results/2026-11-16-p bash scripts/perf-load.sh mongo 10k
```

### PostgreSQL, 10k rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: postgres (PostgreSQL) 16.16 (Debian 16.16-1.pgdg13+1)
- Load: 8 threads for 60 seconds, after 5 seconds of warm-up that were not measured
- Date: 2026-11-16, commit 2e9c4d67
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16-p/manifest-postgres-10k.json), [every request](../../perf/results/2026-11-16-p/load-postgres-10k.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_WARMUP=5 PERF_OUT=perf/results/2026-11-16-p bash scripts/perf-load.sh postgres 10k
```

### PostgreSQL through EF Core, 1m rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: postgres (PostgreSQL) 16.16 (Debian 16.16-1.pgdg13+1) through Npgsql.EntityFrameworkCore.PostgreSQL 10.0.3
- Load: 8 threads for 60 seconds, after 5 seconds of warm-up that were not measured
- Date: 2026-11-16, commit 2e9c4d67
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16-p/manifest-ef-1m.json), [every request](../../perf/results/2026-11-16-p/load-ef-1m.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_WARMUP=5 PERF_OUT=perf/results/2026-11-16-p bash scripts/perf-load.sh ef 1m
```

### MongoDB, 1m rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: MongoDB 7.0.48
- Load: 8 threads for 60 seconds, after 5 seconds of warm-up that were not measured
- Date: 2026-11-16, commit 2e9c4d67
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16-p/manifest-mongo-1m.json), [every request](../../perf/results/2026-11-16-p/load-mongo-1m.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_WARMUP=5 PERF_OUT=perf/results/2026-11-16-p bash scripts/perf-load.sh mongo 1m
```

### PostgreSQL, 1m rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: postgres (PostgreSQL) 16.16 (Debian 16.16-1.pgdg13+1)
- Load: 8 threads for 60 seconds, after 5 seconds of warm-up that were not measured
- Date: 2026-11-16, commit 2e9c4d67
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16-p/manifest-postgres-1m.json), [every request](../../perf/results/2026-11-16-p/load-postgres-1m.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_WARMUP=5 PERF_OUT=perf/results/2026-11-16-p bash scripts/perf-load.sh postgres 1m
```
