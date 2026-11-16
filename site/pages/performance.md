# Performance

These are measurements of Craticula on one machine, not promises. Nothing here changes how Craticula behaves: the only hard limit on the demos is the two second query cut-off. Every number links to the raw result it came from, and each run lists the command that repeats it.

Measured on bench-vm-10c-34g.

## Compile time

Compiling a request means parsing it, checking it against the schema and building the query. Nothing is executed. The specification sets a target of under 50 µs per typical request (PERF-1). The target is benchmarked, not enforced, and the results below say plainly whether it is met. 4 of 12 measured compile times are not under the target.

| Backend | Request shape | Mean time | Allocated per request | PERF-1 |
|---|---|---|---|---|
| mongo | deep-filter | [45.3 µs](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [17.7 KiB](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| postgres | deep-filter | [42.4 µs](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [13.4 KiB](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| search | deep-filter | [42.4 µs](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [17.8 KiB](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| mongo | filter-tree | [53.1 µs](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [17.7 KiB](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | does not meet PERF-1 |
| postgres | filter-tree | [44.1 µs](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [13.9 KiB](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| search | filter-tree | [44.3 µs](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [15.2 KiB](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| mongo | group-aggregate | [61.5 µs](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [17.2 KiB](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | does not meet PERF-1 |
| postgres | group-aggregate | [59.2 µs](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [15.1 KiB](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | does not meet PERF-1 |
| search | group-aggregate | [62.2 µs](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [15.0 KiB](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | does not meet PERF-1 |
| mongo | plain-page | [23.7 µs](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [10.7 KiB](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| postgres | plain-page | [17.4 µs](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [6.9 KiB](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| search | plain-page | [16.4 µs](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [6.6 KiB](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |

## Load on the demo API

A load test posts a mix of grid requests to the demo API on a local stack, without the public rate limit. The table shows latency percentiles and requests per second for each engine and data size.

| Engine | Rows | p50 | p95 | p99 | Throughput | Failed |
|---|---|---|---|---|---|---|
| PostgreSQL through EF Core | 10k | [22.3 ms](../../perf/results/2026-11-16-w/manifest-ef-10k.json) | [40.4 ms](../../perf/results/2026-11-16-w/manifest-ef-10k.json) | [54.1 ms](../../perf/results/2026-11-16-w/manifest-ef-10k.json) | [331.7 /s](../../perf/results/2026-11-16-w/manifest-ef-10k.json) | [0](../../perf/results/2026-11-16-w/manifest-ef-10k.json) |
| MongoDB | 10k | [52.0 ms](../../perf/results/2026-11-16-w/manifest-mongo-10k.json) | [97.2 ms](../../perf/results/2026-11-16-w/manifest-mongo-10k.json) | [132.6 ms](../../perf/results/2026-11-16-w/manifest-mongo-10k.json) | [139.8 /s](../../perf/results/2026-11-16-w/manifest-mongo-10k.json) | [0](../../perf/results/2026-11-16-w/manifest-mongo-10k.json) |
| PostgreSQL | 10k | [17.8 ms](../../perf/results/2026-11-16-w/manifest-postgres-10k.json) | [40.2 ms](../../perf/results/2026-11-16-w/manifest-postgres-10k.json) | [53.0 ms](../../perf/results/2026-11-16-w/manifest-postgres-10k.json) | [381.7 /s](../../perf/results/2026-11-16-w/manifest-postgres-10k.json) | [0](../../perf/results/2026-11-16-w/manifest-postgres-10k.json) |
| PostgreSQL through EF Core | 1m | [1159.6 ms](../../perf/results/2026-11-16-w/manifest-ef-1m.json) | [2861.7 ms](../../perf/results/2026-11-16-w/manifest-ef-1m.json) | [3196.1 ms](../../perf/results/2026-11-16-w/manifest-ef-1m.json) | [5.8 /s](../../perf/results/2026-11-16-w/manifest-ef-1m.json) | [0](../../perf/results/2026-11-16-w/manifest-ef-1m.json) |
| MongoDB | 1m | [4475.3 ms](../../perf/results/2026-11-16-w/manifest-mongo-1m.json) | [9225.9 ms](../../perf/results/2026-11-16-w/manifest-mongo-1m.json) | [9408.9 ms](../../perf/results/2026-11-16-w/manifest-mongo-1m.json) | [1.4 /s](../../perf/results/2026-11-16-w/manifest-mongo-1m.json) | [0](../../perf/results/2026-11-16-w/manifest-mongo-1m.json) |
| PostgreSQL | 1m | [1085.6 ms](../../perf/results/2026-11-16-w/manifest-postgres-1m.json) | [2364.5 ms](../../perf/results/2026-11-16-w/manifest-postgres-1m.json) | [3387.1 ms](../../perf/results/2026-11-16-w/manifest-postgres-1m.json) | [6.5 /s](../../perf/results/2026-11-16-w/manifest-postgres-1m.json) | [0](../../perf/results/2026-11-16-w/manifest-postgres-1m.json) |

## One client at a time

The table above has 8 clients sending requests at once on the same machine, so at 1 million rows it includes waiting. These runs use one client, so each number is what a single request costs on an otherwise idle server.

| Engine | Rows | p50 | p95 | p99 | Throughput | Failed |
|---|---|---|---|---|---|---|
| PostgreSQL through EF Core | 10k | [12.0 ms](../../perf/results/2026-11-16-w-single/manifest-ef-10k.json) | [17.2 ms](../../perf/results/2026-11-16-w-single/manifest-ef-10k.json) | [20.7 ms](../../perf/results/2026-11-16-w-single/manifest-ef-10k.json) | [83.7 /s](../../perf/results/2026-11-16-w-single/manifest-ef-10k.json) | [0](../../perf/results/2026-11-16-w-single/manifest-ef-10k.json) |
| MongoDB | 10k | [25.9 ms](../../perf/results/2026-11-16-w-single/manifest-mongo-10k.json) | [43.9 ms](../../perf/results/2026-11-16-w-single/manifest-mongo-10k.json) | [50.3 ms](../../perf/results/2026-11-16-w-single/manifest-mongo-10k.json) | [35.0 /s](../../perf/results/2026-11-16-w-single/manifest-mongo-10k.json) | [0](../../perf/results/2026-11-16-w-single/manifest-mongo-10k.json) |
| PostgreSQL | 10k | [7.7 ms](../../perf/results/2026-11-16-w-single/manifest-postgres-10k.json) | [18.1 ms](../../perf/results/2026-11-16-w-single/manifest-postgres-10k.json) | [21.5 ms](../../perf/results/2026-11-16-w-single/manifest-postgres-10k.json) | [103.0 /s](../../perf/results/2026-11-16-w-single/manifest-postgres-10k.json) | [0](../../perf/results/2026-11-16-w-single/manifest-postgres-10k.json) |
| PostgreSQL through EF Core | 1m | [320.2 ms](../../perf/results/2026-11-16-w-single/manifest-ef-1m.json) | [433.2 ms](../../perf/results/2026-11-16-w-single/manifest-ef-1m.json) | [481.8 ms](../../perf/results/2026-11-16-w-single/manifest-ef-1m.json) | [3.3 /s](../../perf/results/2026-11-16-w-single/manifest-ef-1m.json) | [0](../../perf/results/2026-11-16-w-single/manifest-ef-1m.json) |
| MongoDB | 1m | [1915.0 ms](../../perf/results/2026-11-16-w-single/manifest-mongo-1m.json) | [3437.4 ms](../../perf/results/2026-11-16-w-single/manifest-mongo-1m.json) | [3461.8 ms](../../perf/results/2026-11-16-w-single/manifest-mongo-1m.json) | [0.4 /s](../../perf/results/2026-11-16-w-single/manifest-mongo-1m.json) | [0](../../perf/results/2026-11-16-w-single/manifest-mongo-1m.json) |
| PostgreSQL | 1m | [301.3 ms](../../perf/results/2026-11-16-w-single/manifest-postgres-1m.json) | [603.2 ms](../../perf/results/2026-11-16-w-single/manifest-postgres-1m.json) | [637.3 ms](../../perf/results/2026-11-16-w-single/manifest-postgres-1m.json) | [2.6 /s](../../perf/results/2026-11-16-w-single/manifest-postgres-1m.json) | [0](../../perf/results/2026-11-16-w-single/manifest-postgres-1m.json) |

## Repeatability

Every measurement was taken twice on the same machine, in two runs one after the other. The target is that the second run lands within 10% of the first.

30 of 36 measurements of the repeat run are within 10% of this run. These 6 are not, so read them with that spread in mind:

- compile mongo/plain-page mean: [23.7 µs](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) then [21.3 µs](../../perf/results/2026-11-16-w-repeat/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json), 10.4% apart
- compile postgres/filter-tree mean: [44.1 µs](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) then [50.3 µs](../../perf/results/2026-11-16-w-repeat/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json), 14.2% apart
- compile search/filter-tree mean: [44.3 µs](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) then [48.8 µs](../../perf/results/2026-11-16-w-repeat/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json), 10.1% apart
- load mongo 1m p95: [9225.9 ms](../../perf/results/2026-11-16-w/manifest-mongo-1m.json) then [7774.5 ms](../../perf/results/2026-11-16-w-repeat/manifest-mongo-1m.json), 15.7% apart
- load mongo 1m p99: [9408.9 ms](../../perf/results/2026-11-16-w/manifest-mongo-1m.json) then [8099.1 ms](../../perf/results/2026-11-16-w-repeat/manifest-mongo-1m.json), 13.9% apart
- load postgres 10k p99: [53.0 ms](../../perf/results/2026-11-16-w/manifest-postgres-10k.json) then [62.1 ms](../../perf/results/2026-11-16-w-repeat/manifest-postgres-10k.json), 17.0% apart

## How each result was produced

### Compile benchmark

- Machine: bench-vm-10c-34g
- Tool: BenchmarkDotNet 0.15.8 on .NET 10.0.404
- Date: 2026-11-16, commit ec955387
- Raw result: [BenchmarkDotNet report](../../perf/results/2026-11-16-w/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json)

To repeat it:

```
bash scripts/perf-compile.sh perf/results/2026-11-16-w/compile
```

### PostgreSQL through EF Core, 10k rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: postgres (PostgreSQL) 16.16 (Debian 16.16-1.pgdg13+1) through Npgsql.EntityFrameworkCore.PostgreSQL 10.0.3
- Load: 8 threads for 60 seconds, after 5 seconds of warm-up that were not measured
- Date: 2026-11-16, commit ec955387
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16-w/manifest-ef-10k.json), [every request](../../perf/results/2026-11-16-w/load-ef-10k.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_WARMUP=5 PERF_OUT=perf/results/2026-11-16-w bash scripts/perf-load.sh ef 10k
```

### MongoDB, 10k rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: MongoDB 7.0.48
- Load: 8 threads for 60 seconds, after 5 seconds of warm-up that were not measured
- Date: 2026-11-16, commit ec955387
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16-w/manifest-mongo-10k.json), [every request](../../perf/results/2026-11-16-w/load-mongo-10k.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_WARMUP=5 PERF_OUT=perf/results/2026-11-16-w bash scripts/perf-load.sh mongo 10k
```

### PostgreSQL, 10k rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: postgres (PostgreSQL) 16.16 (Debian 16.16-1.pgdg13+1)
- Load: 8 threads for 60 seconds, after 5 seconds of warm-up that were not measured
- Date: 2026-11-16, commit ec955387
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16-w/manifest-postgres-10k.json), [every request](../../perf/results/2026-11-16-w/load-postgres-10k.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_WARMUP=5 PERF_OUT=perf/results/2026-11-16-w bash scripts/perf-load.sh postgres 10k
```

### PostgreSQL through EF Core, 1m rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: postgres (PostgreSQL) 16.16 (Debian 16.16-1.pgdg13+1) through Npgsql.EntityFrameworkCore.PostgreSQL 10.0.3
- Load: 8 threads for 60 seconds, after 5 seconds of warm-up that were not measured
- Date: 2026-11-16, commit ec955387
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16-w/manifest-ef-1m.json), [every request](../../perf/results/2026-11-16-w/load-ef-1m.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_WARMUP=5 PERF_OUT=perf/results/2026-11-16-w bash scripts/perf-load.sh ef 1m
```

### MongoDB, 1m rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: MongoDB 7.0.48
- Load: 8 threads for 60 seconds, after 5 seconds of warm-up that were not measured
- Date: 2026-11-16, commit ec955387
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16-w/manifest-mongo-1m.json), [every request](../../perf/results/2026-11-16-w/load-mongo-1m.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_WARMUP=5 PERF_OUT=perf/results/2026-11-16-w bash scripts/perf-load.sh mongo 1m
```

### PostgreSQL, 1m rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: postgres (PostgreSQL) 16.16 (Debian 16.16-1.pgdg13+1)
- Load: 8 threads for 60 seconds, after 5 seconds of warm-up that were not measured
- Date: 2026-11-16, commit ec955387
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16-w/manifest-postgres-1m.json), [every request](../../perf/results/2026-11-16-w/load-postgres-1m.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_WARMUP=5 PERF_OUT=perf/results/2026-11-16-w bash scripts/perf-load.sh postgres 1m
```
