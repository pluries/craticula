using System.Buffers;
using System.Text;
using System.Text.Json;

namespace Craticula.Conformance.Driver;

/// <summary>
/// The C# reference implementation's conformance driver: the loop of
/// <c>spec/conformance-runner.md</c> §8, speaking the JSON Lines protocol of §2 on stdin and stdout.
/// It compiles what it is sent (<see cref="RequestCompiler"/>), prints the artifact
/// (<see cref="ArtifactWriter"/>), and never reads the fixture tree or compares anything — that is
/// the runner's job (TRD T-1(a), ML-3).
///
/// <para>Run it through the runner, from the repository root, against the built assembly (a
/// <c>dotnet run</c> launcher would rebuild on every start):
/// <c>python3 conformance/run.py --driver "dotnet csharp/tools/Craticula.Conformance.Driver/bin/Debug/net10.0/Craticula.Conformance.Driver.dll"</c>.</para>
///
/// <para>stdout carries protocol lines and nothing else — raw UTF-8 without BOM, one compact JSON
/// object per line, flushed line by line; diagnostics go to stderr, which the runner passes
/// through.</para>
/// </summary>
internal static class Program
{
    /// <summary>The spec version this driver claims in its hello (§2.1). A constant:
    /// the runner echoes it without validating it, since the suite has no version number yet.</summary>
    private const string SpecVersion = "0.2.0";

    /// <summary>
    /// The envelope must never be stricter than the compiler: a request nested past the parser's own
    /// 64 levels is the parser's to refuse, as an <c>error</c> answer (§2.2), not a line this driver
    /// cannot even read. The envelope adds one level around <c>agGridRequest</c>, so it reads far
    /// deeper than the parser would.
    /// </summary>
    private static readonly JsonDocumentOptions EnvelopeOptions = new() { MaxDepth = 1_000 };

    public static int Main()
    {
        using var stdin = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false));
        using var stdout = Console.OpenStandardOutput();

        Send(stdout, Line(WriteHello));

        var lineNumber = 0;
        while (stdin.ReadLine() is { } text)
        {
            lineNumber++;
            if (string.IsNullOrWhiteSpace(text))
            {
                continue;
            }

            JsonDocument document;
            try
            {
                document = JsonDocument.Parse(text, EnvelopeOptions);
            }
            catch (JsonException e)
            {
                return Unanswerable(lineNumber, $"it is not JSON ({e.Message})");
            }

            using (document)
            {
                if (ReadId(document.RootElement) is not { } id)
                {
                    return Unanswerable(lineNumber, "it is not a JSON object with a readable string 'id'");
                }

                Send(stdout, Answer(id, document.RootElement));
            }
        }

        // §2.3: the runner closed stdin after the last answer.
        return 0;
    }

    /// <summary>
    /// The answer to one request: <c>{"id", "artifact"}</c>, or <c>{"id", "error"}</c> when anything
    /// from reading the envelope's members to writing the artifact throws. Every exception is
    /// answered, none is swallowed: for a graded case an <c>error</c> answer is a failure, never a
    /// skip (§2.2, §6), so the runner reports it with its kind and message.
    /// </summary>
    private static byte[] Answer(string id, JsonElement request)
    {
        try
        {
            var compiled = RequestCompiler.Compile(
                StringMember(request, "backend"),
                Member(request, "schema").GetRawText(),
                Member(request, "agGridRequest").GetRawText());

            return Line(writer =>
            {
                writer.WriteStartObject();
                writer.WriteString("id", id);
                writer.WritePropertyName("artifact");
                ArtifactWriter.Write(writer, compiled);
                writer.WriteEndObject();
            });
        }
        catch (Exception e)
        {
            return Line(writer => WriteError(writer, id, e));
        }
    }

    private static void WriteHello(Utf8JsonWriter writer)
    {
        writer.WriteStartObject();
        writer.WriteStartObject("hello");
        writer.WriteString("impl", "csharp");
        writer.WriteString("specVersion", SpecVersion);
        writer.WriteStartArray("backends");
        foreach (var backend in RequestCompiler.Backends)
        {
            writer.WriteStringValue(backend);
        }

        writer.WriteEndArray();
        writer.WriteEndObject();
        writer.WriteEndObject();
    }

    private static void WriteError(Utf8JsonWriter writer, string id, Exception error)
    {
        writer.WriteStartObject();
        writer.WriteString("id", id);
        writer.WriteStartObject("error");
        writer.WriteString("kind", error.GetType().Name);
        writer.WriteString("message", error.Message);
        writer.WriteEndObject();
        writer.WriteEndObject();
    }

    /// <summary>The <c>id</c> to echo, uninterpreted (§2.2), or <see langword="null"/> when the line
    /// has none to echo — the one case no answer can be written for.</summary>
    private static string? ReadId(JsonElement request)
    {
        if (request.ValueKind != JsonValueKind.Object
            || !request.TryGetProperty("id", out var id)
            || id.ValueKind != JsonValueKind.String)
        {
            return null;
        }

        try
        {
            return id.GetString();
        }
        catch (InvalidOperationException)
        {
            // An escaped lone surrogate ("\ud800") is valid JSON but no .NET string: nothing to echo,
            // so the line takes the unanswerable path instead of crashing the driver.
            return null;
        }
    }

    private static JsonElement Member(JsonElement request, string name) =>
        request.TryGetProperty(name, out var value)
            ? value
            : throw new FormatException($"The request has no '{name}' member.");

    private static string StringMember(JsonElement request, string name) =>
        Member(request, name) is { ValueKind: JsonValueKind.String } value && value.GetString() is { } text
            ? text
            : throw new FormatException($"The request's '{name}' member must be a string.");

    /// <summary>
    /// A line the driver cannot answer, because there is no <c>id</c> to answer it with. It says why
    /// on stderr and exits non-zero, which the runner reports as a protocol failure (§2.4 item 5)
    /// listing the requests left unanswered.
    /// </summary>
    private static int Unanswerable(int lineNumber, string reason)
    {
        Console.Error.WriteLine($"Craticula.Conformance.Driver: request line {lineNumber} cannot be answered: {reason}.");
        return 1;
    }

    /// <summary>One protocol line: compact JSON — a string value escapes its own line breaks, so the
    /// object cannot span two lines — then <c>\n</c>, as UTF-8 without BOM. Built whole before any
    /// byte reaches stdout, so a write that throws halfway leaves nothing behind.</summary>
    private static byte[] Line(Action<Utf8JsonWriter> write)
    {
        var buffer = new ArrayBufferWriter<byte>();
        using (var writer = new Utf8JsonWriter(buffer, new JsonWriterOptions { Indented = false }))
        {
            write(writer);
        }

        buffer.Write("\n"u8);
        return buffer.WrittenSpan.ToArray();
    }

    /// <summary>Flushed after every line (§8): a buffered driver looks hung and hits the runner's
    /// timeout (§2.4 item 4).</summary>
    private static void Send(Stream stdout, byte[] line)
    {
        stdout.Write(line);
        stdout.Flush();
    }
}
