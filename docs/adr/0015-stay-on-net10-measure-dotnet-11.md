# ADR-0015: Stay on net10.0; measure .NET 11 and review after .NET 12

Status: Accepted   Date: 2026-11-27
Work items: #4054, Epic #4051

Classification: Public

## Context

.NET 11 (11.0.100) is released as an STS release. Microsoft supports it until 2028-11-14, the same day it stops supporting .NET 10 LTS.
The stack rule says an STS release is adopted only through an ADR that names the upgrade date. Every project here targets `net10.0`,
the SDK is pinned to 10.0.100, and the EF Core major is held on the 10.0 line in `dependabot.yml`.

The code was built and tested on SDK 11.0.100, and the record of that is the run record `sdk11-run.md` (kept with feature 010, not published):

- On SDK 11 with the target unchanged (`net10.0`): restore in locked mode, a `-warnaserror` build with 0 warnings and 0 errors, and the
  whole offline suite (7,373 tests) passes.
- As `net11.0`, including the adapters and the EF Core 10 packages: 0 warnings and 0 errors.
- On the 11.0.0 runtime, with `net11.0` binaries and with the `net10.0` binaries rolled forward, one test fails: `IsIsoInstant` accepts
  `2026-01-01T24:00:00Z`, because `DateTimeOffset.TryParse` accepts the hour 24 on that runtime. It is the runtime's behaviour, so an
  application on .NET 11 gets it from today's `net10.0` packages too.

## Decision

Stay on net10.0 only: every project keeps `net10.0`, the SDK pin stays 10.0.100, and no `net11.0` target is added. An application on .NET 11
can already use the `net10.0` packages, and the build and test results above show nothing that a second target would fix. The stance is
reviewed on 2027-12-01 because .NET 12, the next LTS, is expected in November 2027 and both .NET 10 and .NET 11 end support on
2028-11-14, so the next real move is to .NET 12, not to 11. If a reason appears earlier (a package that needs a `net11.0` asset, or a
security fix that ships only for 11), this ADR is reopened then.

## Alternatives

- **Multi-target `net10.0` and `net11.0` for the six core packages.** Why not: the measurements show no gain. The code builds and passes
  as `net10.0` on SDK 11, a `net11.0` app consumes a `net10.0` package, and the one runtime difference appears with either target. It would
  double the build and test matrix, change `global.json`, CI and the lock files, and add a package asset per library, for no user who cannot use the current one.
- **Move to net11.0.** Why not: it drops users on .NET 10 LTS, which has the same support end date,
  and it ties the packages to an STS release. The adapters would also have to leave the held EF Core 10 line.

## Consequences

Positive: no change to the build or the packages; users on .NET 10 and .NET 11 are served by the same assets; the open question has a
dated answer and evidence behind it.

Negative: the packages carry no `net11.0` asset, so a future API only .NET 11 offers cannot be used until the stance is reopened. One
behaviour on the .NET 11 runtime (`T24:00`) is wrong today and needs a code fix (follow-up F-1).

Compliance impact: none. No personal data, no new service, no new dependency.

## Consequences by project

Every project under `csharp/` and `examples/` keeps `net10.0`. The "verified" notes come from the SDK 11 record.

| Project | Kind | Target under this decision | Note |
|---|---|---|---|
| Craticula.Core | src | net10.0 | no change; the one runtime difference is in `IsIsoInstant` (follow-up F-1) |
| Craticula.AgGrid | src | net10.0 | no change; verified on the 11 runtime |
| Craticula.Sql | src | net10.0 | no change; verified on the 11 runtime |
| Craticula.Mongo | src | net10.0 | no change; verified on the 11 runtime |
| Craticula.Search | src | net10.0 | no change; verified on the 11 runtime |
| Craticula.Export.Csv | src | net10.0 | no change; verified on the 11 runtime |
| Craticula.EntityFrameworkCore | src | net10.0 | no change; builds as `net11.0` with the EF Core 10 packages; the Dependabot hold on the EF Core major stays (below) |
| Craticula.Dapper | src | net10.0 | no change; verified on the 11 runtime |
| Craticula.MongoDB.Driver | src | net10.0 | no change; builds as `net11.0`; its live tests were not run |
| Craticula.OpenSearch.Client | src | net10.0 | no change; builds as `net11.0`; its live tests were not run |
| Craticula.Conformance.Driver | tools | net10.0 | no change; the conformance run uses it |
| Craticula.Benchmarks | tools | net10.0 | no change; benchmark figures are per runtime and are not compared here |
| Craticula.Quickstart | samples | net10.0 | no change |
| Craticula.Quickstart.Mongo | samples | net10.0 | no change |
| Craticula.Quickstart.Search | samples | net10.0 | no change |
| Craticula.AgGrid.Tests | tests | net10.0 | follows its package |
| Craticula.Benchmarks.Tests | tests | net10.0 | follows its tool |
| Craticula.Conformance.Tests | tests | net10.0 | follows the driver |
| Craticula.Core.Tests | tests | net10.0 | follows its package; holds the one failing test on the 11 runtime |
| Craticula.Dapper.Tests | tests | net10.0 | follows its package |
| Craticula.EntityFrameworkCore.Tests | tests | net10.0 | follows its package |
| Craticula.Export.Csv.Tests | tests | net10.0 | follows its package |
| Craticula.Integration.Tests | tests | net10.0 | follows the adapters |
| Craticula.Mongo.Tests | tests | net10.0 | follows its package |
| Craticula.MongoDB.Driver.Offline.Tests | tests | net10.0 | follows its package |
| Craticula.MongoDB.Driver.Tests | tests | net10.0 | follows its package; needs a live MongoDB |
| Craticula.OpenSearch.Client.Offline.Tests | tests | net10.0 | follows its package |
| Craticula.OpenSearch.Client.Tests | tests | net10.0 | follows its package; needs a live OpenSearch |
| Craticula.Search.Tests | tests | net10.0 | follows its package |
| Craticula.Sql.Tests | tests | net10.0 | follows its package |
| Demo.Api | demo | net10.0 | no change; the demo image uses the `10.0` SDK and runtime images (Dockerfile follow-up) |
| Demo.Api.Tests | demo | net10.0 | follows the demo |

Dependabot: the hold on the EF Core major (`Microsoft.EntityFrameworkCore.Relational`, `Microsoft.EntityFrameworkCore.Sqlite`,
`Microsoft.Data.Sqlite`) stays, because the adapters stay on `net10.0` and the 10.0 release line; it is reviewed on 2027-12-01 with this ADR.
`Craticula.Dapper` and `Craticula.EntityFrameworkCore` need nothing from feature 011 under this stance beyond the F-1 fix, which
touches `Craticula.Core`.

## Follow-ups

None of these is done by this ADR; each names the file that mentions .NET 10 today.

- **F-1** Refuse the hour `24` in `FilterNodeValidator.IsIsoInstant` (and any other place that relies on `DateTimeOffset.TryParse` to refuse
  `T24:00`), with a test that passes on the 10 and the 11 runtime. Feature 011 takes it; a published fix is a patch version.
- **F-2** Add a build-and-test job on SDK 11 with `DOTNET_ROLL_FORWARD=LatestMajor` (informational, not a gate) so the next .NET 11 servicing
  release shows a new difference early. It touches `.github/workflows/ci.yml` and the Jenkins agent images (outside this repository).
- Files that name .NET 10 and stay as they are: `csharp/global.json`, `csharp/Directory.Build.props`, `.github/workflows/ci.yml`,
  `.github/workflows/license-check.yml`, `.github/workflows/nuget-publish.yml`, `.github/dependabot.yml`, `deploy/demo/Dockerfile`
  (the SDK and runtime images are pinned by digest), and `tech-stack.approved.md` (the approved-stack record).
- Approved-stack entry: none needed for this stance. A move later needs the .NET 11 SDK and the 11 images added to the approved stack record.

## Compliance

No security, personal-data or AI control is touched. Written `Accepted` by the maintainer in solo mode (no approval is pending).
The ADR names no private path, host or credential.
