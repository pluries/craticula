using Craticula.AgGrid;
using Craticula.Core;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Dapper;
using Craticula.EntityFrameworkCore;
using Craticula.Export.Csv;
using Craticula.Mongo;
using Craticula.MongoDB.Driver;
using Craticula.OpenSearch.Client;
using Craticula.Search;
using Craticula.Sql;
using MongoDB.Driver;
using Npgsql;

namespace Demo.Api.Errors;

/// <summary>
/// One place that turns the library's exceptions into <c>{ "error": { "kind", "message" } }</c>. Client mistakes are 400
/// with the library's own message (it names columns and limits, never values or stack traces), an unreachable database
/// is 503, a body the host itself refuses (too large, unreadable) is 413 or 400, anything else is a logged 500 with a generic message.
/// </summary>
public sealed class ApiErrorMiddleware(RequestDelegate next, ILogger<ApiErrorMiddleware> logger)
{
    public async Task InvokeAsync(HttpContext context)
    {
        try
        {
            await next(context);
        }
        catch (OperationCanceledException) when (context.RequestAborted.IsCancellationRequested)
        {
            // The client went away; nobody is left to answer.
        }
        catch (Exception exception)
        {
            var (status, kind, message) = Classify(exception);

            if (status == StatusCodes.Status500InternalServerError)
            {
                logger.LogError(exception, "Unhandled exception on {Method} {Path}", context.Request.Method, context.Request.Path);
            }
            else
            {
                logger.LogInformation("{Kind} on {Path}: {Message}", kind, context.Request.Path, message);
            }

            if (context.Response.HasStarted)
            {
                // A stream that fails midway must not look like a complete file.
                context.Abort();
                return;
            }

            context.Response.Clear();
            context.Response.StatusCode = status;
            await context.Response.WriteAsJsonAsync(new { error = new { kind, message } });
        }
    }

    private static (int Status, string Kind, string Message) Classify(Exception exception)
    {
        const int bad = StatusCodes.Status400BadRequest;

        return exception switch
        {
            AgGridRequestParseException e => (bad, e.Reason, e.Message),
            GridSchemaValidationException e => (bad, "invalid-schema", e.Message),
            UnknownFieldException e => (bad, "unknown-field", e.Message),
            ResourceLimitExceededException e => (bad, "resource-limit-exceeded", e.Message),
            TypeCoercionException e => (bad, "type-coercion", e.Message),
            FilterNodeValidationException e => (bad, "invalid-filter", e.Message),
            SortItemValidationException e => (bad, "invalid-sort", e.Message),
            GroupSpecValidationException e => (bad, "invalid-group", e.Message),
            AggregationValidationException e => (bad, "invalid-aggregation", e.Message),
            SetValuesSpecValidationException e => (bad, "invalid-set-values", e.Message),
            PageSpecValidationException e => (bad, "invalid-page", e.Message),
            // A shape one provider cannot answer like PostgreSQL does (grouped requests on OpenSearch): the message names the shape.
            UnsupportedShapeException e => (bad, "unsupported-shape", e.Message),
            SqlCompilationException or MongoCompilationException or DapperCompilationException
                or EfCoreCompilationException or MongoDriverCompilationException or SearchCompilationException
                => (bad, "compilation-failed", exception.Message),
            // The adapter's own refusals and the value reader's failures (a stored value that does not fit its mapped type) have no inner
            // exception; a failed OpenSearch call always carries one (the transport exception or the status) and falls through to the
            // engine-failure test or to a logged 500.
            OpenSearchClientCompilationException { InnerException: null } => (bad, "compilation-failed", exception.Message),
            CsvWriterException e => (bad, "export-failed", e.Message),
            // Raised by Kestrel/ASP.NET itself: a body over the 1 MiB limit (413) or a body that cannot be read (400).
            BadHttpRequestException { StatusCode: StatusCodes.Status413PayloadTooLarge } => (
                StatusCodes.Status413PayloadTooLarge, "request-too-large", "The request body is larger than the 1 MiB limit."),
            BadHttpRequestException => (bad, "bad-request", "The request could not be read."),
            // The database's own cut-off: PostgreSQL statement_timeout (public mode sets it on the read-only role), MongoDB's maxTimeMS (the library reports it as QueryTimeoutException, since 1.1.0).
            // Listed before the engine-failure test, which would read any MongoException as an unreachable server.
            PostgresException { SqlState: "57014" } or MongoExecutionTimeoutException or QueryTimeoutException => (
                StatusCodes.Status504GatewayTimeout, "query-timeout", "The query took longer than allowed and was cancelled."),
            // Which exceptions are connection failures is declared once, in EngineFailures.
            _ when EngineFailures.IsUnavailable(exception) => (
                StatusCodes.Status503ServiceUnavailable, "backend-unavailable", "The database is not reachable."),
            _ => Internal()
        };

        static (int, string, string) Internal() =>
            (StatusCodes.Status500InternalServerError, "internal-error", "The request failed on the server.");
    }
}
