# Quickstart: Go

**There is no Go implementation yet.** This page says so on purpose, so you do not look for a package that is not there.

## Why

Craticula is specification-first: the rules and the conformance fixtures in `spec/` come first, and every language
implementation has to pass the same fixtures. The Go port is planned for **after the spec freeze** (the spec
freezes at 1.0). Until then the spec can still change, and a port written now would have to be rewritten.

Nothing is published for Go: no package, no install command.

## What you can do today

- Use the C# library, which is the reference implementation: [Quickstart: C#](quickstart-csharp.html).
- Read the rules a Go port will have to follow: [semantics](semantics.html), and the
  schema references ([GridSchema](grid-schema.html), [IR](ir-schema.html)).
- Look at the test a port has to pass: the conformance fixtures
  (`spec/fixtures`) and the language-neutral runner described in
  [`spec/conformance-runner.md`](../../spec/conformance-runner.md). A driver in any language answers the runner's requests and the
  runner grades the answers.
