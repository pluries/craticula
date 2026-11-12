namespace Craticula.MongoDB.Driver.Offline.Tests;

/// <summary>
/// Locates repo-root-relative paths (e.g. <c>spec/fixtures/...</c>) from wherever the test assembly
/// happens to run. Deliberately mirrors <c>Craticula.Dapper.Tests.RepoPaths</c> and its siblings exactly
/// (each is <see langword="internal"/> to its own assembly, so none is reusable from here) rather than
/// introducing a shared assembly for one small helper.
/// </summary>
internal static class RepoPaths
{
    public static string Root { get; } = FindRepoRoot();

    public static string Fixture(params string[] segments)
    {
        var parts = new List<string> { Root, "spec", "fixtures" };
        parts.AddRange(segments);
        return Path.Combine(parts.ToArray());
    }

    /// <summary>The adapter's own source directory. Read by the structural guard that proves the export
    /// path can never construct a row window (see <c>MongoExportStreamTests</c>).</summary>
    public static string AdapterSource(params string[] segments)
    {
        var parts = new List<string> { Root, "csharp", "src", "Craticula.MongoDB.Driver" };
        parts.AddRange(segments);
        return Path.Combine(parts.ToArray());
    }

    private static string FindRepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            if (Directory.Exists(Path.Combine(dir.FullName, "spec")) &&
                Directory.Exists(Path.Combine(dir.FullName, "csharp")))
            {
                return dir.FullName;
            }

            dir = dir.Parent;
        }

        throw new DirectoryNotFoundException(
            $"Could not locate repo root (a directory containing both 'spec' and 'csharp') " +
            $"walking up from '{AppContext.BaseDirectory}'.");
    }
}
