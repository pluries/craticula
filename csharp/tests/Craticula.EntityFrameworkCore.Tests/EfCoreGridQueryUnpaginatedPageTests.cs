using Craticula.Core.Ir;

namespace Craticula.EntityFrameworkCore.Tests;

/// <summary>PG-5 (#3816): a paged entry point never loads every row; the unpaginated page is the streaming entry point's.</summary>
public class EfCoreGridQueryUnpaginatedPageTests
{
    [Fact]
    public async Task The_Paged_Entry_Point_Refuses_The_Unpaginated_Page_And_Names_The_Stream()
    {
        var fixture = FixtureRequest.Load("sort-paging", FixtureRequest.ResolveDirectory("sort-paging", "001"));
        using var database = SqliteFixtureDatabase.Create(fixture.Schema, Datasets.PagedLastNames());

        var ex = await Assert.ThrowsAsync<EfCoreCompilationException>(() =>
            EfCoreGridQuery.FetchPageAsync(database.Rows(), fixture.Ef with { Page = new NonePage() }, EfCoreProviderSemantics.Sqlite));

        Assert.Contains(nameof(EfCoreExportStream), ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_Range_Page_Still_Returns_Its_Window()
    {
        var fixture = FixtureRequest.Load("sort-paging", FixtureRequest.ResolveDirectory("sort-paging", "001"));
        using var database = SqliteFixtureDatabase.Create(fixture.Schema, Datasets.PagedLastNames());

        var page = await EfCoreGridQuery.FetchPageAsync(database.Rows(), fixture.Ef, EfCoreProviderSemantics.Sqlite);

        Assert.NotEmpty(page.Rows);
    }
}
