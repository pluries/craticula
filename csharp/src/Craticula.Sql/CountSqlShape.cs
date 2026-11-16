namespace Craticula.Sql;

/// <summary>
/// CNT-5's fixed spelling for a grouped count's derived table. Lives outside
/// <see cref="SqlQueryBuilder"/> because <c>DialectIndependenceTests</c> bans the lowercase
/// product name from that file's executable source (it is also a collation name there).
/// </summary>
internal static class CountSqlShape
{
    internal const string DerivedTableAlias = "craticula_count";
}
