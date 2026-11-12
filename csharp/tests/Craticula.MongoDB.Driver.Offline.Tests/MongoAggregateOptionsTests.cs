using Craticula.Core.Ir;
using Craticula.Mongo;

namespace Craticula.MongoDB.Driver.Offline.Tests;

/// <summary>TL-1 (#3794): the compiled <c>maxTimeMS</c> becomes the driver's <c>AggregateOptions.MaxTime</c>. Needs no server.</summary>
public sealed class MongoAggregateOptionsTests
{
    private static MongoQueryRequest Request(int? limit)
    {
        var fixture = FixtureRequest.Load("page-export", FixtureRequest.ResolveDirectory("page-export", "008"));
        return fixture.Request with { Page = new RangePage { StartRow = 0, EndRow = 100 }, MaxQueryTimeMs = limit };
    }

    [Fact]
    public void The_Aggregate_Options_Carry_The_Compiled_Limit()
    {
        var query = MongoPipelineBuilder.Build(Request(2000));

        Assert.Equal(TimeSpan.FromMilliseconds(2000), MongoPipelineTranslator.Options(query)!.MaxTime);
    }

    [Fact]
    public void Without_A_Limit_And_Without_A_Collation_There_Are_No_Options()
    {
        var query = MongoPipelineBuilder.Build(Request(null));

        Assert.Null(MongoPipelineTranslator.Options(query));
    }

    [Fact]
    public void A_Collation_And_A_Limit_Are_Both_Carried()
    {
        var request = Request(1500) with
        {
            Filter = new ComparisonNode
            {
                Field = "customerName",
                Op = ComparisonOperator.Eq,
                Value = new StringValue { Value = "acme" }
            }
        };

        var options = MongoPipelineTranslator.Options(MongoPipelineBuilder.Build(request))!;

        Assert.Equal(TimeSpan.FromMilliseconds(1500), options.MaxTime);
        Assert.NotNull(options.Collation);
    }
}
