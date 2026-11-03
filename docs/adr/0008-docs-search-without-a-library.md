# ADR-0008: The docs site searches with its own small matcher, not a library

Status: Proposed   Date: 2026-11-03
Work items: #3554, #3556, #3562   Classification: Public

Accepting this record is the maker's decision.

## Context
The docs site v2 needs search (requirement DS-4 of the docs site specification). Search libraries (Lunr, MiniSearch, Pagefind) add a third-party script and a dependency to approve (`.claude/rules/compliance.md` section 4: a new library needs the Engineering Lead's approval). The site is about thirty small pages; the index is below 120 KB compressed.

## Decision
The build writes one `search-index.json` (title, description, headings and plain text per page, no rule ids) and a vanilla script (`site/js/site.js`, about 3 KB compressed) ranks by exact title, title prefix, title word, heading, description, then text. No library, no network request beyond the site's own host.

## Alternatives
- **MiniSearch or Lunr:** better ranking and typo tolerance, but a vendored third-party file to approve, to keep patched and to scan.
- **Pagefind:** indexes the built HTML at build time with a binary; a new build tool and a larger runtime.
- **No search:** rejected, the site has about forty pages.

## Consequences
- Positive: nothing to approve or update; the ranking is a few lines a maintainer can read; the index is deterministic (byte-identical builds).
- Negative: no typo tolerance and a simple ranking. The matcher can be replaced behind the same index file if the site grows.
- Follow-up: revisit when the site passes about a hundred pages or a visitor reports bad results.

## Compliance
No new third-party dependency, no data leaves the site's own host, no cookie. Approvals: the maker (Tech Lead and Engineering Lead in solo mode). Security: the script writes search results only through `textContent` (a test bans markup sinks), and the build refuses a script element in a page source.
