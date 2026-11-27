using Craticula.AgGrid;
using Craticula.Core.Ir;
using Craticula.Core.Schema;

namespace Craticula.Conformance.Driver;

/// <summary>
/// Names a refusal in the vocabulary of <c>spec/fixtures/schemas/rejection.schema.json</c>
/// (<c>rejectedAt</c> and <c>reason</c>), which a rejection answer carries (<c>conformance-runner.md</c> §2.2, §4.1).
/// Reads the exceptions' own typed members; the one place that reads text is
/// <see cref="IsDuplicateOutputName"/>, because the aggregation validator has no typed member for it.
/// </summary>
internal static class RejectionMapper
{
    /// <summary>The pair for <paramref name="error"/>, or <see langword="false"/> when it is not a request refusal
    /// (a schema that does not parse, a backend the driver does not know, a bug).</summary>
    public static bool TryMap(Exception error, out string rejectedAt, out string reason)
    {
        (rejectedAt, reason) = error switch
        {
            UnknownFieldException { Violations.Count: > 0 } e => ("allowlist", e.Violations[0].Reason),
            ResourceLimitExceededException { Violations.Count: > 0 } e => ("resourceLimits", e.Violations[0].LimitName),
            TypeCoercionException { Violations.Count: > 0 } e => ("typeCoercion", e.Violations[0].Reason),
            AgGridRequestParseException e => (e.RejectedAt, e.RejectionReason),
            AggregationValidationException e => ("requestParsing", IsDuplicateOutputName(e) ? "duplicate-output-name" : "malformed-request"),
            FilterNodeValidationException or GroupSpecValidationException or SortItemValidationException
                or SetValuesSpecValidationException or PageSpecValidationException => ("requestParsing", "malformed-request"),
            _ => ("", "")
        };

        return rejectedAt.Length > 0;
    }

    private static bool IsDuplicateOutputName(AggregationValidationException error) =>
        error.Errors.Any(message => message.Contains("resolve to the output name", StringComparison.Ordinal));
}
