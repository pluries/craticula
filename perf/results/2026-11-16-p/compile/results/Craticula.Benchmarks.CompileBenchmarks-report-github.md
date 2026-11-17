```

BenchmarkDotNet v0.15.8, Linux Ubuntu 26.04.1 LTS (Resolute Raccoon)
Intel Xeon CPU E5-1650 v4 3.60GHz, 1 CPU, 10 logical and 10 physical cores
.NET SDK 10.0.404
  [Host]     : .NET 10.0.15 (10.0.15, 10.0.1526.53008), X64 RyuJIT x86-64-v3
  DefaultJob : .NET 10.0.15 (10.0.15, 10.0.1526.53008), X64 RyuJIT x86-64-v3


```
| Method  | Shape           | Backend  | SchemaPath      | Mean      | Error     | StdDev    | Median    | Gen0   | Gen1   | Allocated |
|-------- |---------------- |--------- |---------------- |----------:|----------:|----------:|----------:|-------:|-------:|----------:|
| **Compile** | **deep-filter**     | **mongo**    | **full-compile**    | **37.497 μs** | **0.8125 μs** | **2.2782 μs** | **37.094 μs** | **1.9531** |      **-** |  **17.72 KB** |
| **Compile** | **deep-filter**     | **mongo**    | **prepared-schema** | **26.762 μs** | **0.5320 μs** | **1.2117 μs** | **26.787 μs** | **1.8311** | **0.0305** |  **15.02 KB** |
| **Compile** | **deep-filter**     | **postgres** | **full-compile**    | **35.153 μs** | **0.9173 μs** | **2.6612 μs** | **34.563 μs** | **1.4648** |      **-** |  **13.44 KB** |
| **Compile** | **deep-filter**     | **postgres** | **prepared-schema** | **23.334 μs** | **0.4629 μs** | **1.0543 μs** | **23.070 μs** | **1.3123** |      **-** |  **10.74 KB** |
| **Compile** | **deep-filter**     | **search**   | **full-compile**    | **37.510 μs** | **0.8862 μs** | **2.4849 μs** | **36.978 μs** | **1.9531** |      **-** |  **17.83 KB** |
| **Compile** | **deep-filter**     | **search**   | **prepared-schema** | **25.519 μs** | **0.5081 μs** | **1.2465 μs** | **25.358 μs** | **1.7090** |      **-** |  **15.13 KB** |
| **Compile** | **filter-tree**     | **mongo**    | **full-compile**    | **42.591 μs** | **1.0645 μs** | **3.1053 μs** | **41.584 μs** | **1.9531** |      **-** |  **17.67 KB** |
| **Compile** | **filter-tree**     | **mongo**    | **prepared-schema** | **18.774 μs** | **0.3746 μs** | **0.8607 μs** | **18.824 μs** | **1.4954** |      **-** |   **12.4 KB** |
| **Compile** | **filter-tree**     | **postgres** | **full-compile**    | **38.911 μs** | **0.7840 μs** | **2.2240 μs** | **38.585 μs** | **1.4648** |      **-** |  **13.92 KB** |
| **Compile** | **filter-tree**     | **postgres** | **prepared-schema** | **15.787 μs** | **0.3154 μs** | **0.6298 μs** | **15.781 μs** | **1.0376** |      **-** |   **8.65 KB** |
| **Compile** | **filter-tree**     | **search**   | **full-compile**    | **40.692 μs** | **0.9506 μs** | **2.7120 μs** | **40.215 μs** | **1.7090** |      **-** |  **15.18 KB** |
| **Compile** | **filter-tree**     | **search**   | **prepared-schema** | **16.616 μs** | **0.3218 μs** | **0.9232 μs** | **16.424 μs** | **1.1902** |      **-** |   **9.92 KB** |
| **Compile** | **group-aggregate** | **mongo**    | **full-compile**    | **53.075 μs** | **1.3048 μs** | **3.7854 μs** | **52.401 μs** | **1.9531** |      **-** |  **17.24 KB** |
| **Compile** | **group-aggregate** | **mongo**    | **prepared-schema** | **13.893 μs** | **0.2758 μs** | **0.6393 μs** | **13.814 μs** | **1.2207** |      **-** |   **9.98 KB** |
| **Compile** | **group-aggregate** | **postgres** | **full-compile**    | **51.875 μs** | **1.0002 μs** | **2.5819 μs** | **51.346 μs** | **1.8311** |      **-** |   **15.1 KB** |
| **Compile** | **group-aggregate** | **postgres** | **prepared-schema** | **12.325 μs** | **0.2459 μs** | **0.5797 μs** | **12.250 μs** | **0.9460** |      **-** |   **7.84 KB** |
| **Compile** | **group-aggregate** | **search**   | **full-compile**    | **52.272 μs** | **1.4990 μs** | **4.3490 μs** | **50.770 μs** | **1.4648** |      **-** |  **15.04 KB** |
| **Compile** | **group-aggregate** | **search**   | **prepared-schema** | **12.510 μs** | **0.2493 μs** | **0.6299 μs** | **12.443 μs** | **0.9460** |      **-** |   **7.77 KB** |
| **Compile** | **plain-page**      | **mongo**    | **full-compile**    | **20.512 μs** | **0.4075 μs** | **0.9685 μs** | **20.459 μs** | **1.3123** |      **-** |  **10.73 KB** |
| **Compile** | **plain-page**      | **mongo**    | **prepared-schema** |  **9.677 μs** | **0.1929 μs** | **0.4432 μs** |  **9.663 μs** | **0.9613** |      **-** |   **7.96 KB** |
| **Compile** | **plain-page**      | **postgres** | **full-compile**    | **17.206 μs** | **0.3370 μs** | **0.9505 μs** | **16.972 μs** | **0.8240** |      **-** |   **6.89 KB** |
| **Compile** | **plain-page**      | **postgres** | **prepared-schema** |  **7.256 μs** | **0.1336 μs** | **0.2932 μs** |  **7.217 μs** | **0.5035** |      **-** |   **4.13 KB** |
| **Compile** | **plain-page**      | **search**   | **full-compile**    | **16.966 μs** | **0.4012 μs** | **1.1575 μs** | **16.877 μs** | **0.7324** |      **-** |   **6.55 KB** |
| **Compile** | **plain-page**      | **search**   | **prepared-schema** |  **7.022 μs** | **0.1391 μs** | **0.3358 μs** |  **6.979 μs** | **0.4578** |      **-** |   **3.79 KB** |
