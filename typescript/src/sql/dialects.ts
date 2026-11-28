import type { Dialect, DialectName } from "./dialect.js";
import { mssql } from "./mssql.js";
import { mysql } from "./mysql.js";
import { oracle } from "./oracle.js";
import { postgres } from "./postgres.js";
import { sqlite } from "./sqlite.js";

/** The dialects this port compiles, in the order the driver declares them: the same order the C# driver uses for its SQL dialects. */
export const DIALECTS: ReadonlyMap<DialectName, Dialect> = new Map<DialectName, Dialect>([
  ["postgres", postgres],
  ["mssql", mssql],
  ["mysql", mysql],
  ["oracle", oracle],
  ["sqlite", sqlite],
]);
