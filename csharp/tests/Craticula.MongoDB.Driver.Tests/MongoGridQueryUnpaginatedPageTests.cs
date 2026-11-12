using Craticula.Core.Ir;
using Craticula.Mongo;
using MongoDB.Driver;

namespace Craticula.MongoDB.Driver.Tests;

/// <summary>PG-5 (#3816): the paged entry point never loads every row. The refusal comes before any server
/// call, so this needs no running MongoDB even though the project is excluded from the offline gate.</summary>
public sealed class MongoGridQueryUnpaginatedPageTests
{
    [Fact]
    public async Task The_Paged_Entry_Point_Refuses_The_Unpaginated_Page_And_Names_The_Stream()
    {
        var fixture = FixtureRequest.Load("page-export", FixtureRequest.ResolveDirectory("page-export", "008"));
        var database = new MongoClient("mongodb://localhost:1").GetDatabase("unused");

        var ex = await Assert.ThrowsAsync<MongoDriverCompilationException>(() =>
            MongoGridQuery.FetchPageAsync(database, fixture.Request with { Page = new NonePage() }));

        Assert.Contains(nameof(MongoExportStream), ex.Message, StringComparison.Ordinal);
    }
}
