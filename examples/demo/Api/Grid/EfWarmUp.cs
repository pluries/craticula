using Microsoft.Extensions.Hosting;

namespace Demo.Api.Grid;

/// <summary>
/// Builds the EF model and compiles one query on every EF route when the API starts. EF does that work on the first use of a route,
/// which on a fresh pod can take longer than the public demo's time limit and answered the first visitor with a 504. <see cref="IGridService.Compile"/>
/// opens no connection, so the warm-up works while the database is still starting; a failure is logged and never stops the API.
/// </summary>
public sealed class EfWarmUp(IEnumerable<IGridService> services, GridRequestPreparer preparer, ILogger<EfWarmUp> logger) : IHostedService
{
    private const string SmallPage = """
        { "startRow": 0, "endRow": 5, "rowGroupCols": [], "valueCols": [], "pivotCols": [], "pivotMode": false, "groupKeys": [],
          "filterModel": null, "sortModel": [] }
        """;

    public Task StartAsync(CancellationToken cancellationToken)
    {
        foreach (var service in services.Where(s => s.Name.StartsWith("ef", StringComparison.Ordinal)))
        {
            try
            {
                service.Compile(preparer.PrepareRows(SmallPage));
                logger.LogInformation("The {Route} route is warm.", service.Name);
            }
            catch (Exception exception)
            {
                logger.LogWarning(exception, "The {Route} route could not be warmed up; its first request will build the model.", service.Name);
            }
        }

        return Task.CompletedTask;
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;
}
