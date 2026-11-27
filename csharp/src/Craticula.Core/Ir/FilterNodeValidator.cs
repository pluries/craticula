namespace Craticula.Core.Ir;

/// <summary>
/// Enforces the structural invariants of <c>spec/ir.schema.json</c>'s <c>$defs/filterNode</c> and
/// <c>$defs/typedValue</c> that <see cref="ComparisonNode"/>'s "one record, nullable slots"
/// flattening of the schema's 4-way <c>oneOf</c> cannot express on its own (see that type's own XML
/// doc for why the flattening exists). Without this, e.g. <c>{"op":"eq"}</c> with no <c>value</c>,
/// or <c>{"op":"in","value":{...}}</c> using the singular slot, deserialize successfully into a
/// <see cref="ComparisonNode"/> no compiler can render — this is the gate that catches that before
/// any compiler (or <see cref="Craticula.Core.Schema.ResourceLimitsValidator"/>) ever sees the tree.
/// </summary>
public static class FilterNodeValidator
{
    /// <summary>
    /// Validates <paramref name="root"/> (and every descendant) against
    /// <c>ir.schema.json</c>'s structural invariants. A <see langword="null"/> root (no filter at
    /// all) is valid — there is nothing to check. Throws <see cref="FilterNodeValidationException"/>
    /// naming every violation found, not just the first.
    /// </summary>
    public static void Validate(FilterNode? root)
    {
        if (root is null)
        {
            return;
        }

        var errors = new List<string>();
        ValidateNode(root, errors);

        if (errors.Count > 0)
        {
            throw new FilterNodeValidationException(errors);
        }
    }

    private static void ValidateNode(FilterNode? node, List<string> errors)
    {
        switch (node)
        {
            case null:
                // Reachable from a null element inside an AndNode/OrNode.Nodes array —
                // RespectNullableAnnotations guards non-nullable *properties*, not collection
                // *elements*, so this must be checked explicitly rather than relying on
                // deserialization to have already rejected it (SEC-6: clean rejection, not an NRE).
                errors.Add("filter tree contains a null node.");
                return;

            case CompositeFilterNode composite:
                if (composite.Nodes.Count == 0)
                {
                    errors.Add($"{composite.GetType().Name}.nodes must not be empty (ir.schema.json minItems:1).");
                }

                foreach (var child in composite.Nodes)
                {
                    ValidateNode(child, errors);
                }

                return;

            case NotNode not:
                ValidateNode(not.Node, errors);
                return;

            case ComparisonNode comparison:
                ValidateComparison(comparison, errors);
                return;

            default:
                errors.Add($"Unrecognized filter node type '{node.GetType().Name}'.");
                return;
        }
    }

    private static void ValidateComparison(ComparisonNode node, List<string> errors)
    {
        if (string.IsNullOrEmpty(node.Field))
        {
            errors.Add($"comparison field must not be blank (op '{node.Op}').");
        }
        else if (node.Field.Length > 256)
        {
            errors.Add($"comparison field '{node.Field[..32]}...' exceeds the 256-character limit (ir.schema.json fieldName.maxLength).");
        }

        switch (Category(node.Op))
        {
            case OperatorCategory.Unary:
                RequireAbsent(node, errors, value: true, values: true, from: true, to: true, inclusivity: true);
                break;

            case OperatorCategory.Binary:
                RequirePresent(node.Value, errors, $"op '{node.Op}' requires 'value'.");
                RequireAbsent(node, errors, value: false, values: true, from: true, to: true, inclusivity: true);
                if (node.Value is not null)
                {
                    ValidateTypedValue(node.Value, errors);
                }

                break;

            case OperatorCategory.Set:
                // SEM-8: an empty list is valid (in [] matches no row, notIn [] every row); only a missing array is not.
                if (node.Values is null)
                {
                    errors.Add($"op '{node.Op}' requires a 'values' array.");
                }
                else
                {
                    foreach (var value in node.Values)
                    {
                        if (value is null)
                        {
                            errors.Add($"op '{node.Op}' has a null element in 'values'.");
                        }
                        else
                        {
                            ValidateTypedValue(value, errors);
                        }
                    }
                }

                RequireAbsent(node, errors, value: true, values: false, from: true, to: true, inclusivity: true);
                break;

            case OperatorCategory.Range:
                RequirePresent(node.From, errors, "'inRange' requires 'from'.");
                RequirePresent(node.To, errors, "'inRange' requires 'to'.");
                if (node.FromInclusive is null)
                {
                    errors.Add("'inRange' requires 'fromInclusive' (SEM-4: never left implicit).");
                }

                if (node.ToInclusive is null)
                {
                    errors.Add("'inRange' requires 'toInclusive' (SEM-4: never left implicit).");
                }

                RequireAbsent(node, errors, value: true, values: true, from: false, to: false, inclusivity: false);
                if (node.From is not null)
                {
                    ValidateTypedValue(node.From, errors);
                }

                if (node.To is not null)
                {
                    ValidateTypedValue(node.To, errors);
                }

                break;
        }
    }

    private static void RequirePresent(TypedValue? value, List<string> errors, string message)
    {
        if (value is null)
        {
            errors.Add(message);
        }
    }

    private static void RequireAbsent(
        ComparisonNode node, List<string> errors, bool value, bool values, bool from, bool to, bool inclusivity)
    {
        if (value && node.Value is not null)
        {
            errors.Add($"op '{node.Op}' must not set 'value'.");
        }

        if (values && node.Values is not null)
        {
            errors.Add($"op '{node.Op}' must not set 'values'.");
        }

        if (from && node.From is not null)
        {
            errors.Add($"op '{node.Op}' must not set 'from'.");
        }

        if (to && node.To is not null)
        {
            errors.Add($"op '{node.Op}' must not set 'to'.");
        }

        if (inclusivity && (node.FromInclusive is not null || node.ToInclusive is not null))
        {
            errors.Add($"op '{node.Op}' must not set 'fromInclusive'/'toInclusive'.");
        }
    }

    private enum OperatorCategory
    {
        Unary,
        Binary,
        Set,
        Range
    }

    private static OperatorCategory Category(ComparisonOperator op) => op switch
    {
        ComparisonOperator.Blank or ComparisonOperator.NotBlank or ComparisonOperator.True or ComparisonOperator.False
            => OperatorCategory.Unary,
        ComparisonOperator.In or ComparisonOperator.NotIn => OperatorCategory.Set,
        ComparisonOperator.InRange => OperatorCategory.Range,
        _ => OperatorCategory.Binary
    };

    private static void ValidateTypedValue(TypedValue value, List<string> errors)
    {
        switch (value)
        {
            case StringValue s when s.Value.Length > 8192:
                errors.Add("stringValue.value exceeds the 8192-character limit (ir.schema.json maxLength).");
                break;

            case DecimalValue d when !DecimalPattern.IsMatch(d.Value) || d.Value.Length > 128:
                errors.Add($"decimalValue.value '{Truncate(d.Value)}' does not match ir.schema.json's numeric-string pattern or exceeds 128 characters.");
                break;

            case DateValue dt when !DatePattern.IsMatch(dt.Value):
                errors.Add($"dateValue.value '{Truncate(dt.Value)}' does not match ir.schema.json's YYYY-MM-DD pattern.");
                break;

            case DatetimeValue dtv:
                if (!DatetimePattern.IsMatch(dtv.Value))
                {
                    errors.Add($"datetimeValue.value '{Truncate(dtv.Value)}' does not match ir.schema.json's ISO-8601 instant pattern.");
                }

                if (!IsIanaZoneIdShape(dtv.Zone))
                {
                    errors.Add($"datetimeValue.zone '{Truncate(dtv.Zone)}' does not match ir.schema.json's IANA-zone-id shape.");
                }

                break;
        }
    }

    /// <summary>
    /// Whether <paramref name="zone"/> has the shape <c>ir.schema.json</c> requires of a
    /// <c>datetimeValue.zone</c> (an IANA zone id: 1-64 characters matching
    /// <c>^[A-Za-z0-9_+-]+(/[A-Za-z0-9_+-]+)*$</c>). Public — not merely the private check inlined
    /// above — because an adapter that RESOLVES a zone id from untrusted input needs the identical
    /// rule at its own boundary, to reject cleanly there rather than letting a bad id travel to
    /// <see cref="Validate"/> and surface as a structural-invariant failure. Sharing the one rule
    /// (rather than each caller keeping a copy of the pattern) is what keeps it from drifting from
    /// <c>ir.schema.json</c>.
    ///
    /// <para>Shape only: this says nothing about whether the id names a zone the host can actually
    /// resolve, nor whether it is a real IANA id rather than a platform alias — notably
    /// <c>localtime</c>, <c>Factory</c> and <c>posixrules</c> all satisfy this shape but are tzdata
    /// implementation artifacts, not zones (and <c>localtime</c> resolves to whatever the server
    /// process is configured for, which SEM-4 forbids as a zone source). A caller resolving
    /// untrusted input must reject those separately.</para>
    /// </summary>
    public static bool IsIanaZoneIdShape(string zone) =>
        zone.Length is > 0 and <= 64 && ZonePattern.IsMatch(zone);

    /// <summary>
    /// Whether <paramref name="raw"/> is an ISO-8601 instant as <c>ir.schema.json</c> requires of a
    /// <c>datetimeValue.value</c> (a date, a time, and a trailing <c>Z</c> or an explicit offset) and a real
    /// instant (month 13 or <c>T24:00</c> is refused). Public for the same reason as
    /// <see cref="IsIanaZoneIdShape"/>: an adapter that must decide whether a wire string is already an instant
    /// needs the identical rule Core's own coercion applies afterwards, so the two cannot drift (Bug #2319).
    /// </summary>
    public static bool IsIsoInstant(string raw) =>
        DatetimePattern.IsMatch(raw)
        && !IsoInstant.HasHourTwentyFour(raw)
        && DateTimeOffset.TryParse(raw, System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.AssumeUniversal, out _);

    /// <summary>Internal (not private) so <see cref="Craticula.Core.Schema.TypeCoercionValidator"/>
    /// reuses the same truncation instead of duplicating it — same-assembly precedent already set by
    /// this file's regex patterns below.</summary>
    internal static string Truncate(string value) => value.Length <= 32 ? value : value[..32] + "...";

    // Patterns copied verbatim from spec/ir.schema.json — see that file for the rationale behind each.
    // internal (not private): Craticula.Core.Schema.TypeCoercionValidator (SEM-5) reuses these same
    // patterns as the shape check half of coercing a StringValue into decimal/date/datetime, rather
    // than maintaining a second copy that could drift from ir.schema.json.
    internal static readonly System.Text.RegularExpressions.Regex DecimalPattern = new(@"^-?[0-9]+(\.[0-9]+)?$");
    internal static readonly System.Text.RegularExpressions.Regex DatePattern = new(@"^[0-9]{4}-[0-9]{2}-[0-9]{2}$");
    internal static readonly System.Text.RegularExpressions.Regex DatetimePattern = new(@"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$");
    private static readonly System.Text.RegularExpressions.Regex ZonePattern = new(@"^[A-Za-z0-9_+-]+(/[A-Za-z0-9_+-]+)*$");
}
