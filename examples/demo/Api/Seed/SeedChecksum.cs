using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using MongoDB.Bson;
using MongoDB.Driver;
using Npgsql;

namespace Demo.Api.Seed;

/// <summary>
/// A SHA-256 of a dataset, lower-case hex, the same for the generated rows and for what a database stores:
/// <see cref="Of"/> of the generator's rows equals <see cref="OfPostgresAsync"/> and <see cref="OfMongoAsync"/> after a seed.
/// <see cref="SeedCommand"/> prints it as a line <c>Checksum: &lt;hex&gt;</c> after the targets ran.
/// </summary>
public static class SeedChecksum
{
    private const string Null = "\\N";

    // One line per row, in id order, fields joined by '|': the same text whatever the store, so only the values count.
    public static string Of(IReadOnlyList<OrderRow> rows)
    {
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        foreach (var row in rows.OrderBy(row => row.Id))
        {
            Append(hash, row.Id, row.OrderNo, row.Customer, row.Country, row.Category, row.Status, row.Amount, row.Quantity,
                row.OrderedAt, row.ShippedOn?.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture), row.IsPriority);
        }

        return Convert.ToHexStringLower(hash.GetHashAndReset());
    }

    public static async Task<string> OfPostgresAsync(string connectionString)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync();
        await using var command = new NpgsqlCommand(
            "SELECT id, order_no, customer, country, category, status, amount, quantity, ordered_at, shipped_on, is_priority FROM orders ORDER BY id",
            connection);
        await using var reader = await command.ExecuteReaderAsync();
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        while (await reader.ReadAsync())
        {
            Append(hash, reader.GetInt64(0), reader.GetString(1), Nullable<string>(reader, 2), Nullable<string>(reader, 3),
                Nullable<string>(reader, 4), reader.GetString(5), reader.IsDBNull(6) ? null : reader.GetDecimal(6),
                reader.IsDBNull(7) ? null : reader.GetInt64(7), reader.GetFieldValue<DateTime>(8),
                reader.IsDBNull(9) ? null : reader.GetFieldValue<DateOnly>(9).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                reader.GetBoolean(10));
        }

        return Convert.ToHexStringLower(hash.GetHashAndReset());
    }

    public static async Task<string> OfMongoAsync(string connectionString)
    {
        var collection = new MongoClient(connectionString).GetDatabase(DemoSettings.MongoDatabase).GetCollection<BsonDocument>("orders");
        using var cursor = await collection.Find(FilterDefinition<BsonDocument>.Empty).Sort(Builders<BsonDocument>.Sort.Ascending("_id")).ToCursorAsync();
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        while (await cursor.MoveNextAsync())
        {
            foreach (var document in cursor.Current)
            {
                Append(hash, document["_id"].ToInt64(), document["orderNo"].AsString, Text(document, "customer"), Text(document, "country"),
                    Text(document, "category"), document["status"].AsString,
                    document["amount"].IsBsonNull ? null : document["amount"].AsDecimal,
                    document["quantity"].IsBsonNull ? null : document["quantity"].ToInt64(),
                    document["orderedAt"].ToUniversalTime(), Text(document, "shippedOn"), document["isPriority"].AsBoolean);
            }
        }

        return Convert.ToHexStringLower(hash.GetHashAndReset());
    }

    private static T? Nullable<T>(NpgsqlDataReader reader, int ordinal) where T : class =>
        reader.IsDBNull(ordinal) ? null : reader.GetFieldValue<T>(ordinal);

    private static string? Text(BsonDocument document, string name) =>
        document[name].IsBsonNull ? null : document[name].AsString;

    private static void Append(
        IncrementalHash hash, long id, string orderNo, string? customer, string? country, string? category, string status,
        decimal? amount, long? quantity, DateTime orderedAt, string? shippedOn, bool isPriority)
    {
        var utc = orderedAt.Kind == DateTimeKind.Unspecified ? DateTime.SpecifyKind(orderedAt, DateTimeKind.Utc) : orderedAt.ToUniversalTime();
        var fields = new[]
        {
            id.ToString(CultureInfo.InvariantCulture),
            Escape(orderNo),
            Escape(customer),
            Escape(country),
            Escape(category),
            Escape(status),
            amount?.ToString("0.00", CultureInfo.InvariantCulture) ?? Null,
            quantity?.ToString(CultureInfo.InvariantCulture) ?? Null,
            new DateTimeOffset(utc).ToUnixTimeMilliseconds().ToString(CultureInfo.InvariantCulture),
            shippedOn ?? Null,
            isPriority ? "1" : "0"
        };
        hash.AppendData(Encoding.UTF8.GetBytes(string.Join('|', fields) + "\n"));
    }

    private static string Escape(string? value) =>
        value is null ? Null : value.Replace("\\", "\\\\").Replace("|", "\\|").Replace("\n", "\\n");
}
