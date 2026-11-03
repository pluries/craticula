# ADR-0009: The docs site loads one script of its own, and the stylesheet carries two themes

Status: Proposed   Date: 2026-11-03
Work items: #3554, #3556, #3562   Classification: Public

Accepting this record is the maker's decision.

## Context
The launch spec's privacy rule (NFR-13) says no page loads a script, a stylesheet or a font from another host and the earlier site had no script at all. The v2 design needs search, a theme switch, copy buttons and a phone menu, which need JavaScript.

## Decision
The site ships two files of its own, `theme.js` (blocking, in the head: marks the page scripted and applies the stored theme before paint) and `site.js` (deferred), each well under 30 KB compressed. NFR-13 is amended: the rule is no script, stylesheet or font **from another host**. Every page still reads without JavaScript (content, sidebar links, anchors, previous and next). The only browser storage is the theme choice, one key, read and written inside `try`.

## Alternatives
- **Keep the site script-free:** no search, no theme switch, no copy buttons; rejected by the design.
- **A script from a CDN:** forbidden by the privacy rule.
- **Inline scripts:** would need a content-security exception; two small files are easier to scan and to cache.

## Consequences
- Positive: the privacy rule keeps its meaning (every request goes to the site's own host, checked by a build-output test); the scripts are scanned by the same checks as the build.
- Negative: JavaScript is needed for search, theme, copy and the phone menu; the content stays readable without it.
- Follow-up: a content-security-policy header on the site's web server would enforce the rule at run time.

## Compliance
No new third-party dependency, no data leaves the site's own host, no cookie. Approvals: the maker (Tech Lead and Engineering Lead in solo mode). Security: the script writes search results only through `textContent` (a test bans markup sinks), and the build refuses a script element in a page source.
