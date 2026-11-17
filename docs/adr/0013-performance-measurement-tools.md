# ADR-0013: Performance is measured with BenchmarkDotNet, a standard-library load script and a generated page

Status: Accepted   Date: 2026-11-16
Work items: #3324, #3845, #3846, #3847, #3848, #3849   Classification: Public

The maintainer accepted this record on 2026-11-16 as project lead and technical lead (solo mode), after entering BenchmarkDotNet in the approved stack record (#3845, commit 2f021b7f). Between 2026-11-15 and that entry the story used the library with the maintainer's agreement. It names no private path or host.

## Context

- The TRD sets a target of under 50 microseconds to compile a typical request (PERF-1), "benchmarked, not enforced". Nothing was ever measured, and the public launch needs numbers a reader can check (FR-17 to FR-20, NFR-08).
- The public demos refuse more than 60 requests a minute per address, so a load test cannot run against them.
- The approved stack record lists "a .NET benchmark library" and "a load-test tool" as not chosen. A new tool needs the Engineering Lead's approval and a licence check.

## Decision

- **Compile time:** BenchmarkDotNet 0.15.8 (MIT) in `csharp/tools/Craticula.Benchmarks`. It reaches the conformance driver's compile entry point through `InternalsVisibleTo`, so there is one copy of the pipeline and no execution adapter is referenced (AR-3). The named shapes are conformance fixtures, so they are the requests the compilers are already graded on.
- **Load:** one Python script, `perf/load.py`, standard library only, against the demo API on a throwaway local stack without public mode, at 10 thousand and 1 million rows, for PostgreSQL and MongoDB. Python is already approved, so no new tool is needed.
- **Evidence:** raw results under `perf/results/<date>/` with a manifest per run (machine label, versions, load, date, commit, the command that repeats it). The site page is generated from those files by `scripts/perf_page.py`, so no number is typed by hand and every number links to its raw file. A repeat run must be within 10% (`perf/compare.py`). *Superseded by NFR-08 (2026-11-17): the repeat is reported as a measured spread, `perf/compare.py` lists the differences and exits 0, and there is no fixed percentage.*
- The numbers are reported whether or not PERF-1 is met. Nothing is tuned to reach a number.

## Alternatives

- **A hand-written timing harness (Stopwatch):** no new package, but warm-up, outliers and allocation measurement would be ours and the numbers less trusted.
- **k6 or bombardier:** better precision at very high rates and a new external binary to approve and pin. The demo API does not need that precision.
- **A hand-written page:** quicker, but a number copied by hand can drift from its raw result, which FR-20 forbids.

## Consequences

- Positive: repeatable, linked numbers; no new binary beyond one NuGet package.
- Negative: BenchmarkDotNet adds a large transitive dependency tree to `csharp/tools` (licence gate: 0 failures at 161 packages). Python's thread-based load script limits the rate it can generate, which is enough for the demo API.
- Follow-up: none for the tools. The first measurement ran on 2026-11-16 (#3848).

## Compliance

- Third-party library: the Engineering Lead's approval (`compliance.md` §4) is the maintainer's entry in the approved stack record (#3845). No PII: the seed is synthetic. No secret: the throwaway database uses the demo's public development password.
- Published files carry a machine label chosen by the maintainer, never the host name or an absolute path; the scripts refuse both.
