using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Mongo;
using MongoDB.Bson;

namespace Craticula.MongoDB.Driver.Tests;

/// <summary>
/// The grid entry point's own contract, proven against a REAL running MongoDB instance
/// (<c>CRATICULA_MONGO_TEST_URI</c>, default <c>mongodb://localhost:27017</c> — see
/// <see cref="MongoFixtureDatabase"/>'s own remarks for how to start it): a real document set seeded,
/// the real <see cref="MongoPipelineBuilder.Build"/> compiling a real fixture's request, executed via
/// <see cref="MongoGridQuery"/>, compared against an INDEPENDENTLY HAND-COMPUTED expected sequence — the
/// same two-sided-oracle discipline <c>Craticula.Dapper.Tests</c> applies, minus the second compiler
/// neither backend has here (see <see cref="MongoFixtureDatabase"/>'s own remarks).
/// </summary>
public sealed class MongoGridQueryTests
{
    private static FixtureRequest ExportableOrdersFixture() =>
        FixtureRequest.Load("page-export", FixtureRequest.ResolveDirectory("page-export", "008"));

    private static FixtureRequest SalesFactFixture() =>
        FixtureRequest.Load("group-aggregation", FixtureRequest.ResolveDirectory("group-aggregation", "001"));

    // ---- ordinary (no group, no projection): WithExplicitProjection + SC-4 physical-path remapping ----

    /// <summary>
    /// EXP-1(b): a grid page with no explicit projection returns every declared field in schema
    /// declaration order, under its LOGICAL colId — not whatever raw document shape a bare, unprojected
    /// pipeline would hand back. This fixture's schema maps <c>id</c> onto the document's own <c>_id</c>
    /// key AND <c>customerName</c> onto a NESTED <c>customer.name</c> path, so both remaps are proven at
    /// once against the real server.
    /// </summary>
    [Fact]
    public async Task An_Ordinary_Fetch_Forces_An_Explicit_Projection_And_Remaps_Physical_Paths()
    {
        var fixture = ExportableOrdersFixture();
        await using var database = await MongoFixtureDatabase.CreateAsync(fixture.Schema, Datasets.ExportableOrders());

        var request = new MongoQueryRequest
        {
            Schema = database.Schema,
            Filter = null,
            Sort = null,
            Page = new RangePage { StartRow = 0, EndRow = 100 },
            Group = null,
            Aggregations = null,
            Projection = null
        };

        var page = await MongoGridQuery.FetchPageAsync(database.Database, request);

        Assert.Equal(database.Schema.FieldOrder, page.Columns);
        Assert.Equal(["id", "orderDate", "customerName", "totalAmount", "status", "region", "notes"], page.Columns);
        Assert.Equal(5, page.Rows.Count);

        // SEM-6 mints "id" as the sole sort key (sortModel is empty upstream of this hand-built request,
        // and this schema's stableKey is "id") -- ascending, so the five ids come back in order.
        var idIndex = page.Columns.ToList().IndexOf("id");
        Assert.Equal([1L, 2L, 3L, 4L, 5L], page.Rows.Select(row => row[idIndex]));

        var nameIndex = page.Columns.ToList().IndexOf("customerName");
        Assert.Equal("Acme", page.Rows[0][nameIndex]);
        Assert.Null(page.Rows[1][nameIndex]);
    }

    /// <summary>
    /// #1622/#1652/#1653's native-CLR-values obligation, checked from the grid path: a
    /// <see cref="MongoDB.Bson.BsonDecimal128"/> cell materializes as a <see cref="decimal"/> keeping its
    /// scale, and a plain ISO date string materializes as a <see cref="DateOnly"/> — against the real
    /// driver, not a hand-written oracle.
    /// </summary>
    [Fact]
    public async Task Cells_Materialize_As_The_Schemas_Declared_Clr_Type()
    {
        var fixture = ExportableOrdersFixture();
        await using var database = await MongoFixtureDatabase.CreateAsync(fixture.Schema, Datasets.ExportableOrders());

        var request = new MongoQueryRequest
        {
            Schema = database.Schema,
            Page = new RangePage { StartRow = 0, EndRow = 100 }
        };

        var page = await MongoGridQuery.FetchPageAsync(database.Database, request);

        var totalAmountIndex = page.Columns.ToList().IndexOf("totalAmount");
        var orderDateIndex = page.Columns.ToList().IndexOf("orderDate");

        var firstRow = page.Rows[0];
        Assert.IsType<decimal>(firstRow[totalAmountIndex]);
        Assert.Equal(19.99m, firstRow[totalAmountIndex]);
        Assert.IsType<DateOnly>(firstRow[orderDateIndex]);
        Assert.Equal(new DateOnly(2024, 1, 1), firstRow[orderDateIndex]);
    }

    /// <summary>EXP-1(b) from the other side: an explicit (export-resolved) projection is honoured in the
    /// order it was asked for, over the grid entry point rather than the export one — a page-scoped
    /// export (<c>exportScope: 'page'</c>) is the same aggregation as a grid block.</summary>
    [Fact]
    public async Task An_Explicit_Projection_Is_Honoured_In_Request_Order()
    {
        var fixture = ExportableOrdersFixture();
        await using var database = await MongoFixtureDatabase.CreateAsync(fixture.Schema, Datasets.ExportableOrders());

        var request = fixture.Request with { Schema = database.Schema, Page = new RangePage { StartRow = 0, EndRow = 3 } };

        Assert.Equal(["customerName", "totalAmount", "orderDate"], request.Projection);

        var page = await MongoGridQuery.FetchPageAsync(database.Database, request);

        Assert.Equal(["customerName", "totalAmount", "orderDate"], page.Columns);
        Assert.Equal(3, page.Rows.Count);
        Assert.All(page.Rows, row => Assert.Equal(3, row.Count));
    }

    // ---- row count: filtered total, not page size, and null when not requested ----------------------

    /// <summary>
    /// AG Grid SSRM's <c>rowCount</c> is "how many documents match the filter", NOT "how many are on this
    /// page" — the distinction is only visible on a request whose page is smaller than its result.
    /// </summary>
    [Fact]
    public async Task The_Row_Count_Is_The_Filtered_Total_And_Not_The_Page_Size()
    {
        var fixture = ExportableOrdersFixture();
        await using var database = await MongoFixtureDatabase.CreateAsync(fixture.Schema, Datasets.ExportableOrders());

        var request = new MongoQueryRequest
        {
            Schema = database.Schema,
            Page = new RangePage { StartRow = 0, EndRow = 3 }
        };

        var page = await MongoGridQuery.FetchPageAsync(database.Database, request, includeRowCount: true);

        Assert.Equal(3, page.Rows.Count);
        Assert.Equal(5, page.RowCount);
    }

    /// <summary><see langword="null"/> and <c>0</c> are different answers: AG Grid treats an unknown
    /// total as "keep asking for blocks" and a zero as "there is nothing". A caller that did not ask for
    /// the count gets <see langword="null"/>.</summary>
    [Fact]
    public async Task An_Unrequested_Row_Count_Is_Null()
    {
        var fixture = ExportableOrdersFixture();
        await using var database = await MongoFixtureDatabase.CreateAsync(fixture.Schema, Datasets.ExportableOrders());

        var request = new MongoQueryRequest
        {
            Schema = database.Schema,
            Page = new RangePage { StartRow = 0, EndRow = 3 }
        };

        var page = await MongoGridQuery.FetchPageAsync(database.Database, request);

        Assert.Null(page.RowCount);
    }

    /// <summary>The separate count entry point answers the same question as the flag, so a host fetching
    /// the total on a different cadence from its blocks cannot be asking something subtly
    /// different — and it must survive MongoDB's own <c>$count</c> quirk (no output document at all when
    /// nothing matches, exercised separately below).</summary>
    [Fact]
    public async Task The_Standalone_Count_Agrees_With_The_Pages_Own()
    {
        var fixture = ExportableOrdersFixture();
        await using var database = await MongoFixtureDatabase.CreateAsync(fixture.Schema, Datasets.ExportableOrders());

        var request = new MongoQueryRequest
        {
            Schema = database.Schema,
            Page = new RangePage { StartRow = 0, EndRow = 3 }
        };

        var page = await MongoGridQuery.FetchPageAsync(database.Database, request, includeRowCount: true);
        var standalone = await MongoGridQuery.CountAsync(database.Database, request);

        Assert.Equal(page.RowCount, standalone);
    }

    /// <summary>MongoDB's <c>$count</c> stage emits NO output document when zero documents reach it —
    /// unlike SQL's <c>COUNT(*)</c>, which always returns exactly one row. An absent result must read as
    /// <c>0</c>, not throw or hang.</summary>
    [Fact]
    public async Task A_Count_Over_Zero_Matching_Documents_Is_Zero_Not_An_Absent_Result()
    {
        var fixture = ExportableOrdersFixture();
        await using var database = await MongoFixtureDatabase.CreateAsync(fixture.Schema, []);

        var request = new MongoQueryRequest
        {
            Schema = database.Schema,
            Page = new RangePage { StartRow = 0, EndRow = 100 }
        };

        var count = await MongoGridQuery.CountAsync(database.Database, request);

        Assert.Equal(0L, count);
    }

    // ---- grouping: _id -> group column rename, real $group/$sum/$avg over Decimal128/Int64 -----------

    /// <summary>
    /// A real grouped level, against the real server: <c>Craticula.Mongo</c>'s own <c>$group</c> stage
    /// always keys its bucket under the literal <c>_id</c>; this package renames it back to the group
    /// column's own colId (<see cref="MongoGridPage"/>'s own remarks) before the grid ever sees it. Sum
    /// over a real <see cref="MongoDB.Bson.BsonDecimal128"/> column, including a bucket with a null
    /// value the server must skip rather than zero the whole bucket.
    /// </summary>
    [Fact]
    public async Task A_Grouped_Level_Renames_The_Bucket_Column_And_Sums_A_Decimal_Field()
    {
        var fixture = SalesFactFixture();
        await using var database = await MongoFixtureDatabase.CreateAsync(fixture.Schema, Datasets.SalesFact());

        var request = fixture.Request with { Schema = database.Schema };

        var page = await MongoGridQuery.FetchPageAsync(database.Database, request);

        Assert.Equal(["region", "amount_sum"], page.Columns);
        Assert.Equal(3, page.Rows.Count);

        var byRegion = page.Rows.ToDictionary(row => (string)row[0]!, row => (decimal)row[1]!);
        Assert.Equal(30.00m, byRegion["AMER"]);
        Assert.Equal(75.25m, byRegion["APAC"]);
        Assert.Equal(350.50m, byRegion["EMEA"]);

        // No explicit sort in this fixture, so SEM-6 mints the group column itself as the tiebreaker
        // (GRP-4) -- ascending, hence AMER, APAC, EMEA in that order.
        Assert.Equal(["AMER", "APAC", "EMEA"], page.Rows.Select(row => row[0]));
    }

    /// <summary>
    /// AGG-1's non-obvious member, against a real integer column: <c>avg</c> does NOT keep the source
    /// field's <see cref="FieldType.Int64"/> the way <c>sum</c>/<c>min</c>/<c>max</c> genuinely do —
    /// MongoDB's own <c>$avg</c> always returns a fractional value. EMEA's two quantities (3, 4) average
    /// to a genuinely fractional 3.5, which only reads back correctly as a real <see cref="double"/>.
    /// </summary>
    [Fact]
    public async Task An_Average_Over_An_Integer_Column_Widens_To_Double()
    {
        var fixture = SalesFactFixture();
        await using var database = await MongoFixtureDatabase.CreateAsync(fixture.Schema, Datasets.SalesFact());

        var request = new MongoQueryRequest
        {
            Schema = database.Schema,
            Page = new RangePage { StartRow = 0, EndRow = 100 },
            Group = new GroupSpec { GroupCols = ["region"], GroupKeys = [] },
            Aggregations = [new Aggregation { Field = "quantity", Func = AggregationFunc.Avg }]
        };

        var page = await MongoGridQuery.FetchPageAsync(database.Database, request);

        Assert.Equal(["region", "quantity_avg"], page.Columns);

        var emeaIndex = page.Rows.ToList().FindIndex(row => (string)row[0]! == "EMEA");
        Assert.True(emeaIndex >= 0, "Expected an EMEA bucket.");

        var value = Assert.IsType<double>(page.Rows[emeaIndex][1]);
        Assert.Equal(3.5, value);
    }

    /// <summary>For a grouped level, <c>RowCount</c> is the BUCKET count, not the leaf-document count —
    /// proven on a page window smaller than the number of buckets, exactly like the ordinary case
    /// above.</summary>
    [Fact]
    public async Task RowCount_For_A_Grouped_Level_Is_The_Bucket_Count()
    {
        var fixture = SalesFactFixture();
        await using var database = await MongoFixtureDatabase.CreateAsync(fixture.Schema, Datasets.SalesFact());

        var request = fixture.Request with { Schema = database.Schema, Page = new RangePage { StartRow = 0, EndRow = 2 } };

        var page = await MongoGridQuery.FetchPageAsync(database.Database, request, includeRowCount: true);

        Assert.Equal(2, page.Rows.Count);
        Assert.Equal(3, page.RowCount); // AMER, APAC, EMEA -- three buckets, not six seeded documents
    }

    // ---- #1647's own code review: three hazards found and fixed, all proven here -----------------------

    /// <summary>
    /// The re-verification pass on this story's own fix found <c>ToDouble</c>'s first
    /// <c>BsonDecimal128</c> arm routed through <c>decimal</c> before reaching <c>double</c> —
    /// narrowing the domain to <c>decimal</c>'s (~1e±28) and re-introducing the exact silent-wrong-value
    /// class the surrounding rewrite exists to remove (a tiny value like <c>1E-40</c> underflowed to
    /// <c>0</c> instead of the double it can represent exactly). Reachable in ordinary use, not only via
    /// a mis-typed document: MongoDB promotes an <c>$avg</c>'s result type to Decimal128 the moment ANY
    /// input to the average is stored as <c>NumberDecimal</c>, even when the schema declares the source
    /// field <see cref="FieldType.Int64"/> — mixed here deliberately to trigger exactly that promotion.
    /// </summary>
    [Fact]
    public async Task An_Average_Promoted_To_Decimal128_By_MongoDB_Still_Reads_Back_As_Double()
    {
        var schema = GridSchema.Parse("""
            {
              "mode": "strict", "source": "items", "stableKey": "id",
              "fields": {
                "id": { "type": "int64", "filterable": true, "sortable": true },
                "category": { "type": "string", "filterable": true, "sortable": true, "groupable": true },
                "quantity": { "type": "int64", "filterable": true, "sortable": true, "aggregatable": ["avg"] }
              }
            }
            """);

        IReadOnlyList<BsonDocument> documents =
        [
            // A mismatched-type seed: MongoDB's $avg promotes to Decimal128 once ANY input is
            // NumberDecimal, even though the schema declares this field Int64. Both share "category" so
            // they land in the SAME bucket and their quantities (3, 4) genuinely average to 3.5.
            new BsonDocument { ["id"] = 1L, ["category"] = "all", ["quantity"] = new BsonDecimal128(3m) },
            new BsonDocument { ["id"] = 2L, ["category"] = "all", ["quantity"] = 4L }
        ];

        await using var database = await MongoFixtureDatabase.CreateAsync(schema, documents);

        var request = new MongoQueryRequest
        {
            Schema = database.Schema,
            Page = new RangePage { StartRow = 0, EndRow = 100 },
            Group = new GroupSpec { GroupCols = ["category"], GroupKeys = [] },
            Aggregations = [new Aggregation { Field = "quantity", Func = AggregationFunc.Avg }]
        };

        var page = await MongoGridQuery.FetchPageAsync(database.Database, request);

        var value = Assert.IsType<double>(page.Rows[0][1]);
        Assert.Equal(3.5, value);
    }

    /// <summary>
    /// <c>Craticula.MongoDB.Driver.MongoValueReader</c>'s own review found <c>BsonValue.ToBoolean()</c>
    /// implements MongoDB query-language TRUTHINESS, not a boolean conversion — a
    /// <see cref="FieldType.Boolean"/> field storing the STRING <c>"false"</c> (the common shape for a
    /// collection seeded from CSV/JSON, since MongoDB is schemaless and nothing prevents it) used to read
    /// back as <see langword="true"/>, silently. Seeded here as a raw <see cref="BsonDocument"/> rather
    /// than through the normal dataset path specifically to reach that mismatched-type shape.
    /// </summary>
    [Fact]
    public async Task A_Boolean_Field_Stored_As_The_Text_False_Reads_Back_As_False_Not_True()
    {
        var schema = GridSchema.Parse("""
            {
              "mode": "strict", "source": "items", "stableKey": "id",
              "fields": {
                "id": { "type": "int64", "filterable": true, "sortable": true },
                "active": { "type": "boolean", "filterable": true, "sortable": true }
              }
            }
            """);

        IReadOnlyList<BsonDocument> documents =
        [
            new BsonDocument { ["id"] = 1L, ["active"] = "false" },
            new BsonDocument { ["id"] = 2L, ["active"] = "true" },
            new BsonDocument { ["id"] = 3L, ["active"] = true }
        ];

        await using var database = await MongoFixtureDatabase.CreateAsync(schema, documents);

        var request = new MongoQueryRequest { Schema = database.Schema, Page = new RangePage { StartRow = 0, EndRow = 100 } };
        var page = await MongoGridQuery.FetchPageAsync(database.Database, request);

        var activeIndex = page.Columns.ToList().IndexOf("active");
        var byId = page.Rows.ToDictionary(row => (long)row[0]!, row => (bool)row[activeIndex]!);

        Assert.False(byId[1]);
        Assert.True(byId[2]);
        Assert.True(byId[3]);
    }

    /// <summary>
    /// The count must not keep SEM-6's mandatory <c>$sort</c> (nor its two SEM-3 bucket-labeling stages): that would turn an
    /// order-independent scalar count into an unbounded blocking sort of the whole filtered set on every filter change. Since
    /// story #3863 the stage list lives in <c>MongoPipelineBuilder.BuildCount</c> (CNT-6, pinned by the count-mode fixtures in
    /// <c>MongoCountTests</c>), and this adapter must use it and strip nothing itself. Structural, mirroring
    /// <c>Craticula.Dapper.Tests</c>' own "no offset" source-scan guards: the property is of the code, not of the datasets
    /// this suite happens to try.
    /// </summary>
    [Fact]
    public void The_Count_Runs_The_Builders_Count_Pipeline_And_Strips_Nothing_Itself()
    {
        var adapter = RepoPaths.AdapterSource("MongoGridQuery.cs");
        var builder = Path.Combine(RepoPaths.Root, "csharp", "src", "Craticula.Mongo", "MongoPipelineBuilder.cs");
        Assert.True(File.Exists(adapter), $"Expected the grid entry point's source at '{adapter}'.");
        Assert.True(File.Exists(builder), $"Expected the pipeline builder's source at '{builder}'.");

        var adapterSource = File.ReadAllText(adapter);

        Assert.Contains("MongoPipelineBuilder.BuildCount(", adapterSource, StringComparison.Ordinal);
        Assert.DoesNotContain("BuildCountPipeline", adapterSource, StringComparison.Ordinal);
        Assert.Contains(
            "\"$skip\" or \"$limit\" or \"$project\" or \"$sort\" or \"$addFields\" or \"$unset\"",
            File.ReadAllText(builder),
            StringComparison.Ordinal);
    }
}
