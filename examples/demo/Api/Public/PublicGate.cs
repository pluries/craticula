using Demo.Api.Errors;

namespace Demo.Api.Public;

/// <summary>
/// Runs after the rate limiter and before <see cref="ApiErrorMiddleware"/>: refuses everything but <c>GET</c> and the four grid POST
/// routes with 405, drops any <c>Set-Cookie</c>, and cancels a grid call after <see cref="PublicSettings.QueryTimeout"/>.
/// </summary>
internal sealed class PublicGate(RequestDelegate next)
{
    private static readonly string[] GridRoutes = ["rows", "values", "export.csv", "query"];

    public async Task InvokeAsync(HttpContext context)
    {
        context.Response.OnStarting(() =>
        {
            context.Response.Headers.Remove("Set-Cookie");
            return Task.CompletedTask;
        });

        var isGet = HttpMethods.IsGet(context.Request.Method);
        var isGridPost = HttpMethods.IsPost(context.Request.Method) && IsGridRoute(context.Request.Path);
        if (!isGet && !isGridPost)
        {
            context.Response.StatusCode = StatusCodes.Status405MethodNotAllowed;
            context.Response.Headers.Allow = "GET, POST";
            await WriteErrorAsync(context, "method-not-allowed", "This demo is read-only.");
            return;
        }

        if (!isGridPost)
        {
            await next(context);
            return;
        }

        var clientAborted = context.RequestAborted;
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(clientAborted);
        timeout.CancelAfter(PublicSettings.QueryTimeout);
        context.RequestAborted = timeout.Token;
        try
        {
            await next(context);
        }
        finally
        {
            context.RequestAborted = clientAborted;
        }

        // ApiErrorMiddleware reads the cancelled token as "the client went away" and writes nothing: the answer is ours.
        if (!timeout.IsCancellationRequested || clientAborted.IsCancellationRequested)
        {
            return;
        }

        if (context.Response.HasStarted)
        {
            // Too late for a status: end the connection so the client sees a failed transfer, not a complete-looking truncated file.
            context.Abort();
            return;
        }

        context.Response.StatusCode = StatusCodes.Status504GatewayTimeout;
        await WriteErrorAsync(context, "query-timeout", "The query took longer than allowed and was cancelled.");
    }

    private static bool IsGridRoute(PathString path)
    {
        var segments = path.Value?.Trim('/').Split('/');
        return segments is ["api", { Length: > 0 }, var route] && GridRoutes.Contains(route, StringComparer.OrdinalIgnoreCase);
    }

    private static Task WriteErrorAsync(HttpContext context, string kind, string message) =>
        context.Response.WriteAsJsonAsync(new { error = new { kind, message } });
}
