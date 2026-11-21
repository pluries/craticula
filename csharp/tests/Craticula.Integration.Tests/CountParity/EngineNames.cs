namespace Craticula.Integration.Tests.CountParity;

/// <summary>
/// The backend and engine names the count check passes to <c>ExecutionFixture.ExpectationFor</c>. <c>OpenSearch</c> and
/// <c>Elasticsearch</c> equal the engine fixtures' <c>EngineName</c> (the string an XEQ-4 divergence's <c>engine</c> matches).
/// </summary>
internal static class EngineNames
{
    public const string Mongo = "mongo";

    public const string Search = "search";

    public const string OpenSearch = "opensearch";

    public const string Elasticsearch = "elasticsearch";
}
