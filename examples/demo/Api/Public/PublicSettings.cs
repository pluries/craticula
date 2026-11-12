using System.Net;

namespace Demo.Api.Public;

/// <summary>
/// The public-mode settings, read from configuration (environment variables are part of it):
/// <c>DEMO_PUBLIC</c> ("1" turns the mode on), <c>DEMO_TRUSTED_PROXIES</c> (comma-separated CIDR list, default empty),
/// <c>DEMO_GLOBAL_LIMIT</c> (requests a minute for the whole process, default 600), <c>DEMO_PROVIDERS</c> (comma-separated
/// route names; empty or unset means every registered provider), <c>DEMO_WEB_DIR</c> (folder of the built page; unset means no page).
/// </summary>
public sealed record PublicSettings
{
    public const string EnabledKey = "DEMO_PUBLIC";
    public const string TrustedProxiesKey = "DEMO_TRUSTED_PROXIES";
    public const string GlobalLimitKey = "DEMO_GLOBAL_LIMIT";
    public const string ProvidersKey = "DEMO_PROVIDERS";
    public const string WebDirKey = "DEMO_WEB_DIR";

    public const int DefaultGlobalLimitPerMinute = 600;

    /// <summary>Requests a minute for one client address. Windows start at an address's first request, not on the clock minute.</summary>
    public const int AddressLimitPerMinute = 60;

    /// <summary>A grid query running longer than this is cancelled and the API answers 504 with error kind <c>query-timeout</c>.</summary>
    public static readonly TimeSpan QueryTimeout = TimeSpan.FromSeconds(2);

    /// <summary>The same limit in milliseconds, for the databases that cut a query themselves (MongoDB: the library's <c>maxTimeMS</c>).</summary>
    public static int QueryTimeoutMs => (int)QueryTimeout.TotalMilliseconds;

    /// <summary>For MongoDB's grid, values and query routes the database cuts at <see cref="QueryTimeout"/>; the gate then waits this much
    /// longer, so it is only a backstop that cannot pre-empt the database's own answer. An export has no database-side limit and keeps the gate's cut.</summary>
    public static readonly TimeSpan DatabaseCutBackstop = TimeSpan.FromSeconds(2);

    public required IReadOnlyList<string> TrustedProxies { get; init; }

    public required int GlobalLimitPerMinute { get; init; }

    public required IReadOnlyList<string> Providers { get; init; }

    public string? WebDir { get; init; }

    /// <summary>A malformed value stops the host at startup with a message that names the variable and never quotes the value.</summary>
    public static PublicSettings From(IConfiguration configuration)
    {
        var trusted = List(configuration[TrustedProxiesKey]);
        foreach (var cidr in trusted)
        {
            if (!IPNetwork.TryParse(cidr, out _))
            {
                throw new InvalidOperationException($"{TrustedProxiesKey} is not a comma-separated list of CIDR ranges.");
            }
        }

        var limit = DefaultGlobalLimitPerMinute;
        var rawLimit = configuration[GlobalLimitKey];
        if (!string.IsNullOrWhiteSpace(rawLimit)
            && (!int.TryParse(rawLimit, System.Globalization.NumberStyles.None, System.Globalization.CultureInfo.InvariantCulture, out limit) || limit < 1))
        {
            throw new InvalidOperationException($"{GlobalLimitKey} is not a positive whole number.");
        }

        var webDir = configuration[WebDirKey];
        return new PublicSettings
        {
            TrustedProxies = trusted,
            GlobalLimitPerMinute = limit,
            Providers = List(configuration[ProvidersKey]),
            WebDir = string.IsNullOrWhiteSpace(webDir) ? null : webDir
        };
    }

    private static string[] List(string? value) =>
        value is null ? [] : value.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
}
