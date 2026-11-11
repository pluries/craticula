namespace Craticula.Core.Schema;

/// <summary>
/// SEC-3: host-configurable resource ceilings enforced by <see cref="ResourceLimitsValidator"/>
/// over an IR filter tree and page spec. All six are plain, non-nullable <see cref="int"/>
/// properties with SEC-3's own defaults — by design there is no way to express "no limit" here
/// (SEC-3: "none unlimited"). Each <c>init</c> accessor additionally rejects non-positive values:
/// a limit of 0 or less is not "no limit", it is a silent denial-of-service (every request,
/// however small, would exceed it) — a plausible outcome of a config binder mapping an absent or
/// blank configuration key to the type's default. There is no upper-bound check: SEC-3 forbids the
/// nullable-"unlimited" sentinel, not a host's own choice to set a very large positive number.
/// </summary>
public sealed record ResourceLimits
{
    private readonly int _maxDepth = 8;
    private readonly int _maxLeaves = 64;
    private readonly int _maxInValues = 1000;
    private readonly int _maxPageSize = 1000;
    private readonly int _maxSetValuesResults = 10000;
    private readonly int _defaultSetValuesResults = 1000;
    private readonly int? _maxQueryTimeMs;

    /// <summary>Max filter tree depth, root node = depth 1 (SEC-3 default: 8).</summary>
    public int MaxDepth
    {
        get => _maxDepth;
        init => _maxDepth = RequirePositive(value, nameof(MaxDepth));
    }

    /// <summary>Max tree-wide leaf comparison count, summed across every branch (SEC-3 default: 64).</summary>
    public int MaxLeaves
    {
        get => _maxLeaves;
        init => _maxLeaves = RequirePositive(value, nameof(MaxLeaves));
    }

    /// <summary>Max values in a single <c>in</c>/<c>notIn</c> set comparison (SEC-3 default: 1000).</summary>
    public int MaxInValues
    {
        get => _maxInValues;
        init => _maxInValues = RequirePositive(value, nameof(MaxInValues));
    }

    /// <summary>Max requested page size, i.e. (endRow - startRow) on a <c>RangePage</c> (SEC-3 default: 1000).</summary>
    public int MaxPageSize
    {
        get => _maxPageSize;
        init => _maxPageSize = RequirePositive(value, nameof(MaxPageSize));
    }

    /// <summary>
    /// Caps BM-3's distinct-values query row limit — a compiled query's own result size, not an input
    /// shape to reject, so unlike the other four limits <see cref="ResourceLimitsValidator.Validate"/>
    /// does not check this one; it is consumed by
    /// <see cref="ResourceLimitsValidator.ResolveSetValuesLimit"/>, which clamps whatever the client
    /// asked for to it (SEC-3 default: 10000).
    /// </summary>
    public int MaxSetValuesResults
    {
        get => _maxSetValuesResults;
        init => _maxSetValuesResults = RequirePositive(value, nameof(MaxSetValuesResults));
    }

    /// <summary>
    /// GRP-6: the cap applied when a <see cref="Ir.SetValuesSpec"/> requests none of its own
    /// (default: 1000). A distinct-values query is <em>never</em> unbounded — a set filter over a
    /// high-cardinality column would otherwise stream the whole column into a dropdown — so "the
    /// client asked for no limit" resolves to this, not to infinity.
    ///
    /// <para>Deliberately a <b>separate</b> knob from <see cref="MaxSetValuesResults"/> rather than
    /// reusing it as the default: the two answer different questions (what a quiet client gets versus
    /// what the loudest one may ever get), and a host that raises the ceiling for an explicit
    /// power-user request has not thereby agreed to send ten thousand values to every set filter that
    /// opens. No ordering between them is enforced here — <see cref="ResourceLimitsValidator.ResolveSetValuesLimit"/>
    /// takes the minimum, so a host configuring a default above its own maximum still gets the
    /// maximum rather than a validation error at construction time.</para>
    /// </summary>
    public int DefaultSetValuesResults
    {
        get => _defaultSetValuesResults;
        init => _defaultSetValuesResults = RequirePositive(value, nameof(DefaultSetValuesResults));
    }

    /// <summary>
    /// TL-4 (query time limit, #3794): the maximum time, in milliseconds, a MongoDB or Search query may
    /// run. <b>The one limit that is unset by default</b> (<see langword="null"/>), a recorded deviation
    /// from SEC-3's "none unlimited": the six limits above bound the <em>shape</em> of a request, and the
    /// library cannot know how slow a host's database is, so a default would be a guess. When set, the
    /// MongoDB compiler adds <c>maxTimeMS</c> and the Search compiler <c>timeout</c> to the artifact;
    /// without it every artifact is what it was. A set value must be a whole number from 1 to
    /// <see cref="int.MaxValue"/> (2,147,483,647: what the engines hold); the type already excludes a
    /// fraction and a larger number. It comes only from the host: no request member sets it.
    /// </summary>
    public int? MaxQueryTimeMs
    {
        get => _maxQueryTimeMs;
        init => _maxQueryTimeMs = value is null ? null : RequirePositive(value.Value, nameof(MaxQueryTimeMs));
    }

    private static int RequirePositive(int value, string paramName) => value > 0
        ? value
        : throw new ArgumentOutOfRangeException(paramName, value, $"{paramName} must be a positive integer — SEC-3 requires every limit configurable but none unlimited, and a value <= 0 would reject every request regardless of size.");
}
