---
translates: odata-migration
title: 从 OData 迁移
description: 把网格从 OData 迁移到编译查询，并了解哪些地方会变。
source_fingerprint: fd82735ea37c07ef6fc24c75d469d2a95817109d4cb1345e8240e4df38b66ee0
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# 从 OData 迁移 {#migrating-from-odata}

本页面向目前网格对接 OData 服务、并希望迁移到 Craticula 的团队。它逐个构造地展示：你在 OData 中写的是什么，Craticula 取而代之接收的请求又是什么。每个示例都是测试会去编译的文件，因此请求和其下的语句都是真实的，不会过时。

从一开始就有两点不同：

- **Craticula 接收 AG Grid 本来就会发送的请求。** 无需构造 URL 查询字符串。网格的 Server-Side Row Model 会 POST 一个 JSON 请求体（`filterModel`、`sortModel`、`startRow`、`endRow`、`rowGroupCols`、`valueCols`、`groupKeys`），Craticula 编译它。下文的“OData”一侧是你的服务收到的内容；“Craticula”一侧是网格发送的内容。
- **Craticula 只编译，不提供服务。** 它返回一条语句及其参数。你用自己的驱动程序执行它，并自己编写端点（参见 [C# 快速入门](quickstart-csharp.html)）。

所有示例都使用同一个小型合成 schema，`orders`（id、customer、amount、active、status、region、country），并打印 PostgreSQL 语句。其他数据库对同一个请求有各自的写法。

````json
{
  "mode": "strict",
  "source": "orders",
  "stableKey": "id",
  "fields": {
    "id": {
      "type": "int64",
      "sortable": true,
      "physical": {
        "sql": {
          "column": "id"
        }
      },
      "aggregatable": [
        "count"
      ]
    },
    "customer": {
      "type": "string",
      "filterable": true,
      "sortable": true,
      "physical": {
        "sql": {
          "column": "customer"
        }
      }
    },
    "amount": {
      "type": "decimal",
      "filterable": true,
      "sortable": true,
      "aggregatable": [
        "sum",
        "avg",
        "min",
        "max",
        "count"
      ],
      "physical": {
        "sql": {
          "column": "amount"
        }
      }
    },
    "active": {
      "type": "boolean",
      "filterable": true,
      "sortable": true,
      "physical": {
        "sql": {
          "column": "active"
        }
      }
    },
    "status": {
      "type": "string",
      "filterable": true,
      "sortable": true,
      "physical": {
        "sql": {
          "column": "status"
        }
      }
    },
    "region": {
      "type": "string",
      "filterable": true,
      "sortable": true,
      "physical": {
        "sql": {
          "column": "region"
        }
      },
      "groupable": true
    },
    "country": {
      "type": "string",
      "filterable": true,
      "sortable": true,
      "groupable": true,
      "physical": {
        "sql": {
          "column": "country"
        }
      }
    }
  }
}
````

## `$filter` {#filter}

### 对单列的比较 {#a-comparison-on-one-column}

OData：`$filter=status eq 'active'`。`ne`、`gt`、`ge`、`lt`、`le` 同理：它们分别变为过滤类型 `equals`、`notEqual`、`greaterThan`、`greaterThanOrEqual`、`lessThan`、`lessThanOrEqual`。

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "status": {
      "filterType": "text",
      "type": "equals",
      "filter": "active"
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE "status" COLLATE craticula_ci = $1 ORDER BY "id" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: 'active', 100, 0
````

该比较带有 `COLLATE craticula_ci`：**文本默认不区分大小写地比较**（[Case sensitivity](semantics.html#sem-1)）。在 OData 中，结果通常取决于服务及其数据库。如果你的用户依赖精确的大小写，请在 schema 中把该字段声明为 `caseSensitivity: "sensitive"`。

### `contains`、`startswith`、`endswith`，以及跨列的 `and` {#contains-startswith-endswith-and-and-across-columns}

OData：`$filter=contains(customer,'acme') and amount gt 100`。文本函数对应过滤类型 `contains`、`startsWith` 和 `endsWith`；`notContains` 是网格的文本过滤唯一具备的否定形式。不同列上的过滤以 AND 连接，每列在 `filterModel` 中占一项。

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "customer": {
      "filterType": "text",
      "type": "contains",
      "filter": "acme"
    },
    "amount": {
      "filterType": "number",
      "type": "greaterThan",
      "filter": 100
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE ("customer" ILIKE '%' || $1 || '%' ESCAPE '\' AND "amount" > $2::numeric) ORDER BY "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'acme', '100', 100, 0
````

`contains` 匹配是经过转义的：用户输入的 `%` 和 `_` 是字面字符，绝不是通配符（[Substring matching on OpenSearch](semantics.html#sem-7)）。

### 单列上的 `or` {#or-on-one-column}

OData：`$filter=amount gt 100 or amount lt 10`。同一列上的两个条件放在该列的 `conditions` 数组中，并设 `operator: "OR"`（或 `"AND"`）。

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "amount": {
      "filterType": "number",
      "operator": "OR",
      "conditions": [
        {
          "filterType": "number",
          "type": "greaterThan",
          "filter": 100
        },
        {
          "filterType": "number",
          "type": "lessThan",
          "filter": 10
        }
      ]
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE ("amount" > $1::numeric OR "amount" < $2::numeric) ORDER BY "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: '100', '10', 100, 0
````

### `in` {#in}

OData（4.01）：`$filter=status in ('active','pending')`。这就是网格的集合过滤（set filter）。

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "status": {
      "filterType": "set",
      "values": [
        "active",
        "pending"
      ]
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE "status" COLLATE craticula_ci = ANY($1) ORDER BY "id" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: ['active', 'pending'], 100, 0
````

### `ne` 和 `not` {#ne-and-not}

OData：`$filter=status ne 'blocked'` 或 `$filter=not (status eq 'blocked')`。在网格中，这就是 `notEqual` 过滤类型。

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "status": {
      "filterType": "text",
      "type": "notEqual",
      "filter": "blocked"
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE ("status" COLLATE craticula_ci <> $1 OR "status" IS NULL) ORDER BY "id" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: 'blocked', 100, 0
````

请仔细阅读该语句。`status ne 'blocked'` 同样会返回 `status` 为 `NULL` 的行。Craticula 的否定运算符有意包含空值行（[Null handling](semantics.html#sem-2)），所以网格的行为与 AG Grid 自带的内存过滤一致。SQL 的三值逻辑会丢掉这些行，而 OData 服务可能丢也可能不丢。在迁移任何排除某些值的过滤之前，请先用测试检查旧的行为。

### `eq null` 和 `ne null` {#eq-null-and-ne-null}

OData：`$filter=region eq null`。有两种形式，它们在文本列上有所不同。

- 网格的 `blank` 过滤类型：在文本列上是空值**或空字符串**，在数字或日期列上则只有 `NULL`。

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "region": {
      "filterType": "text",
      "type": "blank"
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE ("region" IS NULL OR "region" = '') ORDER BY "id" ASC NULLS LAST LIMIT $1 OFFSET $2
-- parameters: 100, 0
````

- 在 `customFilters` 扩展中书写的、值为 null 的 `eq`：恰好是 `NULL`，不包括其他任何东西（[Grouping and drill-down](semantics.html#grp-7)）。这就是 OData 的 `eq null`。

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {},
  "sortModel": [],
  "customFilters": {
    "type": "comparison",
    "field": "region",
    "op": "eq",
    "value": {
      "type": "null"
    }
  }
}
````

````sql
SELECT * FROM "orders" WHERE "region" IS NULL ORDER BY "id" ASC NULLS LAST LIMIT $1 OFFSET $2
-- parameters: 100, 0
````

`ne null` 在文本列上没有精确的写法。`notBlank` 返回既不是 null 也不是空的行。不要写值为 null 的 `neq`（它只返回空值行，这是 SQL 的三值逻辑与 SEM-2 共同作用的结果），也不要在空值测试外面套 `not`（它会返回每一行）。

### 范围与布尔值 {#ranges-and-booleans}

`$filter=amount ge 10 and amount le 20` 是同一列上以 AND 连接的两个条件。

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "amount": {
      "filterType": "number",
      "operator": "AND",
      "conditions": [
        {
          "filterType": "number",
          "type": "greaterThanOrEqual",
          "filter": 10
        },
        {
          "filterType": "number",
          "type": "lessThanOrEqual",
          "filter": 20
        }
      ]
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE ("amount" >= $1::numeric AND "amount" <= $2::numeric) ORDER BY "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: '10', '20', 100, 0
````

网格自带的区间（in-range）选项会被拒绝，因为它的两个边界没有包含性说明；`customFilters` 扩展有一个 `inRange` 运算符，其包含性是明确写出的。布尔属性 `$filter=active eq true` 是布尔列上的集合过滤，它编译为 `true` 运算符。

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "active": {
      "filterType": "set",
      "values": [
        "true"
      ]
    }
  },
  "sortModel": []
}
````

````sql
SELECT * FROM "orders" WHERE "active" = $1 ORDER BY "id" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: true, 100, 0
````

### 日期与日期时间 {#dates-and-date-times}

日期过滤采用网格的线上格式：`yyyy-MM-dd`，或 `yyyy-MM-dd HH:mm:ss`，后者是按请求携带的时区（`requestContext.zone`）或解析器选项所指定的时区读取的挂钟时间，默认为 UTC（[Dates and time zones](semantics.html#sem-4)）。形如 `2026-01-01T00:00:00Z` 的 OData 字面量，或带偏移量的字面量，不符合这一格式。请把它转换到请求的时区，或者通过 `customFilters` 以带类型的 `datetime` 值发送确切的时刻，并在其中指明时区。

### 其他情形：`and`、`or`、`not` 构成的树 {#anything-else-a-tree-of-and-or-not}

AG Grid 的过滤一次只覆盖一列。对于诸如 `not startswith(customer,'test') and (status eq 'active' or amount gt 1000)` 这样的嵌套，Craticula 在 `filterModel` 旁边接受一个扩展：`customFilters`，即由 `and`、`or`、`not` 和比较节点构成的树，比较节点基于一个封闭的、共 17 个运算符的集合：`eq`、`neq`、`gt`、`gte`、`lt`、`lte`、`contains`、`notContains`、`startsWith`、`endsWith`、`in`、`notIn`、`inRange`、`blank`、`notBlank`、`true`、`false`。被否定的 `startsWith` 或 `endsWith` 也放在这里，因为网格没有这样的过滤类型。该树与 `filterModel` 以 AND 合并。它的深度和大小是有限制的（SEC-3 的资源限制），所以过大的 `$filter` 会被拒绝，而不是被编译。

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {},
  "sortModel": [],
  "customFilters": {
    "type": "and",
    "nodes": [
      {
        "type": "not",
        "node": {
          "type": "comparison",
          "field": "customer",
          "op": "startsWith",
          "value": {
            "type": "string",
            "value": "test"
          }
        }
      },
      {
        "type": "or",
        "nodes": [
          {
            "type": "comparison",
            "field": "status",
            "op": "eq",
            "value": {
              "type": "string",
              "value": "active"
            }
          },
          {
            "type": "comparison",
            "field": "amount",
            "op": "gt",
            "value": {
              "type": "decimal",
              "value": "1000"
            }
          }
        ]
      }
    ]
  }
}
````

````sql
SELECT * FROM "orders" WHERE ((NOT ("customer" ILIKE $1 || '%' ESCAPE '\') OR "customer" IS NULL) AND ("status" COLLATE craticula_ci = $2 OR "amount" > $3::numeric)) ORDER BY "id" ASC NULLS LAST LIMIT $4 OFFSET $5
-- parameters: 'test', 'active', '1000', 100, 0
````

## `$orderby`、`$top`、`$skip`、`$count` {#orderby-top-skip-count}

OData：`$orderby=amount desc,id&$top=20&$skip=40`。`$orderby` 就是 `sortModel`，第一项优先。`$skip` 是 `startRow`，`$skip + $top` 是 `endRow`（不含），所以 `$skip=40&$top=20` 就是 `startRow: 40`、`endRow: 60`。

````json
{
  "startRow": 40,
  "endRow": 60,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {},
  "sortModel": [
    {
      "colId": "amount",
      "sort": "desc"
    },
    {
      "colId": "id",
      "sort": "asc"
    }
  ]
}
````

````sql
SELECT * FROM "orders" ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST LIMIT $1 OFFSET $2
-- parameters: 20, 40
````

有两点不同：

- **空值的位置。** OData 的标准把空值当作最小值排序：升序时在前，降序时在后。网格不发送空值位置，所以 Craticula 使用相反的固定规则：**升序时在后，降序时在前**（[Null ordering](semantics.html#sem-3)），如上面的 `amount DESC NULLS FIRST` 所示。迁移之后，凡是对含有空值的列做升序排序，这些行都会出现在不同的位置。
- **稳定的顺序。** 服务必须让 `$skip`/`$top` 在多次请求之间保持稳定。无论网格按什么排序，Craticula 都能保证这一点：它始终以 schema 的**稳定键**结束排序（[Deterministic paging](semantics.html#sem-6)），所以两行绝不会在页与页之间互换位置。

`$count=true`（响应中的 `@odata.count`）对应于执行适配器在你请求时与页面一起返回的行计数（`includeRowCount`：`RowCount`，以及 AG Grid 的 `lastRow`）。在 SQL 和 MongoDB 上，它是第二次查询。在 OpenSearch 和 Elasticsearch 上，它默认设有上限，超过 10,000 行时报告为未知（参见[索引指南](index-guidance.html)）。

## `$apply`：`groupby` 与 `aggregate` {#apply-groupby-and-aggregate}

OData：`$apply=groupby((country),aggregate(amount with sum as total))`。网格的行分组发送 `rowGroupCols`（分组列，最外层在前）、`valueCols`（聚合：`sum`、`min`、`max`、`avg`、`count`）和 `groupKeys`（用户已展开的分组）。

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [
    {
      "id": "country",
      "displayName": "Country",
      "field": "country"
    }
  ],
  "valueCols": [
    {
      "id": "amount",
      "displayName": "Amount",
      "field": "amount",
      "aggFunc": "sum"
    }
  ],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {},
  "sortModel": [
    {
      "colId": "country",
      "sort": "asc"
    }
  ]
}
````

````sql
SELECT "country" AS "country", COALESCE(SUM("amount"), 0) AS "amount_sum" FROM "orders" GROUP BY "country" ORDER BY "country" ASC NULLS LAST LIMIT $1 OFFSET $2
-- parameters: 100, 0
````

一个请求只返回**一个层级**。对于 `groupby((country,region))`，网格先请求各个国家。当用户展开 Germany 时，它发送分组键 `Germany`，得到 Germany 的各个地区：

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [
    {
      "id": "country",
      "displayName": "Country",
      "field": "country"
    },
    {
      "id": "region",
      "displayName": "Region",
      "field": "region"
    }
  ],
  "valueCols": [
    {
      "id": "amount",
      "displayName": "Amount",
      "field": "amount",
      "aggFunc": "sum"
    }
  ],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [
    {
      "type": "string",
      "value": "Germany"
    }
  ],
  "filterModel": {},
  "sortModel": [
    {
      "colId": "region",
      "sort": "asc"
    }
  ]
}
````

````sql
SELECT "region" AS "region", COALESCE(SUM("amount"), 0) AS "amount_sum" FROM "orders" WHERE "country" = $1 GROUP BY "region" ORDER BY "region" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: 'Germany', 100, 0
````

再深入一层，两个键都用完后，它得到的就是行：

````json
{
  "startRow": 0,
  "endRow": 100,
  "rowGroupCols": [
    {
      "id": "country",
      "displayName": "Country",
      "field": "country"
    },
    {
      "id": "region",
      "displayName": "Region",
      "field": "region"
    }
  ],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [
    {
      "type": "string",
      "value": "Germany"
    },
    {
      "type": "string",
      "value": "Bavaria"
    }
  ],
  "filterModel": {},
  "sortModel": [
    {
      "colId": "id",
      "sort": "asc"
    }
  ]
}
````

````sql
SELECT "id", "customer", "amount", "active", "status", "region", "country" FROM "orders" WHERE ("country" = $1 AND "region" = $2) ORDER BY "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'Germany', 'Bavaria', 100, 0
````

AG Grid 自己的请求把键作为普通字符串携带（`groupKeys: ["Germany"]`）。Craticula 提供的解析器则把每个键当作带类型的值（`{"type": "string", "value": "Germany"}`），所以在请求被解析之前，你的前端适配器需要做一个小步骤，根据列类型给键加上类型。演示中的 `toWireRequest`（[`datasource.ts`](../../examples/demo/web/src/datasource.ts)）只用十行就做到了这一点，空键也包括在内。

需要了解的差异：

- `count` 统计的是列中非空值的个数，而不是行数（[AGG-1](semantics.html#agg-1)），并且该列必须在其 `aggregatable` 设置中列出 `count`。要统计行数，请统计稳定键。
- 没有值的分组，其 sum 为 `0`，而 `avg`、`min`、`max` 为 `NULL`（[AGG-6](semantics.html#agg-6)）。
- 键为空值的分组自成一个分组，你要用空的分组键来展开它（[Grouping and drill-down](semantics.html#grp-7)）。
- 聚合结果以 `<field>_<function>`（`amount_sum`）命名，除非网格的列 id 另有指定。
- 按聚合值对分组排序，在搜索引擎上不可用（组合聚合只按键的顺序列出分组）。

## 没有对应物的内容 {#what-has-no-equivalent}

| OData | 为什么没有，以及该怎么办 |
|---|---|
| `$expand`、导航属性、跨关系的 `$filter` | 一个 schema 只读取一个数据源（一张表、一个集合或一个索引），每一列都是它的字段。请建立一个把数据联接起来的视图或索引，并把该视图声明为数据源。 |
| `$select` | 列由 schema 决定。请求不能只要其中一部分，而且**执行适配器**只返回已声明的字段。使用单纯的编译器时，普通的行查询是 `SELECT *`，所以你没有声明的列仍然会出现在结果中：请在你声明为数据源的视图里把它去掉。导出可以指定列名。 |
| `$search` | 没有跨字段的全文搜索。请使用某一列上的文本过滤，或者使用带 `contains` 过滤的搜索引擎索引。 |
| `any` 和 `all`（lambda 运算符） | 它们需要集合属性，而扁平的数据源没有。请做反规范化，或者在视图中过滤。 |
| 算术运算（`add`、`sub`、`mul`、`div`、`mod`）和 `$compute` | 运算符集合是封闭的，这样每个运算符在每种数据库上都有经过测试的含义（技术需求中的 AR-6）。请把计算出的值作为数据源的一列提供出来。 |
| `$filter` 和 `$orderby` 中的函数（`tolower`、`toupper`、`trim`、`concat`、`substring`、`length`、`indexof`、`year`、`month`、`day`、`round`、`now`） | 原因相同。文本默认已经不区分大小写，而日期的某一部分可以是一列，或者日期上的一个范围。 |
| `groupby` **之前**的 `$apply=filter(...)` | 把它放进 `filterModel` 或 `customFilters`：与 OData 一样，它在行被分组之前过滤行。 |
| `aggregate` **之后**带过滤的 `$apply`（即 SQL 的 `HAVING`）、`topcount`、`concat`、`join`、`compute`、`rollup` | 一个分组请求只有一个层级和五种聚合，而 `filterModel` 总是在聚合之前过滤行。请在查询之后再过滤分组。 |
| `countdistinct`、`aggregate` 内部的 `$count`、自定义聚合 | 聚合集合是封闭的：`sum`、`min`、`max`、`avg`、`count`。 |
| `$batch`、`$format`、`$metadata`、`$value`、动作和函数 | 它们关乎传输和服务，而不是查询。Craticula 编译查询，没有服务层。 |

## 下一步 {#next}

- 这些示例所依赖的规则：[语义](semantics.html)。
- schema 的每一项设置：[GridSchema 参考](grid-schema.html)。
- 在真实数据库上运行同样的请求：[C# 快速入门](quickstart-csharp.html)。
