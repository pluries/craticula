"""The public files name the maintainer and link to the pages that show who they are (the open-source certificate's project check needs a
clear relationship between the subscriber and the project). Public, like the other site tests. Standard library only."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "Christian Stephan"
PERSONAL_SITE = "https://cstephan.dev"
PROFILE = "https://www.linkedin.com/in/christian-stephan"
GITHUB = "https://github.com/chrisstephanrm"
FILES = ("site/home.html", "README.md", "NOTICE")


def read(relative: str) -> str:
    path = ROOT / relative
    assert path.is_file(), f"{relative} does not exist"
    return path.read_text(encoding="utf-8")


# the footer stays as DS-16 fixes it (licence, repository, spec version): the maintainer line is on the home page
class MaintainerIdentityTests(unittest.TestCase):
    def test_every_public_entry_point_names_the_maintainer(self):
        for relative in FILES:
            with self.subTest(file=relative):
                self.assertIn(NAME, read(relative))

    def test_the_site_and_the_readme_link_to_both_profiles(self):
        for relative in ("site/home.html", "README.md"):
            with self.subTest(file=relative):
                text = read(relative)
                self.assertIn(PERSONAL_SITE, text)
                self.assertIn(PROFILE, text)
                self.assertIn(GITHUB, text)

    def test_the_notice_file_carries_the_copyright_line(self):
        text = read("NOTICE")
        self.assertIn(f"Copyright 2026 {NAME}", text)
        self.assertTrue(text.startswith("Craticula"))

    def test_the_license_text_is_the_unchanged_apache_2_text(self):
        text = read("LICENSE")
        self.assertIn("Apache License", text)
        self.assertIn("Version 2.0, January 2004", text)
        self.assertIn("[name of copyright owner]", text)   # the appendix boilerplate stays as published; the notice lives in NOTICE


if __name__ == "__main__":
    unittest.main()
