#!/usr/bin/env python3
"""Pack smoke (story #1658, AC-2): proves the ten Craticula packages before anything is published.

Usage: pack_smoke.py [--root <repo>] [--feed <dir>] [--keep] [--skip-consumers]   (stdlib, Python 3.10+, .NET 10 SDK)

What it does, in order:
  1. `dotnet pack -c Release` of the ten csharp/src projects into a temporary local feed (never inside the repo tree).
     --feed <dir> skips the pack and inspects the .nupkg files already in <dir>.
  2. Inspects every .nupkg (zip + nuspec, no NuGet client): id, version (= the Version property of
     csharp/src/Directory.Build.props), license expression Apache-2.0, repository URL and commit, description, README
     present and non-empty, XML doc file, no loose .pdb, an embedded PDB that carries SourceLink, and the dependency
     list. The six compile-only packages may depend on Craticula.* only; each of the four adapters must carry exactly
     its third-party range (EXPECTED_RANGES) plus Craticula.* at the package version.
  3. Two scratch consumers in the temporary folder, each with its own NuGet packages folder (a stale cached
     Craticula.* cannot hide a defect): (a) Craticula.AgGrid + Craticula.Sql, restored from the local feed ALONE
     (nuget.config with <clear/>), built with warnings as errors and run on fixture operators/001-eq-string, whose
     printed PostgreSQL statement and parameters must equal the fixture's expected artifact; (b) Craticula.Dapper,
     restored from the local feed plus nuget.org (a source mapping keeps Craticula.* on the local feed), built.

HOW THE PDB AND SOURCELINK MARKERS ARE CHECKED. DebugType=embedded means no .pdb file in the package and a Portable
PDB inside the DLL, announced by a debug-directory entry of type 17 (EmbeddedPortablePDB). The script reads the PE
debug directory (stdlib struct), takes that entry's blob ("MPDB" + uncompressed size + raw deflate), inflates it with
zlib and requires the Portable PDB signature "BSJB" and the Source Link custom-debug-information GUID
CC110556-A091-4D38-9FEC-25AB9A351A6A in the PDB's GUID heap (present only when a SourceLink map was embedded). The
nuspec's <repository commit="..."> (40 hex digits) is checked as well.

Exit codes: 0 every check passed; 1 at least one defect, each printed as `pack-smoke: <package>: <defect>`;
2 usage or environment error (no dotnet, the temporary folder inside the repo, an unreadable props file).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path

CORE_PACKAGES = (
    "Craticula.Core",
    "Craticula.AgGrid",
    "Craticula.Sql",
    "Craticula.Mongo",
    "Craticula.Search",
    "Craticula.Export.Csv",
)

# Third-party ranges the nuspec of each adapter must carry, exactly (TRD OS-3; the csproj VersionOverride).
EXPECTED_RANGES: dict[str, dict[str, str]] = {
    "Craticula.Dapper": {"Dapper": "[2.1.89,3.0.0)"},
    "Craticula.MongoDB.Driver": {"MongoDB.Driver": "[3.14.0,4.0.0)"},
    "Craticula.OpenSearch.Client": {"OpenSearch.Client": "[2.2.0,3.0.0)"},
    "Craticula.EntityFrameworkCore": {"Microsoft.EntityFrameworkCore.Relational": "[10.0.12,11.0.0)"},
}

PACKAGES = CORE_PACKAGES + tuple(EXPECTED_RANGES)

LICENSE = "Apache-2.0"
REPOSITORY_URL = "https://github.com/pluries/craticula"
TARGET_FOLDER = "lib/net10.0"
FIXTURE = "operators/001-eq-string"

# Source Link custom debug information, CC110556-A091-4D38-9FEC-25AB9A351A6A, as stored in the PDB's GUID heap.
SOURCELINK_GUID = bytes.fromhex("560511cc91a0384d9fec25ab9a351a6a")
DEBUG_TYPE_EMBEDDED_PDB = 17

COMMAND_TIMEOUT = 900


# ---------------------------------------------------------------------------------------------------- versions

def norm_version(version: str) -> str:
    """Pads a numeric version to three parts so '3.0' and '3.0.0' compare equal; a prerelease suffix is kept."""
    core, dash, suffix = version.strip().partition("-")
    parts = core.split(".")
    while len(parts) < 3:
        parts.append("0")
    return ".".join(parts) + dash + suffix


def norm_range(version_range: str) -> str:
    """'[2.1.79, 3.0)' -> '[2.1.79,3.0.0)'; a bare version (a minimum-only range) -> that version, padded."""
    text = version_range.replace(" ", "")
    if text[:1] in "[(" and text[-1:] in "])" and "," in text:
        low, high = text[1:-1].split(",", 1)
        return f"{text[0]}{norm_version(low) if low else ''},{norm_version(high) if high else ''}{text[-1]}"
    return norm_version(text)


# ---------------------------------------------------------------------------------------------------- PE and PDB

def _section_offset(data: bytes, sections: list[tuple[int, int, int]], rva: int) -> int | None:
    for virtual_size, virtual_address, raw_pointer in sections:
        if virtual_address <= rva < virtual_address + max(virtual_size, 1):
            return raw_pointer + (rva - virtual_address)
    return None


def debug_entries(data: bytes) -> list[tuple[int, int, int]]:
    """The PE debug directory as (type, size, file offset) triples. Raises ValueError when data is not a PE image."""
    try:
        if data[:2] != b"MZ":
            raise ValueError("no MZ header")
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe:pe + 4] != b"PE\0\0":
            raise ValueError("no PE signature")
        coff = pe + 4
        section_count, = struct.unpack_from("<H", data, coff + 2)
        optional_size, = struct.unpack_from("<H", data, coff + 16)
        optional = coff + 20
        magic, = struct.unpack_from("<H", data, optional)
        directories = optional + (112 if magic == 0x20B else 96)
        debug_rva, debug_size = struct.unpack_from("<II", data, directories + 6 * 8)
        sections = []
        table = optional + optional_size
        for index in range(section_count):
            virtual_size, virtual_address, _raw_size, raw_pointer = struct.unpack_from("<IIII", data, table + index * 40 + 8)
            sections.append((virtual_size, virtual_address, raw_pointer))
        if debug_rva == 0 or debug_size == 0:
            return []
        start = _section_offset(data, sections, debug_rva)
        if start is None:
            raise ValueError("debug directory outside every section")
        entries = []
        for index in range(debug_size // 28):
            _flags, _stamp, _major, _minor, kind, size, _rva, pointer = struct.unpack_from("<IIHHIIII", data, start + index * 28)
            entries.append((kind, size, pointer))
        return entries
    except struct.error as error:
        raise ValueError(f"truncated image ({error})") from error


def check_dll(data: bytes) -> list[str]:
    """Defects of one DLL's debug information: an embedded Portable PDB that carries SourceLink."""
    try:
        entries = debug_entries(data)
    except ValueError as error:
        return [f"not a readable .NET assembly: {error}"]
    blobs = [(size, pointer) for kind, size, pointer in entries if kind == DEBUG_TYPE_EMBEDDED_PDB]
    if not blobs:
        return ["no embedded PDB (the PE debug directory has no EmbeddedPortablePDB entry; DebugType=embedded lost?)"]
    size, pointer = blobs[0]
    blob = data[pointer:pointer + size]
    if blob[:4] != b"MPDB" or len(blob) < 8:
        return ["embedded PDB entry has no MPDB header"]
    try:
        pdb = zlib.decompress(blob[8:], -15)
    except zlib.error as error:
        return [f"embedded PDB does not inflate ({error})"]
    if pdb[:4] != b"BSJB":
        return ["embedded PDB is not a Portable PDB (no BSJB signature)"]
    if SOURCELINK_GUID not in pdb:
        return ["embedded PDB carries no SourceLink map (Source Link GUID absent; PublishRepositoryUrl or the repository commit lost?)"]
    return []


# ---------------------------------------------------------------------------------------------------- nupkg

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def read_version_property(props: Path) -> str:
    match = re.search(r"<Version>\s*([^<\s]+)\s*</Version>", props.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"no <Version> property in {props}")
    return match.group(1)


def nuspec_of(archive: zipfile.ZipFile) -> ET.Element:
    names = [name for name in archive.namelist() if name.endswith(".nuspec") and "/" not in name]
    if len(names) != 1:
        raise ValueError(f"expected one root .nuspec, found {len(names)}")
    return ET.fromstring(archive.read(names[0]))


def inspect_nupkg(path: Path, version: str) -> tuple[str, list[str]]:
    """(package id, defects) of one .nupkg; the id is read from the nuspec, the file name when that fails."""
    stem = path.name[: -len(".nupkg")]
    fallback_id = next((name for name in sorted(PACKAGES, key=len, reverse=True) if stem.startswith(name + ".")), stem)
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as error:
        return fallback_id, [f"not a readable zip ({error})"]
    with archive:
        try:
            root = nuspec_of(archive)
        except (ValueError, ET.ParseError) as error:
            return fallback_id, [f"nuspec unreadable ({error})"]
        metadata = next((child for child in root if _local(child.tag) == "metadata"), None)
        if metadata is None:
            return fallback_id, ["nuspec has no metadata element"]
        fields = {_local(child.tag): child for child in metadata}

        def text(name: str) -> str:
            element = fields.get(name)
            return (element.text or "").strip() if element is not None else ""

        package_id = text("id") or fallback_id
        defects: list[str] = []

        if package_id not in PACKAGES:
            defects.append("id is not one of the ten shipped packages")
        if text("version") != version:
            defects.append(f"version is '{text('version')}', the Version property is '{version}'")
        if path.name != f"{package_id}.{text('version')}.nupkg":
            defects.append(f"file name {path.name} does not match id and version")

        license_element = fields.get("license")
        if license_element is None or license_element.get("type") != "expression" or (license_element.text or "").strip() != LICENSE:
            shown = (license_element.text or "").strip() if license_element is not None else "none"
            defects.append(f"license is '{shown}', expected the expression {LICENSE}")

        if not text("description"):
            defects.append("description is empty")

        repository = fields.get("repository")
        if repository is None or repository.get("url") != REPOSITORY_URL:
            shown = repository.get("url") if repository is not None else "none"
            defects.append(f"repository URL is '{shown}', expected {REPOSITORY_URL}")
        elif not re.fullmatch(r"[0-9a-f]{40}", repository.get("commit") or ""):
            defects.append("repository commit is missing or not a 40-digit hash (SourceLink needs a git checkout)")

        names = set(archive.namelist())
        readme = text("readme")
        if not readme:
            defects.append("nuspec has no readme element")
        elif readme not in names:
            defects.append(f"README '{readme}' is declared but not in the package")
        elif not archive.read(readme).strip():
            defects.append(f"README '{readme}' is empty")

        dll = f"{TARGET_FOLDER}/{package_id}.dll"
        xml_doc = f"{TARGET_FOLDER}/{package_id}.xml"
        if xml_doc not in names:
            defects.append(f"XML documentation file {xml_doc} is missing")
        elif not archive.read(xml_doc).strip():
            defects.append(f"XML documentation file {xml_doc} is empty")
        loose = sorted(name for name in names if name.lower().endswith(".pdb"))
        if loose:
            defects.append(f"loose PDB in the package ({', '.join(loose)}); the PDB must be embedded")
        if dll not in names:
            defects.append(f"assembly {dll} is missing")
        else:
            defects.extend(f"{dll}: {defect}" for defect in check_dll(archive.read(dll)))

        defects.extend(check_dependencies(package_id, version, metadata))
        return package_id, defects


def check_dependencies(package_id: str, version: str, metadata: ET.Element) -> list[str]:
    declared: dict[str, str] = {}
    for dependencies in (child for child in metadata if _local(child.tag) == "dependencies"):
        for node in dependencies.iter():
            if _local(node.tag) == "dependency":
                declared[node.get("id", "")] = node.get("version", "")

    defects: list[str] = []
    third_party = {name: value for name, value in declared.items() if not name.startswith("Craticula.")}
    expected = EXPECTED_RANGES.get(package_id, {})
    if package_id in CORE_PACKAGES or not expected:
        for name in sorted(third_party):
            defects.append(f"third-party dependency '{name}' {third_party[name]} on a compile-only package (only Craticula.* allowed)")
    else:
        for name, wanted in expected.items():
            if name not in third_party:
                defects.append(f"dependency range for '{name}' is missing (expected {wanted})")
            elif norm_range(third_party[name]) != wanted:
                defects.append(f"dependency '{name}' is '{third_party[name]}', expected exactly {wanted}")
        for name in sorted(set(third_party) - set(expected)):
            defects.append(f"unexpected third-party dependency '{name}' {third_party[name]}")

    for name, value in declared.items():
        if name.startswith("Craticula."):
            if name not in PACKAGES:
                defects.append(f"depends on '{name}', which is not one of the ten packages")
            elif norm_range(value) != norm_version(version):
                defects.append(f"depends on {name} '{value}', expected the package version {version}")
    return defects


def inspect_feed(feed: Path, version: str) -> list[str]:
    """Every defect in a folder of .nupkg files, as `<package>: <defect>` lines."""
    defects: list[str] = []
    seen: set[str] = set()
    files = sorted(feed.glob("*.nupkg"))
    for path in files:
        package_id, problems = inspect_nupkg(path, version)
        seen.add(package_id)
        defects.extend(f"{package_id}: {problem}" for problem in problems)
    for package_id in PACKAGES:
        if package_id not in seen:
            defects.append(f"{package_id}: no .nupkg was produced (IsPackable lost, or the pack failed)")
    for stray in sorted(feed.glob("*.snupkg")):
        defects.append(f"{stray.name}: symbol package produced; the PDB is meant to be embedded")
    return defects


def unlisted_projects(src: Path) -> list[str]:
    """csharp/src folders that hold a project but are not in PACKAGES (a new package must be added to the smoke)."""
    return sorted(
        folder.name
        for folder in src.iterdir()
        if folder.is_dir() and (folder / f"{folder.name}.csproj").is_file() and folder.name not in PACKAGES
    )


# ---------------------------------------------------------------------------------------------------- consumers

PROGRAM = """\
using System.Text.Json;
using Craticula.AgGrid;
using Craticula.Core.Schema;
using Craticula.Sql;

var schema = GridSchema.Parse(File.ReadAllText(args[0]));
var parsed = AgGridRequestParser.Parse(File.ReadAllText(args[1]), new AgGridParseOptions { Schema = schema });
var filter = GridFilterPipeline.Process(
    parsed.NativeFilter, parsed.CustomFilters, parsed.Page, schema, new ResourceLimits(),
    parsed.Group, parsed.Aggregations);
var query = SqlQueryBuilder.Build(
    new SqlQueryRequest { Schema = schema, Filter = filter, Sort = parsed.Sort, Page = parsed.Page },
    PostgresDialect.Instance);
Console.WriteLine(JsonSerializer.Serialize(new { dialect = query.Dialect, sql = query.Sql, @params = query.Parameters }));
"""

DAPPER_PROGRAM = """\
using System.Data;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Dapper;
using Craticula.Sql;

public static class Example
{
    public static Task<DapperGridPage> Fetch(
        IDbConnection openConnection, GridSchema schema, FilterNode? filter, IReadOnlyList<SortItem>? sort, PageSpec page) =>
        DapperGridQuery.FetchPageAsync(
            openConnection,
            new SqlQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
            PostgresDialect.Instance,
            includeRowCount: true);
}
"""


def nuget_config(feed: Path, with_nuget_org: bool) -> str:
    sources = f'    <add key="local" value="{feed}" />\n'
    mapping = ""
    if with_nuget_org:
        sources += '    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />\n'
        mapping = (
            "  <packageSourceMapping>\n"
            '    <packageSource key="local"><package pattern="Craticula.*" /></packageSource>\n'
            '    <packageSource key="nuget.org"><package pattern="*" /></packageSource>\n'
            "  </packageSourceMapping>\n"
        )
    return f'<?xml version="1.0" encoding="utf-8"?>\n<configuration>\n  <packageSources>\n    <clear />\n{sources}  </packageSources>\n{mapping}</configuration>\n'


def consumer_project(package_references: list[str], output_exe: bool) -> str:
    refs = "\n".join(f'    <PackageReference Include="{name}" Version="{{VERSION}}" />' for name in package_references)
    kind = "<OutputType>Exe</OutputType>" if output_exe else ""
    return (
        '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n    <TargetFramework>net10.0</TargetFramework>\n'
        f"    <Nullable>enable</Nullable>\n    <ImplicitUsings>enable</ImplicitUsings>\n    {kind}\n"
        "    <NuGetAudit>false</NuGetAudit>\n  </PropertyGroup>\n  <ItemGroup>\n"
        f"{refs}\n  </ItemGroup>\n</Project>\n"
    )


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        command, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=COMMAND_TIMEOUT
    )


def tail(result: subprocess.CompletedProcess, lines: int = 25) -> str:
    text = (result.stdout + "\n" + result.stderr).strip().splitlines()
    return "\n".join("    " + line for line in text[-lines:])


def build_consumer(name: str, folder: Path, feed: Path, cache: Path, projects: list[str], program: str,
                   version: str, exe: bool, with_nuget_org: bool) -> tuple[subprocess.CompletedProcess | None, list[str]]:
    """Writes, restores and builds one scratch consumer. Returns the build result (None when it failed) and defects."""
    folder.mkdir(parents=True)
    (folder / "nuget.config").write_text(nuget_config(feed, with_nuget_org), encoding="utf-8")
    (folder / f"{name}.csproj").write_text(consumer_project(projects, exe).replace("{VERSION}", version), encoding="utf-8")
    (folder / "Program.cs").write_text(program, encoding="utf-8")
    env = dict(os.environ, NUGET_PACKAGES=str(cache), DOTNET_NOLOGO="1", DOTNET_CLI_TELEMETRY_OPTOUT="1")
    label = " + ".join(projects)
    restore = run(["dotnet", "restore", "--nologo", "-v", "q"], folder, env)
    if restore.returncode != 0:
        return None, [f"{label}: clean consumer '{name}' does not restore ({'local feed only' if not with_nuget_org else 'local feed + nuget.org'})\n{tail(restore)}"]
    build = run(["dotnet", "build", "--no-restore", "-c", "Release", "--nologo", "-v", "q", "-warnaserror",
                 "-nodeReuse:false", "-p:UseSharedCompilation=false"], folder, env)
    if build.returncode != 0:
        return None, [f"{label}: clean consumer '{name}' does not compile\n{tail(build)}"]
    return build, []


def run_consumers(tmp: Path, feed: Path, version: str, fixture: Path) -> list[str]:
    defects: list[str] = []

    folder = tmp / "consumer-aggrid-sql"
    built, problems = build_consumer("ConsumerAgGridSql", folder, feed, tmp / "packages-aggrid-sql",
                                     ["Craticula.AgGrid", "Craticula.Sql"], PROGRAM, version, exe=True, with_nuget_org=False)
    defects.extend(problems)
    if built is not None:
        env = dict(os.environ, DOTNET_NOLOGO="1")
        ran = run(["dotnet", "run", "--no-build", "-c", "Release", "--", str(fixture / "schema.json"),
                   str(fixture / "agGridRequest.json")], folder, env)
        expected = json.loads((fixture / "expected" / "postgres.artifact.json").read_text(encoding="utf-8"))
        if ran.returncode != 0:
            defects.append(f"Craticula.AgGrid + Craticula.Sql: the consumer compiled but failed to run\n{tail(ran)}")
        else:
            try:
                printed = json.loads(ran.stdout.strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError):
                printed = None
            if printed != {"dialect": expected["dialect"], "sql": expected["sql"], "params": expected["params"]}:
                defects.append(
                    "Craticula.AgGrid + Craticula.Sql: the packaged compiler's PostgreSQL output differs from the fixture "
                    f"{FIXTURE} expected artifact\n    printed:  {ran.stdout.strip()}\n    expected: {json.dumps(expected)}"
                )

    folder = tmp / "consumer-dapper"
    _, problems = build_consumer("ConsumerDapper", folder, feed, tmp / "packages-dapper",
                                 ["Craticula.Dapper"], DAPPER_PROGRAM, version, exe=False, with_nuget_org=True)
    defects.extend(problems)
    return defects


# ---------------------------------------------------------------------------------------------------- main

def pack_all(root: Path, feed: Path) -> list[str]:
    defects: list[str] = []
    env = dict(os.environ, DOTNET_NOLOGO="1", DOTNET_CLI_TELEMETRY_OPTOUT="1")
    for package in PACKAGES:
        project = root / "csharp" / "src" / package / f"{package}.csproj"
        result = run(["dotnet", "pack", str(project), "-c", "Release", "-o", str(feed), "--nologo", "-v", "q"], root, env)
        if result.returncode != 0:
            defects.append(f"{package}: dotnet pack failed (exit {result.returncode})\n{tail(result)}")
    return defects


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Pack smoke (story #1658).")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--feed", type=Path, help="inspect the .nupkg files already in this folder instead of packing")
    parser.add_argument("--keep", action="store_true", help="keep the temporary folder and print its path")
    parser.add_argument("--skip-consumers", action="store_true", help="inspect the packages only")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    src = root / "csharp" / "src"
    props = src / "Directory.Build.props"
    if not props.is_file():
        print(f"pack-smoke: {props} not found (is --root the repository?)", file=sys.stderr)
        return 2
    try:
        version = read_version_property(props)
    except ValueError as error:
        print(f"pack-smoke: {error}", file=sys.stderr)
        return 2
    if shutil.which("dotnet") is None and (args.feed is None or not args.skip_consumers):
        print("pack-smoke: the dotnet CLI (.NET 10 SDK) is required on PATH", file=sys.stderr)
        return 2
    fixture = root / "spec" / "fixtures" / FIXTURE

    tmp = Path(tempfile.mkdtemp(prefix="craticula-pack-smoke-")).resolve()
    try:
        if tmp == root or root in tmp.parents:
            print(f"pack-smoke: the temporary folder {tmp} is inside the repository; set TMPDIR elsewhere", file=sys.stderr)
            return 2
        if args.keep:
            print(f"pack-smoke: temporary folder kept at {tmp}", file=sys.stderr)

        defects = [f"{name}: csharp/src/{name} holds a project that the smoke does not list (add it to PACKAGES)"
                   for name in unlisted_projects(src)]

        if args.feed is not None:
            feed = args.feed.resolve()
            if not feed.is_dir():
                print(f"pack-smoke: --feed {feed} is not a folder", file=sys.stderr)
                return 2
        else:
            feed = tmp / "feed"
            feed.mkdir()
            print(f"pack-smoke: packing {len(PACKAGES)} projects (Release, version {version})", flush=True)
            defects.extend(pack_all(root, feed))

        print("pack-smoke: inspecting the packages", flush=True)
        package_defects = inspect_feed(feed, version)
        defects.extend(package_defects)

        if args.skip_consumers:
            pass
        elif any("no .nupkg was produced" in defect for defect in package_defects):
            print("pack-smoke: consumers skipped, the feed is incomplete", flush=True)
        else:
            print("pack-smoke: restoring and building the clean consumers", flush=True)
            defects.extend(run_consumers(tmp, feed, version, fixture))

        if defects:
            for defect in defects:
                print(f"pack-smoke: {defect}")
            print(f"pack-smoke: FAILED, {len(defects)} defect(s)")
            return 1
        print(f"pack-smoke: OK, {len(PACKAGES)} packages at {version}")
        return 0
    except subprocess.TimeoutExpired as error:
        print(f"pack-smoke: a command timed out after {COMMAND_TIMEOUT}s: {' '.join(map(str, error.cmd))}", file=sys.stderr)
        return 2
    finally:
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
