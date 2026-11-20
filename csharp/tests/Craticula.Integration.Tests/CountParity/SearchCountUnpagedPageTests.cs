using Craticula.Core.Ir;
using Craticula.Integration.Tests.Containers.Document;
using Craticula.Integration.Tests.Oracle;

namespace Craticula.Integration.Tests.CountParity;

/// <summary>The unpaged page a Search count run asks for (FR-007, FR-007a, OSE-11(d)).</summary>
public sealed class SearchCountUnpagedPageTests
{
    // FR-007a: a grouped level cannot compile without a window, so it is read through one of GroupWindow groups
    [Fact]
    public void A_Grouped_Request_Is_Read_Through_The_Group_Window()
    {
        var fixture = ExecutionFixture.Load("group-aggregation/001-group-top-level-no-keys-consumed");

        var page = SearchCountEngine.UnpagedPageFor(PreparedRequest.For(fixture, fixture.Schema));

        var range = Assert.IsType<RangePage>(page);
        Assert.Equal(0, range.StartRow);
        Assert.Equal(SearchCountEngine.GroupWindow, range.EndRow);
    }

    // FR-007: a flat level is read whole
    [Fact]
    public void A_Flat_Request_Is_Read_Unpaged()
    {
        var fixture = ExecutionFixture.Load("sort-paging/001-single-key-string-asc-nulls-last-default");

        Assert.IsType<NonePage>(SearchCountEngine.UnpagedPageFor(PreparedRequest.For(fixture, fixture.Schema)));
    }
}
