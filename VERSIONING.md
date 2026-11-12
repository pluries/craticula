# Versioning

Craticula uses [Semantic Versioning](https://semver.org): `MAJOR.MINOR.PATCH`.

## Two versions

- The **spec version** is written in [`spec/VERSION`](spec/VERSION). It versions the specification: the IR schema,
  the semantics and the conformance fixtures. Each implementation states the spec version it passes.
- The **package version** is the version of the .NET packages. All ten packages share one version number.

The two move separately. The compatibility table in the [README](README.md#compatibility) shows the spec version on
`main`, which the next release implements. The notes of each release state the spec version that release was built with.
The latest published package version is on nuget.org.

## What drives the package version

- The package version follows the public API of the packages and the spec version they implement.
- It never follows the version of a dependency. A new major of AG Grid, a database driver or any other library does
  not change our version by itself.

## What is a breaking change

One rule decides the bump. A change is breaking, and needs a new major version, when it does any of these:

- It removes or changes a public type or member, so that code that compiled before no longer compiles.
- It changes the shape of the compiled artifact (the SQL text and parameters, the MongoDB pipeline or the search query)
  for the same request and schema: its structure, the order of its parameters, or the meaning of a field.
- It changes an error kind: a request that was accepted is rejected, or the other way round, or a rejection now has a
  different kind.

A spec change that alters the generated text or the semantics without changing the shape (for example a typed cast or a
rendering fix) is a minor version. A change is a patch only when the output for every valid request is unchanged.

## What the public contract covers

Besides the types and the compiled artifacts, the contract includes the request shapes the adapter accepts: the Server-Side
Row Model requests of AG Grid v31 to v36 and the flat requests AG Grid Community's Infinite Row Model sends (sort, text,
number and date filters, paging). Dropping support for one of those shapes is a breaking change, like any other
accepted request that becomes rejected.

## Adapters and provider majors

Each adapter package declares a version range for the library it wraps: the current major, with the lowest version
we have tested as the floor. It never pins one exact version.

When a provider ships a new major:

- Widen the range to include it.
- If our public API survives unchanged, bump the minor version.
- If our public API has to change, bump the major version.
- Publish parallel package lines only when both provider majors must be supported at the same time.

## Tags and commits

- A release is tagged `dotnet-vX.Y.Z`.
- The release job proposes a version from the latest public tag. The maintainer who approves the release confirms it or types another,
  following the rule above.

## The conformance fixture suite

The fixture suite is versioned by the spec version. The release notes also show how many fixtures the suite holds.
That number is a count, not a version.

## Recorded exceptions

An exception is a release that does not follow the rule above. Each one is written down here, with the reason, and the release notes say so.

- **1.2.0 (default page size).** (1.1.0 was published on 2026-11-12 from an older public commit and holds only dependency updates; this is the release that carries the feature.) From this release a request with no row window gets a default page of 100 rows instead of every
  row, and the paged entry points of the adapters refuse the unpaginated page with an error that names the streaming entry point.
  Under the rule above that is a new major version, because the compiled artifact for such a request changes. The maintainer chose a
  minor version: AG Grid's Server-Side Row Model always sends a window, an export of everything is unchanged, and only a custom client
  or a host that builds the request by hand could notice. A host that relied on "no window means every row" asks for it on purpose: an
  export, or `ignorePageLimit` once the host has allowed it (`AgGridParseOptions.AllowUnboundedRows`).
