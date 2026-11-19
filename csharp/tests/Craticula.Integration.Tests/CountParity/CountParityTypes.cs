using Craticula.Integration.Tests.Oracle;

namespace Craticula.Integration.Tests.CountParity;

/// <summary>What one engine answered for one fixture: the count, the rows of the unpaged request, and the count query sent.</summary>
internal sealed record CountParityRun(long? Count, int UnpagedRows, string CountedQuery);

/// <summary>The seam between the engine-neutral comparison and a live adapter or an offline stub (FR-015).</summary>
internal interface ICountParityEngine
{
    /// <summary><c>"mongo"</c> or <c>"search"</c>: the backend argument of <c>ExecutionFixture.ExpectationFor</c>.</summary>
    string Backend { get; }

    /// <summary>Null, <c>"opensearch"</c> or <c>"elasticsearch"</c>.</summary>
    string? Engine { get; }

    Task<CountParityRun> RunAsync(ExecutionFixture fixture);
}
