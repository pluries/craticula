namespace Craticula.AgGrid;

/// <summary>
/// AG-1/AG-5: thrown by <see cref="AgGridRequestParser.Parse"/> when an AG Grid SSRM request's wire
/// shape cannot be turned into a candidate IR document at all — distinct from every
/// <c>Craticula.Core.Ir</c>/<c>Craticula.Core.Schema</c> validation exception, which reports a
/// well-formed-but-invalid IR document; this one means the request never became IR in the first
/// place. Matches <c>spec/fixtures/schemas/rejection.schema.json</c>'s <c>requestParsing</c> stage,
/// which per that schema's own description "covers malformed-wire-shape cases that never reach IR
/// validation at all" (listed last in that enum only because it is requestParsing's catch-all, even
/// though it conceptually runs first).
///
/// <para><see cref="Reason"/> is one of the two <c>requestParsing</c>-stage reason codes from
/// <c>rejection.schema.json</c>'s own closed set: <c>"unknown-operator"</c> (a <c>filterType</c>,
/// condition <c>type</c>, or <c>aggFunc</c> outside this adapter's closed vocabulary — covers AR-6's
/// operator set, AG-2's date presets, and AG Grid's native <c>inRange</c>, which carries no
/// inclusivity flags), or <c>"malformed-request"</c> (the JSON shape itself doesn't conform to the
/// wire contract this adapter parses — a filter value sent as an object/array instead of a scalar, a
/// null array element where an object is required, an unsupported envelope such as
/// <c>pivotMode:true</c> or the <c>setValuesRequest</c> envelope, ...).</para>
/// </summary>
public sealed class AgGridRequestParseException(
    string reason,
    string message,
    Exception? innerException = null,
    string rejectedAt = AgGridRequestParseException.ParsingStage,
    string? rejectionReason = null)
    : Exception(message, innerException)
{
    /// <summary>The stage of a failure that never reached IR validation.</summary>
    public const string ParsingStage = "requestParsing";

    public string Reason { get; } = reason;

    /// <summary>
    /// The validation stage the conformance oracle (<c>rejection.schema.json</c>'s <c>rejectedAt</c>) names for this
    /// refusal: <c>requestParsing</c>, or <c>typeCoercion</c> for a value the adapter could not turn into the type the
    /// request implies (an unparseable date text).
    /// </summary>
    public string RejectedAt { get; } = rejectedAt;

    /// <summary>The oracle's <c>reason</c> for this refusal; equal to <see cref="Reason"/> unless the stage says more.</summary>
    public string RejectionReason { get; } = rejectionReason ?? reason;
}
