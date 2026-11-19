using Craticula.Integration.Tests.Containers.Document;
using Craticula.Integration.Tests.Oracle;

namespace Craticula.Integration.Tests.CountParity;

/// <summary>The pure guard that keeps the parked grouped Search read from running (D-006, T017; removed by T017a).</summary>
public sealed class SearchCountEngineGuardTests
{
    private const string GroupedFixture = "group-aggregation/001-group-top-level-no-keys-consumed";
    private const string FlatFixture = "sort-paging/001-single-key-string-asc-nulls-last-default";

    // US2-AS3, D-006: a grouped Search level needs the unpaged window (OSE-11(d))
    [Fact]
    public void A_Grouped_Request_Is_Refused_Naming_D006()
    {
        var fixture = ExecutionFixture.Load(GroupedFixture);

        var refusal = Assert.Throws<InvalidOperationException>(() =>
            SearchCountEngine.RefuseGroupedUntilD006(PreparedRequest.For(fixture, fixture.Schema)));

        Assert.Contains("D-006", refusal.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void A_Flat_Request_Is_Not_Refused()
    {
        var fixture = ExecutionFixture.Load(FlatFixture);

        var exception = Record.Exception(() => SearchCountEngine.RefuseGroupedUntilD006(PreparedRequest.For(fixture, fixture.Schema)));

        Assert.Null(exception);
    }
}
