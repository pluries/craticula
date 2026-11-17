using Craticula.Integration.Tests.Docker;

namespace Craticula.Integration.Tests.Containers.Sql;

// SC-2 of story #3863 on every engine the execution-equality tier runs: the count equals the number of rows the same request
// returns without a window. Same collections, so each engine's container is shared with the XEQ tests.

/// <summary>PostgreSQL 16.</summary>
[Collection(PostgresCollection.Name)]
public class PostgresCountParityTests(PostgresEngine engine)
{
    public static TheoryData<string> Fixtures() => SqlExecutionRunner.TypedFixturesFor("postgres");

    [DockerTheory]
    [MemberData(nameof(Fixtures))]
    public Task Count_Equals_The_Unpaged_Rows_On_Postgres(string name) => SqlExecutionRunner.AssertCountEqualsUnpagedRowsAsync(engine, name);
}

/// <summary>SQL Server 2022.</summary>
[Collection(MssqlCollection.Name)]
public class MssqlCountParityTests(MssqlEngine engine)
{
    public static TheoryData<string> Fixtures() => SqlExecutionRunner.TypedFixturesFor("mssql");

    [DockerTheory]
    [MemberData(nameof(Fixtures))]
    public Task Count_Equals_The_Unpaged_Rows_On_Mssql(string name) => SqlExecutionRunner.AssertCountEqualsUnpagedRowsAsync(engine, name);
}

/// <summary>MySQL 8.4.</summary>
[Collection(MySqlCollection.Name)]
public class MySqlCountParityTests(MySqlEngine engine)
{
    public static TheoryData<string> Fixtures() => SqlExecutionRunner.TypedFixturesFor("mysql");

    [DockerTheory]
    [MemberData(nameof(Fixtures))]
    public Task Count_Equals_The_Unpaged_Rows_On_MySql(string name) => SqlExecutionRunner.AssertCountEqualsUnpagedRowsAsync(engine, name);
}

/// <summary>Oracle Database Free 23ai.</summary>
[Collection(OracleCollection.Name)]
public class OracleCountParityTests(OracleEngine engine)
{
    public static TheoryData<string> Fixtures() => SqlExecutionRunner.TypedFixturesFor("oracle");

    [DockerTheory]
    [MemberData(nameof(Fixtures))]
    public Task Count_Equals_The_Unpaged_Rows_On_Oracle(string name) => SqlExecutionRunner.AssertCountEqualsUnpagedRowsAsync(engine, name);
}

/// <summary>SQLite, in-process.</summary>
[Collection(SqliteCollection.Name)]
public class SqliteCountParityTests(SqliteEngine engine)
{
    public static TheoryData<string> Fixtures() => SqlExecutionRunner.TypedFixturesFor("sqlite");

    [Theory]
    [MemberData(nameof(Fixtures))]
    public Task Count_Equals_The_Unpaged_Rows_On_Sqlite(string name) => SqlExecutionRunner.AssertCountEqualsUnpagedRowsAsync(engine, name);
}
