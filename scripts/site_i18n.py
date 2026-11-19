#!/usr/bin/env python3
"""Translations of the docs site (spec 004-site-languages, tasks T001 to T003b).

SKELETON written by the test task (T001, T002): every function raises NotImplementedError until T003a and T003b fill it.
The contract the tests pin: a translation file is a header block of `key: value` lines plus a page (`parse_translation`),
`fingerprint` and `ui_fingerprint` say when an English source changed (US2-AS10, AS13, AS14, D-015), `check_fingerprint`
names a stale translation (US2-AS1), and `config_problem` says why `languages`, `i18n` and each page's `scope` of
`site/site.json` cannot be used (US1-AS13, FR-027). Standard library only; this module never imports `build_site` at the top.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class I18nError(Exception):
    """A translation file or the language configuration is not usable."""


@dataclass
class Translation:
    """A parsed translation file: its header keys and the page text that follows the header."""
    header: dict[str, str] = field(default_factory=dict)
    body: str = ""


def parse_translation(text: str) -> Translation:
    """Split a translation file into header and body. Raises I18nError naming the first of `translates`, `title`,
    `description`, `source_fingerprint`, `drafter`, `drafted_on`, `status` that is missing or empty, and for a `status`
    that is neither `machine-drafted` nor `approved` (US2-AS17)."""
    raise NotImplementedError


def fingerprint(text: str, title: str, description: str, home_template: str | None = None) -> str:
    """SHA-256 hex of an English document: `text` is the Markdown after `{{include}}` expansion (for the home document,
    `site/pages/index.md`); `home_template` is the text of `site/home.html` for the home document only (US2-AS10, AS13, AS14)."""
    raise NotImplementedError


def ui_fingerprint(english_ui: dict, groups: dict) -> str:
    """SHA-256 hex of the interface file's English source: the strings of `site/i18n/en/ui.json` plus the group card
    descriptions of `site/site.json` `groups` (D-015)."""
    raise NotImplementedError


def check_fingerprint(language: str, document: str, recorded: str | None, current: str) -> list[str]:
    """US2-AS1: no finding when `recorded` equals `current`; otherwise one finding naming the language, the document
    and both fingerprints (`recorded` None: the file records none)."""
    raise NotImplementedError


def config_problem(config: dict, slugs: list[str]) -> str | None:
    """Why the `languages` and `i18n` keys of site.json or a page's `scope` cannot be used, or None. `slugs` are the page
    slugs; one that equals a language prefix (a known folder or a declared `path`) is a problem (US1-AS13)."""
    raise NotImplementedError
