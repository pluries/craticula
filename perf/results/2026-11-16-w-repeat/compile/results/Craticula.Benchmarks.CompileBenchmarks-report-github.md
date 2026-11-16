```

BenchmarkDotNet v0.15.8, Linux Ubuntu 26.04.1 LTS (Resolute Raccoon)
Intel Xeon CPU E5-1650 v4 3.60GHz, 1 CPU, 10 logical and 10 physical cores
.NET SDK 10.0.404
  [Host]     : .NET 10.0.15 (10.0.15, 10.0.1526.53008), X64 RyuJIT x86-64-v3
  DefaultJob : .NET 10.0.15 (10.0.15, 10.0.1526.53008), X64 RyuJIT x86-64-v3


```
| Method  | Shape           | Backend  | Mean     | Error    | StdDev   | Median   | Gen0   | Allocated |
|-------- |---------------- |--------- |---------:|---------:|---------:|---------:|-------:|----------:|
| **Compile** | **deep-filter**     | **mongo**    | **46.57 μs** | **2.183 μs** | **6.227 μs** | **45.17 μs** | **1.9531** |  **17.72 KB** |
| **Compile** | **deep-filter**     | **postgres** | **42.40 μs** | **1.477 μs** | **4.286 μs** | **41.97 μs** | **1.4648** |  **13.44 KB** |
| **Compile** | **deep-filter**     | **search**   | **41.60 μs** | **1.536 μs** | **4.481 μs** | **40.72 μs** | **1.9531** |  **17.83 KB** |
| **Compile** | **filter-tree**     | **mongo**    | **51.00 μs** | **2.750 μs** | **7.935 μs** | **49.24 μs** | **1.9531** |  **17.67 KB** |
| **Compile** | **filter-tree**     | **postgres** | **50.35 μs** | **2.111 μs** | **5.988 μs** | **49.87 μs** | **1.4648** |  **13.92 KB** |
| **Compile** | **filter-tree**     | **search**   | **48.79 μs** | **2.443 μs** | **6.970 μs** | **48.63 μs** | **0.9766** |  **15.18 KB** |
| **Compile** | **group-aggregate** | **mongo**    | **58.56 μs** | **2.308 μs** | **6.622 μs** | **58.26 μs** | **1.9531** |  **17.24 KB** |
| **Compile** | **group-aggregate** | **postgres** | **55.03 μs** | **1.759 μs** | **5.159 μs** | **53.71 μs** | **1.4648** |   **15.1 KB** |
| **Compile** | **group-aggregate** | **search**   | **60.92 μs** | **2.392 μs** | **6.940 μs** | **59.97 μs** | **1.4648** |  **15.04 KB** |
| **Compile** | **plain-page**      | **mongo**    | **21.28 μs** | **0.529 μs** | **1.535 μs** | **20.95 μs** | **1.3123** |  **10.73 KB** |
| **Compile** | **plain-page**      | **postgres** | **16.72 μs** | **0.449 μs** | **1.280 μs** | **16.36 μs** | **0.7324** |   **6.89 KB** |
| **Compile** | **plain-page**      | **search**   | **16.68 μs** | **0.331 μs** | **0.905 μs** | **16.52 μs** | **0.7324** |   **6.55 KB** |
