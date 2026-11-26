# Security policy

Craticula turns AG Grid server-side requests into native SQL, MongoDB and OpenSearch queries. A flaw in that translation
can expose data, so we take reports seriously and ask you to report them privately.

## Report a vulnerability

Please do **not** open a public issue or pull request for a security problem.

1. Open the [private vulnerability report form](https://github.com/pluries/craticula/security/advisories/new), or go to the
   **Security** tab of this repository.
2. Choose **Report a vulnerability** (GitHub Private Vulnerability Reporting).
3. Describe what you found, the version or commit, and how to reproduce it. A request or a failing test is the most useful.

Only the maintainer and GitHub can read the report until it is made public.

## What to expect

- We acknowledge your report within **7 calendar days**.
- We give a first assessment (accepted, needs more information, or not a vulnerability) within **30 days**.
- We do not promise a fixed date for the fix. We keep you informed, credit you in the advisory if you wish, and agree
  the disclosure date with you once a fix is released.

## Supported versions

| Version | Supported |
|---|---|
| The latest release | Yes |
| The current `main` branch | Yes (while no release exists, `main` is the supported version) |
| Older releases | No |

See [VERSIONING.md](VERSIONING.md) for how versions are numbered.

## What counts

In scope: the compilers and adapters in `csharp/src/`, for example a way to inject into a generated query, to reach a
column or field that the schema does not allow, to bypass a limit, or to make an export write data it should not.

Out of scope: the example application in `examples/demo`. It runs only on your own machine with throw-away local
credentials and is not meant to be exposed.
