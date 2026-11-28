import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { CompileError } from "../src/errors.js";
import type { Dialect } from "../src/sql/dialect.js";
import { ParameterBag } from "../src/sql/params.js";
import { mssql } from "../src/sql/mssql.js";
import { mysql } from "../src/sql/mysql.js";
import { oracle } from "../src/sql/oracle.js";
import { sqlite } from "../src/sql/sqlite.js";

// Feature 014, T020 (US2-AS2, US2-AS3): the rules each dialect owns (SQL-1, SQL-3 to SQL-8, SEM-1, SEM-3, SEM-7), beyond what the fixtures reach.
const fresh = (dialect: Dialect) => new ParameterBag(dialect);

describe("quoting and placeholders (SQL-1)", () => {
  it("each dialect quotes with its own delimiter and doubles it", () => {
    assert.equal(mssql.quoteIdentifier("a]b"), "[a]]b]");
    assert.equal(mysql.quoteIdentifier("a`b"), "`a``b`");
    assert.equal(oracle.quoteIdentifier('a"b'), '"a""b"');
    assert.equal(sqlite.quoteIdentifier('a"b'), '"a""b"');
  });

  it("each dialect spells its placeholder, numbered where the engine numbers", () => {
    assert.deepEqual([0, 1].map((i) => mssql.placeholder(i)), ["@p1", "@p2"]);
    assert.deepEqual([0, 1].map((i) => oracle.placeholder(i)), [":p1", ":p2"]);
    assert.deepEqual([0, 1].map((i) => mysql.placeholder(i)), ["?", "?"]);
    assert.deepEqual([0, 1].map((i) => sqlite.placeholder(i)), ["?", "?"]);
  });
});

describe("paging and the row cap (EXP-2, GRP-6)", () => {
  it("SQL Server and Oracle bind the offset first; MySQL and SQLite the limit first", () => {
    for (const dialect of [mssql, oracle]) {
      const bag = fresh(dialect);
      assert.match(dialect.paging(20, 10, bag), /^OFFSET \S+ ROWS FETCH NEXT \S+ ROWS ONLY$/);
      assert.deepEqual(bag.values, [20, 10]);
    }
    for (const dialect of [mysql, sqlite]) {
      const bag = fresh(dialect);
      assert.equal(dialect.paging(20, 10, bag), "LIMIT ? OFFSET ?");
      assert.deepEqual(bag.values, [10, 20]);
    }
  });

  it("the row cap stands alone, with a literal zero offset on SQL Server only", () => {
    assert.equal(mssql.rowLimit(5, fresh(mssql)), "OFFSET 0 ROWS FETCH NEXT @p1 ROWS ONLY");
    assert.equal(oracle.rowLimit(5, fresh(oracle)), "FETCH FIRST :p1 ROWS ONLY");
    assert.equal(mysql.rowLimit(5, fresh(mysql)), "LIMIT ?");
    assert.equal(sqlite.rowLimit(5, fresh(sqlite)), "LIMIT ?");
  });

  it("only SQL Server groups for distinct values", () => {
    assert.deepEqual([mssql, mysql, oracle, sqlite].map((d) => d.distinctValuesUseGroupBy), [true, false, false, false]);
  });
});

describe("case sensitivity and sort keys (SEM-1, SEM-3)", () => {
  it("SQL Server collates the column both ways and emulates null position with a bucket key", () => {
    assert.equal(mssql.scalar("[n]", "eq", "x", "string", "insensitive", fresh(mssql)), "[n] COLLATE Latin1_General_CI_AS = @p1");
    assert.equal(mssql.scalar("[n]", "eq", "x", "string", "sensitive", fresh(mssql)), "[n] COLLATE Latin1_General_CS_AS = @p1");
    assert.equal(mssql.sortKey("[n]", "asc", "last", "notApplicable"), "CASE WHEN [n] IS NULL THEN 1 ELSE 0 END ASC, [n] ASC");
    assert.equal(mssql.sortKey("[n]", "desc", "first", "sensitive"), "CASE WHEN [n] COLLATE Latin1_General_CS_AS IS NULL THEN 1 ELSE 0 END DESC, [n] COLLATE Latin1_General_CS_AS DESC");
  });

  it("MySQL applies no collation and emulates null position with ISNULL", () => {
    assert.equal(mysql.scalar("`n`", "eq", "x", "string", "insensitive", fresh(mysql)), "`n` = ?");
    assert.equal(mysql.sortKey("`n`", "desc", "first", "insensitive"), "ISNULL(`n`) DESC, `n` DESC");
  });

  it("Oracle collates the column with BINARY_CI or BINARY and orders nulls natively", () => {
    assert.equal(oracle.scalar('"n"', "eq", "x", "string", "insensitive", fresh(oracle)), '"n" COLLATE BINARY_CI = :p1');
    assert.equal(oracle.sortKey('"n"', "asc", "last", "sensitive"), '"n" COLLATE BINARY ASC NULLS LAST');
  });

  it("SQLite collates the value on a comparison but the column in a set and a sort", () => {
    assert.equal(sqlite.scalar('"n"', "eq", "x", "string", "insensitive", fresh(sqlite)), '"n" = ? COLLATE NOCASE');
    assert.equal(sqlite.setMembership('"n"', false, ["a"], "string", "insensitive", fresh(sqlite)), '"n" COLLATE NOCASE IN (?)');
    assert.equal(sqlite.sortKey('"n"', "asc", "last", "insensitive"), '"n" COLLATE NOCASE ASC NULLS LAST');
  });
});

describe("the substring family (SEM-7, SQL-5)", () => {
  it("SQL Server concatenates with plus and escapes a left bracket", () => {
    const bag = fresh(mssql);
    assert.equal(mssql.substring("[n]", "anywhere", false, "[a]%", "insensitive", bag), "[n] COLLATE Latin1_General_CI_AS LIKE '%' + @p1 + '%' ESCAPE '\\'");
    assert.deepEqual(bag.values, ["\\[a]\\%"]);
  });

  it("MySQL concatenates with CONCAT and writes the escape as two backslashes", () => {
    assert.equal(mysql.substring("`n`", "start", true, "a", "insensitive", fresh(mysql)), "`n` NOT LIKE CONCAT(?, '%') ESCAPE '\\\\'");
  });

  it("Oracle collates and uses LIKE with the double bar", () => {
    assert.equal(oracle.substring('"n"', "end", false, "a", "insensitive", fresh(oracle)), `"n" COLLATE BINARY_CI LIKE '%' || :p1 ESCAPE '\\'`);
  });

  it("SQLite uses GLOB for a case-sensitive match, with its own escaping, and LIKE for a folded one", () => {
    const bag = fresh(sqlite);
    assert.equal(sqlite.substring('"n"', "anywhere", false, "a*b?[c", "sensitive", bag), `"n" GLOB '*' || ? || '*'`);
    assert.deepEqual(bag.values, ["a[*]b[?][[]c"]);
    assert.equal(sqlite.substring('"n"', "start", true, "a", "insensitive", fresh(sqlite)), `"n" NOT LIKE ? || '%' ESCAPE '\\'`);
  });
});

describe("set membership (SQL-4)", () => {
  it("every non-PostgreSQL dialect binds one parameter per value", () => {
    for (const dialect of [mssql, mysql, oracle, sqlite]) {
      const bag = fresh(dialect);
      const sql = dialect.setMembership("c", true, [1, 2, 3], "int64", "notApplicable", bag);
      assert.match(sql, /^c NOT IN \(.+, .+, .+\)$/);
      assert.deepEqual(bag.values, [1, 2, 3]);
    }
  });
});

describe("Oracle treats the empty string as NULL (SQL-7)", () => {
  it("refuses an empty value in a comparison, a substring and any member of a set, binding nothing", () => {
    const bag = fresh(oracle);
    assert.throws(() => oracle.scalar('"n"', "eq", "", "string", "insensitive", bag), CompileError);
    assert.throws(() => oracle.substring('"n"', "anywhere", false, "", "insensitive", bag), CompileError);
    assert.throws(() => oracle.setMembership('"n"', true, ["a", ""], "string", "insensitive", bag), CompileError);
    assert.deepEqual(bag.values, []);
  });

  it("says so on the engine's flag and no other", () => {
    assert.deepEqual([mssql, mysql, oracle, sqlite].map((d) => d.emptyStringIsNull), [false, false, true, false]);
  });
});

describe("instants (SEM-4)", () => {
  it("only SQLite binds instants with a fixed three-digit fraction", () => {
    assert.deepEqual([mssql, mysql, oracle, sqlite].map((d) => d.datetimeBoundsAreFixedWidth), [false, false, false, true]);
  });
});
