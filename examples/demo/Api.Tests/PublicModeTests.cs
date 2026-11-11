using System.Net;
using System.Text;
using System.Text.Json;
using Craticula.Core.Export;
using Craticula.Core.Grid;
using Demo.Api.Grid;
using Demo.Api.Public;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;

namespace Demo.Api.Tests;

/// <summary>
/// Public mode (DEMO_PUBLIC=1) end to end over HTTP, with a counting fake provider named <c>fake</c>: no database is needed, and
/// "a 429 never reaches the database" is a call count on the fake. The test client's connection address is 127.0.0.1.
/// </summary>
public sealed class PublicModeTests
{
    private const string TrustLoopback = "127.0.0.0/8";

    private static async Task<(WebApplication App, HttpClient Client)> StartAsync(
        FakeGrid? fake = null, Action<WebApplicationBuilder>? more = null) =>
        await ApiHostFixture.StartAsync(null, builder =>
        {
            builder.Configuration[PublicSettings.EnabledKey] = "1";
            if (fake is not null)
            {
                builder.Services.AddSingleton<IGridService>(fake);
            }

            more?.Invoke(builder);
        });

    private static async Task<HttpResponseMessage> PostRowsAsync(HttpClient client, string? clientAddress = null, string provider = "fake", string body = "")
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, $"/api/{provider}/rows")
        {
            Content = new StringContent(body.Length == 0 ? Requests.PageSize(10) : body, Encoding.UTF8, "application/json")
        };
        if (clientAddress is not null)
        {
            request.Headers.Add("CF-Connecting-IP", clientAddress);
        }

        return await client.SendAsync(request);
    }

    private static async Task<JsonElement> ErrorAsync(HttpResponseMessage response) =>
        JsonDocument.Parse(await response.Content.ReadAsStringAsync()).RootElement.GetProperty("error").Clone();

    [Fact]
    public async Task T1_PutDeleteAndANonGridPost_Answer405_AndTheGridPostAnswers200()
    {
        var fake = new FakeGrid();
        var (app, client) = await StartAsync(fake);
        await using (app)
        using (client)
        {
            using var put = await client.PutAsync("/api/fake/rows", new StringContent("{}", Encoding.UTF8, "application/json"));
            using var delete = await client.DeleteAsync("/api/fake/rows");
            using var otherPost = await client.PostAsync("/api/fake/orders", new StringContent("{}", Encoding.UTF8, "application/json"));
            using var healthPost = await client.PostAsync("/api/health", new StringContent("{}", Encoding.UTF8, "application/json"));
            using var grid = await PostRowsAsync(client);

            Assert.Equal(HttpStatusCode.MethodNotAllowed, put.StatusCode);
            Assert.Equal(HttpStatusCode.MethodNotAllowed, delete.StatusCode);
            Assert.Equal(HttpStatusCode.MethodNotAllowed, otherPost.StatusCode);
            Assert.Equal(HttpStatusCode.MethodNotAllowed, healthPost.StatusCode);
            Assert.Equal(HttpStatusCode.OK, grid.StatusCode);
            Assert.Equal(1, fake.RowCalls);
        }
    }

    [Fact]
    public async Task T2_The61stRequestInAMinuteFromOneAddressIs429WithRetryAfter_AnotherAddressStillAnswers_AndNo429ReachesTheProvider()
    {
        var fake = new FakeGrid();
        var (app, client) = await StartAsync(fake, builder => builder.Configuration[PublicSettings.TrustedProxiesKey] = TrustLoopback);
        await using (app)
        using (client)
        {
            for (var i = 1; i <= PublicSettings.AddressLimitPerMinute; i++)
            {
                using var ok = await PostRowsAsync(client, "203.0.113.1");
                Assert.True(HttpStatusCode.OK == ok.StatusCode, $"request {i}: {ok.StatusCode}");
            }

            using var limited = await PostRowsAsync(client, "203.0.113.1");
            using var other = await PostRowsAsync(client, "203.0.113.2");

            Assert.Equal(HttpStatusCode.TooManyRequests, limited.StatusCode);
            Assert.True(limited.Headers.Contains("Retry-After"));
            Assert.Equal(HttpStatusCode.OK, other.StatusCode);
            Assert.Equal(PublicSettings.AddressLimitPerMinute + 1, fake.RowCalls);
        }
    }

    [Fact]
    public async Task T3_TheHeaderIsIgnoredWhenThePeerIsNotATrustedProxy_SoASpoofedAddressDoesNotResetTheCount()
    {
        var fake = new FakeGrid();
        var (app, client) = await StartAsync(fake);
        await using (app)
        using (client)
        {
            for (var i = 1; i <= PublicSettings.AddressLimitPerMinute; i++)
            {
                using var ok = await PostRowsAsync(client, $"198.51.100.{i}");
                Assert.True(HttpStatusCode.OK == ok.StatusCode, $"request {i}: {ok.StatusCode}");
            }

            using var limited = await PostRowsAsync(client, "198.51.100.200");

            Assert.Equal(HttpStatusCode.TooManyRequests, limited.StatusCode);
            Assert.Equal(PublicSettings.AddressLimitPerMinute, fake.RowCalls);
        }
    }

    [Fact]
    public async Task T3_ATrustedProxyWithoutTheHeader_IsCountedByTheConnectionAddress()
    {
        var fake = new FakeGrid();
        var (app, client) = await StartAsync(fake, builder => builder.Configuration[PublicSettings.TrustedProxiesKey] = TrustLoopback);
        await using (app)
        using (client)
        {
            for (var i = 1; i <= PublicSettings.AddressLimitPerMinute; i++)
            {
                using var ok = await PostRowsAsync(client);
                Assert.Equal(HttpStatusCode.OK, ok.StatusCode);
            }

            using var limited = await PostRowsAsync(client);

            Assert.Equal(HttpStatusCode.TooManyRequests, limited.StatusCode);
        }
    }

    [Fact]
    public async Task T4_ASlowGridCallIsCancelledAfterTwoSeconds_AndTheApiAnswersAnErrorBodyNotAHang()
    {
        var fake = new FakeGrid { Slow = true };
        var (app, client) = await StartAsync(fake);
        await using (app)
        using (client)
        {
            client.Timeout = TimeSpan.FromSeconds(15);
            var started = DateTime.UtcNow;

            using var response = await PostRowsAsync(client);
            var elapsed = DateTime.UtcNow - started;
            var error = await ErrorAsync(response);

            Assert.Equal(HttpStatusCode.GatewayTimeout, response.StatusCode);
            Assert.Equal("query-timeout", error.GetProperty("kind").GetString());
            Assert.InRange(elapsed, TimeSpan.FromSeconds(1.5), TimeSpan.FromSeconds(8));
        }
    }

    [Fact]
    public async Task T5_AnOversizedPageAndATooDeepFilter_GetTheLibrariesRejection()
    {
        var (app, client) = await StartAsync(new FakeGrid());
        await using (app)
        using (client)
        {
            using var oversized = await PostRowsAsync(client, body: Requests.PageSize(100_000));
            using var deep = await PostRowsAsync(client, body: DeepNotFilter(8));

            Assert.Equal(HttpStatusCode.BadRequest, oversized.StatusCode);
            Assert.Equal("resource-limit-exceeded", (await ErrorAsync(oversized)).GetProperty("kind").GetString());
            Assert.Equal(HttpStatusCode.BadRequest, deep.StatusCode);
            Assert.Equal("resource-limit-exceeded", (await ErrorAsync(deep)).GetProperty("kind").GetString());
        }
    }

    [Fact]
    public async Task T6_DemoProvidersPostgres_ListsOnlyPostgresInHealth()
    {
        var (app, client) = await StartAsync(more: builder => builder.Configuration[PublicSettings.ProvidersKey] = "postgres");
        await using (app)
        using (client)
        {
            var json = JsonDocument.Parse(await client.GetStringAsync("/api/health")).RootElement;

            Assert.Equal(["postgres"], json.GetProperty("providers").EnumerateArray().Select(p => p.GetString()));
        }
    }

    [Fact]
    public async Task T7_AboveTheGlobalLimitEveryAddressGets429_AndNothingRefusedReachesTheProvider()
    {
        var fake = new FakeGrid();
        var (app, client) = await StartAsync(fake, builder =>
        {
            builder.Configuration[PublicSettings.TrustedProxiesKey] = TrustLoopback;
            builder.Configuration[PublicSettings.GlobalLimitKey] = "5";
        });
        await using (app)
        using (client)
        {
            for (var i = 1; i <= 5; i++)
            {
                using var ok = await PostRowsAsync(client, $"203.0.113.{i}");
                Assert.True(HttpStatusCode.OK == ok.StatusCode, $"request {i}: {ok.StatusCode}");
            }

            using var fresh = await PostRowsAsync(client, "203.0.113.99");
            using var first = await PostRowsAsync(client, "203.0.113.1");

            Assert.Equal(HttpStatusCode.TooManyRequests, fresh.StatusCode);
            Assert.True(fresh.Headers.Contains("Retry-After"));
            Assert.Equal(HttpStatusCode.TooManyRequests, first.StatusCode);
            Assert.Equal(5, fake.RowCalls);
        }
    }

    [Fact]
    public async Task T8_AWriteShapedCraftedFilter_GetsTheLibrariesRejection()
    {
        var fake = new FakeGrid();
        var (app, client) = await StartAsync(fake);
        await using (app)
        using (client)
        {
            using var response = await PostRowsAsync(client, body: """
                {
                  "startRow": 0, "endRow": 10, "rowGroupCols": [], "valueCols": [], "pivotCols": [], "pivotMode": false, "groupKeys": [],
                  "filterModel": { "customer": { "filterType": "text", "type": "equals", "filter": { "$set": { "status": "x" } } } },
                  "sortModel": []
                }
                """);

            Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
            Assert.Equal("malformed-request", (await ErrorAsync(response)).GetProperty("kind").GetString());
            Assert.Equal(0, fake.RowCalls);
        }
    }

    [Fact]
    public async Task NoResponseCarriesACookie_NotEvenTheRefusedOnes()
    {
        var (app, client) = await StartAsync(new FakeGrid());
        await using (app)
        using (client)
        {
            using var ok = await PostRowsAsync(client);
            using var refused = await client.DeleteAsync("/api/fake/rows");
            using var health = await client.GetAsync("/api/health");

            foreach (var response in new[] { ok, refused, health })
            {
                Assert.False(response.Headers.Contains("Set-Cookie"));
            }
        }
    }

    [Fact]
    public async Task DemoWebDir_ServesTheBuiltPageFromTheRoot()
    {
        var folder = Directory.CreateTempSubdirectory("craticula-demo-web-");
        try
        {
            await File.WriteAllTextAsync(Path.Combine(folder.FullName, "index.html"), "<html><body>demo-page-marker</body></html>");
            var (app, client) = await StartAsync(new FakeGrid(), builder => builder.Configuration[PublicSettings.WebDirKey] = folder.FullName);
            await using (app)
            using (client)
            {
                using var response = await client.GetAsync("/");

                Assert.Equal(HttpStatusCode.OK, response.StatusCode);
                Assert.Contains("demo-page-marker", await response.Content.ReadAsStringAsync());
            }
        }
        finally
        {
            folder.Delete(recursive: true);
        }
    }

    [Fact]
    public async Task Ipv6_AddressesInTheSameSlash64ShareOneBudget_AnotherSlash64HasItsOwn()
    {
        var fake = new FakeGrid();
        var (app, client) = await StartAsync(fake, builder => builder.Configuration[PublicSettings.TrustedProxiesKey] = TrustLoopback);
        await using (app)
        using (client)
        {
            for (var i = 1; i <= PublicSettings.AddressLimitPerMinute; i++)
            {
                using var ok = await PostRowsAsync(client, $"2001:db8:1:2::{i:x}");
                Assert.True(HttpStatusCode.OK == ok.StatusCode, $"request {i}: {ok.StatusCode}");
            }

            using var sameNetwork = await PostRowsAsync(client, "2001:db8:1:2:ffff:abcd:1:1");
            using var otherNetwork = await PostRowsAsync(client, "2001:db8:1:3::1");

            Assert.Equal(HttpStatusCode.TooManyRequests, sameNetwork.StatusCode);
            Assert.Equal(HttpStatusCode.OK, otherNetwork.StatusCode);
        }
    }

    [Fact]
    public async Task Health_IsExemptFromThePerAddressLimit()
    {
        var fake = new FakeGrid();
        var (app, client) = await StartAsync(fake, builder => builder.Configuration[PublicSettings.TrustedProxiesKey] = TrustLoopback);
        await using (app)
        using (client)
        {
            for (var i = 1; i <= PublicSettings.AddressLimitPerMinute; i++)
            {
                using var ok = await PostRowsAsync(client, "203.0.113.7");
                Assert.Equal(HttpStatusCode.OK, ok.StatusCode);
            }

            using var limited = await PostRowsAsync(client, "203.0.113.7");
            using var health = await GetHealthAsync(client, "203.0.113.7");

            Assert.Equal(HttpStatusCode.TooManyRequests, limited.StatusCode);
            Assert.Equal(HttpStatusCode.OK, health.StatusCode);
        }
    }

    [Fact]
    public async Task Health_IsExemptFromTheGlobalCap()
    {
        var (app, client) = await StartAsync(new FakeGrid(), builder =>
        {
            builder.Configuration[PublicSettings.TrustedProxiesKey] = TrustLoopback;
            builder.Configuration[PublicSettings.GlobalLimitKey] = "3";
        });
        await using (app)
        using (client)
        {
            for (var i = 1; i <= 3; i++)
            {
                using var ok = await PostRowsAsync(client, $"203.0.113.{i}");
                Assert.Equal(HttpStatusCode.OK, ok.StatusCode);
            }

            using var limited = await PostRowsAsync(client, "203.0.113.50");
            using var healthFresh = await GetHealthAsync(client, "203.0.113.51");
            using var healthBare = await GetHealthAsync(client, null);

            Assert.Equal(HttpStatusCode.TooManyRequests, limited.StatusCode);
            Assert.Equal(HttpStatusCode.OK, healthFresh.StatusCode);
            Assert.Equal(HttpStatusCode.OK, healthBare.StatusCode);
        }
    }

    [Fact]
    public async Task AStreamCutByTheGateAfterTheResponseStarted_FailsTheResponseInsteadOfEndingAsACleanTruncated200()
    {
        var fake = new FakeGrid { Streaming = true };
        var (app, client) = await StartAsync(fake);
        await using (app)
        using (client)
        {
            client.Timeout = TimeSpan.FromSeconds(20);

            var failure = await Record.ExceptionAsync(async () =>
            {
                using var request = new HttpRequestMessage(HttpMethod.Post, "/api/fake/export.csv")
                {
                    Content = new StringContent(Requests.StatusExport, Encoding.UTF8, "application/json")
                };
                using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead);
                await response.Content.ReadAsByteArrayAsync();
            });

            Assert.True(fake.Stalled, "the stream never reached the stall: the test did not exercise a started response");
            Assert.NotNull(failure);
        }
    }

    [Theory]
    [InlineData("craticula-pg.pluries.dev")]
    [InlineData("10.1.2.3:8080")]
    public async Task TheShippedAllowedHostsDoNotBlockThePublicHostnameOrAPodAddress(string host)
    {
        var (app, client) = await StartAsync(new FakeGrid());
        await using (app)
        using (client)
        {
            using var request = new HttpRequestMessage(HttpMethod.Get, "/api/health");
            request.Headers.Host = host;

            using var response = await client.SendAsync(request);

            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        }
    }

    private static async Task<HttpResponseMessage> GetHealthAsync(HttpClient client, string? clientAddress)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, "/api/health");
        if (clientAddress is not null)
        {
            request.Headers.Add("CF-Connecting-IP", clientAddress);
        }

        return await client.SendAsync(request);
    }

    /// <summary>customFilters nesting <paramref name="levels"/> "not" wrappers around one comparison (spec/fixtures/adversarial/004); the demo's depth limit is 6.</summary>
    private static string DeepNotFilter(int levels)
    {
        var node = """{ "type": "comparison", "field": "amount", "op": "gt", "value": { "type": "decimal", "value": "10.00" } }""";
        for (var i = 0; i < levels; i++)
        {
            node = $$"""{ "type": "not", "node": {{node}} }""";
        }

        return $$"""
            { "startRow": 0, "endRow": 100, "rowGroupCols": [], "valueCols": [], "pivotCols": [], "pivotMode": false, "groupKeys": [],
              "filterModel": null, "sortModel": [], "customFilters": {{node}} }
            """;
    }

    private sealed class FakeGrid : IGridService
    {
        private int rowCalls;

        public bool Slow { get; init; }

        public bool Streaming { get; init; }

        public bool Stalled { get; private set; }

        public int RowCalls => Volatile.Read(ref rowCalls);

        public string Name => "fake";

        public async Task<GridPageResult> FetchRowsAsync(PreparedRows request, CancellationToken cancellationToken)
        {
            Interlocked.Increment(ref rowCalls);
            if (Slow)
            {
                await Task.Delay(Timeout.Infinite, cancellationToken);
            }

            return new GridPageResult { Columns = ["id"], Rows = [], IsLastPage = true };
        }

        public Task<IReadOnlyList<object?>> FetchSetValuesAsync(PreparedSetValues request, CancellationToken cancellationToken) =>
            throw new NotSupportedException();

        public async IAsyncEnumerable<ExportRow> StreamExportAsync(
            PreparedRows request, [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken)
        {
            if (!Streaming)
            {
                throw new NotSupportedException();
            }

            // More than Kestrel's output buffer, so the response has started when the stream stalls.
            var width = request.Parsed.Export!.Columns.Count;
            var cell = new string('a', 1024);
            for (var i = 0; i < 300; i++)
            {
                yield return new ExportRow([.. Enumerable.Repeat<object?>(cell, width)]);
            }

            Stalled = true;
            await Task.Delay(Timeout.Infinite, cancellationToken);
        }

        public CompiledQueryView Compile(PreparedRows request) => throw new NotSupportedException();
    }
}
