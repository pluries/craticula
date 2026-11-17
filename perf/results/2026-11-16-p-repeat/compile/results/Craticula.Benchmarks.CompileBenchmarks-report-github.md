```

BenchmarkDotNet v0.15.8, Linux Ubuntu 26.04.1 LTS (Resolute Raccoon)
Intel Xeon CPU E5-1650 v4 3.60GHz, 1 CPU, 10 logical and 10 physical cores
.NET SDK 10.0.404
  [Host]     : .NET 10.0.15 (10.0.15, 10.0.1526.53008), X64 RyuJIT x86-64-v3
  DefaultJob : .NET 10.0.15 (10.0.15, 10.0.1526.53008), X64 RyuJIT x86-64-v3


```
| Method  | Shape           | Backend  | SchemaPath      | Mean      | Error     | StdDev    | Median    | Gen0   | Allocated |
|-------- |---------------- |--------- |---------------- |----------:|----------:|----------:|----------:|-------:|----------:|
| **Compile** | **deep-filter**     | **mongo**    | **full-compile**    | **37.773 μs** | **0.7480 μs** | **1.8488 μs** | **37.478 μs** | **1.9531** |  **17.72 KB** |
| **Compile** | **deep-filter**     | **mongo**    | **prepared-schema** | **26.517 μs** | **0.6654 μs** | **1.9092 μs** | **26.158 μs** | **1.7090** |  **15.02 KB** |
| **Compile** | **deep-filter**     | **postgres** | **full-compile**    | **35.179 μs** | **0.8334 μs** | **2.3912 μs** | **34.914 μs** | **1.4648** |  **13.44 KB** |
| **Compile** | **deep-filter**     | **postgres** | **prepared-schema** | **22.892 μs** | **0.5556 μs** | **1.6029 μs** | **22.500 μs** | **1.2207** |  **10.74 KB** |
| **Compile** | **deep-filter**     | **search**   | **full-compile**    | **38.153 μs** | **0.9209 μs** | **2.6862 μs** | **37.641 μs** | **1.9531** |  **17.83 KB** |
| **Compile** | **deep-filter**     | **search**   | **prepared-schema** | **25.867 μs** | **0.5506 μs** | **1.6148 μs** | **25.573 μs** | **1.7090** |  **15.13 KB** |
| **Compile** | **filter-tree**     | **mongo**    | **full-compile**    | **41.400 μs** | **0.8244 μs** | **2.2567 μs** | **40.828 μs** | **1.9531** |  **17.67 KB** |
| **Compile** | **filter-tree**     | **mongo**    | **prepared-schema** | **17.971 μs** | **0.3487 μs** | **0.8554 μs** | **17.775 μs** | **1.4954** |   **12.4 KB** |
| **Compile** | **filter-tree**     | **postgres** | **full-compile**    | **37.807 μs** | **0.7532 μs** | **1.7753 μs** | **37.815 μs** | **1.4648** |  **13.92 KB** |
| **Compile** | **filter-tree**     | **postgres** | **prepared-schema** | **15.564 μs** | **0.3097 μs** | **0.6927 μs** | **15.592 μs** | **1.0376** |   **8.65 KB** |
| **Compile** | **filter-tree**     | **search**   | **full-compile**    | **43.591 μs** | **1.9662 μs** | **5.7043 μs** | **42.006 μs** | **1.7090** |  **15.18 KB** |
| **Compile** | **filter-tree**     | **search**   | **prepared-schema** | **19.463 μs** | **0.6994 μs** | **2.0622 μs** | **19.362 μs** | **1.1902** |   **9.92 KB** |
| **Compile** | **group-aggregate** | **mongo**    | **full-compile**    | **62.440 μs** | **2.2560 μs** | **6.5809 μs** | **61.558 μs** | **1.9531** |  **17.24 KB** |
| **Compile** | **group-aggregate** | **mongo**    | **prepared-schema** | **16.405 μs** | **0.4097 μs** | **1.2015 μs** | **16.485 μs** | **1.2207** |   **9.98 KB** |
| **Compile** | **group-aggregate** | **postgres** | **full-compile**    | **58.775 μs** | **1.8999 μs** | **5.4206 μs** | **57.266 μs** | **1.4648** |   **15.1 KB** |
| **Compile** | **group-aggregate** | **postgres** | **prepared-schema** | **13.941 μs** | **0.3310 μs** | **0.9603 μs** | **13.727 μs** | **0.9460** |   **7.84 KB** |
| **Compile** | **group-aggregate** | **search**   | **full-compile**    | **56.227 μs** | **1.6587 μs** | **4.7590 μs** | **55.122 μs** | **1.4648** |  **15.04 KB** |
| **Compile** | **group-aggregate** | **search**   | **prepared-schema** | **13.943 μs** | **0.3272 μs** | **0.9543 μs** | **13.758 μs** | **0.9460** |   **7.77 KB** |
| **Compile** | **plain-page**      | **mongo**    | **full-compile**    | **20.176 μs** | **0.4047 μs** | **1.1348 μs** | **20.118 μs** | **1.2207** |  **10.73 KB** |
| **Compile** | **plain-page**      | **mongo**    | **prepared-schema** | **10.101 μs** | **0.2015 μs** | **0.4789 μs** | **10.188 μs** | **0.9613** |   **7.96 KB** |
| **Compile** | **plain-page**      | **postgres** | **full-compile**    | **16.913 μs** | **0.3803 μs** | **1.0727 μs** | **16.813 μs** | **0.7324** |   **6.89 KB** |
| **Compile** | **plain-page**      | **postgres** | **prepared-schema** |  **8.015 μs** | **0.2837 μs** | **0.8366 μs** |  **7.798 μs** | **0.5035** |   **4.13 KB** |
| **Compile** | **plain-page**      | **search**   | **full-compile**    | **17.702 μs** | **0.5678 μs** | **1.6564 μs** | **17.228 μs** | **0.7324** |   **6.55 KB** |
| **Compile** | **plain-page**      | **search**   | **prepared-schema** |  **7.367 μs** | **0.1410 μs** | **0.3639 μs** |  **7.380 μs** | **0.4578** |   **3.79 KB** |
