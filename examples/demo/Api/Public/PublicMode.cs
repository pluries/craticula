using System.Net;
using System.Threading.RateLimiting;
using Demo.Api.Grid;
using Demo.Api.Seed;
using Microsoft.Extensions.FileProviders;

namespace Demo.Api.Public;

/// <summary>
/// The protections a public demo needs; <see cref="DemoApp.Build"/> calls both methods only when <c>DEMO_PUBLIC=1</c>.
/// <list type="bullet">
/// <item>Only the four grid routes (<c>POST /api/{provider}/rows|values|export.csv|query</c>) and <c>GET</c>s are served;
/// PUT, DELETE and any other POST answer 405.</item>
/// <item>Per-address limit of <see cref="PublicSettings.AddressLimitPerMinute"/>: the address is the <c>CF-Connecting-IP</c> header
/// when the connecting peer is inside <see cref="PublicSettings.TrustedProxies"/>, else the connection address. A refused request
/// answers 429 with <c>Retry-After</c> and never reaches a provider. A second limit, <see cref="PublicSettings.GlobalLimitPerMinute"/>,
/// counts every address together and answers 429 the same way.</item>
/// <item>A grid call is cancelled after <see cref="PublicSettings.QueryTimeout"/>: 504, <c>{ "error": { "kind": "query-timeout", ... } }</c>.</item>
/// <item>No response carries a <c>Set-Cookie</c> header.</item>
/// <item><c>DEMO_PROVIDERS</c> restricts the registered providers (so <c>/api/health</c> lists only them); <c>DEMO_WEB_DIR</c>
/// serves the built page from <c>/</c>.</item>
/// </list>
/// </summary>
public static class PublicMode
{
    private const string ForwardedForHeader = "CF-Connecting-IP";

    /// <summary>Registers the services (rate limiter, provider filter, settings).</summary>
    public static void Register(WebApplicationBuilder builder)
    {
        var settings = PublicSettings.From(builder.Configuration);
        var trusted = settings.TrustedProxies.Select(IPNetwork.Parse).ToArray();
        builder.Services.AddSingleton(settings);

        // The last registration wins: these replace the ones DemoApp made.
        if (settings.Providers.Count > 0)
        {
            builder.Services.AddSingleton(services => new ProviderRegistry(
                services.GetServices<IGridService>().Where(service => settings.Providers.Contains(service.Name, StringComparer.Ordinal))));
        }

        // The shipped appsettings.json lists localhost only, which would refuse the public hostname and the kubelet's probe on the pod IP.
        // Who may reach the pod is decided by the ingress and the network policy (ADR-0007), so the host-name filter has nothing left to add.
        builder.Configuration["AllowedHosts"] = "*";

        builder.Services.AddRateLimiter(options =>
        {
            options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
            // The per-address window comes first: a request it refuses does not use up the process-wide one.
            options.GlobalLimiter = PartitionedRateLimiter.CreateChained(
                PartitionedRateLimiter.Create<HttpContext, string>(context => IsHealth(context)
                    ? RateLimitPartition.GetNoLimiter("health")
                    : RateLimitPartition.GetFixedWindowLimiter(ClientAddress(context, trusted), _ => Window(PublicSettings.AddressLimitPerMinute))),
                PartitionedRateLimiter.Create<HttpContext, string>(context => IsHealth(context)
                    ? RateLimitPartition.GetNoLimiter("health")
                    : RateLimitPartition.GetFixedWindowLimiter("global", _ => Window(settings.GlobalLimitPerMinute))));
            options.OnRejected = async (rejection, cancellationToken) =>
            {
                var retryAfter = rejection.Lease.TryGetMetadata(MetadataName.RetryAfter, out var delay) ? delay : TimeSpan.FromMinutes(1);
                rejection.HttpContext.Response.Headers.RetryAfter = Math.Max(1, (int)Math.Ceiling(retryAfter.TotalSeconds)).ToString(System.Globalization.CultureInfo.InvariantCulture);
                await rejection.HttpContext.Response.WriteAsJsonAsync(
                    new { error = new { kind = "rate-limited", message = "Too many requests. Try again later." } }, cancellationToken);
            };
        });
    }

    /// <summary>Adds the middleware, before the error middleware and the routes.</summary>
    public static void Use(WebApplication app)
    {
        var settings = app.Services.GetRequiredService<PublicSettings>();

        app.UseRateLimiter();
        app.UseMiddleware<PublicGate>();

        if (settings.WebDir is { } webDir)
        {
            var files = new PhysicalFileProvider(Path.GetFullPath(webDir));
            app.UseDefaultFiles(new DefaultFilesOptions { FileProvider = files });
            app.UseStaticFiles(new StaticFileOptions { FileProvider = files });
        }
    }

    private static FixedWindowRateLimiterOptions Window(int permits) => new()
    {
        PermitLimit = permits,
        Window = TimeSpan.FromMinutes(1),
        QueueLimit = 0,
        AutoReplenishment = true
    };

    // CF-Connecting-IP counts only from a trusted proxy; from anyone else it is client input and is ignored.
    private static string ClientAddress(HttpContext context, IReadOnlyList<IPNetwork> trusted)
    {
        var peer = Normalize(context.Connection.RemoteIpAddress);
        if (peer is not null
            && trusted.Any(network => network.Contains(peer))
            && IPAddress.TryParse(context.Request.Headers[ForwardedForHeader].ToString(), out var forwarded))
        {
            return Key(Normalize(forwarded)!);
        }

        return peer is null ? "unknown" : Key(peer);
    }

    // An IPv6 subscriber holds a whole /64, so rotating inside it must not buy a fresh budget.
    private static string Key(IPAddress address)
    {
        if (address.AddressFamily != System.Net.Sockets.AddressFamily.InterNetworkV6)
        {
            return address.ToString();
        }

        Span<byte> bytes = stackalloc byte[16];
        address.TryWriteBytes(bytes, out _);
        bytes[8..].Clear();
        return $"{new IPAddress(bytes)}/64";
    }

    // The probe and the scheduled check must see a flooded demo as up: refusing them would restart a healthy pod.
    private static bool IsHealth(HttpContext context) =>
        HttpMethods.IsGet(context.Request.Method) && context.Request.Path.Equals("/api/health", StringComparison.OrdinalIgnoreCase);

    private static IPAddress? Normalize(IPAddress? address) =>
        address is { IsIPv4MappedToIPv6: true } ? address.MapToIPv4() : address;
}
