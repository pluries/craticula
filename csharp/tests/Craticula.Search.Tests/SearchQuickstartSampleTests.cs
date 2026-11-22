using System.Reflection;
using Craticula.Tests.Shared;

namespace Craticula.Search.Tests;

/// <summary>
/// Spec 005, US6: runs the entry point of the compile-only Search sample and compares what it prints with the recorded
/// <c>expected-output.txt</c>, so a compiler change that alters the output fails here and names the sample and the file.
/// It writes to the console, so it shares a collection that never runs beside another test.
/// </summary>
[Collection(ConsoleOutputCollection.Name)]
public class SearchQuickstartSampleTests
{
    private const string Sample = "Craticula.Quickstart.Search";
    private const string ExpectedFile = "expected-output.txt";

    private static string ExpectedPath => Path.Combine(RepoPaths.Root, "csharp", "samples", Sample, ExpectedFile);

    private static MethodInfo EntryPoint => Assembly.Load(new AssemblyName(Sample)).EntryPoint
        ?? throw new InvalidOperationException(Sample + " has no entry point.");

    // US6-AS2, US6-AS3, US6-AS4 (the expected output ends with the refusal line), SC-010
    [Fact]
    public void The_Search_Quickstart_Prints_Exactly_Its_Expected_Output()
    {
        var actual = SampleOutput.Capture(EntryPoint);
        var equal = SampleOutput.SameOutput(File.ReadAllText(ExpectedPath), actual);

        Assert.True(equal, SampleOutput.SampleMismatchMessage(Sample, ExpectedFile));
    }

    // GUARD, green on arrival: it proves the comparison helper, not the sample (the match test above is the red one). US6-AS3, SC-010
    [Fact]
    public void A_Changed_Character_Is_Detected()
    {
        var real = SampleOutput.Capture(EntryPoint);
        var changed = string.Concat("X", real.AsSpan(1));

        Assert.False(SampleOutput.SameOutput(real, changed));
        var message = SampleOutput.SampleMismatchMessage(Sample, ExpectedFile);
        Assert.Contains(Sample, message);
        Assert.Contains(ExpectedFile, message);
    }
}

[CollectionDefinition(Name, DisableParallelization = true)]
public sealed class ConsoleOutputCollection
{
    public const string Name = "Console output";
}
