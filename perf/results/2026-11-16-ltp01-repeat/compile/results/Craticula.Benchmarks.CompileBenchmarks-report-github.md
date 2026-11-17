```

BenchmarkDotNet v0.15.8, Linux Ubuntu 26.04 (Resolute Raccoon)
11th Gen Intel Core i7-11800H 2.30GHz (Max: 0.80GHz), 1 CPU, 16 logical and 8 physical cores
.NET SDK 10.0.115
  [Host]     : .NET 10.0.15 (10.0.15, 10.0.1526.53008), X64 RyuJIT x86-64-v4
  DefaultJob : .NET 10.0.15 (10.0.15, 10.0.1526.53008), X64 RyuJIT x86-64-v4


```
| Method  | Shape           | Backend  | SchemaPath      | Mean      | Error     | StdDev    | Gen0   | Gen1   | Allocated |
|-------- |---------------- |--------- |---------------- |----------:|----------:|----------:|-------:|-------:|----------:|
| **Compile** | **deep-filter**     | **mongo**    | **full-compile**    | **29.098 μs** | **0.2691 μs** | **0.2386 μs** | **1.4038** |      **-** |  **17.72 KB** |
| **Compile** | **deep-filter**     | **mongo**    | **prepared-schema** | **17.135 μs** | **0.1748 μs** | **0.1460 μs** | **1.2207** |      **-** |  **15.02 KB** |
| **Compile** | **deep-filter**     | **postgres** | **full-compile**    | **22.206 μs** | **0.1105 μs** | **0.0923 μs** | **1.0681** |      **-** |  **13.44 KB** |
| **Compile** | **deep-filter**     | **postgres** | **prepared-schema** | **15.481 μs** | **0.0900 μs** | **0.0702 μs** | **0.8545** |      **-** |  **10.74 KB** |
| **Compile** | **deep-filter**     | **search**   | **full-compile**    | **23.844 μs** | **0.1619 μs** | **0.1435 μs** | **1.2207** |      **-** |  **17.83 KB** |
| **Compile** | **deep-filter**     | **search**   | **prepared-schema** | **16.613 μs** | **0.1716 μs** | **0.1605 μs** | **1.2207** |      **-** |  **15.13 KB** |
| **Compile** | **filter-tree**     | **mongo**    | **full-compile**    | **25.569 μs** | **0.1102 μs** | **0.0920 μs** | **1.4343** | **0.0305** |  **17.67 KB** |
| **Compile** | **filter-tree**     | **mongo**    | **prepared-schema** | **11.413 μs** | **0.0777 μs** | **0.0688 μs** | **1.0071** | **0.0153** |   **12.4 KB** |
| **Compile** | **filter-tree**     | **postgres** | **full-compile**    | **26.741 μs** | **0.1251 μs** | **0.1045 μs** | **1.1292** |      **-** |  **13.92 KB** |
| **Compile** | **filter-tree**     | **postgres** | **prepared-schema** | **10.160 μs** | **0.0411 μs** | **0.0343 μs** | **0.7019** |      **-** |   **8.65 KB** |
| **Compile** | **filter-tree**     | **search**   | **full-compile**    | **26.744 μs** | **0.1324 μs** | **0.1239 μs** | **1.2207** |      **-** |  **15.18 KB** |
| **Compile** | **filter-tree**     | **search**   | **prepared-schema** | **11.808 μs** | **0.1451 μs** | **0.1358 μs** | **0.8087** |      **-** |   **9.92 KB** |
| **Compile** | **group-aggregate** | **mongo**    | **full-compile**    | **36.687 μs** | **0.7080 μs** | **0.6623 μs** | **1.4038** |      **-** |  **17.24 KB** |
| **Compile** | **group-aggregate** | **mongo**    | **prepared-schema** |  **8.631 μs** | **0.0500 μs** | **0.0443 μs** | **0.8087** |      **-** |   **9.98 KB** |
| **Compile** | **group-aggregate** | **postgres** | **full-compile**    | **31.125 μs** | **0.0891 μs** | **0.0744 μs** | **1.2207** |      **-** |   **15.1 KB** |
| **Compile** | **group-aggregate** | **postgres** | **prepared-schema** |  **9.093 μs** | **0.0605 μs** | **0.0537 μs** | **0.6256** |      **-** |   **7.84 KB** |
| **Compile** | **group-aggregate** | **search**   | **full-compile**    | **35.259 μs** | **0.4724 μs** | **0.4419 μs** | **1.2207** |      **-** |  **15.04 KB** |
| **Compile** | **group-aggregate** | **search**   | **prepared-schema** |  **9.332 μs** | **0.0307 μs** | **0.0240 μs** | **0.6256** |      **-** |   **7.77 KB** |
| **Compile** | **plain-page**      | **mongo**    | **full-compile**    | **12.254 μs** | **0.0475 μs** | **0.0396 μs** | **0.8698** |      **-** |  **10.73 KB** |
| **Compile** | **plain-page**      | **mongo**    | **prepared-schema** |  **6.794 μs** | **0.0391 μs** | **0.0347 μs** | **0.6485** | **0.0076** |   **7.96 KB** |
| **Compile** | **plain-page**      | **postgres** | **full-compile**    | **10.897 μs** | **0.0479 μs** | **0.0425 μs** | **0.5493** |      **-** |   **6.89 KB** |
| **Compile** | **plain-page**      | **postgres** | **prepared-schema** |  **5.211 μs** | **0.0238 μs** | **0.0211 μs** | **0.3357** |      **-** |   **4.13 KB** |
| **Compile** | **plain-page**      | **search**   | **full-compile**    | **11.449 μs** | **0.0610 μs** | **0.0541 μs** | **0.5341** |      **-** |   **6.55 KB** |
| **Compile** | **plain-page**      | **search**   | **prepared-schema** |  **4.584 μs** | **0.0197 μs** | **0.0164 μs** | **0.3052** |      **-** |   **3.79 KB** |
