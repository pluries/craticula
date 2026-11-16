```

BenchmarkDotNet v0.15.8, Linux Ubuntu 26.04 (Resolute Raccoon)
11th Gen Intel Core i7-11800H 2.30GHz (Max: 0.80GHz), 1 CPU, 16 logical and 8 physical cores
.NET SDK 10.0.115
  [Host]     : .NET 10.0.15 (10.0.15, 10.0.1526.53008), X64 RyuJIT x86-64-v4
  DefaultJob : .NET 10.0.15 (10.0.15, 10.0.1526.53008), X64 RyuJIT x86-64-v4


```
| Method  | Shape           | Backend  | SchemaPath      | Mean      | Error     | StdDev    | Gen0   | Gen1   | Allocated |
|-------- |---------------- |--------- |---------------- |----------:|----------:|----------:|-------:|-------:|----------:|
| **Compile** | **deep-filter**     | **mongo**    | **full-compile**    | **23.189 μs** | **0.1071 μs** | **0.1001 μs** | **1.4343** | **0.0305** |  **17.72 KB** |
| **Compile** | **deep-filter**     | **mongo**    | **prepared-schema** | **17.855 μs** | **0.1279 μs** | **0.1068 μs** | **1.2207** |      **-** |  **15.02 KB** |
| **Compile** | **deep-filter**     | **postgres** | **full-compile**    | **22.114 μs** | **0.1505 μs** | **0.1334 μs** | **1.0681** |      **-** |  **13.44 KB** |
| **Compile** | **deep-filter**     | **postgres** | **prepared-schema** | **15.680 μs** | **0.2574 μs** | **0.2408 μs** | **0.8545** |      **-** |  **10.74 KB** |
| **Compile** | **deep-filter**     | **search**   | **full-compile**    | **24.754 μs** | **0.2009 μs** | **0.1781 μs** | **1.2207** |      **-** |  **17.83 KB** |
| **Compile** | **deep-filter**     | **search**   | **prepared-schema** | **17.482 μs** | **0.1149 μs** | **0.1018 μs** | **1.2207** |      **-** |  **15.13 KB** |
| **Compile** | **filter-tree**     | **mongo**    | **full-compile**    | **27.211 μs** | **0.2263 μs** | **0.2006 μs** | **1.4343** | **0.0305** |  **17.67 KB** |
| **Compile** | **filter-tree**     | **mongo**    | **prepared-schema** | **12.042 μs** | **0.0543 μs** | **0.0508 μs** | **1.0071** | **0.0153** |   **12.4 KB** |
| **Compile** | **filter-tree**     | **postgres** | **full-compile**    | **26.063 μs** | **0.3044 μs** | **0.2847 μs** | **1.1292** |      **-** |  **13.92 KB** |
| **Compile** | **filter-tree**     | **postgres** | **prepared-schema** | **10.774 μs** | **0.0385 μs** | **0.0342 μs** | **0.7019** |      **-** |   **8.65 KB** |
| **Compile** | **filter-tree**     | **search**   | **full-compile**    | **25.667 μs** | **0.0866 μs** | **0.0810 μs** | **1.2207** |      **-** |  **15.18 KB** |
| **Compile** | **filter-tree**     | **search**   | **prepared-schema** | **11.001 μs** | **0.0646 μs** | **0.0604 μs** | **0.8087** |      **-** |   **9.92 KB** |
| **Compile** | **group-aggregate** | **mongo**    | **full-compile**    | **34.556 μs** | **0.1221 μs** | **0.1082 μs** | **1.4038** |      **-** |  **17.24 KB** |
| **Compile** | **group-aggregate** | **mongo**    | **prepared-schema** |  **9.630 μs** | **0.0334 μs** | **0.0279 μs** | **0.8087** |      **-** |   **9.98 KB** |
| **Compile** | **group-aggregate** | **postgres** | **full-compile**    | **31.508 μs** | **0.1868 μs** | **0.1747 μs** | **1.2207** |      **-** |   **15.1 KB** |
| **Compile** | **group-aggregate** | **postgres** | **prepared-schema** |  **8.268 μs** | **0.0468 μs** | **0.0415 μs** | **0.6256** |      **-** |   **7.84 KB** |
| **Compile** | **group-aggregate** | **search**   | **full-compile**    | **34.746 μs** | **0.1620 μs** | **0.1436 μs** | **1.2207** |      **-** |  **15.04 KB** |
| **Compile** | **group-aggregate** | **search**   | **prepared-schema** |  **7.965 μs** | **0.0442 μs** | **0.0392 μs** | **0.6256** |      **-** |   **7.77 KB** |
| **Compile** | **plain-page**      | **mongo**    | **full-compile**    | **12.895 μs** | **0.0548 μs** | **0.0486 μs** | **0.8698** |      **-** |  **10.73 KB** |
| **Compile** | **plain-page**      | **mongo**    | **prepared-schema** |  **6.560 μs** | **0.1242 μs** | **0.1430 μs** | **0.6485** | **0.0076** |   **7.96 KB** |
| **Compile** | **plain-page**      | **postgres** | **full-compile**    | **10.532 μs** | **0.0628 μs** | **0.0557 μs** | **0.5493** |      **-** |   **6.89 KB** |
| **Compile** | **plain-page**      | **postgres** | **prepared-schema** |  **4.986 μs** | **0.0521 μs** | **0.0462 μs** | **0.3357** |      **-** |   **4.13 KB** |
| **Compile** | **plain-page**      | **search**   | **full-compile**    | **11.954 μs** | **0.0845 μs** | **0.0791 μs** | **0.5341** |      **-** |   **6.55 KB** |
| **Compile** | **plain-page**      | **search**   | **prepared-schema** |  **4.565 μs** | **0.0200 μs** | **0.0178 μs** | **0.3052** |      **-** |   **3.79 KB** |
