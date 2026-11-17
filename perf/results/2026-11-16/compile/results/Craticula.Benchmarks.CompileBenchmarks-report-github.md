```

BenchmarkDotNet v0.15.8, Linux Ubuntu 26.04.1 LTS (Resolute Raccoon)
Intel Xeon CPU E5-1650 v4 3.60GHz, 1 CPU, 10 logical and 10 physical cores
.NET SDK 10.0.404
  [Host]     : .NET 10.0.15 (10.0.15, 10.0.1526.53008), X64 RyuJIT x86-64-v3
  DefaultJob : .NET 10.0.15 (10.0.15, 10.0.1526.53008), X64 RyuJIT x86-64-v3


```
| Method  | Shape           | Backend  | Mean     | Error    | StdDev   | Gen0   | Allocated |
|-------- |---------------- |--------- |---------:|---------:|---------:|-------:|----------:|
| **Compile** | **deep-filter**     | **mongo**    | **39.49 μs** | **0.790 μs** | **1.952 μs** | **2.1362** |  **17.72 KB** |
| **Compile** | **deep-filter**     | **postgres** | **36.11 μs** | **0.752 μs** | **2.168 μs** | **1.4648** |  **13.44 KB** |
| **Compile** | **deep-filter**     | **search**   | **38.64 μs** | **0.956 μs** | **2.758 μs** | **1.9531** |  **17.83 KB** |
| **Compile** | **filter-tree**     | **mongo**    | **42.89 μs** | **0.940 μs** | **2.711 μs** | **1.9531** |  **17.67 KB** |
| **Compile** | **filter-tree**     | **postgres** | **40.36 μs** | **0.949 μs** | **2.783 μs** | **1.4648** |  **13.92 KB** |
| **Compile** | **filter-tree**     | **search**   | **40.31 μs** | **0.897 μs** | **2.617 μs** | **1.7090** |  **15.18 KB** |
| **Compile** | **group-aggregate** | **mongo**    | **54.06 μs** | **1.452 μs** | **4.259 μs** | **1.9531** |  **17.24 KB** |
| **Compile** | **group-aggregate** | **postgres** | **50.96 μs** | **1.264 μs** | **3.666 μs** | **1.4648** |   **15.1 KB** |
| **Compile** | **group-aggregate** | **search**   | **52.14 μs** | **1.267 μs** | **3.677 μs** | **1.4648** |  **15.04 KB** |
| **Compile** | **plain-page**      | **mongo**    | **21.33 μs** | **0.423 μs** | **1.137 μs** | **1.2207** |  **10.73 KB** |
| **Compile** | **plain-page**      | **postgres** | **17.58 μs** | **0.358 μs** | **1.044 μs** | **0.8240** |   **6.89 KB** |
| **Compile** | **plain-page**      | **search**   | **17.32 μs** | **0.349 μs** | **1.023 μs** | **0.7935** |   **6.55 KB** |
