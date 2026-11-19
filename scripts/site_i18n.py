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

import functools
import hashlib
import html
import json
import re
import shutil
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
UI_MAPS = (GROUPS, "group_names", "subgroups", "theme_names")
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


def _page_files(folder: Path, slug: str) -> list[Path]:
    """The files of one document: its Markdown and, for the home page, its template."""
    names = [f"{slug}.md"] + (["home.html"] if slug == "index" else [])
    return [folder / name for name in names if (folder / name).is_file()]


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

    def is_stale(self, lang: str, slug: str, current: str) -> bool:
        """Whether the file's recorded English fingerprint is not `current`; a file that cannot be read is stale."""
        try:
            return _read(self.root, lang, f"{slug}.md").header.get(FINGERPRINT) != current
        except (I18nError, OSError):
            return True

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
    return ui


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
    clash = sorted(set(slugs) & language_prefixes(config)) if not any(problems) else []
    if clash:
        problems.append(f"page slug '{clash[0]}' is also the prefix of a language folder; a page cannot take a language's name")
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
    """A language that is disabled, or a page that is removed, must leave nothing in the output."""
    for name in language_prefixes(config):
        if SAFE_NAME.fullmatch(name):
            shutil.rmtree(out_dir / name, ignore_errors=True)


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
