#!/usr/bin/env python3
"""Pins the pack smoke's package inspection (scripts/pack_smoke.py) offline with synthetic nupkgs (story #1658, AC-2).

No dotnet, no network: each case writes tiny zips (a nuspec, a README, an XML doc, a hand-built PE image with an
embedded Portable PDB) into a temporary folder and runs `inspect_feed` over it. Run: python3 scripts/test_pack_smoke.py
(also run by Craticula.Conformance.Tests/PackSmokeTests.cs on every `dotnet test`).
"""
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pack_check_unpublished as check  # noqa: E402
import pack_smoke as smoke  # noqa: E402

VERSION = "1.0.0"
COMMIT = "a" * 40


def make_pe(pdb: bytes | None, kind: int = smoke.DEBUG_TYPE_EMBEDDED_PDB) -> bytes:
    """A minimal PE32+ image: one section holding a debug directory with one entry whose blob is MPDB + deflate(pdb)."""
    section_rva, section_raw = 0x1000, 0x200
    blob = b"" if pdb is None else b"MPDB" + struct.pack("<I", len(pdb)) + zlib.compress(pdb)[2:-4]
    entry_offset = section_raw
    blob_offset = section_raw + 28
    entries = b"" if pdb is None else struct.pack("<IIHHIIII", 0, 0, 0, 0, kind, len(blob), section_rva + 28, blob_offset)
    optional = bytearray(112 + 16 * 8)
    struct.pack_into("<H", optional, 0, 0x20B)
    struct.pack_into("<II", optional, 112 + 6 * 8, section_rva if pdb is not None else 0, len(entries))
    pe_offset = 0x80
    header = bytearray(0x200)
    header[0:2] = b"MZ"
    struct.pack_into("<I", header, 0x3C, pe_offset)
    header[pe_offset:pe_offset + 4] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", header, pe_offset + 4, 0x8664, 1, 0, 0, 0, len(optional), 0)
    header[pe_offset + 24:pe_offset + 24 + len(optional)] = optional
    section = pe_offset + 24 + len(optional)
    struct.pack_into("<8sIIII", header, section, b".rdata", 0x1000, section_rva, 0x1000, section_raw)
    return bytes(header) + entries + blob


GOOD_PDB = b"BSJB" + b"\0" * 32 + smoke.SOURCELINK_GUID + b"\0" * 16


def nuspec(package_id, version=VERSION, license_text=smoke.LICENSE, license_type="expression", readme_element="README.md",
           repository_url=smoke.REPOSITORY_URL, commit=COMMIT, dependencies=None, description="A package."):
    if dependencies is None:
        dependencies = {}
    deps = "".join(f'<dependency id="{name}" version="{value}" />' for name, value in dependencies.items())
    return (
        '<?xml version="1.0"?><package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd"><metadata>'
        f"<id>{package_id}</id><version>{version}</version><authors>x</authors>"
        f'<license type="{license_type}">{license_text}</license>'
        + (f"<readme>{readme_element}</readme>" if readme_element else "")
        + f"<description>{description}</description>"
        + (f'<repository type="git" url="{repository_url}" commit="{commit}" />' if repository_url else "")
        + f'<dependencies><group targetFramework="net10.0">{deps}</group></dependencies></metadata></package>'
    )


def default_dependencies(package_id):
    deps = {"Craticula.Core": VERSION} if package_id != "Craticula.Core" else {}
    deps.update(smoke.EXPECTED_RANGES.get(package_id, {}) and {
        name: value.replace(",", ", ") for name, value in smoke.EXPECTED_RANGES[package_id].items()})
    return deps


def write_package(feed: Path, package_id: str, *, version=VERSION, pe: bytes | None = None, readme: bool = True,
                  xml_doc: bool = True, extra_files=(), **spec):
    spec.setdefault("dependencies", default_dependencies(package_id))
    spec.setdefault("version", version)
    path = feed / f"{package_id}.{version}.nupkg"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{package_id}.nuspec", nuspec(package_id, **spec))
        if readme:
            archive.writestr("README.md", "# readme\n")
        archive.writestr(f"{smoke.TARGET_FOLDER}/{package_id}.dll", pe if pe is not None else make_pe(GOOD_PDB))
        if xml_doc:
            archive.writestr(f"{smoke.TARGET_FOLDER}/{package_id}.xml", "<doc />")
        for name in extra_files:
            archive.writestr(name, "x")
    return path


def good_feed(feed: Path):
    for package_id in smoke.PACKAGES:
        write_package(feed, package_id)


class PackSmokeInspection(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.feed = Path(self._tmp.name)

    def defects(self):
        return smoke.inspect_feed(self.feed, VERSION)

    def assert_defect(self, package_id: str, needle: str):
        found = self.defects()
        self.assertTrue(any(d.startswith(f"{package_id}: ") and needle in d for d in found),
                        f"expected a defect for {package_id} containing '{needle}', got: {found}")

    def test_good_set_passes(self):
        good_feed(self.feed)
        self.assertEqual([], self.defects())

    def test_missing_readme_fails(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.Sql", readme=False)
        self.assert_defect("Craticula.Sql", "README 'README.md' is declared but not in the package")

    def test_nuspec_without_readme_element_fails(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.Mongo", readme_element="")
        self.assert_defect("Craticula.Mongo", "no readme element")

    def test_missing_adapter_range_fails(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.Dapper", dependencies={"Craticula.Core": VERSION, "Craticula.Sql": VERSION})
        self.assert_defect("Craticula.Dapper", "dependency range for 'Dapper' is missing")

    def test_wrong_adapter_range_fails(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.MongoDB.Driver",
                      dependencies={"Craticula.Core": VERSION, "MongoDB.Driver": "3.14.1"})
        self.assert_defect("Craticula.MongoDB.Driver", "expected exactly [3.14.1,4.0.0)")

    def test_range_spelled_with_spaces_or_short_upper_bound_passes(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.OpenSearch.Client",
                      dependencies={"Craticula.Core": VERSION, "OpenSearch.Client": "[2.2.0, 3.0)"})
        self.assertEqual([], self.defects())

    def test_stray_third_party_dependency_on_a_core_package_fails(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.Search", dependencies={"Craticula.Core": VERSION, "Newtonsoft.Json": "13.0.3"})
        self.assert_defect("Craticula.Search", "third-party dependency 'Newtonsoft.Json'")

    def test_extra_third_party_dependency_on_an_adapter_fails(self):
        good_feed(self.feed)
        deps = default_dependencies("Craticula.Dapper") | {"Newtonsoft.Json": "13.0.3"}
        write_package(self.feed, "Craticula.Dapper", dependencies=deps)
        self.assert_defect("Craticula.Dapper", "unexpected third-party dependency 'Newtonsoft.Json'")

    def test_craticula_dependency_with_the_wrong_version_fails(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.Sql", dependencies={"Craticula.Core": "0.9.0"})
        self.assert_defect("Craticula.Sql", "expected the package version 1.0.0")

    def test_wrong_license_fails(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.Core", license_text="MIT")
        self.assert_defect("Craticula.Core", "license is 'MIT'")

    def test_license_as_file_instead_of_expression_fails(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.Core", license_type="file")
        self.assert_defect("Craticula.Core", "license is")

    def test_wrong_version_fails(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.Core", version="1.0.1", dependencies={})
        (self.feed / "Craticula.Core.1.0.0.nupkg").unlink()
        self.assert_defect("Craticula.Core", "version is '1.0.1', the Version property is '1.0.0'")

    def test_wrong_repository_url_fails(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.Core", repository_url="https://example.invalid/x")
        self.assert_defect("Craticula.Core", "repository URL is 'https://example.invalid/x'")

    def test_missing_repository_commit_fails(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.Core", commit="")
        self.assert_defect("Craticula.Core", "repository commit is missing")

    def test_missing_xml_doc_fails(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.Core", xml_doc=False)
        self.assert_defect("Craticula.Core", "XML documentation file")

    def test_loose_pdb_fails(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.Core", extra_files=[f"{smoke.TARGET_FOLDER}/Craticula.Core.pdb"])
        self.assert_defect("Craticula.Core", "loose PDB")

    def test_dll_without_embedded_pdb_fails(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.Core", pe=make_pe(None))
        self.assert_defect("Craticula.Core", "no embedded PDB")

    def test_embedded_pdb_without_sourcelink_fails(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.Core", pe=make_pe(b"BSJB" + b"\0" * 64))
        self.assert_defect("Craticula.Core", "no SourceLink map")

    def test_garbage_dll_fails(self):
        good_feed(self.feed)
        write_package(self.feed, "Craticula.Core", pe=b"not a pe")
        self.assert_defect("Craticula.Core", "not a readable .NET assembly")

    def test_missing_package_fails(self):
        good_feed(self.feed)
        (self.feed / "Craticula.Export.Csv.1.0.0.nupkg").unlink()
        self.assert_defect("Craticula.Export.Csv", "no .nupkg was produced")

    def test_symbol_package_fails(self):
        good_feed(self.feed)
        (self.feed / "Craticula.Core.1.0.0.snupkg").write_bytes(b"x")
        self.assertTrue(any("symbol package" in d for d in self.defects()))

    def test_corrupt_zip_names_the_package_file(self):
        good_feed(self.feed)
        (self.feed / "Craticula.Core.1.0.0.nupkg").write_bytes(b"not a zip")
        self.assert_defect("Craticula.Core", "not a readable zip")


class PackSmokeHelpers(unittest.TestCase):
    def test_range_normalization(self):
        self.assertEqual("[2.1.79,3.0.0)", smoke.norm_range("[2.1.79, 3.0)"))
        self.assertEqual("[10.0.11,11.0.0)", smoke.norm_range("[10.0.11,11.0.0)"))
        self.assertEqual("2.1.79", smoke.norm_range("2.1.79"))
        self.assertEqual("1.0.0", smoke.norm_version("1.0"))

    def test_version_property_is_read_from_the_props_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            props = Path(tmp) / "Directory.Build.props"
            props.write_text("<Project><PropertyGroup><Version>2.3.4</Version></PropertyGroup></Project>", encoding="utf-8")
            self.assertEqual("2.3.4", smoke.read_version_property(props))
            props.write_text("<Project />", encoding="utf-8")
            with self.assertRaises(ValueError):
                smoke.read_version_property(props)

    def test_unlisted_project_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)
            for name in ("Craticula.Core", "Craticula.Brand.New"):
                (src / name).mkdir()
                (src / name / f"{name}.csproj").write_text("<Project />", encoding="utf-8")
            (src / "docs").mkdir()
            self.assertEqual(["Craticula.Brand.New"], smoke.unlisted_projects(src))

    def test_ten_packages_six_compile_only_four_adapters(self):
        self.assertEqual(10, len(smoke.PACKAGES))
        self.assertEqual(6, len(smoke.CORE_PACKAGES))
        self.assertEqual(4, len(smoke.EXPECTED_RANGES))


class PackCheckUnpublished(unittest.TestCase):
    """The release workflow's version-exists check, with an injected lookup (no network)."""

    def test_listed_version_is_reported(self):
        listed = {"Craticula.Core": ["0.9.0", "1.0.0"], "Craticula.Sql": ["0.9.0"]}
        found = check.published_ids("1.0.0", ("Craticula.Core", "Craticula.Sql", "Craticula.Mongo"), lambda i: listed.get(i))
        self.assertEqual(["Craticula.Core"], found)

    def test_unknown_id_404_counts_as_not_published(self):
        self.assertEqual([], check.published_ids("1.0.0", ("Craticula.Core",), lambda i: None))

    def test_version_forms_compare_equal(self):
        self.assertEqual(["Craticula.Core"], check.published_ids("1.0", ("Craticula.Core",), lambda i: ["1.0.0+abc"]))
        self.assertEqual([], check.published_ids("1.0.0", ("Craticula.Core",), lambda i: ["1.0.0-rc.1"]))

    def test_lookup_failure_propagates_so_the_check_fails_closed(self):
        def broken(_):
            raise check.RegistryLookupError("down")
        with self.assertRaises(check.RegistryLookupError):
            check.published_ids("1.0.0", ("Craticula.Core",), broken)

    def test_ids_are_the_smoke_list(self):
        self.assertIs(smoke.PACKAGES, check.smoke.PACKAGES)


if __name__ == "__main__":
    unittest.main()
