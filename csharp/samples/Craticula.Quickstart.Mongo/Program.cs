using Craticula.AgGrid;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Mongo;

const string RequestHead = """{ "startRow": 0, "endRow": 50, "rowGroupCols": [], "valueCols": [], "pivotCols": [], "pivotMode": false, "groupKeys": [],""";

// 1. The schema is the allowlist: a field that is not listed here can never reach a pipeline, and every path in the
//    pipeline comes from `physical.mongo.path`, never from the request.
const string schemaJson = """
    {
      "mode": "strict",
      "source": "tickets",
      "stableKey": "id",
      "fields": {
        "id":       { "type": "int64",  "sortable": true, "physical": { "mongo": { "path": "id" } } },
        "subject":  { "type": "string", "filterable": true, "sortable": true, "physical": { "mongo": { "path": "subject" } },
                      "text": { "caseSensitivity": "insensitive", "searchMode": "substring" } },
        "priority": { "type": "int64",  "filterable": true, "sortable": true, "physical": { "mongo": { "path": "priority" } } }
      }
    }
    """;

// 2. A request exactly as AG Grid's server-side row model sends it: subjects containing "refund", priority above 2,
//    most urgent first, the first 50 rows.
const string requestJson = RequestHead + """
      "filterModel": {
        "subject": { "filterType": "text", "type": "contains", "filter": "refund" },
        "priority": { "filterType": "number", "type": "greaterThan", "filter": 2 }
      },
      "sortModel": [ { "colId": "priority", "sort": "desc" } ] }
    """;

// 5 (input). The grid asks to filter on `password`, which the schema does not list.
const string hostileJson = RequestHead + """
      "filterModel": { "password": { "filterType": "text", "type": "equals", "filter": "x" } }, "sortModel": [] }
    """;

GridSchema schema = GridSchema.Parse(schemaJson);

// 3. Parse the request into the canonical IR, then validate it against the schema and the resource limits.
MongoQueryRequest Prepare(string json)
{
    AgGridParsedRequest parsed = AgGridRequestParser.Parse(json, new AgGridParseOptions { Schema = schema });
    FilterNode? filter = GridFilterPipeline.Process(
        parsed.NativeFilter, parsed.CustomFilters, parsed.Page, schema, new ResourceLimits(), parsed.Group, parsed.Aggregations);
    return new MongoQueryRequest { Schema = schema, Filter = filter, Sort = parsed.Sort, Page = parsed.Page };
}

// 5. A field the schema does not list is refused before any pipeline exists.
string Refuse(string json)
{
    try
    {
        Prepare(json);
        return "-- the unknown column was NOT refused";
    }
    catch (UnknownFieldException error)
    {
        return $"-- refused: {error.GetType().Name}: {error.Message}";
    }
}

MongoQueryRequest request = Prepare(requestJson);

// 4. Compile: one aggregation pipeline for the page and one for the row count. Values are data in the documents, never
//    concatenated into code.
MongoQuery page = MongoPipelineBuilder.Build(request);
MongoQuery count = MongoPipelineBuilder.BuildCount(request);

Console.WriteLine($"-- collection: {page.Collection}");
Console.WriteLine("-- page");
Console.WriteLine(page.ToArtifact().ToJsonString());
Console.WriteLine("-- count");
Console.WriteLine(count.ToArtifact().ToJsonString());
Console.WriteLine();
Console.WriteLine(Refuse(hostileJson));
