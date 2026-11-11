using Demo.Api.Errors;
using Microsoft.Data.Sqlite;

namespace Demo.Api.Seed;

/// <summary>What `seed [provider ...]` asked for: the targets to fill, or the names that are not known.</summary>
public sealed record SeedPlan(IReadOnlyList<SeedTarget> Targets, IReadOnlyList<string> Unknown);

/// <summary>
/// The `seed` command: generate once, write the same rows to each requested database, print the counts. Each provider is
/// seeded on its own, so a database that is down reports its error and the others still run.
/// Exit codes: 0 every requested provider holds the right count, 1 a count differs, 2 a provider failed or a name is unknown.
/// </summary>
public static class SeedCommand
{
    /// <summary>Pure: no argument means the default targets; names (case-insensitive, repeats ignored) select a subset in the order given.</summary>
    public static SeedPlan Parse(IReadOnlyList<string> names, IReadOnlyList<SeedTarget> known)
    {
        if (names.Count == 0)
        {
            return new SeedPlan([.. known.Where(target => target.Default)], []);
        }

        var targets = new List<SeedTarget>();
        var unknown = new List<string>();
        foreach (var name in names)
        {
            var target = known.FirstOrDefault(candidate => string.Equals(candidate.Name, name, StringComparison.OrdinalIgnoreCase));
            if (target is null)
            {
                unknown.Add(name);
            }
            else if (!targets.Contains(target))
            {
                targets.Add(target);
            }
        }

        return new SeedPlan(targets, unknown);
    }

    public static Task<int> RunAsync(IReadOnlyList<string> names) =>
        RunAsync(names, SeedTargets.All, Console.Out, Console.Error);

    public static async Task<int> RunAsync(
        IReadOnlyList<string> names, IReadOnlyList<SeedTarget> known, TextWriter output, TextWriter error)
    {
        var plan = Parse(names, known);
        if (plan.Unknown.Count > 0)
        {
            error.WriteLine($"Unknown provider: {string.Join(", ", plan.Unknown)}. Known providers: {string.Join(", ", known.Select(target => target.Name))}.");
            return 2;
        }

        var rows = OrderGenerator.Generate();
        output.WriteLine($"Generated {rows.Count} orders (seed {OrderGenerator.Seed}).");

        var seedChecksum = SeedChecksum.Of(rows);
        var mismatch = false;
        var checksumMismatch = false;
        var failed = false;
        foreach (var target in plan.Targets)
        {
            try
            {
                var count = await target.SeedAsync(rows);
                output.WriteLine(target.Describe(count));
                mismatch |= count != rows.Count;
                if (target.ChecksumAsync is not null)
                {
                    var stored = await target.ChecksumAsync();
                    if (stored != seedChecksum)
                    {
                        checksumMismatch = true;
                        error.WriteLine($"Checksum mismatch for {target.Name}: database {stored}, seed {seedChecksum}");
                    }
                }
            }
            catch (Exception ex) when (IsSeedFailure(ex))
            {
                failed = true;
                error.WriteLine($"Seed failed for {target.Name}: {ex.Message}");
                error.WriteLine(target.Hint);
            }
        }

        // Every value printed here already equals the seed's: a target that read another one reported a mismatch above.
        if (!failed && !checksumMismatch)
        {
            output.WriteLine($"Checksum: {seedChecksum}");
        }

        return failed ? 2 : mismatch || checksumMismatch ? 1 : 0;
    }

    /// <summary>
    /// What counts as that provider failing (printed with its hint, exit 2, the others still run): an engine that is down, plus the
    /// ordinary setup failures of a file database: any SQLite error (a read-only or not-a-database file) and the file system's own
    /// (a folder that cannot be created or written), an optional engine whose setting is missing, and a MySQL refusal of the login or the database (1045, 1044, 1049), a SQL Server login failure (18456) and the PostgreSQL equivalents (28P01 a refused password, 28000 a refused connection, 3D000 a missing database): setting problems, not bugs. Anything else is a bug and still ends the command.
    /// </summary>
    private static bool IsSeedFailure(Exception ex) =>
        EngineFailures.IsUnavailable(ex) || ex is SqliteException or IOException or UnauthorizedAccessException or SeedSettingException
            or MySqlConnector.MySqlException { Number: 1045 or 1044 or 1049 }
            or Microsoft.Data.SqlClient.SqlException { Number: 18456 }
            or Npgsql.PostgresException { SqlState: "28P01" or "28000" or "3D000" };
}
