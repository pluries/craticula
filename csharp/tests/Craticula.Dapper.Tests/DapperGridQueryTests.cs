using Craticula.Core.Ir;
using Craticula.Sql;

namespace Craticula.Dapper.Tests;

/// <summary>
/// The grid entry point's own contract: what a page carries, and what the optional count means. The
/// ROWS a page contains are asserted by <see cref="DapperExecutionEqualityTests"/>; what is left for
/// here is the envelope — the part #1646 had to invent, and therefore the part with no oracle behind it
/// at all (see <see cref="DapperGridPage"/> on why it is deliberately not OQ-8's shared response type).
/// </summary>
public class DapperGridQueryTests
{
    private static readonly ISqlDialect Sqlite = SqliteDialect.Instance;

    private static FixtureRequest Paged() =>
        FixtureRequest.Load("sort-paging", FixtureRequest.ResolveDirectory("sort-paging", "011"));

    /// <summary>
    /// AG Grid SSRM's <c>rowCount</c> is "how many rows match the filter", NOT "how many are on this
    /// page" — the distinction is only visible on a request whose page is smaller than its result, which
    /// is why sort-paging/011 (35 rows, a 20-row window landing 15) is the fixture used.
    /// </summary>
    [Fact]
    public async Task The_Row_Count_Is_The_Filtered_Total_And_Not_The_Page_Size()
    {
        var fixture = Paged();
        using var database = SqliteFixtureDatabase.Create(fixture.Schema, Datasets.PagedLastNames());

        var page = await DapperGridQuery.FetchPageAsync(
            database.Connection, fixture.Sql, Sqlite, includeRowCount: true);

        Assert.Equal(15, page.Rows.Count);
        Assert.Equal(35, page.RowCount);
    }

    /// <summary><see langword="null"/> and <c>0</c> are different answers: AG Grid treats an unknown
    /// total as "keep asking for blocks" and a zero as "there is nothing". A caller that did not ask for
    /// the count gets <see langword="null"/>.</summary>
    [Fact]
    public async Task An_Unrequested_Row_Count_Is_Null()
    {
        var fixture = Paged();
        using var database = SqliteFixtureDatabase.Create(fixture.Schema, Datasets.PagedLastNames());

        var page = await DapperGridQuery.FetchPageAsync(database.Connection, fixture.Sql, Sqlite);

        Assert.Null(page.RowCount);
    }

    /// <summary>The separate count entry point answers the same question as the flag, so a host that
    /// fetches the total on a different cadence from its blocks cannot be asking something subtly
    /// different.</summary>
    [Fact]
    public async Task The_Standalone_Count_Agrees_With_The_Pages_Own()
    {
        var fixture = Paged();
        using var database = SqliteFixtureDatabase.Create(fixture.Schema, Datasets.PagedLastNames());

        var page = await DapperGridQuery.FetchPageAsync(
            database.Connection, fixture.Sql, Sqlite, includeRowCount: true);
        var standalone = await DapperGridQuery.CountAsync(database.Connection, fixture.Sql, Sqlite);

        Assert.Equal(page.RowCount, standalone);
    }

    /// <summary>
    /// EXP-1(b): a grid page with no explicit projection returns every declared field in GRP-3's
    /// declaration order, under its LOGICAL colId — not the physical column names a bare <c>SELECT *</c>
    /// would hand back. sort-paging/011's <c>lastName</c> lives in <c>last_name</c>, so the two differ
    /// and the assertion is not vacuous.
    /// </summary>
    [Fact]
    public async Task A_Page_Names_Its_Columns_By_Logical_ColId_In_Declaration_Order()
    {
        var fixture = Paged();
        using var database = SqliteFixtureDatabase.Create(fixture.Schema, Datasets.PagedLastNames());

        var page = await DapperGridQuery.FetchPageAsync(database.Connection, fixture.Sql, Sqlite);

        Assert.Equal(fixture.Schema.FieldOrder, page.Columns);
        Assert.Contains("lastName", page.Columns);
        Assert.Equal("last_name", SqliteFixtureDatabase.PhysicalColumn(fixture.Schema, "lastName"));

        foreach (var row in page.Rows)
        {
            Assert.Equal(page.Columns.Count, row.Count);
        }
    }

    /// <summary>EXP-1(b) again, from the other side: an explicit projection is honoured in the order it
    /// was asked for, and it may be a SUBSET that omits the stable key the ordering still needs.</summary>
    [Fact]
    public async Task An_Explicit_Projection_Is_Honoured_In_Request_Order()
    {
        var fixture = FixtureRequest.Load("page-export", FixtureRequest.ResolveDirectory("page-export", "008"));
        var request = fixture.Sql with { Page = new RangePage { StartRow = 0, EndRow = 3 } };

        using var database = SqliteFixtureDatabase.Create(fixture.Schema, Datasets.ExportableOrders());
        var page = await DapperGridQuery.FetchPageAsync(database.Connection, request, Sqlite);

        Assert.Equal(["customerName", "totalAmount", "orderDate"], page.Columns);
        Assert.Equal(3, page.Rows.Count);
        Assert.All(page.Rows, row => Assert.Equal(3, row.Count));
    }

    /// <summary>
    /// #1622/#1653's native-CLR-values obligation, checked from the grid path: a cell materializes as
    /// the schema's declared CLR type, not whatever the SQLite driver's own storage class happens to
    /// hand back (a <c>decimal</c> column reads as a boxed <see cref="decimal"/>, a <c>date</c> column's
    /// TEXT storage reads back as a <see cref="DateOnly"/>).
    /// </summary>
    [Fact]
    public async Task Cells_Materialize_As_The_Schemas_Declared_Clr_Type()
    {
        var fixture = FixtureRequest.Load("page-export", FixtureRequest.ResolveDirectory("page-export", "008"));
        using var database = SqliteFixtureDatabase.Create(fixture.Schema, Datasets.ExportableOrders());

        // This fixture is an export of everything (the unpaginated page), which the paged entry point refuses (PG-5);
        // the subject here is cell materialization, so ask for the same rows as one window.
        var windowed = fixture.Sql with { Page = new RangePage { StartRow = 0, EndRow = 100 } };
        var page = await DapperGridQuery.FetchPageAsync(database.Connection, windowed, Sqlite);

        var totalAmountIndex = page.Columns.ToList().IndexOf("totalAmount");
        var orderDateIndex = page.Columns.ToList().IndexOf("orderDate");

        var firstRow = page.Rows[0];
        Assert.IsType<decimal>(firstRow[totalAmountIndex]);
        Assert.Equal(19.99m, firstRow[totalAmountIndex]);
        Assert.IsType<DateOnly>(firstRow[orderDateIndex]);
        Assert.Equal(new DateOnly(2024, 1, 1), firstRow[orderDateIndex]);
    }

    /// <summary>
    /// #1646's own code review: <c>avg</c> over a non-decimal source column must materialize as a
    /// fractional <see cref="double"/>, not the source field's own <see cref="Craticula.Core.Schema.FieldType.Int64"/>
    /// — the exact defect this fixture's own two ages (30, 31) discriminate, since their average (30.5)
    /// is only distinguishable from a rounded/truncated 30 or 31 by actually keeping the fraction.
    /// dialect-parity/024 is the fixture that shape was measured against.
    /// </summary>
    [Fact]
    public async Task An_Average_Over_An_Integer_Column_Keeps_Its_Fractional_Value()
    {
        var fixture = FixtureRequest.Load(
            "dialect-parity", FixtureRequest.ResolveDirectory("dialect-parity", "024"));

        IReadOnlyList<IReadOnlyDictionary<string, object?>> dataset =
        [
            new Dictionary<string, object?> { ["id"] = 1L, ["department"] = "Eng", ["salary"] = 100m, ["age"] = 30L },
            new Dictionary<string, object?> { ["id"] = 2L, ["department"] = "Eng", ["salary"] = 200m, ["age"] = 31L }
        ];

        using var database = SqliteFixtureDatabase.Create(fixture.Schema, dataset);
        var page = await DapperGridQuery.FetchPageAsync(database.Connection, fixture.Sql, Sqlite);

        var ageIndex = page.Columns.ToList().IndexOf("age_avg");
        Assert.True(ageIndex >= 0, $"Expected an 'age_avg' column, got: {string.Join(", ", page.Columns)}");

        var value = Assert.IsType<double>(page.Rows[0][ageIndex]);
        Assert.Equal(30.5, value);
    }
}
