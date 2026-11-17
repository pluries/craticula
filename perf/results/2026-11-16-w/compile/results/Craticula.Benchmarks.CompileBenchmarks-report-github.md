```

BenchmarkDotNet v0.15.8, Linux Ubuntu 26.04.1 LTS (Resolute Raccoon)
Intel Xeon CPU E5-1650 v4 3.60GHz, 1 CPU, 10 logical and 10 physical cores
.NET SDK 10.0.404
  [Host]     : .NET 10.0.15 (10.0.15, 10.0.1526.53008), X64 RyuJIT x86-64-v3
  DefaultJob : .NET 10.0.15 (10.0.15, 10.0.1526.53008), X64 RyuJIT x86-64-v3


```
| Method  | Shape           | Backend  | Mean     | Error    | StdDev   | Median   | Gen0   | Allocated |
|-------- |---------------- |--------- |---------:|---------:|---------:|---------:|-------:|----------:|
| **Compile** | **deep-filter**     | **mongo**    | **45.34 μs** | **2.291 μs** | **6.609 μs** | **43.91 μs** | **1.9531** |  **17.72 KB** |
| **Compile** | **deep-filter**     | **postgres** | **42.40 μs** | **1.852 μs** | **5.253 μs** | **41.18 μs** | **1.4648** |  **13.44 KB** |
| **Compile** | **deep-filter**     | **search**   | **42.44 μs** | **1.820 μs** | **5.279 μs** | **40.85 μs** | **1.9531** |  **17.83 KB** |
| **Compile** | **filter-tree**     | **mongo**    | **53.07 μs** | **2.172 μs** | **6.161 μs** | **53.22 μs** | **1.9531** |  **17.67 KB** |
| **Compile** | **filter-tree**     | **postgres** | **44.08 μs** | **1.279 μs** | **3.691 μs** | **43.79 μs** | **1.4648** |  **13.92 KB** |
| **Compile** | **filter-tree**     | **search**   | **44.33 μs** | **1.670 μs** | **4.792 μs** | **42.93 μs** | **1.4648** |  **15.18 KB** |
| **Compile** | **group-aggregate** | **mongo**    | **61.50 μs** | **2.364 μs** | **6.969 μs** | **61.35 μs** | **1.9531** |  **17.24 KB** |
| **Compile** | **group-aggregate** | **postgres** | **59.17 μs** | **3.006 μs** | **8.625 μs** | **56.94 μs** | **1.4648** |   **15.1 KB** |
| **Compile** | **group-aggregate** | **search**   | **62.21 μs** | **2.485 μs** | **7.289 μs** | **60.80 μs** | **1.4648** |  **15.04 KB** |
| **Compile** | **plain-page**      | **mongo**    | **23.74 μs** | **0.941 μs** | **2.700 μs** | **23.32 μs** | **1.2207** |  **10.73 KB** |
| **Compile** | **plain-page**      | **postgres** | **17.44 μs** | **0.347 μs** | **0.846 μs** | **17.40 μs** | **0.8240** |   **6.89 KB** |
| **Compile** | **plain-page**      | **search**   | **16.41 μs** | **0.356 μs** | **1.038 μs** | **16.23 μs** | **0.7324** |   **6.55 KB** |
