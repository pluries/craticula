# Site translations

This folder holds what the docs site needs to publish its pages in French, German, Italian, Spanish and Chinese
(spec 004-site-languages). The English pages in `site/pages/` and `README.md` are the source; a translation never
replaces them and never becomes a second source.

## Layout

- `en/ui.json` - the English interface strings (navigation, labels).
- `<lang>/` for `fr`, `de`, `it`, `es`, `zh` - one Markdown file per translated document, named like the English
  page (`<lang>/the-gridschema.md`), and a `ui.json` for the interface strings of that language (a document in its own right, with the same stamp and approval).
- `glossary.json` - the terms that stay in English and the renderings a machine translation must not use.
- `approvers.txt` - the names allowed to approve a translation, one per line.
- `approvals.json` - the record of every approval (language, document, approver, fingerprints of the English text
  and of the translation at that time).

This folder is data, not a site page: this README is not built into the site.

## A translated page

Each file starts with a header block of `key: value` lines between `---` lines. The required keys are:

- `translates` - the English document this file renders.
- `title` and `description` - the translated page title and description.
- `source_fingerprint` - the fingerprint of the English text it was drafted from (set by `stamp`).
- `drafter` and `drafted_on` - who drafted it and when.
- `status` - `machine-drafted` until a person approves it, then `approved`.

When the English page changes, its fingerprint no longer matches and the translation is stale until it is
redrafted and stamped again. The home page has a second file, `home.html`, translated and stamped the same way.

Every translated heading ends with `{#english-anchor}`, the anchor of the English heading, so a link to a
section works in every language. Code blocks, identifiers, numbers and link targets stay exactly as in English.
A page with no translation is served in English only; that is allowed and is shown as such on the site.

## Workflow

Run from the repository root, with Python 3.10 or later.

1. Draft the translation file (by hand or with a machine). The drafting step edits only `<lang>/` files.
2. `python3 scripts/site_i18n.py stamp <lang> <document>` records the fingerprint of the English text in the header.
3. `python3 scripts/site_i18n.py status` counts the documents of each language by state.
4. `python3 scripts/site_i18n.py gate <lang>` lists what keeps a language from being enabled (exit 1 when there is
   anything); it is also run by the site tests.
5. `python3 scripts/site_i18n.py approve <lang> <document> --by "<name in approvers.txt>"` marks the document
   `approved` and writes its record. It needs a terminal and asks for a typed confirmation (`<lang>/<document>`);
   without a terminal it exits with code 2 and writes nothing.

## What is protected, and why

`approvers.txt`, `approvals.json` and `glossary.json` decide what may be published as approved. Drafting
(a person's or an agent's) never edits them: an approval that the drafter could write for itself is no approval.
The maintainer lists the three paths in `.claude/protected-paths.txt` so that tooling cannot change them; only
`approve` writes `approvals.json`, and only after the typed confirmation.

The glossary's `verbatim` list names the terms that must appear unchanged wherever the English page uses them
(product, package and engine names). Its `forbidden` object has one entry per language (an empty object for none) with
the renderings a machine translation tends to produce for a term, such as a translated `GridSchema`. Matching
is by whole word and ignores case.
