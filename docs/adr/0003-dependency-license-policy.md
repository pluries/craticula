# ADR-0003: Dependencies must carry an allowlisted license, checked in CI

Status: Proposed (Engineering Lead approval pending)   Date: 2026-10-16
Work items: #1626, #1664   Classification: Public

## Context
Craticula is published under Apache-2.0 and its compile-only core has no runtime dependencies (AR-3). The adapters, test
projects and tooling do depend on packages, and a copyleft or source-available license in that tree would put obligations
on users of the library or block commercial use. TRD OS-6 already lists which licenses are acceptable and names two known
traps, but nothing enforces it: a pull request that adds `MySql.Data` (GPL-2.0) would merge today. `compliance.md` section 4
requires approval for each new library; a written policy that a tool checks makes that approval repeatable.

## Decision
The license policy of TRD OS-6 is adopted as written and enforced by `nuget-license` on every `PackageReference` under
`csharp/`, test projects included.

- **Allowed:** MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, 0BSD, Unlicense, PostgreSQL, Zlib.
- **Case by case:** MPL-2.0, only when an ADR names the package and the reason. Without that ADR the check fails.
- **Denied:** GPL, LGPL, AGPL, SSPL, BUSL, Elastic License, Commons Clause, and any "non-commercial" clause.
- **Named traps:** `MySql.Data` is rejected by name with the message "use MySqlConnector". `Oracle.ManagedDataAccess.Core`
  (Oracle's free-use terms, free but not open source) is accepted in **test projects only**, today
  `csharp/tests/Craticula.Integration.Tests` (story #2880, approved in the tech stack on 2026-10-22), and never in a package
  under `csharp/src/`, so it cannot reach a user of the library. It is flagged in the docs that name it. An Oracle adapter
  package would need its own decision.
- **Out of the check:** `examples/demo` follows ADR 0002.
- **Overrides:** a package whose license the tool misreads gets an entry in an overrides file
  (`scripts/license-overrides.json`), with a written reason per entry and the exact version, so an upgrade re-opens the review.
  An entry without a reason, or one that matches no package, fails the check. The first real run (2026-10-23, `nuget-license`
  4.0.18) needed three, all in test projects and none in a shipped package:
  - `Oracle.ManagedDataAccess.Core` 23.26.301, the named trap above (license file, Oracle's free-use terms).
  - `Microsoft.Data.SqlClient.SNI.runtime` 7.1.0: Microsoft's native runtime that `Microsoft.Data.SqlClient` (MIT) pulls in for
    the integration tests. It declares a license file (Microsoft Software License Terms: free to use, redistributable runtime),
    not an SPDX id. Accepted as a reviewed exception, test projects only.
  - `xunit.abstractions` 2.0.3: declares only a license URL; the xunit project is Apache-2.0.

The same check runs in the public repository's workflow and in the maintainer's pull request pipeline, so a dependency is
caught before it reaches `main` on either side. A failure names the package and the license it found.

## Alternatives considered
- **Review licenses by hand when a dependency is added** — it depends on someone remembering and leaves no record.
- **Denylist only** — a new or unusual license would pass silently. An allowlist fails safe.
- **Check only on the public repository** — the maintainer's own pull requests would merge unchecked, because they are made
  on the private repository first.
- **Check only the packages that ship** — test and tooling licenses matter less, but the tool cannot tell them apart without
  extra configuration, and today every such package is permissive. Revisit if a useful test-only package needs a denied license.

## Consequences
- Positive: a denied license fails the build with a clear message; the policy is written once and the same on both sides.
- Negative: the allowlist and overrides file need upkeep; a tool outage fails the pull request check (never a release,
  NFR-04 of the governance spec).
- Follow-ups: story #1664 builds the check; the ISMS change request for the new tooling covers it; a later TypeScript, Python or
  Go port adds its own checker (`license-checker`, `pip-licenses`, `go-licenses`) under this policy.

## Compliance
| Control | Impact | Approver | Status |
|---|---|---|---|
| New dependency / tooling (`compliance.md` §4) | `nuget-license` runs in CI | Engineering Lead | pending |
| Security or data design | none; no data, no secret | Security Officer | not needed |
| New environment / tooling (ISMS change request) | new checks in two pipelines | Security Officer | pending, drafted with the governance feature |
| AI model / provider / prompt architecture | none | n/a | n/a |
