using Craticula.Core.Ir;
using Craticula.Sql;
using Microsoft.Data.Sqlite;

namespace Craticula.Dapper.Tests;

/// <summary>PG-5 (#3816): a paged entry point never loads every row; the unpaginated page is the streaming entry point's.</summary>
public class DapperGridQueryUnpaginatedPageTests
{
    private static FixtureRequest Paged() =>
        FixtureRequest.Load("sort-paging", FixtureRequest.ResolveDirectory("sort-paging", "007"));

    [Fact]
    public async Task The_Paged_Entry_Point_Refuses_The_Unpaginated_Page_And_Names_The_Stream()
    {
        var fixture = Paged();
        using var connection = new SqliteConnection("Data Source=:memory:");

        var ex = await Assert.ThrowsAsync<DapperCompilationException>(() =>
            DapperGridQuery.FetchPageAsync(connection, fixture.Sql with { Page = new NonePage() }, SqliteDialect.Instance));

        Assert.Contains(nameof(DapperExportStream), ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task The_Refusal_Happens_Before_Any_Database_Access()
    {
        var fixture = Paged();
        using var connection = new SqliteConnection("Data Source=:memory:");

        await Assert.ThrowsAsync<DapperCompilationException>(() =>
            DapperGridQuery.FetchPageAsync(connection, fixture.Sql with { Page = new NonePage() }, SqliteDialect.Instance));

        Assert.Equal(System.Data.ConnectionState.Closed, connection.State);
    }
}
