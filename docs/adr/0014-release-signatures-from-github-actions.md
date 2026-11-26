# ADR-0014: Sigstore signatures for the release packages come from a separate GitHub Actions workflow

Status: Accepted   Date: 2026-11-25
Work items: #4029

Classification: Public

## Context

The OpenSSF Scorecard of the public mirror scores `Signed-Releases` 0 of 10. The packages are signed (ADR-0005, ADR-0011: an author
signature inside each `.nupkg`, made on the maintainer's Windows agent), but Scorecard cannot see inside a package. It looks for a signature or
provenance file among the assets of each GitHub release: `.sig`, `.asc`, `.sigstore.json` and similar, or `.intoto.jsonl`.

Constraints that already apply:

- ADR-0010 and ADR-0012: `nuget-publish.yml` has three jobs in a chain, the maintainer approves the environment `nuget`, and its tests pin
  that shape. The `publish` job holds the only OIDC token and runs no repository code. Adding a job there changes a pinned design.
- ADR-0011: the author signature is made with the maintainer's Certum certificate. No key for it exists in GitHub.
- A signature of the repository's own workflow can vouch for bytes. It cannot say who built them, and it must not claim to.

## Decision

A new workflow, `.github/workflows/release-signatures.yml`, runs after `NuGet publish` succeeds on `main` (`workflow_run`). It finds the
release for that run's tag from the run title, downloads the ten `Craticula.*.nupkg` assets, signs each with Sigstore keyless signing
(`cosign sign-blob --bundle`, the workflow's GitHub OIDC identity) and uploads one `<package>.nupkg.sigstore.json` bundle per package to
the same release. It checks out nothing and runs no repository code. Its permissions are `contents: write` (upload the assets) and
`id-token: write` (Sigstore). `nuget-publish.yml` is not changed.

A reader verifies a package with `cosign verify-blob --bundle <file>.sigstore.json --certificate-identity
https://github.com/pluries/craticula/.github/workflows/release-signatures.yml@refs/heads/main --certificate-oidc-issuer
https://token.actions.githubusercontent.com <file>`.

## Alternatives

- **A fourth job in `nuget-publish.yml`.** One workflow, one approval. Rejected: it reopens the pinned three-job design and its tests,
  and a failing signing job would sit inside the release run.
- **SLSA build provenance (`actions/attest-build-provenance`).** Rejected for now: it states that the workflow built the files. The
  packages are built and signed in Jenkins, so that statement would be false.
- **Signing in Jenkins.** Rejected: the Jenkins agent has no Sigstore identity that a reader can tie to this repository.
- **Signing the releases that already exist.** Rejected: a signature made today would vouch for bytes as of today, and the date of
  the older releases would suggest more than it shows. Only future releases get a bundle.

## Consequences

- Positive: `Signed-Releases` can score for a release that carries bundles. The signing identity is the workflow file on `main`, which a
  reader can check. A failure of this workflow never blocks or reverses a NuGet push: the packages are already published.
- Negative: Scorecard reads the latest releases, and the four existing ones stay unsigned, so the score rises slowly, one release
  at a time. The workflow cannot be run before the next release. Its first real run is the next release, and the maintainer must look at
  its result (the release checklist). The workflow depends on two external services, GitHub's OIDC and Sigstore's
  public instance.
- The bundles go public. They contain the workflow identity and a transparency-log entry, no secret and no personal data.
- The signature is on the package as uploaded to the release. It says the workflow saw these bytes, not who made them.

## Compliance

Controls touched: a new workflow with a write permission and an OIDC token (supply chain; `scripts/test_workflows.py` pins its
triggers, permissions and pins). The project has one maintainer, who accepts this record; no other approval is pending.
No new secret, no stored key. The two actions are pinned to commit SHAs.
