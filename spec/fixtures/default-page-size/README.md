# `default-page-size/`: a default page when no window is sent (PG-1..PG-5)

Spec: the addendum "default page size" in `../../semantics.md`. The harness sets the host's default page size and its switch for
`ignorePageLimit` from `requestContext` (`../../conformance-runner.md` §3); a production parser never reads them from the wire.

| Case | Proves |
|---|---|
| `001-no-window-gets-default-page` | no window, not an export: the page `[0, 100)` (PG-1) |
| `002-custom-default-page-size` | the host's default page size is used (PG-1) |
| `003-ignore-page-limit-allowed-is-unpaginated` | an allowed `ignorePageLimit` is the unpaginated page (PG-3) |
| `004-default-page-carries-the-time-limit` | a default page carries the query time limit (PG-4, TL-1, TL-2) |
| `005-unpaginated-carries-no-time-limit` | an explicit all-rows request carries none (PG-4, TL-3) |

A refusal (`ignorePageLimit` without the host's switch, a malformed value) is not a compiled artifact; it is covered by the
parser tests, not by a fixture (`../README.md`, out of tier).
