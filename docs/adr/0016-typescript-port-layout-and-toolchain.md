# ADR-0016: Where the TypeScript port lives and how it is built

Status: Accepted   Date: 2026-11-27
Work items: #4056, Epic #4051

Classification: Public

## Context

The ports implement the frozen spec (1.0.0) and are graded by the same conformance runner as the C# code. Before the real port starts,
a walking skeleton (a conformance driver for one fixture family on PostgreSQL) has to settle the questions every later TypeScript
feature builds on: where the code lives, how it is released, which Node it needs, which module format, which tools, and how many
dependencies. Each answer is hard to change once a package is on npm, so they are written down now.

## Decision

- **Layout:** one repository, a `typescript/` folder next to `csharp/`, as the README plans. A single history keeps the spec, the
  fixtures, the runner and every implementation changing together, because the spec is the source of truth for all of them.
- **Tags:** TypeScript releases are tagged `ts-vX.Y.Z`. The C# tags stay `dotnet-vX.Y.Z`. Each ecosystem has its own prefix because a
  release job and a version number belong to one ecosystem, and a Go module in a subfolder needs its own prefix later anyway.
- **Minimum runtime:** Node 22. It is a maintained LTS line, the CI runs it and the newest LTS (Node 24 today), and the decision is
  reviewed by 2027-03-31, before Node 22 leaves maintenance in April 2027, because a minimum below a supported line costs the port
  compatibility work for no user.
- **Module format:** ES modules only (`"type": "module"`, `NodeNext`). A second CommonJS build doubles the packaging and the test
  matrix; whether the published package also ships CommonJS is decided with the first npm release.
- **Toolchain:** the TypeScript compiler in strict mode, and Node's built-in `node:test` runner. No bundler, no test framework,
  because every added tool is another dependency to audit, and the compiler and the runner Node ships do what the port needs.
- **Dependencies:** no runtime dependency, and at most three development dependencies, pinned exactly in `package.json` and in the lock
  file; installs run from the lock file (`npm ci`) without lifecycle scripts. The library handles untrusted requests and sits close to
  a database, so the supply chain stays as short as it can be. Dependabot watches `/typescript` with the same two-week cooldown as the
  other ecosystems.
- **Name:** the skeleton package is private and named `craticula-typescript-skeleton`. The public name and scope are decided with the
  first release, because a published name is a promise that cannot be taken back; nothing is registered now.

## Alternatives

- **A separate repository for the TypeScript port.** Why not: the spec, the fixtures and the runner would live in another place from
  the code they grade, and every spec change would need two pull requests.
- **CommonJS, or both formats, from the start.** Why not: it is the larger packaging and test surface, and the skeleton is not a
  package anyone installs.
- **A test framework such as Vitest or Jest, or a bundler.** Why not: each brings many transitive dependencies, which the dependency policy above rules out for a
  library with this exposure.
- **A lower Node minimum (20).** Why not: it is past the maintained lines the CI would test.

## Consequences

Positive: one place and one toolchain for the TypeScript features; a short, auditable supply chain; the questions the feature map listed
for 012 are answered.

Negative: no CommonJS consumers until the first release decides it; the minimum Node needs a review before April 2027; the choice of a
single repository means the TypeScript CI shares the workflow file with the C# one.

Follow-ups: the public package name and scope, provenance and the npm release job (feature 017), the compiler and request adapter
(features 013 to 016), and promoting the `typescript` job to a required check.

## Compliance

No personal data and no secret. A new ecosystem enters the approved stack record (npm and the TypeScript development dependencies, with
licences). Written `Accepted` by the maintainer in solo mode (no approval is pending).
