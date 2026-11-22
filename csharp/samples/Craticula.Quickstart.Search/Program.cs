using Craticula.AgGrid;
using Craticula.Core.Schema;
using Craticula.Search;

// The schema is the allowlist: a field that is not listed here can never reach a query, and every field name in the
// query comes from `physical.search.field`, never from the request.
GridSchema grid = GridSchema.Parse("""
    {
      "mode": "strict",
      "source": "products",
      "stableKey": "id",
      "fields": {
        "id":    { "type": "int64",  "sortable": true, "physical": { "search": { "field": "id" } } },
        "name":  { "type": "string", "filterable": true, "sortable": true,
                   "physical": { "search": { "field": "name", "keywordSubField": "name.keyword" } },
                   "text": { "caseSensitivity": "insensitive", "searchMode": "substring" } },
        "stock": { "type": "int64",  "filterable": true, "sortable": true, "physical": { "search": { "field": "stock" } } }
      }
    }
    """);

// Requests exactly as AG Grid's server-side row model sends them: names containing "lamp" with more than 5 in stock,
// lowest stock first, the first 25 rows; and a hostile one that filters on a field the schema does not list.
string[] requests =
[
    """
    { "startRow": 0, "endRow": 25, "rowGroupCols": [], "valueCols": [], "pivotCols": [], "pivotMode": false, "groupKeys": [],
      "filterModel": {
        "name": { "filterType": "text", "type": "contains", "filter": "lamp" },
        "stock": { "filterType": "number", "type": "greaterThan", "filter": 5 }
      },
      "sortModel": [ { "colId": "stock", "sort": "asc" } ] }
    """,
];
const string hostile = """
    { "startRow": 0, "endRow": 25, "rowGroupCols": [], "valueCols": [], "pivotCols": [], "pivotMode": false, "groupKeys": [],
      "filterModel": { "password": { "filterType": "text", "type": "equals", "filter": "x" } }, "sortModel": [] }
    """;

foreach (string json in requests)
{
    // Parse into the canonical IR, validate against the schema and the limits, then compile the page and the count.
    AgGridParsedRequest parsed = AgGridRequestParser.Parse(json, new AgGridParseOptions { Schema = grid });
    var filter = GridFilterPipeline.Process(
        parsed.NativeFilter, parsed.CustomFilters, parsed.Page, grid, new ResourceLimits(), parsed.Group, parsed.Aggregations);
    var query = new SearchQueryRequest { Schema = grid, Filter = filter, Sort = parsed.Sort, Page = parsed.Page };

    SearchQuery rows = SearchQueryBuilder.Build(query);
    SearchQuery total = SearchQueryBuilder.BuildCount(query);

    Console.WriteLine($"-- index: {rows.Index}");
    Console.WriteLine("-- page");
    Console.WriteLine(rows.ToArtifact().ToJsonString());
    Console.WriteLine("-- count");
    Console.WriteLine(total.ToArtifact().ToJsonString());
    Console.WriteLine();
}

// A field the schema does not list is refused before any query exists.
try
{
    AgGridParsedRequest bad = AgGridRequestParser.Parse(hostile, new AgGridParseOptions { Schema = grid });
    GridFilterPipeline.Process(bad.NativeFilter, bad.CustomFilters, bad.Page, grid, new ResourceLimits(), bad.Group, bad.Aggregations);
    Console.WriteLine("-- the unknown column was NOT refused");
}
catch (UnknownFieldException error)
{
    Console.WriteLine($"-- refused: {error.GetType().Name}: {error.Message}");
}
