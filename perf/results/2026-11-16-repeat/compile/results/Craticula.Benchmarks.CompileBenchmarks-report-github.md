```

BenchmarkDotNet v0.15.8, Linux Ubuntu 26.04.1 LTS (Resolute Raccoon)
Intel Xeon CPU E5-1650 v4 3.60GHz, 1 CPU, 10 logical and 10 physical cores
.NET SDK 10.0.404
  [Host]     : .NET 10.0.15 (10.0.15, 10.0.1526.53008), X64 RyuJIT x86-64-v3
  DefaultJob : .NET 10.0.15 (10.0.15, 10.0.1526.53008), X64 RyuJIT x86-64-v3


```
| Method  | Shape           | Backend  | Mean     | Error    | StdDev   | Median   | Gen0   | Allocated |
|-------- |---------------- |--------- |---------:|---------:|---------:|---------:|-------:|----------:|
| **Compile** | **deep-filter**     | **mongo**    | **39.71 μs** | **0.797 μs** | **2.311 μs** | **39.28 μs** | **1.9531** |  **17.72 KB** |
| **Compile** | **deep-filter**     | **postgres** | **35.55 μs** | **0.711 μs** | **1.822 μs** | **35.37 μs** | **1.4648** |  **13.44 KB** |
| **Compile** | **deep-filter**     | **search**   | **37.70 μs** | **1.101 μs** | **3.212 μs** | **36.75 μs** | **1.9531** |  **17.83 KB** |
| **Compile** | **filter-tree**     | **mongo**    | **42.43 μs** | **1.048 μs** | **3.023 μs** | **41.88 μs** | **1.9531** |  **17.67 KB** |
| **Compile** | **filter-tree**     | **postgres** | **38.93 μs** | **0.776 μs** | **1.875 μs** | **38.67 μs** | **1.4648** |  **13.92 KB** |
| **Compile** | **filter-tree**     | **search**   | **41.70 μs** | **0.990 μs** | **2.887 μs** | **41.25 μs** | **1.7090** |  **15.18 KB** |
| **Compile** | **group-aggregate** | **mongo**    | **55.86 μs** | **1.222 μs** | **3.526 μs** | **55.54 μs** | **1.9531** |  **17.24 KB** |
| **Compile** | **group-aggregate** | **postgres** | **51.87 μs** | **1.032 μs** | **2.532 μs** | **51.59 μs** | **1.8311** |   **15.1 KB** |
| **Compile** | **group-aggregate** | **search**   | **50.66 μs** | **1.295 μs** | **3.738 μs** | **49.68 μs** | **1.4648** |  **15.04 KB** |
| **Compile** | **plain-page**      | **mongo**    | **24.25 μs** | **1.214 μs** | **3.578 μs** | **23.64 μs** | **1.2207** |  **10.73 KB** |
| **Compile** | **plain-page**      | **postgres** | **17.42 μs** | **0.347 μs** | **0.859 μs** | **17.40 μs** | **0.8240** |   **6.89 KB** |
| **Compile** | **plain-page**      | **search**   | **16.83 μs** | **0.480 μs** | **1.361 μs** | **16.59 μs** | **0.7324** |   **6.55 KB** |
