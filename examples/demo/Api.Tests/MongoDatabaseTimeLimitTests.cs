using Craticula.Core;
using Demo.Api.Grid;
using Demo.Api.Public;
using Demo.Api.Seed;
using MongoDB.Driver;

namespace Demo.Api.Tests;

/// <summary>#3806 / ADR-0007 decision 5: in public mode the MongoDB cut-off is the database's (<c>maxTimeMS</c>, library 1.1.0), not
/// only the app's.</summary>
public sealed class MongoDatabaseTimeLimitTests
{
    private static MongoGridService Service(int? maxQueryTimeMs)
    {
        var database = new MongoClient(DemoSettings.Mongo).GetDatabase(DemoSettings.MongoDatabase);
        return new MongoGridService(database, new GridRequestPreparer(OpenSearchSeeder.LoadSchema(), DemoLimits.Default), maxQueryTimeMs);
    }

    private static PreparedRows Rows() =>
        new GridRequestPreparer(OpenSearchSeeder.LoadSchema(), DemoLimits.Default).PrepareRows(Requests.PageSize(10));

    [Fact]
    public void The_Compiled_Query_Carries_MaxTimeMS_When_A_Limit_Is_Set()
    {
        var view = Service(2000).Compile(Rows());

        Assert.Contains("\"maxTimeMS\": 2000", view.Text, StringComparison.Ordinal);
    }

    [Fact]
    public void The_Compiled_Query_Carries_No_Limit_When_None_Is_Set()
    {
        var view = Service(null).Compile(Rows());

        Assert.DoesNotContain("maxTimeMS", view.Text, StringComparison.Ordinal);
    }

    [Fact]
    public void Public_Mode_Uses_The_Two_Second_Limit_In_Milliseconds() =>
        Assert.Equal(2000, PublicSettings.QueryTimeoutMs);

    [RequiresDatabasesFact]
    public async Task A_Query_Over_The_Limit_Is_Cut_By_MongoDB_And_Reported_As_A_Query_Timeout()
    {
        var service = Service(1);
        var request = new GridRequestPreparer(OpenSearchSeeder.LoadSchema(), DemoLimits.Default).PrepareRows(Requests.TextFilter("customer", "contains", "zzz-never-present"));

        await Assert.ThrowsAsync<QueryTimeoutException>(() => service.FetchRowsAsync(request, CancellationToken.None));
    }

    [Fact]
    public void A_Distinct_Values_Query_Carries_The_Limit_Into_Its_Command_Options()
    {
        var query = Craticula.Mongo.MongoPipelineBuilder.BuildSetValues(new Craticula.Mongo.MongoSetValuesRequest
        {
            Schema = OpenSearchSeeder.LoadSchema(),
            ColId = "country",
            RowLimit = 100,
            MaxQueryTimeMs = 2000
        });

        Assert.Equal(TimeSpan.FromMilliseconds(2000), MongoGridService.OptionsFor(query).MaxTime);
    }

    [Fact]
    public void Without_A_Limit_The_Command_Options_Have_No_MaxTime()
    {
        var query = Craticula.Mongo.MongoPipelineBuilder.BuildSetValues(new Craticula.Mongo.MongoSetValuesRequest
        {
            Schema = OpenSearchSeeder.LoadSchema(),
            ColId = "country",
            RowLimit = 100
        });

        Assert.Null(MongoGridService.OptionsFor(query).MaxTime);
    }

    [RequiresDatabasesFact]
    public async Task Without_A_Limit_The_Same_Query_Completes()
    {
        var service = Service(null);
        var request = new GridRequestPreparer(OpenSearchSeeder.LoadSchema(), DemoLimits.Default).PrepareRows(Requests.TextFilter("customer", "contains", "zzz-never-present"));

        var page = await service.FetchRowsAsync(request, CancellationToken.None);

        Assert.NotNull(page);
    }
}
