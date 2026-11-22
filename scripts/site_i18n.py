#!/usr/bin/env python3
"""Translations of the docs site (spec 004-site-languages).

A translation is a file `site/i18n/<lang>/<slug>.md`: a header block of `key: value` lines between two `---` lines (an HTML
comment holds the same lines in a `home.html`), then the page. `Translations.page` turns one into a copy of the English `Page`
with the translated title and description. `fingerprint` and `ui_fingerprint` say when an English source changed (US2-AS10,
AS13, AS14), `check_fingerprint` names a stale translation (US2-AS1), and `config_problem` says why `languages`, `i18n` or a
page's `scope` of `site/site.json` cannot be used (US1-AS13, FR-027). Standard library only; this module never imports
`build_site` at the top, because `build_site` imports it.
"""
from __future__ import annotations

import argparse
import datetime
import functools
import hashlib
import html
import itertools
import json
import re
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from build_site import Page

ENCODING = "utf-8"
SITE = "site"
I18N = "i18n"
ENGLISH = "en"
LANGUAGES = "languages"
PATH = "path"
ENABLED = "enabled"
SCOPE = "scope"
STATUS = "status"
TRANSLATES = "translates"
DASHES = "---"
COMMENT_OPEN, COMMENT_CLOSE = "<!--", "-->"
GROUPS = "groups"
FINGERPRINT = "source_fingerprint"
UI_FILE = "ui.json"
BOM = "\ufeff"
SCOPES = ("translated", "english")
LANGUAGE_FOLDERS = ("fr", "de", "it", "es", "zh")
STATUSES = ("machine-drafted", "approved")
REQUIRED_KEYS = (TRANSLATES, "title", "description", FINGERPRINT, "drafter", "drafted_on", STATUS)
THEME_MAP = "theme_names"
UI_MAPS = (GROUPS, "group_names", "subgroups", THEME_MAP)
NESTED_MAPS = UI_MAPS[1:]
THEME_KEYS = ("auto", "light", "dark")
SCRIPT_KEYS = ("copy", "copied", "copy_failed", "copy_aria", "search_aria", "search_label", "search_placeholder", "search_empty",
               "search_none", "search_loading", "search_unavailable", "search_english", "search_english_url", "result_one", "result_other", "theme_aria", "theme_title", "theme_names")
_HEADER_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*)$")
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_BADGE_ITEM = r"(?:\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)|!\[[^\]]*\]\([^)]*\))"
_BADGE_LINE = re.compile(rf"^\s*{_BADGE_ITEM}(?:\s+{_BADGE_ITEM})*\s*$")
_DRAFTER = "claude"


class I18nError(Exception):
    """A translation file or the language configuration is not usable."""


@dataclass
class Translation:
    """A parsed translation file: its header keys and the page text that follows the header."""
    header: dict[str, str] = field(default_factory=dict)
    body: str = ""


def _lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _header_block(lines: list[str]) -> tuple[list[str], list[str], str]:
    """The header lines, the body lines and the form of the header (`---` or an HTML comment)."""
    first = lines[0].strip() if lines else ""
    closing = {DASHES: DASHES, COMMENT_OPEN: COMMENT_CLOSE}.get(first)
    if closing is None:
        raise I18nError("the file does not start with a header block (`---` or `<!--`)")
    for index in range(1, len(lines)):
        if lines[index].strip() == closing:
            return lines[1:index], lines[index + 1:], first
    raise I18nError(f"the header block is never closed (expected a line `{closing}`)")


def _header_values(lines: list[str]) -> dict[str, str]:
    header: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        match = _HEADER_LINE.match(line.rstrip())
        if match is None:
            raise I18nError(f"header line is not `key: value`: {line[:60]!r}")
        header[match.group(1)] = match.group(2).strip()
    return header


def parse_translation(text: str) -> Translation:
    """Split a translation file into header and body. Raises I18nError naming the keys among `REQUIRED_KEYS` that are missing
    or empty, and for a `status` that is neither `machine-drafted` nor `approved` (US2-AS17)."""
    head, body, _ = _header_block(_lines(text.lstrip(BOM)))
    header = _header_values(head)
    missing = [key for key in REQUIRED_KEYS if not header.get(key)]
    if missing:
        raise I18nError(f"the header misses {', '.join(missing)}")
    if header[STATUS] not in STATUSES:
        raise I18nError(f"status '{header[STATUS]}' must be one of {', '.join(STATUSES)}")
    return Translation(header, "\n".join(body))


def _normal(text: str) -> str:
    return "\n".join(line.rstrip() for line in _lines(text))


def _prose(text: str) -> str:
    """The text a reader of the English page translates: no HTML comment, no badge line, blank runs folded."""
    kept: list[str] = []
    for line in _lines(_COMMENT.sub("", text)):
        line = line.rstrip()
        if _BADGE_LINE.match(line) or (not line and (not kept or not kept[-1])):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def fingerprint(text: str, title: str, description: str, home_template: str | None = None) -> str:
    """The SHA-256 (64 hex characters) of an English document: `text` is its Markdown after `{{include}}` expansion, without
    badge image lines and HTML comments, with LF endings and no trailing spaces; then its title and its description. The home
    document passes `home_template`, the text of `site/home.html`, which is covered as well (US2-AS10, AS13, AS14)."""
    parts = [_prose(text), title, description]
    if home_template is not None:
        parts.append(_normal(home_template))
    return hashlib.sha256("\x00".join(parts).encode(ENCODING)).hexdigest()


def ui_fingerprint(english_ui: dict, groups: dict) -> str:
    """The SHA-256 of the interface file's English source: the strings of `site/i18n/en/ui.json` and the group card
    descriptions of `site/site.json` `groups`, whatever the order of their keys (US2-AS10)."""
    material = json.dumps({"ui": english_ui, GROUPS: groups}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(material.encode(ENCODING)).hexdigest()


def check_fingerprint(language: str, document: str, recorded: str | None, current: str) -> list[str]:
    """US2-AS1: no finding when `recorded` equals `current`; otherwise one finding naming the language, the document and both
    fingerprints (`recorded` None: the file records none)."""
    if recorded == current:
        return []
    return [f"{language}/{document}: stale: the translation records the English fingerprint {recorded or 'none'}, "
            f"the English document is now {current}; re-draft it from the English page and run stamp"]


def _serialise(translation: Translation, form: str) -> str:
    lines = "".join(f"{key}: {value}\n" for key, value in translation.header.items())
    opening, closing = (DASHES, DASHES) if form == DASHES else (COMMENT_OPEN, COMMENT_CLOSE)
    return f"{opening}\n{lines}{closing}\n{translation.body}"


def _update_header(path: Path, values: dict[str, str]) -> None:
    text = path.read_text(encoding=ENCODING)
    form = text.lstrip(BOM).lstrip().split("\n", 1)[0].strip()
    parsed = parse_translation(text)
    parsed.header.update(values)
    with open(path, "w", encoding=ENCODING, newline="\n") as handle:
        handle.write(_serialise(parsed, form))


def _document_names(slug: str) -> list[str]:
    """The files of one document: its Markdown and, for the home page, its template (`home.html`)."""
    return [f"{slug}.md"] + ([HOME_FILE] if slug == "index" else [])


def _page_files(folder: Path, slug: str) -> list[Path]:
    """The files of one document that exist."""
    return [folder / name for name in _document_names(slug) if (folder / name).is_file()]


def _absent(root: Path, lang: str, slug: str) -> list[str]:
    """The names of the files of a document that a language does not have; the document is missing when there is any."""
    return [name for name in _document_names(slug) if not (_folder(root, lang) / name).is_file()]


def _require_declared(root: Path, lang: str) -> None:
    """`lang` must be a translated language of `site/site.json`; it becomes a folder name, so nothing else may reach a path."""
    if lang == ENGLISH or lang not in _declared(_read_ui(root / SITE_FILE)):
        raise I18nError(f"the language '{lang}' is not declared in {SITE_FILE} `{LANGUAGES}`")


def _folder(root: Path, lang: str) -> Path:
    return root / SITE / I18N / lang


def _read(root: Path, lang: str, name: str) -> Translation:
    shown = f"{SITE}/{I18N}/{lang}/{name}"
    path = _folder(root, lang) / name
    if not path.is_file():
        raise I18nError(f"{shown} does not exist")
    try:
        return parse_translation(path.read_text(encoding=ENCODING))
    except (I18nError, UnicodeDecodeError) as error:
        raise I18nError(f"{shown}: {error}") from error


def page_fingerprint(site, page: "Page") -> str:
    """The fingerprint of an English page of `site`, a `build_site.SiteBuild` of the English site."""
    home = site.read(page.template) if page.template else None
    return fingerprint(site.page_text(page), page.title, page.description, home)


def stamp(root: Path, lang: str, slug: str, today: str) -> str:
    """Write the fingerprint of the English page `slug`, the drafter and `drafted_on: <today>` into `site/i18n/<lang>/<slug>.md`
    (and `home.html` for `index`), and set `status: machine-drafted`; every other key and the body stay as they are. Returns the
    fingerprint written. Raises I18nError for a slug the site does not have or a translation file that does not exist."""
    from build_site import BuildError, SiteBuild, load_config  # build_site imports this module
    _require_declared(root, lang)
    folder = _folder(root, lang)
    if not (folder / f"{slug}.md").is_file():
        raise I18nError(f"{SITE}/{I18N}/{lang}/{slug}.md does not exist")
    try:
        english = SiteBuild(root, load_config(root), "")
    except BuildError as error:
        raise I18nError(str(error)) from error
    page = english.pages_by_slug.get(slug)
    if page is None:
        raise I18nError(f"the site has no page '{slug}'")
    value = page_fingerprint(english, page)
    values = {FINGERPRINT: value, "drafter": _DRAFTER, "drafted_on": today, STATUS: STATUSES[0]}
    for path in _page_files(folder, slug):
        _update_header(path, values)
    return value


class Translations:
    """The translation files of a repository, read on demand: `english` maps each slug to the English `Page`."""

    def __init__(self, root: Path, english: Mapping[str, "Page"]) -> None:
        self.root, self.english = root, english

    def _file(self, lang: str, name: str) -> Path:
        return _folder(self.root, lang) / name

    def exists(self, lang: str, slug: str) -> bool:
        return self._file(lang, f"{slug}.md").is_file()

    def page(self, lang: str, slug: str) -> "Page | None":
        """A copy of the English page `slug` carrying the translated title and description (the text is not on a `Page` here; the
        build seeds it from the translation body), or None when the language has no file for the slug. Raises I18nError when the
        file exists and cannot be parsed."""
        english = self.english.get(slug)
        if english is None or not self.exists(lang, slug):
            return None
        header = _read(self.root, lang, f"{slug}.md").header
        if header[TRANSLATES] != slug:
            raise I18nError(f"{SITE}/{I18N}/{lang}/{slug}.md: `{TRANSLATES}` says '{header[TRANSLATES]}', the file is the page '{slug}'")
        return replace(english, title=header["title"], description=header["description"], rendered=None)

    def body(self, lang: str, slug: str) -> str:
        """The page text of a translation file, without its header. Raises I18nError when the file cannot be read."""
        return _read(self.root, lang, f"{slug}.md").body

    def template(self, lang: str, rel: str) -> str | None:
        """The page template of a language (`site/i18n/<lang>/home.html` for `site/home.html`) without its header, or None."""
        name = Path(rel).name
        if not self._file(lang, name).is_file():
            return None
        return _read(self.root, lang, name).body


def enabled_languages(config: dict) -> list[str]:
    """The codes of the translated languages the build writes: those of `config["languages"]` with `enabled` true, in file
    order, without `en` (the source, always built). No `languages` key: an empty list."""
    return [code for code, entry in _declared(config).items() if code != ENGLISH and entry.get(ENABLED) is True]


def _declared(config: dict) -> dict:
    return config.get(LANGUAGES) or {}


def ui_path(root: Path, lang: str) -> Path:
    return _folder(root, lang) / UI_FILE


def _read_ui(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding=ENCODING))
    except (OSError, ValueError) as error:
        raise I18nError(f"cannot read {path.as_posix()}: {error}") from error
    if not isinstance(value, dict):
        raise I18nError(f"{path.as_posix()}: the file must hold one JSON object")
    return value


def _english_ui(root: Path) -> dict:
    """`site/i18n/en/ui.json` with the group card descriptions of `site/site.json` merged in as its `groups` (D-015)."""
    ui = _read_ui(ui_path(root, ENGLISH))
    groups = _read_ui(root / SITE / "site.json").get(GROUPS)
    return {**ui, GROUPS: groups} if isinstance(groups, dict) else ui


@functools.lru_cache(maxsize=None)
def default_ui() -> dict:
    """The English interface text of this checkout: what a render function uses when it is not given one."""
    return _english_ui(Path(__file__).resolve().parent.parent)


def load_ui(root: Path, lang: str, reference: dict | None = None) -> dict:
    """The interface text of a language. `en` is the English file with the `site.json` group descriptions merged in; with
    `reference` (the English one), a key a translation misses is an error, so `groups` is required in a translation only."""
    if lang == ENGLISH:
        return _english_ui(root)
    ui = _read_ui(ui_path(root, lang))
    if reference is not None:
        missing = [key for key in reference if key not in ui]
        if missing:
            raise I18nError(f"{ui_path(root, lang).relative_to(root).as_posix()} misses the key(s): {', '.join(missing)}")
        wrong = [key for key in UI_MAPS if key in reference and not isinstance(ui[key], dict)]
        if wrong:
            raise I18nError(f"{ui_path(root, lang).relative_to(root).as_posix()}: {', '.join(wrong)} must be an object")
        _check_nested(ui_path(root, lang).relative_to(root).as_posix(), ui, reference)
    return ui


def _check_nested(shown: str, ui: dict, reference: dict) -> None:
    """The names of the themes, of the groups and of the sub-groups: a translation that leaves one out would show an English label or none."""
    for name in NESTED_MAPS:
        expected = THEME_KEYS if name == THEME_MAP else reference.get(name, {})
        missing = [key for key in expected if key not in ui[name]]
        if missing:
            raise I18nError(f"{shown}: {name} misses the key(s): {', '.join(missing)}")


def script_ui(ui: dict) -> str:
    """The strings `site.js` shows, as the JSON of the `data-ui` attribute of `<body>`; no extra request, no script of its own."""
    return json.dumps({key: ui[key] for key in SCRIPT_KEYS if key in ui}, ensure_ascii=False, separators=(",", ":"))


SAFE_NAME = re.compile(r"[a-z]{2,3}(-[A-Za-z0-9]{2,8})?")
RESERVED_NAMES = frozenset({"images", "img", "fonts"})


def _language_problem(code: str, entry: object) -> str | None:
    if not isinstance(entry, dict):
        return f"language '{code}' must be an object"
    for key in ("name", PATH, "lang"):
        if key in entry and not isinstance(entry[key], str):
            return f"language '{code}': '{key}' must be a string"
    if ENABLED in entry and not isinstance(entry[ENABLED], bool):
        return f"language '{code}': '{ENABLED}' must be true or false"
    path = entry.get(PATH, code)
    if code != ENGLISH and (not SAFE_NAME.fullmatch(code) or not SAFE_NAME.fullmatch(path) or path in RESERVED_NAMES or code in RESERVED_NAMES):
        return f"language '{code}': the code and '{PATH}' ('{path}') must each be one short folder name such as 'fr' or 'zh-Hans', not a name the build uses"
    return None


def language_prefixes(config: dict) -> set[str]:
    """Every folder name a language may take: the five known ones and the paths the configuration declares."""
    declared = {entry.get(PATH, code) for code, entry in _declared(config).items() if code != ENGLISH}
    return set(LANGUAGE_FOLDERS) | declared


def _scope_problem(entry: object) -> str | None:
    if not isinstance(entry, dict) or entry.get(SCOPE) in SCOPES:
        return None
    return f"page '{entry.get('slug')}': '{SCOPE}' must be 'translated' or 'english'"


def _clash_problem(config: dict, slugs: list[str]) -> str | None:
    """Two languages that write into one folder, or a page that takes the name of a language folder."""
    owners: dict[str, str] = {}
    for code, entry in _declared(config).items():
        path = entry.get(PATH, code)
        if code != ENGLISH and owners.setdefault(path, code) != code:
            return f"languages '{owners[path]}' and '{code}' both write into the path '{path}'; each needs its own `{PATH}`"
    clash = sorted(set(slugs) & language_prefixes(config))
    return f"page slug '{clash[0]}' is also the prefix of a language folder; a page cannot take a language's name" if clash else None


def config_problem(config: dict, slugs: list[str]) -> str | None:
    """Why the `languages` and `i18n` keys of site.json or a page's `scope` cannot be used (or a page slug takes a language
    folder), or None. `slugs` are the page slugs (US1-AS13, FR-027)."""
    languages = config.get(LANGUAGES, {})
    if not isinstance(languages, dict):
        return f"'{LANGUAGES}' must map a language code to an object"
    problems = [_language_problem(code, entry) for code, entry in languages.items()]
    options = config.get(I18N, {})
    if not isinstance(options, dict) or not isinstance(options.get("complete", False), bool):
        problems.append(f"'{I18N}' must be an object whose 'complete' is true or false")
    problems.append(None if any(problems) else _clash_problem(config, slugs))
    problems += [_scope_problem(entry) for entry in config.get("pages", [])]
    return next((problem for problem in problems if problem), None)


def language_path(config: dict, code: str) -> str:
    if code == ENGLISH:
        return ""
    return _declared(config).get(code, {}).get(PATH, code)


def language_attribute(config: dict, code: str) -> str:
    return _declared(config).get(code, {}).get("lang", code)


def languages_to_build(config: dict, preview: tuple[str, ...] = ()) -> list[str]:
    """The enabled languages, plus the disabled ones named for a preview, in file order. An unknown one is an error."""
    declared = [code for code in _declared(config) if code != ENGLISH]
    unknown = [code for code in preview if code not in declared]
    if unknown:
        raise I18nError(f"--preview-languages: {', '.join(unknown)} is not a language of {SITE}/site.json")
    wanted = set(enabled_languages(config)) | set(preview)
    return [code for code in declared if code in wanted]


def clear_language_folders(out_dir: Path, config: dict) -> None:
    """A language that is disabled, or a page that is removed, must leave nothing in the output. Only the folders of the declared languages
    go; a folder that is a symbolic link is refused before anything is removed, so the build never writes through it."""
    folders = [(code, out_dir / language_path(config, code)) for code in _declared(config) if code != ENGLISH]
    for code, folder in folders:
        if folder.is_symlink():
            raise I18nError(f"language '{code}': {folder.as_posix()} is a symbolic link; remove it before building")
    for _, folder in folders:
        if SAFE_NAME.fullmatch(folder.name):
            shutil.rmtree(folder, ignore_errors=True)


def address(base: str, path: str, slug: str) -> str:
    return f"{base.rstrip('/')}/" + (f"{path}/" if path else "") + f"{slug}.html"


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    path: str
    lang: str


@dataclass
class LanguageSet:
    """The languages one build writes (English first), for each the slugs that have a translation file, and for each the line that
    says in its own words that a page is English only (`notes`)."""
    languages: list[Language] = field(default_factory=list)
    translated: dict[str, set[str]] = field(default_factory=dict)
    base: str = ""
    notes: dict[str, str] = field(default_factory=dict)

    def prefix(self, code: str) -> str:
        path = next((entry.path for entry in self.languages if entry.code == code), "")
        return "../" * len([part for part in path.split("/") if part])

    def _is_translated(self, code: str, slug: str) -> bool:
        return code == ENGLISH or slug in self.translated.get(code, set())

    def _has_translation(self, slug: str) -> bool:
        return any(slug in slugs for slugs in self.translated.values())

    def alternates(self, code: str, slug: str) -> str:
        """The canonical link and the `hreflang` alternates of a page; nothing while only English is built or without a base
        address. A page no language has translated carries its English canonical address and `x-default` only (US1-AS5)."""
        if len(self.languages) < 2 or not self.base:
            return ""
        english = next(entry for entry in self.languages if entry.code == ENGLISH)
        own = next(entry for entry in self.languages if entry.code == code)
        links = [f'<link rel="canonical" href="{html.escape(address(self.base, own.path, slug))}">']
        if self._has_translation(slug):
            links += [f'<link rel="alternate" hreflang="{html.escape(entry.lang)}" href="{html.escape(address(self.base, entry.path, slug))}">'
                      for entry in self.languages if self._is_translated(entry.code, slug)]
        links.append(f'<link rel="alternate" hreflang="x-default" href="{html.escape(address(self.base, english.path, slug))}">')
        return "".join(links)

    def _item(self, current: Language, entry: Language, slug: str) -> str:
        """One link of the control: the same page in that language, or its home page (with the language's own "English only"
        line after the link) when that language has no file for the page."""
        translated = self._is_translated(entry.code, slug)
        target = slug if translated else "index"
        if entry.code == current.code:
            href = f"{slug}.html"
        else:
            href = self.prefix(current.code) + (f"{entry.path}/" if entry.path else "") + f"{target}.html"
        mark = ' aria-current="true"' if entry.code == current.code else ""
        link = f'<a href="{html.escape(href)}" lang="{html.escape(entry.lang)}" hreflang="{html.escape(entry.lang)}"{mark}>{html.escape(entry.name)}</a>'
        note = self.notes.get(entry.code, "")
        if translated or not note:
            return link
        return f'{link}<span class="lang-note" lang="{html.escape(entry.lang)}">{html.escape(note)}</span>'

    def menu(self, code: str, slug: str, label: str) -> str:
        """The language control: a dropdown of plain links to the same page in every language built, the current one marked."""
        if len(self.languages) < 2:
            return ""
        current = next(entry for entry in self.languages if entry.code == code)
        items = "".join(self._item(current, entry, slug) for entry in self.languages)
        return (f'<nav class="lang-menu" aria-label="{html.escape(label)}" lang="{html.escape(current.lang)}"><details class="lang-dropdown">'
                f'<summary><span class="lang-current">{html.escape(current.name)}</span></summary><div class="lang-panel">{items}</div></details></nav>')


def language_set(config: dict, base: str, codes: list[str], translations: Translations, notes: dict[str, str] | None = None) -> LanguageSet:
    """English plus `codes`, with the slugs each of them has translated and, in `notes`, each language's "English only" line."""
    entries = [Language(code, _declared(config).get(code, {}).get("name", code), language_path(config, code),
                        language_attribute(config, code)) for code in [ENGLISH, *codes]]
    translated = {code: {slug for slug in translations.english if translations.exists(code, slug)} for code in codes}
    return LanguageSet(entries, translated, base, notes or {})


# ---------------------------------------------------------------- checks and approvals (US2, US3)

APPROVALS_FILE = f"{SITE}/{I18N}/approvals.json"
APPROVERS_FILE = f"{SITE}/{I18N}/approvers.txt"
GLOSSARY_FILE = f"{SITE}/{I18N}/glossary.json"
LANGUAGE_KEY, DOCUMENT_KEY, HASH_KEY, APPROVED_BY = "language", "document", "translation_hash", "approved_by"
APPROVAL_KEYS = (LANGUAGE_KEY, DOCUMENT_KEY, FINGERPRINT, HASH_KEY, APPROVED_BY, "approved_on")
STATE_WORDS = ("missing", "stale", "machine-drafted", "approved")
NOT_APPROVED = "not approved"
COMPLETE_KEY = "complete"
APPROVED = STATUSES[1]
HOME_FILE = "home.html"
CODE_BLOCK = "code block"
SITE_FILE = f"{SITE}/site.json"
_FENCE_OPEN = re.compile(r"^(\s*)(`{3,}|~{3,})\s*(\S*)")
_HEADING_LINE = re.compile(r"^(#{1,6})\s+(.*?)(?:\s+#+)?\s*$")
_DECLARED = re.compile(r"^(.*?)\s*\{#([\w-]+)\}$")
_DECLARATION = re.compile(r"\{#[\w-]*\}")
_INLINE_CODE = re.compile(r"(`+)(.+?)\1", re.S)
_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)[^)]*\)")
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)[^)]*\)")
_URL = re.compile(r"https?://[^\s<>)\]\"'`]+")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)+\|?\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_TAG_NAME = re.compile(r"<([a-zA-Z][a-zA-Z0-9-]*)")
_START_TAG = re.compile(r"""<([a-zA-Z][a-zA-Z0-9-]*)((?:"[^"]*"|'[^']*'|[^>"'])*)>""")
# Two small patterns in place of one: first the `= value` of every attribute that has a name before it goes, then what is left are the names.
# They differ from one combined pattern only for an attribute whose name would itself start with "=" after a value, which no browser runs as script.
_ATTRIBUTE_VALUE = re.compile(r"""(?<=[^\s"'>/=])\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'>]+)""")
_ATTRIBUTE_NAME = re.compile(r"""[^\s"'>/=]+""")
_TARGET_ATTRIBUTE = re.compile(r"\b(?:href|src)=\"([^\"]*)\"")
_PRE, _CODE = re.compile(r"<pre\b[^>]*>(.*?)</pre>", re.S), re.compile(r"<code\b[^>]*>(.*?)</code>", re.S)
_SCRIPT = re.compile(r"<script\b", re.I)
_BLOCKED_ELEMENTS = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


@dataclass
class _Chunk:
    """A run of lines of one kind: prose, or a fenced block (`raw` holds its fence lines, `body` the code between them)."""
    code: bool
    raw: list[str]
    tag: str = ""
    body: list[str] = field(default_factory=list)


@dataclass
class _Scan:
    """A page split into its fenced code blocks (the language tag, a newline, the code lines) and the lines outside them."""
    blocks: list[str] = field(default_factory=list)
    prose: list[str] = field(default_factory=list)


def _fenced(lines: list[str], start: int, opening: re.Match) -> _Chunk:
    indent, marker, tag = opening.groups()
    closing = re.compile(rf"^\s*{re.escape(marker[0])}{{{len(marker)},}}\s*$")
    end = next((index for index in range(start + 1, len(lines)) if closing.match(lines[index])), None)
    stop = len(lines) if end is None else end
    body = [(line[len(indent):] if not line[:len(indent)].strip() else line).rstrip() for line in lines[start + 1:stop]]
    return _Chunk(True, lines[start:stop if end is None else end + 1], tag, body)


def _chunks(text: str) -> list[_Chunk]:
    lines = _lines(text)
    chunks: list[_Chunk] = []
    prose: list[str] = []
    index = 0
    while index < len(lines):
        opening = _FENCE_OPEN.match(lines[index])
        if opening is None:
            prose.append(lines[index])
            index += 1
            continue
        if prose:
            chunks.append(_Chunk(False, prose))
            prose = []
        chunks.append(_fenced(lines, index, opening))
        index += len(chunks[-1].raw)
    return chunks + ([_Chunk(False, prose)] if prose else [])


def _scan(text: str) -> _Scan:
    """Split Markdown at its fenced blocks (``` and ~~~); the lines of a block are right-trimmed and de-indented by the fence's indent."""
    scan = _Scan()
    for chunk in _chunks(text):
        if chunk.code:
            scan.blocks.append(chunk.tag + "\n" + "\n".join(chunk.body))
        else:
            scan.prose.extend(chunk.raw)
    return scan


def _visible(text: str) -> str:
    """The text a translator reads: no HTML comment and no badge line outside the code blocks (the same two things `fingerprint` ignores)."""
    lines: list[str] = []
    for chunk in _chunks(text):
        if chunk.code:
            lines.extend(chunk.raw)
            continue
        kept = _COMMENT.sub("", "\n".join(chunk.raw)).split("\n")
        lines.extend(line for line in kept if not _BADGE_LINE.match(line))
    return "\n".join(lines)


def _same(target: str) -> str:
    return target


def _difference(word: str, english: list[str], translated: list[str]) -> list[str]:
    """One finding when two lists of items are not the same multiset, naming what the translation lacks and what it adds."""
    lacking, added = Counter(english) - Counter(translated), Counter(translated) - Counter(english)
    if not lacking and not added:
        return []
    return [f"{word}: the translation lacks {sorted(lacking)} and adds {sorted(added)}"]


def _block_findings(english: list[str], translated: list[str]) -> list[str]:
    found: list[str] = []
    for index in range(max(len(english), len(translated))):
        if index >= len(translated):
            found.append(f"{CODE_BLOCK} {index + 1} is missing from the translation")
        elif index >= len(english):
            found.append(f"{CODE_BLOCK} {index + 1} is not in the English page")
        elif english[index] != translated[index]:
            found.append(f"{CODE_BLOCK} {index + 1} differs from the English one")
    return found


def _headings(prose: list[str]) -> list[str]:
    return [match.group(2) for match in map(_HEADING_LINE.match, prose) if match]


def _heading_findings(english: list[str], translated: list[str], english_anchors: list[str]) -> list[str]:
    found: list[str] = []
    if len(english) != len(translated):
        found.append(f"heading: the translation has {len(translated)} headings, the English page {len(english)}")
    matches = [_DECLARED.match(text) for text in translated]
    found += [f"anchor: the heading '{text}' does not end in its English anchor {{#id}}" for text, match in zip(translated, matches) if match is None]
    declared = [match.group(2) for match in matches if match]
    if len(declared) == len(translated) and declared != english_anchors:
        found.append(f"anchor: the declared anchors {declared} are not the English ones {english_anchors}")
    return found


def _urls(text: str) -> set[str]:
    return {found.rstrip(".,;:!?") for found in _URL.findall(text)}


def check_identity(label: str, english: str, translated: str, english_anchors: list[str], resolve=None) -> list[str]:
    """Code, targets, headings and anchors of the translation against the English page. Findings start with `label` and name:
    `code block <n>` (fenced blocks, tag included, from 1; a missing or extra block says so), `inline code`, `image`, `link` (compared by
    target; `resolve(target) -> str`, identity when None, is applied to every link and image target first, so two spellings of one page
    and anchor are equal), `URL` (an http(s) address English lacks), `heading` (the count) and `anchor` (each translated heading must end
    in `{#id}`; the ids in order must equal `english_anchors`)."""
    resolve = resolve or _same
    source, target = _scan(english), _scan(translated)
    found = _block_findings(source.blocks, target.blocks)
    before, after = "\n".join(source.prose), "\n".join(target.prose)
    found += _difference("inline code", _code_spans(before), _code_spans(after))
    for word, pattern in (("image", _IMAGE), ("link", _LINK)):
        found += _difference(word, [resolve(item) for item in pattern.findall(before)], [resolve(item) for item in pattern.findall(after)])
    found += [f"URL: the translation adds {url}" for url in sorted(_urls(translated) - _urls(english))]
    found += _heading_findings(_headings(source.prose), _headings(target.prose), english_anchors)
    return [f"{label}: {finding}" for finding in found]


def _code_spans(text: str) -> list[str]:
    """Inline code spans as the renderer reads them (across line breaks), whitespace collapsed so a re-wrapped span is equal."""
    return [" ".join(item[1].split()) for item in _INLINE_CODE.findall(text)]


def _numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(_DECLARATION.sub("", text)))


def _counts(prose: list[str]) -> dict[str, int]:
    quotes = sum(1 for index, line in enumerate(prose) if line.lstrip().startswith(">") and (index == 0 or not prose[index - 1].lstrip().startswith(">")))
    return {"table": sum(1 for line in prose if _TABLE_RULE.match(line)), "list item": sum(1 for line in prose if _LIST_ITEM.match(line)), "admonition": quotes}


def check_numbers(label: str, english: str, translated: str) -> list[str]:
    """The set of digit strings (`{#id}` excluded) and the counts of tables, list items and block quotes equal the English ones. Findings
    start with `label` and name `number`, `table`, `list item` or `admonition`."""
    found = [f"number {value} is missing from the translation" for value in sorted(_numbers(english) - _numbers(translated))]
    found += [f"number {value} is not in the English page" for value in sorted(_numbers(translated) - _numbers(english))]
    before, after = _counts(_scan(english).prose), _counts(_scan(translated).prose)
    found += [f"{word}: the English page has {before[word]}, the translation {after[word]}" for word in before if before[word] != after[word]]
    return [f"{label}: {finding}" for finding in found]


def _has_token(text: str, term: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", text, re.I) is not None


_HEADING_ANCHOR = re.compile(r"^(#{1,6}\s.*?)\s*\{#[^}]*\}\s*$", re.M)


def _without_anchors(text: str) -> str:
    return _HEADING_ANCHOR.sub(r"\1", text)


def check_glossary(label: str, lang: str, english: str, translated: str, glossary: dict) -> list[str]:
    """`glossary` is `{"verbatim": [term...], "forbidden": {lang: {term: [word...]}}}`. A verbatim term in `english` must be in `translated`
    and no forbidden word of `lang` may be, both as a whole token without regard to case (a token is bounded by anything but an ASCII
    letter, digit or underscore, so `GridSchema` next to Chinese characters counts). A `lang` that has no key in `forbidden` (an empty
    object is an entry) is one finding naming the language."""
    english, translated = _without_anchors(english), _without_anchors(translated)
    found = [f"the term '{term}' must stay as written in English" for term in glossary.get("verbatim", [])
             if _has_token(english, term) and not _has_token(translated, term)]
    forbidden = glossary.get("forbidden", {})
    if lang not in forbidden:
        found.append(f"the glossary has no entry for the language '{lang}'")
    for term, words in forbidden.get(lang, {}).items():
        found += [f"'{word}' is a forbidden rendering of '{term}'" for word in words if _has_token(translated, word)]
    return [f"{label}: {finding}" for finding in found]


def _markup(text: str) -> str:
    return _COMMENT.sub("", text)


def _element_texts(pattern: re.Pattern, text: str) -> list[str]:
    return [found.strip() for found in pattern.findall(text)]


def _attribute_sets(markup: str) -> list[tuple[str, frozenset[str]]]:
    """Each start tag in document order with the lower-cased names of its attributes, however they are quoted."""
    return [(tag.lower(), frozenset(name.lower() for name in _ATTRIBUTE_NAME.findall(_ATTRIBUTE_VALUE.sub(" ", attributes)))) for tag, attributes in _START_TAG.findall(markup)]


def _attribute_findings(source: str, target: str) -> list[str]:
    english, translated = _attribute_sets(source), _attribute_sets(target)
    if [tag for tag, _ in english] != [tag for tag, _ in translated]:
        return []
    found = []
    for (tag, before), (_, after) in zip(english, translated):
        if before != after:
            found.append(f"attribute(s) of <{tag}> differ: the translation lacks {sorted(before - after)} and adds {sorted(after - before)}")
    return found


def check_template(label: str, english_html: str, translated_html: str) -> list[str]:
    """`home.html` of a language against `site/home.html`. Findings start with `label`, name `home.html` and the thing: `structure` (the
    sequence of element names), `attribute` (the names of the attributes of each element), `<pre>`, `<code>`, `href and src`, `number` (the digit strings of the visible text), a `<script>` or a URL
    English lacks."""
    source, target = _markup(english_html), _markup(translated_html)
    found: list[str] = []
    if _TAG_NAME.findall(source) != _TAG_NAME.findall(target):
        found.append("structure differs from the English template")
    for word, pattern in (("<pre>", _PRE), ("<code>", _CODE)):
        if _element_texts(pattern, source) != _element_texts(pattern, target):
            found.append(f"{word} differs from the English template")
    if sorted(_TARGET_ATTRIBUTE.findall(source)) != sorted(_TARGET_ATTRIBUTE.findall(target)):
        found.append("href and src differ from the English template")
    if _numbers(_visible_html(source)) != _numbers(_visible_html(target)):
        found.append("number differs from the English template")
    found += _attribute_findings(source, target)
    if len(_SCRIPT.findall(target)) > len(_SCRIPT.findall(source)):
        found.append("a <script> is added")
    found += [f"the address {url} is added" for url in sorted(_urls(target) - _urls(source))]
    return [f"{label}: {HOME_FILE} {finding}" for finding in found]


def _visible_html(markup: str) -> str:
    return html.unescape(_TAG.sub(" ", _BLOCKED_ELEMENTS.sub(" ", markup)))


def _site_entries(root: Path) -> list[dict]:
    pages = _read_ui(root / SITE_FILE).get("pages", [])
    return [entry for entry in pages if isinstance(entry, dict)]


def _scoped(root: Path, scope: str) -> list[str]:
    return [entry["slug"] for entry in _site_entries(root) if entry.get(SCOPE) == scope and isinstance(entry.get("slug"), str)]


def check_scope(root: Path, lang: str) -> list[str]:
    """One finding `<lang>/<slug>: ...` per file `site/i18n/<lang>/<slug>.md` whose slug is a page of `scope: english`."""
    folder = _folder(root, lang)
    if not folder.is_dir():
        return []
    english = set(_scoped(root, SCOPES[1]))
    return [f"{lang}/{path.stem}: the page is English only; remove {SITE}/{I18N}/{lang}/{path.name}" for path in sorted(folder.glob("*.md")) if path.stem in english]


def _english_anchors(text: str) -> list[str]:
    """The anchor of each heading of the English text, in order, as the renderer gives them."""
    from build_site import render_markdown  # build_site imports this module
    return [anchor for _, _, anchor in render_markdown(text).headings]


def documents(root: Path) -> list[str]:
    """The slugs of the documents: the pages of `scope: translated` of `site/site.json`, in page order (21 in this repository, `index`
    included); an English-only page, a split semantics part and `ui.json` are not documents."""
    return _scoped(root, SCOPES[0])


def missing_pages(root: Path, lang: str) -> list[str]:
    """The documents that have no `site/i18n/<lang>/<slug>.md`, in page order."""
    return [slug for slug in documents(root) if _absent(root, lang, slug)]


class _English:
    """The English site of a repository, built once: the text, the fingerprint and the link resolver of each of its pages."""

    def __init__(self, root: Path) -> None:
        from build_site import BuildError, SiteBuild, load_config  # build_site imports this module
        try:
            self.site = SiteBuild(root, load_config(root), "")
        except BuildError as error:
            raise I18nError(str(error)) from error

    def page(self, slug: str) -> "Page":
        page = self.site.pages_by_slug.get(slug)
        if page is None:
            raise I18nError(f"the site has no page '{slug}'")
        return page

    def fingerprint(self, slug: str) -> str:
        return page_fingerprint(self.site, self.page(slug))

    def text(self, slug: str) -> str:
        return self.site.page_text(self.page(slug))

    def template(self, slug: str) -> str | None:
        rel = self.page(slug).template
        return self.site.read(rel) if rel else None

    def resolver(self, slug: str):
        """The link resolver the build applies to the page, so two spellings of one target compare equal (its own findings are not used)."""
        page = self.page(slug)
        return self.site.resolver_for(page, self.site.page_anchors(slug), [], itertools.repeat(0))


def _load_json(path: Path, kind: type, default):
    if not path.is_file():
        return default
    try:
        value = json.loads(path.read_text(encoding=ENCODING))
    except (OSError, ValueError) as error:
        raise I18nError(f"cannot read {path.name}: {error}") from error
    if not isinstance(value, kind):
        raise I18nError(f"{path.name}: the file must hold one JSON {kind.__name__}")
    return value


def _records(root: Path) -> list[dict]:
    """The approval records of `site/i18n/approvals.json`; a missing file holds none."""
    return _load_json(root / APPROVALS_FILE, list, [])


def _glossary(root: Path) -> dict:
    return _load_json(root / GLOSSARY_FILE, dict, {})


def _approvers(root: Path) -> list[str]:
    """The names of `site/i18n/approvers.txt`, one per line, blank lines skipped; a missing file holds none."""
    path = root / APPROVERS_FILE
    if not path.is_file():
        return []
    return [line.strip() for line in path.read_text(encoding=ENCODING).lstrip(BOM).splitlines() if line.strip()]


def _bodies(root: Path, lang: str, document: str) -> list[str]:
    folder = _folder(root, lang)
    return ["\n".join(_header_block(_lines(path.read_text(encoding=ENCODING).lstrip(BOM)))[1]) for path in _page_files(folder, document)]


def translation_fingerprint(root: Path, lang: str, document: str) -> str:
    """The SHA-256 of the translation as approved: the normalised bodies (header excluded) of `<document>.md` and, for `index`, `home.html`;
    for the document `ui.json` the normalised text of the file. An empty string when a file cannot be read."""
    try:
        if document == UI_FILE:
            parts = [(ui_path(root, lang)).read_text(encoding=ENCODING).lstrip(BOM)]
        else:
            parts = _bodies(root, lang, document)
    except (OSError, UnicodeDecodeError, I18nError):
        return ""
    if not parts:
        return ""
    return hashlib.sha256("\x00".join(_normal(part).rstrip("\n") for part in parts).encode(ENCODING)).hexdigest()


def ui_source_fingerprint(root: Path) -> str:
    """The English source fingerprint of every `ui.json` (`ui_fingerprint` of `site/i18n/en/ui.json` and the `groups` of `site/site.json`)."""
    groups = _read_ui(root / SITE_FILE).get(GROUPS, {})
    return ui_fingerprint(_read_ui(ui_path(root, ENGLISH)), groups if isinstance(groups, dict) else {})


def _label_parts(label: str) -> tuple[str, str]:
    language, _, document = label.partition("/")
    return language, document


def _of_document(records: list[dict], label: str) -> list[dict]:
    language, document = _label_parts(label)
    return [record for record in records if record.get(LANGUAGE_KEY) == language and record.get(DOCUMENT_KEY) == document]


def check_approval(label: str, header: dict[str, str], records: list[dict], approvers: list[str]) -> list[str]:
    """For a header with `status: approved`, the record of the label's language and document must name an `approved_by` that is in
    `approvers`; a finding starts with `label` and names the approver. A header that is not `approved` has no finding."""
    if header.get(STATUS) != APPROVED:
        return []
    return [f"{label}: approved by '{record.get(APPROVED_BY)}', who is not in {APPROVERS_FILE}"
            for record in _of_document(records, label)[-1:] if record.get(APPROVED_BY) not in approvers]


def check_approval_record(label: str, header: dict[str, str], records: list[dict], own: str, current: str) -> list[str]:
    """A header with `status: approved` needs a record whose language and document are the label's, whose `source_fingerprint` is `current`
    (the English fingerprint of today) and whose `translation_hash` is `own`; otherwise one finding that starts with `label` and names
    `approvals.json`. A header that is not `approved` needs none."""
    if header.get(STATUS) != APPROVED:
        return []
    if any(record.get(FINGERPRINT) == current and record.get(HASH_KEY) == own for record in _of_document(records, label)):
        return []
    return [f"{label}: the status is approved but {APPROVALS_FILE} has no record of this document for the English text and the translation as they are now"]


def _headers(root: Path, lang: str, slug: str) -> list[dict[str, str]]:
    return [_read(root, lang, path.name).header for path in _page_files(_folder(root, lang), slug)]


class _Checker:
    """The checks of the translations of one repository; the English site is built once."""

    def __init__(self, root: Path) -> None:
        self.root, self.english = root, _English(root)
        self.glossary, self.records, self.approvers = _glossary(root), _records(root), _approvers(root)

    def content(self, lang: str, slug: str, label: str) -> list[str]:
        """The checks of the text of one translation (code, targets, numbers, glossary) and, for a page with a template, of that template."""
        translation = _read(self.root, lang, f"{slug}.md")
        source, target = _visible(self.english.text(slug)), _visible(translation.body)
        found = check_identity(label, source, target, _english_anchors(source), self.english.resolver(slug))
        found += check_numbers(label, source, target) + check_glossary(label, lang, source, target, self.glossary)
        return found + self.template(lang, slug, label)

    def template(self, lang: str, slug: str, label: str) -> list[str]:
        english = self.english.template(slug)
        if english is None:
            return []
        name = Path(self.english.page(slug).template).name
        if not (_folder(self.root, lang) / name).is_file():
            return [f"{label}: {name} is missing"]
        return check_template(label, english, _read(self.root, lang, name).body)

    def page(self, lang: str, slug: str) -> list[str]:
        if slug not in documents(self.root):
            raise I18nError(f"the site has no document '{slug}'")
        label = f"{lang}/{slug}"
        header = _read(self.root, lang, f"{slug}.md").header
        current = self.english.fingerprint(slug)
        found = [] if header[TRANSLATES] == slug else [f"{label}: `{TRANSLATES}` says '{header[TRANSLATES]}'"]
        for each in _headers(self.root, lang, slug):
            found += check_fingerprint(lang, slug, each.get(FINGERPRINT), current)
        found += self.content(lang, slug, label)
        own = translation_fingerprint(self.root, lang, slug)
        found += check_approval_record(label, header, self.records, own, current) + check_approval(label, header, self.records, self.approvers)
        return list(dict.fromkeys(found))


def check_page(root: Path, lang: str, slug: str) -> list[str]:
    """Every check of one translation against the English page of today (stale fingerprint, `translates`, identity, numbers, glossary,
    approval and its record, `home.html` for `index`). Findings start with `<lang>/<slug>`. Raises I18nError for a file or slug that is not there."""
    return _Checker(root).page(lang, slug)


def _confirmed(lang: str, document: str) -> bool:
    try:
        typed = input(f"Approve {lang}/{document}? Type {lang}/{document} to confirm: ")
    except EOFError:
        return False
    return typed.strip() == f"{lang}/{document}"


def _approval_source(root: Path, lang: str, document: str) -> str:
    """The English fingerprint the approval is for. Raises I18nError for a document that does not exist or whose draft is stale."""
    if document == UI_FILE:
        if not ui_path(root, lang).is_file():
            raise I18nError(f"{SITE}/{I18N}/{lang}/{UI_FILE} does not exist")
        return ui_source_fingerprint(root)
    if document not in documents(root):
        raise I18nError(f"the site has no document '{document}'")
    absent = _absent(root, lang, document)
    if absent:
        raise I18nError(f"{lang}/{document}: {', '.join(absent)} does not exist; the document is missing")
    current = _English(root).fingerprint(document)
    for header in _headers(root, lang, document):
        if header.get(FINGERPRINT) != current:
            raise I18nError(f"{lang}/{document} is stale: re-draft it and run stamp before approving")
    return current


def approve(root: Path, lang: str, document: str, by: str, today: str) -> str:
    """The only writer of an approval. Raises I18nError, writing nothing, when `sys.stdin` is not a terminal, when `by` is not on
    `approvers.txt`, or when the line typed at the prompt is not `<lang>/<document>`. Otherwise sets `status: approved` in the header(s)
    of the document and writes its record (`APPROVAL_KEYS`) into `approvals.json`, replacing the record of the same language and document;
    returns the English fingerprint. `document` may be `ui.json`."""
    _require_declared(root, lang)
    if not sys.stdin.isatty():
        raise I18nError("approve needs a terminal: it asks for a typed confirmation")
    if by not in _approvers(root):
        raise I18nError(f"'{by}' is not in {APPROVERS_FILE}")
    source = _approval_source(root, lang, document)
    own = translation_fingerprint(root, lang, document)
    if not own:
        raise I18nError(f"{lang}/{document} cannot be read")
    if not _confirmed(lang, document):
        raise I18nError("not confirmed: nothing was written")
    record = dict(zip(APPROVAL_KEYS, (lang, document, source, own, by, today)))
    kept = [item for item in _records(root) if (item.get(LANGUAGE_KEY), item.get(DOCUMENT_KEY)) != (lang, document)]
    (root / APPROVALS_FILE).write_text(json.dumps([*kept, record], indent=2, ensure_ascii=False) + "\n", encoding=ENCODING)
    if document != UI_FILE:
        for path in _page_files(_folder(root, lang), document):
            _update_header(path, {STATUS: APPROVED})
    return source


def _state(root: Path, lang: str, slug: str, current: str, records: list[dict]) -> str:
    """The first word of `STATE_WORDS` that applies to one document of a language."""
    if _absent(root, lang, slug):
        return STATE_WORDS[0]
    try:
        headers = _headers(root, lang, slug)
    except (I18nError, OSError, UnicodeDecodeError):
        return STATE_WORDS[1]
    if any(header.get(FINGERPRINT) != current for header in headers):
        return STATE_WORDS[1]
    own = translation_fingerprint(root, lang, slug)
    if all(header.get(STATUS) == APPROVED for header in headers) and any(record.get(FINGERPRINT) == current and record.get(HASH_KEY) == own
                                                   for record in _of_document(records, f"{lang}/{slug}")):
        return STATE_WORDS[3]
    return STATE_WORDS[2]


def status(root: Path) -> dict[str, dict[str, int]]:
    """FR-019, US3-AS6: for each language of `site/site.json` but `en`, the count of each word of `STATE_WORDS` over the documents, a document
    in the first that applies: no file `missing`; a fingerprint that is not the English one of today `stale`; `approved` with a matching record
    `approved`; otherwise `machine-drafted`. A missing `approvals.json` is no approval."""
    english, records = _English(root), _records(root)
    current = {slug: english.fingerprint(slug) for slug in documents(root)}
    languages = [code for code in _declared(_read_ui(root / SITE_FILE)) if code != ENGLISH]
    counts = {code: Counter(_state(root, code, slug, value, records) for slug, value in current.items()) for code in languages}
    return {code: {word: row[word] for word in STATE_WORDS} for code, row in counts.items()}


def render_status(counts: dict[str, dict[str, int]]) -> str:
    """One line per language: its code, then each word of `STATE_WORDS` in that order followed by its number."""
    return "".join(f"{code:<4}" + "  ".join(f"{word} {row[word]}" for word in STATE_WORDS) + "\n" for code, row in counts.items())


def _ui_state(root: Path, lang: str, records: list[dict]) -> str | None:
    """The finding of the interface file of one language, or None when its record matches the file and the English source of today."""
    own = translation_fingerprint(root, lang, UI_FILE)
    source = ui_source_fingerprint(root)
    if own and any(record.get(FINGERPRINT) == source and record.get(HASH_KEY) == own for record in _of_document(records, f"{lang}/{UI_FILE}")):
        return None
    return f"{lang}/{UI_FILE}: {NOT_APPROVED}"


def _gate_words(root: Path, lang: str, slug: str, state: str) -> str:
    if state == STATE_WORDS[0]:
        return f"{state} ({', '.join(_absent(root, lang, slug))})"
    return NOT_APPROVED if state == STATE_WORDS[2] else state


def check_enable_gate(root: Path, lang: str) -> list[str]:
    """FR-024, US4-AS4, AS5: one finding per document of `lang` (`<lang>/<slug>: missing`, `: stale` or `: not approved`) and one for
    `<lang>/ui.json: not approved` when its record is missing, stale or does not match the file. No finding when all are current and approved."""
    english, records = _English(root), _records(root)
    found = []
    for slug in documents(root):
        state = _state(root, lang, slug, english.fingerprint(slug), records)
        if state != APPROVED:
            found.append(f"{lang}/{slug}: " + _gate_words(root, lang, slug, state))
    ui = _ui_state(root, lang, records)
    return found + ([ui] if ui else [])


def _complete(config: dict) -> bool:
    options = config.get(I18N)
    return (isinstance(options, dict) and options.get(COMPLETE_KEY) is True) or bool(enabled_languages(config))


def _checked_files(root: Path, lang: str) -> list[str]:
    """The slugs of the documents that have a translation file in the folder of `lang`."""
    return [slug for slug in documents(root) if (_folder(root, lang) / f"{slug}.md").is_file()]


def _language_findings(checker: _Checker, root: Path, lang: str) -> list[str]:
    found = check_scope(root, lang)
    for slug in _checked_files(root, lang):
        try:
            found += checker.page(lang, slug)
        except I18nError as error:
            found.append(f"{lang}/{slug}: {error}")
    return found


def check_site(root: Path) -> list[str]:
    """The findings of `check_page` for every translation file of every language folder, of `check_scope`, and, when `i18n.complete` is true,
    `<lang>/<slug>: missing` for each missing document of each declared language. A missing document is no finding otherwise."""
    config = _read_ui(root / SITE_FILE)
    codes = [code for code in _declared(config) if code != ENGLISH]
    present = [code for code in codes if _folder(root, code).is_dir() or code in enabled_languages(config)]
    checker = _Checker(root)
    found: list[str] = []
    for code in present:
        found += _language_findings(checker, root, code)
    if _complete(config):
        found += [f"{code}/{slug}: {STATE_WORDS[0]}" for code in codes for slug in missing_pages(root, code)]
    return found


def _run_stamp(root: Path, args: argparse.Namespace) -> int:
    print(stamp(root, args.language, args.document, datetime.date.today().isoformat()))
    return 0


def _run_status(root: Path, args: argparse.Namespace) -> int:
    sys.stdout.write(render_status(status(root)))
    return 0


def _run_gate(root: Path, args: argparse.Namespace) -> int:
    findings = check_enable_gate(root, args.language)
    for finding in findings:
        print(finding, file=sys.stderr)
    return 1 if findings else 0


def _run_approve(root: Path, args: argparse.Namespace) -> int:
    approve(root, args.language, args.document, args.by, datetime.date.today().isoformat())
    return 0


# name -> (handler, positional arguments, help)
SUBCOMMANDS = {
    "stamp": (_run_stamp, ("language", "document"), "record the English fingerprint in a draft"),
    STATUS: (_run_status, (), "count the documents of each language by state"),
    "gate": (_run_gate, ("language",), "list what keeps a language from being enabled"),
    "approve": (_run_approve, ("language", "document"), "approve a document (asks for a typed confirmation)"),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translations of the docs site (spec 004-site-languages).")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, (handler, arguments, text) in SUBCOMMANDS.items():
        command = commands.add_parser(name, help=text)
        for argument in arguments:
            command.add_argument(argument)
        if name == "approve":
            command.add_argument("--by", required=True, help="a name of approvers.txt")
        command.set_defaults(handler=handler)
    return parser


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    """`stamp <lang> <slug>`, `status`, `gate <lang>` (exit 1, findings on stderr, when the gate has any) and `approve <lang> <document>
    --by <name>` (exit 2, nothing written, without a terminal). Dispatches through a table of subcommands."""
    args = _parser().parse_args(argv)
    base = root if root is not None else Path(__file__).resolve().parent.parent
    try:
        return args.handler(base, args)
    except I18nError as error:
        print(f"site_i18n: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
