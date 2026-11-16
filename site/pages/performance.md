# Performance

These are measurements of Craticula on one machine, not promises. Nothing here changes how Craticula behaves: the only hard limit on the demos is the two second query cut-off. Every number links to the raw result it came from, and each run lists the command that repeats it.

Measured on bench-vm-10c-34g.

## Compile time

Compiling a request means parsing it, checking it against the schema and building the query. Nothing is executed. The specification sets a target of under 50 µs per typical request (PERF-1). The target is benchmarked, not enforced, and the results below say plainly whether it is met. 3 of 12 measured compile times are not under the target.

| Backend | Request shape | Mean time | Allocated per request | PERF-1 |
|---|---|---|---|---|
| mongo | deep-filter | [39.5 µs](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [17.7 KiB](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| postgres | deep-filter | [36.1 µs](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [13.4 KiB](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| search | deep-filter | [38.6 µs](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [17.8 KiB](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| mongo | filter-tree | [42.9 µs](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [17.7 KiB](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| postgres | filter-tree | [40.4 µs](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [13.9 KiB](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| search | filter-tree | [40.3 µs](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [15.2 KiB](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| mongo | group-aggregate | [54.1 µs](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [17.2 KiB](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | does not meet PERF-1 |
| postgres | group-aggregate | [51.0 µs](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [15.1 KiB](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | does not meet PERF-1 |
| search | group-aggregate | [52.1 µs](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [15.0 KiB](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | does not meet PERF-1 |
| mongo | plain-page | [21.3 µs](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [10.7 KiB](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| postgres | plain-page | [17.6 µs](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [6.9 KiB](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |
| search | plain-page | [17.3 µs](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | [6.6 KiB](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) | meets PERF-1 |

## Load on the demo API

A load test posts a mix of grid requests to the demo API on a local stack, without the public rate limit. The table shows latency percentiles and requests per second for each engine and data size.

| Engine | Rows | p50 | p95 | p99 | Throughput | Failed |
|---|---|---|---|---|---|---|
| PostgreSQL through EF Core | 10k | [23.5 ms](../../perf/results/2026-11-16/manifest-ef-10k.json) | [44.9 ms](../../perf/results/2026-11-16/manifest-ef-10k.json) | [67.5 ms](../../perf/results/2026-11-16/manifest-ef-10k.json) | [308.2 /s](../../perf/results/2026-11-16/manifest-ef-10k.json) | [0](../../perf/results/2026-11-16/manifest-ef-10k.json) |
| MongoDB | 10k | [60.8 ms](../../perf/results/2026-11-16/manifest-mongo-10k.json) | [114.8 ms](../../perf/results/2026-11-16/manifest-mongo-10k.json) | [161.6 ms](../../perf/results/2026-11-16/manifest-mongo-10k.json) | [120.2 /s](../../perf/results/2026-11-16/manifest-mongo-10k.json) | [0](../../perf/results/2026-11-16/manifest-mongo-10k.json) |
| PostgreSQL | 10k | [21.9 ms](../../perf/results/2026-11-16/manifest-postgres-10k.json) | [47.7 ms](../../perf/results/2026-11-16/manifest-postgres-10k.json) | [68.8 ms](../../perf/results/2026-11-16/manifest-postgres-10k.json) | [320.0 /s](../../perf/results/2026-11-16/manifest-postgres-10k.json) | [0](../../perf/results/2026-11-16/manifest-postgres-10k.json) |
| PostgreSQL through EF Core | 1m | [1279.4 ms](../../perf/results/2026-11-16/manifest-ef-1m.json) | [2683.8 ms](../../perf/results/2026-11-16/manifest-ef-1m.json) | [3416.4 ms](../../perf/results/2026-11-16/manifest-ef-1m.json) | [5.6 /s](../../perf/results/2026-11-16/manifest-ef-1m.json) | [0](../../perf/results/2026-11-16/manifest-ef-1m.json) |
| MongoDB | 1m | [4289.3 ms](../../perf/results/2026-11-16/manifest-mongo-1m.json) | [8410.6 ms](../../perf/results/2026-11-16/manifest-mongo-1m.json) | [8693.0 ms](../../perf/results/2026-11-16/manifest-mongo-1m.json) | [1.6 /s](../../perf/results/2026-11-16/manifest-mongo-1m.json) | [0](../../perf/results/2026-11-16/manifest-mongo-1m.json) |
| PostgreSQL | 1m | [1123.0 ms](../../perf/results/2026-11-16/manifest-postgres-1m.json) | [2677.3 ms](../../perf/results/2026-11-16/manifest-postgres-1m.json) | [3966.4 ms](../../perf/results/2026-11-16/manifest-postgres-1m.json) | [6.1 /s](../../perf/results/2026-11-16/manifest-postgres-1m.json) | [0](../../perf/results/2026-11-16/manifest-postgres-1m.json) |

## Repeatability

Every measurement was taken twice on the same machine, in two runs one after the other. The target is that the second run lands within 10% of the first.

29 of 36 measurements of the repeat run are within 10% of this run. These 7 are not, so read them with that spread in mind:

- compile mongo/plain-page mean: [21.3 µs](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json) then [24.2 µs](../../perf/results/2026-11-16-repeat/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json), 13.7% apart
- load mongo 1m p95: [8410.6 ms](../../perf/results/2026-11-16/manifest-mongo-1m.json) then [9472.5 ms](../../perf/results/2026-11-16-repeat/manifest-mongo-1m.json), 12.6% apart
- load mongo 1m p99: [8693.0 ms](../../perf/results/2026-11-16/manifest-mongo-1m.json) then [9796.2 ms](../../perf/results/2026-11-16-repeat/manifest-mongo-1m.json), 12.7% apart
- load postgres 10k p50: [21.9 ms](../../perf/results/2026-11-16/manifest-postgres-10k.json) then [19.5 ms](../../perf/results/2026-11-16-repeat/manifest-postgres-10k.json), 11.0% apart
- load postgres 10k p95: [47.7 ms](../../perf/results/2026-11-16/manifest-postgres-10k.json) then [41.0 ms](../../perf/results/2026-11-16-repeat/manifest-postgres-10k.json), 14.0% apart
- load postgres 10k p99: [68.8 ms](../../perf/results/2026-11-16/manifest-postgres-10k.json) then [56.1 ms](../../perf/results/2026-11-16-repeat/manifest-postgres-10k.json), 18.5% apart
- load postgres 10k requests per second: [320.0 /s](../../perf/results/2026-11-16/manifest-postgres-10k.json) then [362.6 /s](../../perf/results/2026-11-16-repeat/manifest-postgres-10k.json), 13.3% apart

## How each result was produced

### Compile benchmark

- Machine: bench-vm-10c-34g
- Tool: BenchmarkDotNet 0.15.8 on .NET 10.0.404
- Date: 2026-11-16, commit a5b2356
- Raw result: [BenchmarkDotNet report](../../perf/results/2026-11-16/compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json)

To repeat it:

```
bash scripts/perf-compile.sh perf/results/2026-11-16/compile
```

### PostgreSQL through EF Core, 10k rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: postgres (PostgreSQL) 16.16 (Debian 16.16-1.pgdg13+1) through Npgsql.EntityFrameworkCore.PostgreSQL 10.0.3
- Load: 8 threads for 60 seconds
- Date: 2026-11-16, commit a5b2356
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16/manifest-ef-10k.json), [every request](../../perf/results/2026-11-16/load-ef-10k.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_OUT=perf/results/2026-11-16 bash scripts/perf-load.sh ef 10k
```

### MongoDB, 10k rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: MongoDB 7.0.48
- Load: 8 threads for 60 seconds
- Date: 2026-11-16, commit a5b2356
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16/manifest-mongo-10k.json), [every request](../../perf/results/2026-11-16/load-mongo-10k.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_OUT=perf/results/2026-11-16 bash scripts/perf-load.sh mongo 10k
```

### PostgreSQL, 10k rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: postgres (PostgreSQL) 16.16 (Debian 16.16-1.pgdg13+1)
- Load: 8 threads for 60 seconds
- Date: 2026-11-16, commit a5b2356
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16/manifest-postgres-10k.json), [every request](../../perf/results/2026-11-16/load-postgres-10k.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_OUT=perf/results/2026-11-16 bash scripts/perf-load.sh postgres 10k
```

### PostgreSQL through EF Core, 1m rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: postgres (PostgreSQL) 16.16 (Debian 16.16-1.pgdg13+1) through Npgsql.EntityFrameworkCore.PostgreSQL 10.0.3
- Load: 8 threads for 60 seconds
- Date: 2026-11-16, commit a5b2356
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16/manifest-ef-1m.json), [every request](../../perf/results/2026-11-16/load-ef-1m.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_OUT=perf/results/2026-11-16 bash scripts/perf-load.sh ef 1m
```

### MongoDB, 1m rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: MongoDB 7.0.48
- Load: 8 threads for 60 seconds
- Date: 2026-11-16, commit a5b2356
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16/manifest-mongo-1m.json), [every request](../../perf/results/2026-11-16/load-mongo-1m.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_OUT=perf/results/2026-11-16 bash scripts/perf-load.sh mongo 1m
```

### PostgreSQL, 1m rows

- Machine: bench-vm-10c-34g (Linux 7.0.0-43-generic, 10 logical CPUs, Python 3.14.4)
- Engine: postgres (PostgreSQL) 16.16 (Debian 16.16-1.pgdg13+1)
- Load: 8 threads for 60 seconds
- Date: 2026-11-16, commit a5b2356
- Oversized request: answered 400 with resource-limit-exceeded
- Raw results: [manifest](../../perf/results/2026-11-16/manifest-postgres-1m.json), [every request](../../perf/results/2026-11-16/load-postgres-1m.jsonl)

To repeat it:

```
PERF_MACHINE=bench-vm-10c-34g PERF_CONCURRENCY=8 PERF_DURATION=60 PERF_OUT=perf/results/2026-11-16 bash scripts/perf-load.sh postgres 1m
```
