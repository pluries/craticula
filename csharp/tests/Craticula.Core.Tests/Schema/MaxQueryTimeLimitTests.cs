using Craticula.Core;
using Craticula.Core.Schema;

namespace Craticula.Core.Tests.Schema;

/// <summary>TL-4 (query time limit, #3794): the one optional <see cref="ResourceLimits"/> member and
/// the <see cref="QueryTimeoutException"/> of TL-5.</summary>
public class MaxQueryTimeLimitTests
{
    [Fact]
    public void Default_Is_Unset() => Assert.Null(new ResourceLimits().MaxQueryTimeMs);

    [Theory]
    [InlineData(1)]
    [InlineData(2000)]
    [InlineData(int.MaxValue)]
    public void A_Whole_Positive_Value_Up_To_The_Engine_Maximum_Is_Accepted(int value) =>
        Assert.Equal(value, new ResourceLimits { MaxQueryTimeMs = value }.MaxQueryTimeMs);

    [Fact]
    public void Null_Is_Accepted_As_Unset() =>
        Assert.Null(new ResourceLimits { MaxQueryTimeMs = null }.MaxQueryTimeMs);

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    [InlineData(int.MinValue)]
    public void Zero_Or_Negative_Is_Rejected_When_Configured(int value)
    {
        var ex = Assert.Throws<ArgumentOutOfRangeException>(() => new ResourceLimits { MaxQueryTimeMs = value });
        Assert.Equal(nameof(ResourceLimits.MaxQueryTimeMs), ex.ParamName);
    }

    [Fact]
    public void Error_Kind_Is_Query_Timeout() => Assert.Equal("query-timeout", QueryTimeoutException.ErrorKind);

    [Fact]
    public void Message_Names_No_Query_Text()
    {
        var ex = new QueryTimeoutException();
        Assert.DoesNotContain("SELECT", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("$match", ex.Message);
        Assert.Contains("time", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Inner_Exception_Is_Kept_But_Not_Echoed_In_The_Message()
    {
        var inner = new InvalidOperationException("db.orders.aggregate([{$match: {secret: 1}}])");
        var ex = new QueryTimeoutException(inner);
        Assert.Same(inner, ex.InnerException);
        Assert.DoesNotContain("secret", ex.Message);
    }
}
