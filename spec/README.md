# `spec/` — the language-neutral source of truth

Per **AR-1** of the maintainers' technical requirements document (TRD, kept privately), this
project is specification-first: `spec/` is not tied to any single language's type system, and
every language implementation (C#, TypeScript, Python, Go — see AR-2, ML-1/ML-2) conforms to what
lives here. The spec never conforms to an implementation. If a language port needs a shape the
spec doesn't have, the spec changes first, then the port follows.

## What's here today

- **`ir.schema.json`** — the canonical IR (intermediate representation) document, expressed as a
  [JSON Schema, draft 2020-12](https://json-schema.org/draft/2020-12/schema). It defines the
  vendor-neutral shape every frontend adapter produces and every backend compiler consumes
  (AR-2 layer 2): a recursive filter tree (`And`/`Or`/`Not`/`Comparison`, AR-5), the closed
  17-operator set (AR-6), fully-typed values (AR-7), group spec, aggregation spec (AR-8), sort
  spec (AR-9), and a page spec covering both bounded ranges and the unpaginated `none` mode used
  for full exports (EXP-2). The schema carries no `maxItems`/`maximum` bounds tied to SEC-3's
  resource limits (max depth, max leaves, max in-values, max page size) — those are host-configurable,
  so a fixed structural bound would reject a legitimately higher-configured host's IR. All of SEC-3
  is enforced by a runtime validator built in a later work item, not by this schema. The one
  exception is a handful of amplification caps unrelated to SEC-3 (string/identifier `maxLength`,
  `int64` numeric bounds) that exist purely to keep the *shape* well-formed, not to police policy.
- **`semantics.md`** — the normative semantics document (§7 of the TRD, rules SEM-1..SEM-7: case
  sensitivity, null handling, null ordering, dates & zones, type coercion, deterministic paging,
  and `contains` on ES/OpenSearch; plus SEM-8, empty set membership (added in #2455, beyond the TRD's enumeration), and an addendum pinning aggregation semantics the TRD's own
  SEM-1..7 enumeration doesn't cover). Each rule states the normative behavior, the naive alternative
  it rules out, a worked example per backend family (SQL, MongoDB, OpenSearch/Elasticsearch)
  reaching the same logical outcome through different backend-native mechanisms, an explicit
  "must NOT" list, and cross-links into `ir.schema.json`'s `$defs`. Every compiler references this
  document instead of re-deriving these behaviors on its own. The examples are illustrative, not
  the enforceable contract — that's what `fixtures/` (below) is for.
- **`grid-schema.schema.json`** — the `GridSchema` config shape (SC-1..SC-5: field allowlist mode,
  per-field type/physical-mapping/text-options, `stableKey`, the SC-5 static filter hook). Authored
  ahead of the actual `GridSchema` model/validator (a later Feature #1617 story), which conforms to
  this shape rather than the reverse — the same spec-first ordering as `ir.schema.json` vs. its
  eventual compiler implementations.
- **`fixtures/`** — the shared, language-agnostic conformance fixture suite (§11, T-1): grid
  request + schema config + expected per-backend artifact, per case. This is what makes identical
  semantics across backends *and* across the four language implementations (G3, G4) enforceable
  rather than aspirational. See `fixtures/README.md` for the format, backend-coverage policy, and
  category index. Execution-equality fixtures (`dataset.json`/`expectedRows.json`, T-1b) have their format
  pinned (`semantics.md` XEQ-1..XEQ-4, `fixtures/schemas/dataset.schema.json` and `expected-rows.schema.json`);
  they are hand-derived from the semantics, never copied from an engine run, and are authored category;
  228 fixtures carry the pair today (rule: XEQ-1..XEQ-4; worked example `operators/001`). The cross-backend parity property over generated requests (T-3) and its divergence register are
  stated in `semantics.md` PAR-1..PAR-4.
- **`conformance-runner.md`** — how an implementation is graded against `fixtures/` (T-1 tier (a), ML-3): the
  driver protocol every language implements, what a driver pins (limits, clock, entry point), the per-backend
  equality rules by reference, and the runner's report and exit status (#1654).

## When this spec is frozen

`spec/VERSION` becomes 1.0.0 against written criteria, kept in [`VERSIONING.md`](../VERSIONING.md#freezing-the-specification)
together with what a spec version number promises. `python3 scripts/check-spec-freeze.py` lists which criteria are met.
