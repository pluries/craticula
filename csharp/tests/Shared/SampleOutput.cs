using System.Reflection;

namespace Craticula.Tests.Shared;

/// <summary>
/// Spec 005, US6: shared by the output tests of the compile-only samples (linked into each test project, not a project of its own).
/// Runs a sample's entry point with the console redirected and compares what it printed with the recorded file.
/// </summary>
internal static class SampleOutput
{
    public static bool SameOutput(string expected, string actual) => Normalize(expected) == Normalize(actual);

    public static string SampleMismatchMessage(string sample, string file) =>
        $"The output of the sample {sample} differs from {file}. Re-run the sample and record its output in that file if the change is intended.";

    public static string Capture(MethodInfo entryPoint)
    {
        var original = Console.Out;
        using var captured = new StringWriter();
        try
        {
            Console.SetOut(captured);
            entryPoint.Invoke(null, entryPoint.GetParameters().Length == 0 ? null : [Array.Empty<string>()]);
        }
        finally
        {
            Console.SetOut(original);
        }

        return captured.ToString();
    }

    private static string Normalize(string text) => text.Replace("\r\n", "\n").TrimEnd('\n');
}
