using System.Data;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Sql;
using Dapper;

namespace Craticula.Dapper;

/// <summary>
/// The <b>grid</b> entry point: one page of rows for an AG Grid SSRM block, optionally with the
/// filtered total — <see cref="SqlQueryBuilder.Build"/>'s <c>{sql, params[]}</c> executed via Dapper
/// against an already-open <see cref="IDbConnection"/> the host owns (connection
/// pooling/transactions/retry are not this package's concern — see this project's own remarks).
///
/// <para><b>Grouping/aggregation need NO special handling here.</b> Unlike
/// <c>Craticula.EntityFrameworkCore.EfCoreGridQuery</c> (which re-derives a <c>GROUP BY</c> itself via
/// <c>GroupingPlan.Resolve</c>, because it never produces SQL text at all), this method just executes
/// whatever SQL <see cref="SqlQueryBuilder.Build"/> already emits — that compiler already fully handles
/// grouped/aggregated/drill-down requests internally (BM-2). <see cref="DapperGridPage.Columns"/> is
/// read directly off the executed reader's OWN column names rather than computed from
/// <see cref="GroupSpec"/>/<see cref="Aggregation"/>, so nothing here decides whether a request is
/// grouped, drilled down, or plain — it only decides how wide a row is and what each cell is CALLED,
/// both of which the compiled statement itself already answers.</para>
///
/// <para><b>The one place this method still reads the request's own shape: which schema
/// <see cref="FieldType"/> a column materializes as.</b> The compiled statement's column names are
/// either a real field's logical colId (the group column, or an ordinary/leaf row's own field) — looked
/// up in <see cref="GridSchema.Fields"/> directly — or an aggregation's
/// <see cref="Aggregation.OutputName"/> (<c>amount_sum</c>), which is never a schema field and falls
/// back to <see cref="SqlQueryRequest.Aggregations"/>, matched by POSITION (GRP-3 always renders
/// <c>[groupColumn, ...aggregations]</c> in that order). This reads the request's own already-resolved
/// data to label a result correctly; it does not re-decide how the SQL was built, which is the
/// distinction this package's plan draws.</para>
/// </summary>
public static class DapperGridQuery
{
    /// <summary>The row window this package compiles a count query with — large enough to never bound a
    /// real result, and present ONLY so that wrapping the compiled statement's own <c>ORDER BY</c> in a
    /// derived table is legal SQL on every dialect: SQL Server specifically REJECTS an <c>ORDER BY</c>
    /// inside a derived table/subquery unless it also carries <c>TOP</c>/<c>OFFSET</c>/<c>FOR XML</c>,
    /// and <see cref="SqlQueryBuilder.Build"/> always renders a trailing <c>ORDER BY</c> (SEM-6
    /// guarantees at least one key). The ordering itself is wasted work for a count — the same point
    /// <c>EfCoreGridQuery</c>'s own count query makes — but <c>Craticula.Sql</c> has no public
    /// "just the WHERE clause" primitive to avoid it.</summary>
    private const int CountRowWindow = int.MaxValue;

    /// <summary>
    /// Compiles and executes one grid page: filter, order, row window, projection — whatever shape
    /// <see cref="SqlQueryBuilder.Build"/> resolves <paramref name="request"/> to.
    /// </summary>
    /// <param name="connection">An already-open connection. Never opened or closed here.</param>
    /// <param name="request">The validated IR — the same shape <see cref="SqlQueryBuilder.Build"/>
    /// itself accepts, since this method's whole job is executing what that compiler produces.</param>
    /// <param name="dialect">The target engine's rendering rules.</param>
    /// <param name="includeRowCount">Whether to also run the count query
    /// (<see cref="DapperGridPage.RowCount"/>). Defaults to <see langword="false"/>: it is a second
    /// round trip, and a grid needs the total once per filter change rather than once per block.</param>
    /// <param name="cancellationToken">EXP-7's cancellation hook, observed by both queries.</param>
    public static async Task<DapperGridPage> FetchPageAsync(
        IDbConnection connection,
        SqlQueryRequest request,
        ISqlDialect dialect,
        bool includeRowCount = false,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(connection);
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(dialect);

        // PG-5: every row is read by streaming; a paged call never loads the whole result.
        if (request.Page is NonePage)
        {
            throw new DapperCompilationException(
                "FetchPageAsync returns one window of rows and refuses EXP-2's unpaginated page, which would load " +
                "every row into memory (PG-5). Read every row with DapperExportStream.StreamAsync.");
        }

        var query = SqlQueryBuilder.Build(WithExplicitProjection(request), dialect);
        var (sql, parameters) = DapperParameterBinder.Prepare(query);

        var columns = new List<string>();
        var rows = new List<IReadOnlyList<object?>>();

        var command = new CommandDefinition(sql, parameters, cancellationToken: cancellationToken);
        using (var reader = await connection.ExecuteReaderAsync(command).ConfigureAwait(false))
        {
            for (var index = 0; index < reader.FieldCount; index++)
            {
                columns.Add(reader.GetName(index));
            }

            var types = ResolveColumnTypes(columns, request.Schema, request.Aggregations);

            while (await ReadRowAsync(reader, cancellationToken).ConfigureAwait(false))
            {
                var cells = new object?[columns.Count];
                for (var index = 0; index < columns.Count; index++)
                {
                    cells[index] = DapperValueReader.Read(reader, index, types[index]);
                }

                rows.Add(cells);
            }
        }

        var rowCount = includeRowCount
            ? await CountAsync(connection, request, dialect, cancellationToken).ConfigureAwait(false)
            : (long?)null;

        return new DapperGridPage { Columns = columns, Rows = rows, RowCount = rowCount };
    }

    /// <summary>
    /// The filtered row count on its own — the same query <see cref="FetchPageAsync"/> runs when asked,
    /// exposed so that asking for it separately cannot mean asking a different question. For a grouped
    /// level this is the BUCKET count, automatically: see this type's own remarks.
    ///
    /// <para><b>How, given <c>Craticula.Sql</c> exposes no count-mode build.</b> The request is
    /// recompiled with a huge <see cref="RangePage"/> (see <see cref="CountRowWindow"/>) and wrapped as
    /// <c>SELECT COUNT(*) FROM (&lt;compiled statement&gt;) craticula_count</c> — no <c>AS</c> before
    /// the derived-table alias, deliberately: Oracle's grammar does not accept one there (only before a
    /// COLUMN alias), while every other dialect this compiler targets accepts a bare alias too, so
    /// omitting it is the one spelling that is simultaneously correct SQL everywhere rather than correct
    /// on four dialects out of five.</para>
    /// </summary>
    public static async Task<long> CountAsync(
        IDbConnection connection,
        SqlQueryRequest request,
        ISqlDialect dialect,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(connection);
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(dialect);

        var inner = SqlQueryBuilder.Build(
            request with { Page = new RangePage { StartRow = 0, EndRow = CountRowWindow } }, dialect);
        var wrapped = inner with { Sql = $"SELECT COUNT(*) FROM ({inner.Sql}) craticula_count" };

        var (sql, parameters) = DapperParameterBinder.Prepare(wrapped);
        var command = new CommandDefinition(sql, parameters, cancellationToken: cancellationToken);

        return await connection.ExecuteScalarAsync<long>(command).ConfigureAwait(false);
    }

    /// <summary>
    /// Forces an EXPLICIT projection when the request has neither a <see cref="GroupSpec"/> nor its own
    /// <see cref="SqlQueryRequest.Projection"/> — the ordinary, unprojected grid page.
    ///
    /// <para><b>Why: <see cref="SqlQueryBuilder"/>'s <c>SELECT *</c> is a physical-column shape.</b>
    /// GRP-3 renders bare <c>*</c> for exactly this case (no group state, no export projection), and
    /// <c>*</c> hands back PHYSICAL column names — a schema whose <c>fiscalYear</c> lives in
    /// <c>fiscal_year</c> would otherwise give this package's caller a reader column it cannot map back
    /// to the logical colId the grid asked for. Every other branch of <c>RenderProjection</c> (a grouped
    /// level, a drill-down leaf, an explicit export projection) already emits an aliased column list
    /// under the LOGICAL name, so only this one case needs forcing.</para>
    /// </summary>
    private static SqlQueryRequest WithExplicitProjection(SqlQueryRequest request) =>
        request.Group is null && request.Projection is null
            ? request with { Projection = request.Schema.FieldOrder }
            : request;

    /// <summary>
    /// Which <see cref="FieldType"/> each of <paramref name="columns"/> materializes as: a real schema
    /// field's own declared type, or — for a column that is not one (an aggregate's output name) —
    /// the aggregation at the matching POSITION in <paramref name="aggregations"/>, resolved per
    /// <see cref="ResolveAggregationType"/>. See this type's own remarks for why position, not name, is
    /// what resolves it.
    /// </summary>
    private static FieldType[] ResolveColumnTypes(
        IReadOnlyList<string> columns, GridSchema schema, IReadOnlyList<Aggregation>? aggregations)
    {
        var types = new FieldType[columns.Count];

        for (var index = 0; index < columns.Count; index++)
        {
            if (schema.Fields.TryGetValue(columns[index], out var field))
            {
                types[index] = field.Type;
                continue;
            }

            // Not a declared field: GRP-3 renders [groupColumn, ...aggregations], so the group column
            // (index 0) is always found above and every later, unmatched column is an aggregate at
            // aggregations[index - 1].
            var aggregationIndex = index - 1;
            if (aggregations is null || aggregationIndex < 0 || aggregationIndex >= aggregations.Count)
            {
                throw new DapperCompilationException(
                    $"Column '{columns[index]}' at position {index} is neither a declared schema field nor a " +
                    "resolvable aggregation output — the compiled statement's own shape disagrees with the " +
                    "request that produced it.");
            }

            types[index] = ResolveAggregationType(aggregations[aggregationIndex], schema);
        }

        return types;
    }

    /// <summary>
    /// AGG-1's rule for <see cref="AggregationFunc.Count"/> (always an integer) plus one more this
    /// package's own review found: <see cref="AggregationFunc.Avg"/> does NOT keep the source field's
    /// declared type the way <c>sum</c>/<c>min</c>/<c>max</c> genuinely do. Postgres/MySQL/SQLite's
    /// <c>AVG()</c> over an integer or floating column returns a fractional result — reading it back as
    /// <see cref="FieldType.Int64"/> would run <see cref="DapperValueReader"/>'s
    /// <c>Convert.ToInt64</c> on a real average and silently truncate it (measured:
    /// <c>spec/fixtures/dialect-parity/024</c> is exactly this shape, <c>avg</c> over an
    /// <see cref="FieldType.Int64"/> column). Widened to <see cref="FieldType.Double"/> rather than the
    /// source type for every non-<see cref="FieldType.Decimal"/> source, since a decimal source's own
    /// precision is worth preserving and every other numeric source already loses no meaningful
    /// precision going through <see cref="double"/>.
    ///
    /// <para><b>Residual, NOT closed by this widening: SQL Server truncates <c>AVG(bigint)</c> to
    /// <c>bigint</c> at the ENGINE itself</b> (T-SQL's own numeric-promotion rule for exact types,
    /// unlike Postgres/MySQL/SQLite, which all promote to a fractional result). Reading the mssql
    /// result as <see cref="FieldType.Double"/> changes nothing there — the value handed to Dapper is
    /// already the truncated one, and this package has no SQL text of its own to add a <c>CAST</c> to;
    /// that fix belongs in <c>Craticula.Sql</c>'s own aggregation rendering, which is shared by every
    /// SQL-executing consumer, not this one adapter's read-back step. Recorded rather than hidden: this
    /// widening closes the defect on 4 of 5 dialects, not silently on all 5.</para>
    /// </summary>
    private static FieldType ResolveAggregationType(Aggregation aggregation, GridSchema schema)
    {
        if (aggregation.Func == AggregationFunc.Count)
        {
            return FieldType.Int64;
        }

        var sourceType = schema.Fields[aggregation.Field].Type;
        return aggregation.Func == AggregationFunc.Avg && sourceType != FieldType.Decimal
            ? FieldType.Double
            : sourceType;
    }

    /// <summary>
    /// Pulls the next row asynchronously when the underlying reader supports it
    /// (<see cref="System.Data.Common.DbDataReader"/>, which every provider this package has been
    /// measured against returns), falling back to a synchronous <see cref="IDataReader.Read"/>
    /// otherwise — <c>Dapper.SqlMapper.ExecuteReaderAsync</c>'s own return type is the classic
    /// <see cref="IDataReader"/> interface, not the richer async-capable base class, so this package
    /// cannot assume the richer shape without checking.
    /// </summary>
    internal static Task<bool> ReadRowAsync(IDataReader reader, CancellationToken cancellationToken) =>
        reader is System.Data.Common.DbDataReader dbReader
            ? dbReader.ReadAsync(cancellationToken)
            : Task.FromResult(reader.Read());
}
