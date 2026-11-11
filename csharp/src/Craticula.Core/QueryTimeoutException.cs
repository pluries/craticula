namespace Craticula.Core;

/// <summary>
/// TL-5 (query time limit, #3794): the engine ran out of the host's maximum query time. The execution
/// adapters throw this one type: MongoDB's "maximum time expired" error (code 50) and a Search
/// response whose <c>timed_out</c> is true both become a <see cref="QueryTimeoutException"/>, so a host
/// catches it once. The message names no query text; the engine's own error is kept as the inner
/// exception for a host's log, never echoed to a caller.
/// </summary>
public sealed class QueryTimeoutException : Exception
{
    /// <summary>The error kind a host reports to its client (the demo answers 504 with it).</summary>
    public const string ErrorKind = "query-timeout";

    private const string Text = "The query ran longer than the configured maximum query time and was cancelled.";

    public QueryTimeoutException()
        : base(Text)
    {
    }

    public QueryTimeoutException(Exception? innerException)
        : base(Text, innerException)
    {
    }

    /// <summary>Always <see cref="ErrorKind"/>.</summary>
    public string Kind => ErrorKind;
}
