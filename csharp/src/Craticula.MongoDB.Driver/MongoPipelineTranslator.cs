using System.Text.Json.Nodes;
using MongoDB.Bson;
using MongoDB.Driver;

namespace Craticula.MongoDB.Driver;

/// <summary>
/// Translates <c>Craticula.Mongo</c>'s hand-emitted Extended JSON (<see cref="JsonObject"/>, from
/// <c>System.Text.Json.Nodes</c> — AR-3's "no driver package in the compiler" choice) into the shapes
/// <c>MongoDB.Driver</c>'s own API needs: a <see cref="BsonDocument"/> array for
/// <c>IMongoCollection{TDocument}.AggregateAsync</c>'s pipeline argument, and an
/// <see cref="AggregateOptions"/> carrying the query-level collation, when present.
///
/// <para><b>The translation is text round-tripping through the driver's OWN Extended JSON reader, not
/// a hand-rolled node walk — and that choice was checked, not assumed.</b> <c>MongoDB.Bson</c>'s
/// <see cref="BsonDocument.Parse(string)"/> already implements a MongoDB Extended JSON reader — the
/// exact dialect <c>Craticula.Mongo.MongoExtendedJson.Encode</c> hand-emits
/// (<c>{"$numberDecimal": "19.99"}</c> for a <c>decimal</c>, <c>{"$date": "…Z"}</c> for a
/// <c>datetime</c>) — so re-serializing each stage to its JSON text via
/// <see cref="JsonNode.ToJsonString(System.Text.Json.JsonSerializerOptions?)"/> and re-parsing it
/// through that reader reproduces the exact BSON types the compiler intended
/// (<see cref="BsonDecimal128"/>, <see cref="BsonDateTime"/>) with no separate mapping table to keep in
/// sync with <c>MongoExtendedJson</c>'s own choices — a new Extended JSON convention the compiler
/// starts emitting is understood here automatically as long as the driver's reader already supports
/// it, which is the whole class of built-in BSON types. Verified against several real
/// <c>Craticula.Mongo.Tests</c> fixture pipelines (a <c>$numberDecimal</c> value, a <c>$date</c> value,
/// a <c>$regex</c>/<c>$options</c> query operator, an <c>$expr</c>/<c>$literal</c> escape) before
/// relying on it — the plan's own instruction not to assume a naive round trip works without
/// checking. This story's own execution tests are the end-to-end proof: a decimal or datetime filter
/// that compared wrong would show up as a wrong row set against the real container, not merely as a
/// parse failure.</para>
/// </summary>
internal static class MongoPipelineTranslator
{
    /// <summary>Each pipeline stage, in order — <c>Craticula.Mongo.MongoQuery.Pipeline</c>'s own
    /// element order IS the aggregation's stage order, and the driver's pipeline argument is
    /// positional, so nothing here may reorder them.</summary>
    public static BsonDocument[] Translate(IReadOnlyList<JsonObject> stages)
    {
        var translated = new BsonDocument[stages.Count];
        for (var index = 0; index < stages.Count; index++)
        {
            translated[index] = TranslateDocument(stages[index]);
        }

        return translated;
    }

    /// <summary>One Extended JSON document, translated the same way a pipeline stage is — shared by
    /// <see cref="Translate"/> and <see cref="Options"/>, since a collation document is Extended JSON
    /// too (it just travels as a command option rather than a pipeline element).</summary>
    public static BsonDocument TranslateDocument(JsonObject document) => BsonDocument.Parse(document.ToJsonString());

    /// <summary>
    /// <c>Craticula.Mongo.MongoQuery.Collation</c>, translated into the driver's own
    /// <see cref="AggregateOptions.Collation"/> — MongoDB's <c>collation</c> is an <c>aggregate()</c>
    /// COMMAND option, not a pipeline stage (<c>MongoQuery</c>'s own remarks), so it travels separately
    /// from <see cref="Translate"/>'s stage array. <see cref="Collation.FromBsonDocument"/> is the
    /// driver's own reader for the <c>{locale, strength, …}</c> shape
    /// <c>MongoPipelineBuilder.NewCollation</c> emits, so this needs no field-by-field mapping of its
    /// own — it inherits whichever collation options the compiler starts emitting next, not just
    /// today's <c>locale</c>/<c>strength</c> pair. Returns <see langword="null"/> options when the
    /// query carries no collation at all, which the driver treats identically to an omitted option.
    /// </summary>
    public static AggregateOptions? Options(Craticula.Mongo.MongoQuery query)
    {
        if (query.Collation is null && query.MaxTimeMs is null)
        {
            return null;
        }

        var options = new AggregateOptions();
        if (query.Collation is not null)
        {
            options.Collation = Collation.FromBsonDocument(TranslateDocument(query.Collation));
        }

        if (query.MaxTimeMs is { } maxTimeMs)
        {
            options.MaxTime = TimeSpan.FromMilliseconds(maxTimeMs);
        }

        return options;
    }
}
