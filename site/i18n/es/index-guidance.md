---
translates: index-guidance
title: Guía de índices y bases de datos
description: Los índices y ajustes de base de datos que mantienen las consultas compiladas rápidas y exactas.
source_fingerprint: 3d3bf891b84587e5732e82a2bb52c06b0c2ee549efb1865d1fc2d889fe36ebf5
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Guía de índices y bases de datos {#index-and-database-guidance}

Craticula compila consultas; nunca crea una tabla, un índice ni una colación. Esta página enumera, para cada base de datos, lo que **usted**
debe configurar para que las consultas compiladas devuelvan las filas correctas y se ejecuten con rapidez. Las reglas que lo sustentan están en la
[semántica](semantics.html); los fixtures por base de datos que fijan las sentencias están en
[`spec/fixtures/dialect-parity`](../../spec/fixtures/dialect-parity/README.md).

A continuación aparecen dos tipos de obligación, y la diferencia importa:

- **Ruidosa:** la base de datos rechaza la sentencia (falta una colación, servidor antiguo). Se da cuenta de inmediato.
- **Silenciosa:** la sentencia se ejecuta y devuelve filas incorrectas (una columna que ignora la diferencia entre mayúsculas y minúsculas cuando no debería). Nada se lo advierte, así que
  son las que conviene leer dos veces.

## De un vistazo {#at-a-glance}

| Base de datos | Usted debe proporcionar | Si no lo hace |
|---|---|---|
| PostgreSQL | versión 12 o posterior con ICU; la colación `craticula_ci`; `timestamptz` para las fechas y horas | ruidosa en los dos primeros casos (toda comparación que no distingue mayúsculas de minúsculas falla), silenciosa con `timestamp` |
| SQL Server | colación binaria o que distinga mayúsculas de minúsculas en las columnas de agrupación; `datetime2` con hora UTC | silenciosa: `EMEA` y `emea` comparten un grupo |
| MySQL / MariaDB | colación `_bin` o `_as_cs` en las columnas que distinguen mayúsculas de minúsculas y en las de agrupación; `DATETIME` con hora UTC | silenciosa: la declaración se ignora |
| SQLite | versión 3.30.0 o posterior; fechas y horas almacenadas como `yyyy-MM-ddTHH:mm:ss.fffZ` | ruidosa para la versión, silenciosa para el texto de la fecha y hora |
| Oracle | 12.2 o posterior; identificadores entre comillas; colación binaria en las columnas de agrupación (el ajuste de sesión predeterminado) | ruidosa en los dos primeros casos, silenciosa en el último |
| MongoDB | servidor 4.2 o posterior | ruidosa: el pipeline se rechaza |
| OpenSearch / Elasticsearch | subcampos `keyword`, un normalizador para ordenar sin distinguir mayúsculas de minúsculas, un tipo numérico preciso para los decimales | silenciosa si falta un subcampo `keyword` en un filtro (ninguna fila coincide), ruidosa en una ordenación; silenciosa en el redondeo |

Todo motor necesita además que la **clave estable del esquema sea única, con a lo sumo un `NULL`**
([Deterministic paging](semantics.html#sem-6)). La mayoría de los motores permite que una restricción de unicidad admita muchos `NULL`, lo que rompe la garantía de paginación; declare la
clave `NOT NULL`. Una clave estable de texto que no distingue mayúsculas de minúsculas necesita además una colación binaria o que distinga mayúsculas de minúsculas en MySQL y en SQL
Server; de lo contrario, dos claves que solo difieren en las mayúsculas quedan empatadas.

## Índices para todas las bases de datos {#indexes-for-every-database}

- **Filtros.** Un campo de texto se compara sin distinguir mayúsculas de minúsculas de forma predeterminada ([Case sensitivity](semantics.html#sem-1)). La regla está diseñada para que un
  índice simple sobre la columna siga pudiendo usarse en la igualdad: el compilador indica una colación en la comparación en lugar de envolver la
  columna en `lower()`. Haga que el índice coincida con esa colación (más abajo). Las coincidencias de subcadena (`contains`, `endsWith`) empiezan con un
  comodín, que ningún índice B-tree ordinario puede atender; consulte cada motor.
- **Ordenación.** Toda consulta ordenada termina con la clave estable del esquema, en sentido ascendente y con los nulos al final ([Deterministic paging](semantics.html#sem-6)),
  y Craticula escribe por sí misma la posición de los nulos ([Null ordering](semantics.html#sem-3)). Un índice atiende la ordenación solo si coincide con ese
  orden exacto. En PostgreSQL, SQLite y Oracle, el orden del inicio rápido es `amount DESC NULLS FIRST, id ASC NULLS LAST`, de modo que el
  índice que coincide es `(amount DESC NULLS FIRST, id ASC NULLS LAST)`; un índice simple `(amount, id)` no coincide con una ordenación descendente.
  En SQL Server y MySQL la sentencia ordena primero por una prueba de nulos (`CASE WHEN ... IS NULL`, `ISNULL(...)`), que ningún índice de columna
  atiende, y en MongoDB la ordenación se ejecuta sobre campos auxiliares calculados. Por tanto, en esos casos indexe sus **filtros** y cuente con que la ordenación
  se realice después de ellos. Revise el plan (`EXPLAIN`) con sus propios datos; Craticula no puede conocer el tamaño de sus tablas.
- **Paginación.** `OFFSET` suele volverse más lento cuanto más profunda es la página. La exportación CSV recorre el resultado en el orden de la clave y no usa
  `OFFSET`.

## PostgreSQL {#postgresql}

Requiere PostgreSQL 12 o posterior compilado con ICU (una colación no determinista). Configuración única, en la base de datos que contiene sus tablas:

```sql
CREATE COLLATION craticula_ci (provider = icu, locale = 'und-u-ks-level2', deterministic = false);
```

Sin ella, toda `=`, `IN`, comparación de rango y `ORDER BY` que no distingue mayúsculas de minúsculas falla con una colación desconocida
([Case sensitivity](semantics.html#sem-1)).

- **La igualdad y la ordenación** en un campo de texto que no distingue mayúsculas de minúsculas nombran `craticula_ci`. Un índice creado con esa colación
  (`CREATE INDEX ... ON orders (customer COLLATE craticula_ci)`) es el que coincide; compruébelo con `EXPLAIN`.
- **`contains`, `startsWith`, `endsWith`** se compilan a `ILIKE`. Respáldelos con un índice de trigramas: `CREATE EXTENSION pg_trgm;`
  y después `CREATE INDEX ... USING gin (customer gin_trgm_ops);`.
- **Fechas:** declare las columnas `datetime` como `timestamptz`. Con un `timestamp` simple, el servidor compara a través de la zona horaria de la sesión y
  las filas se desplazan sin ningún error ([Dates and time zones](semantics.html#sem-4)).
- Las columnas de agrupación no necesitan colación: la colación predeterminada de PostgreSQL es determinista, de modo que `EMEA` y `emea` son dos grupos, como
  exige [Grouping and drill-down](semantics.html#grp-2).

## SQL Server {#sql-server}

No hace falta configurar colaciones para los filtros: la sentencia lleva `COLLATE Latin1_General_CI_AS` (o `Latin1_General_CS_AS` para un campo que usted
declaró con distinción de mayúsculas y minúsculas) en línea, de modo que ninguna de las dos direcciones depende de la colación propia de la base de datos.

- **Columnas de agrupación, obligación silenciosa.** Un `GROUP BY` y un desglose deben ser exactos ([Grouping and drill-down](semantics.html#grp-2)), y la
  sentencia no indica ninguna colación en ese punto. La colación predeterminada habitual de SQL Server (`SQL_Latin1_General_CP1_CI_AS`) no distingue mayúsculas de minúsculas, de modo que una columna
  agrupada declarada con ella pone `EMEA` y `emea` en un mismo grupo. Declare cada columna agrupable, y la clave estable si es de texto,
  con una colación binaria o que distinga mayúsculas de minúsculas. La definición de la columna es, por ejemplo:

  ```sql
  country nvarchar(100) COLLATE Latin1_General_100_BIN2 NULL
  ```

  Los filtros sobre esa columna siguen comparando sin distinguir mayúsculas de minúsculas, porque indican su propia colación en línea. El precio es
  la velocidad: una comparación que nombra una colación distinta de la de la columna normalmente no puede usar una búsqueda por índice, así que mida un
  filtro que no distingue mayúsculas de minúsculas en una columna por la que también agrupa.
- **Fechas.** `datetime2` no tiene zona horaria. Almacene la lectura en UTC; el compilador compara directamente el instante UTC con ella,
  y los resultados vuelven en UTC ([Dates and time zones](semantics.html#sem-4)).
- **Entity Framework Core:** establezca `PatternMatchFoldsCase = false` en la semántica del proveedor, salvo que la colación de todas las columnas en las que se busca
  ignore la diferencia entre mayúsculas y minúsculas; `true` envía un `LIKE` simple que, en una columna con colación binaria, coincide solo con la misma capitalización. Consulte el
  [README del adaptador](../../csharp/src/Craticula.EntityFrameworkCore/README.md).

## MySQL y MariaDB {#mysql-and-mariadb}

Allí, la distinción entre mayúsculas y minúsculas pertenece a la colación de la **columna**, que una sentencia no puede reemplazar de forma portable.

- **Los campos que no distinguen mayúsculas de minúsculas** (el valor predeterminado) funcionan en cualquier columna `_ci`, como `utf8mb4_0900_ai_ci`, y un índice simple sobre la
  columna atiende la igualdad en ellos (no una coincidencia de subcadena, que empieza con un comodín).
- **Campos que distinguen mayúsculas de minúsculas, obligación silenciosa.** Un campo declarado con `caseSensitivity: "sensitive"` necesita una colación de columna `_bin` o `_as_cs`
  (`utf8mb4_bin`, `utf8mb4_0900_as_cs`). En una columna `_ci` la declaración no tiene efecto y las comparaciones siguen sin
  distinguir mayúsculas de minúsculas; la sentencia compilada no se lo advierte.
- **Las columnas de agrupación** necesitan la misma colación binaria o `_as_cs` para obtener grupos exactos ([Grouping and drill-down](semantics.html#grp-2)):

  ```sql
  country varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin
  ```

  Una columna tiene una sola colación, de modo que una columna agrupable que se hace binaria también hace que los filtros y prefijos que no distinguen mayúsculas de minúsculas sobre esa
  misma columna pasen a distinguirlas, en silencio (la divergencia aceptada n.º 4 de GRP-2). Si necesita ambos comportamientos en un campo, decida cuál importa
  más; el compilador no puede darle ambos desde una sola columna.
- **Entity Framework Core:** igual que en SQL Server, establezca `PatternMatchFoldsCase = false` salvo que la colación de todas las columnas en las que se busca ignore la diferencia entre mayúsculas y minúsculas.
- **Fechas.** `DATETIME` no tiene zona horaria: almacene UTC. Si usa MySqlConnector, deje `DateTimeKind` en su valor predeterminado o establézcalo en UTC;
  `Local` solo etiqueta el valor y desplazaría cada instante según el desfase del servidor ([Dates and time zones](semantics.html#sem-4)).

## SQLite {#sqlite}

- **Versión 3.30.0 o posterior**, por `NULLS FIRST` / `NULLS LAST`. Una biblioteca más antigua rechaza la sentencia.
- Los campos **que no distinguen mayúsculas de minúsculas** usan `COLLATE NOCASE`, que solo ignora la diferencia entre mayúsculas y minúsculas de las letras ASCII (`É` y `é` siguen siendo distintas). Un índice
  declarado `(customer COLLATE NOCASE)` los atiende.
- **Fechas y horas, obligación silenciosa.** SQLite no tiene tipo de marca de tiempo y compara el texto carácter por carácter. Almacene cada
  `datetime` exactamente como `yyyy-MM-ddTHH:mm:ss.fffZ`, en UTC, con tres dígitos de fracción ([Dates and time zones](semantics.html#sem-4)). Cualquier otro
  ancho (`...:00Z`, `yyyy-MM-dd HH:mm:ss`) devuelve filas incorrectas sin ningún error.
- **Entity Framework Core** enlaza un `DateTime` en su propia forma `yyyy-MM-dd HH:mm:ss`, así que asigne cada fecha y hora desde y hacia el
  texto almacenado en su `DbContext`. Sin la asignación, un `eq` no encuentra nada, el límite de un rango cuenta la fecha completa como posterior y
  una exportación ordenada por fecha y hora puede repetir filas. El
  [README del adaptador](../../csharp/src/Craticula.EntityFrameworkCore/README.md) tiene
  los detalles.

## Oracle {#oracle}

- **Servidor 12.2 o posterior.** Las sentencias usan `COLLATE BINARY_CI` y `COLLATE BINARY`; un servidor más antiguo las rechaza.
  Oracle documenta `COMPATIBLE >= 12.2` y `MAX_STRING_SIZE = EXTENDED` como requisito previo de la colación ligada a los datos.
- **Qué se verificó.** Las sentencias compiladas se ejecutaron contra Oracle Database Free 23.26.3 en un contenedor
  (`gvenzl/oracle-free:23.26.3-slim-faststart`, `COMPATIBLE = 23.6.0`, `MAX_STRING_SIZE = STANDARD`): los 45 fixtures de Oracle
  devuelven las filas esperadas, y la propiedad de paridad entre backends se cumple con Oracle entre ocho motores. En ese servidor, el
  operador `COLLATE` dentro de una sentencia funciona sin `EXTENDED`; solo **declarar** una colación en una columna falla
  (`ORA-43929`). Oracle 12.2 a 21c **no** se probaron: el mínimo indicado arriba es lo que dice la documentación de Oracle, no una medición.
- **Identificadores entre comillas.** Cree la tabla y todas las columnas con nombres entre comillas que coincidan exactamente con la escritura de `source` y `column`
  del esquema. Oracle convierte a mayúsculas un nombre sin comillas, y la sentencia compilada pone comillas a todos los identificadores
  (`ORA-00942` si difieren).
- **Ajustes de sesión.** Las sentencias compiladas pasan las fechas, las fechas y horas y los decimales como texto y no añaden ninguna conversión, de modo que Oracle los convierte
  según los ajustes de la sesión. Establezca `NLS_DATE_FORMAT = 'YYYY-MM-DD'`,
  `NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD"T"HH24:MI:SS.FF"Z"'` y `NLS_NUMERIC_CHARACTERS = '.,'` en la conexión; sin ellos,
  todo filtro de fecha, de fecha y hora o de decimales falla (`ORA-01861`, `ORA-01722`), y una configuración regional del cliente con coma decimal puede provocarlo
  solo en algunas máquinas.
- **Columnas de agrupación, obligación silenciosa.** Ejecute la sesión con `NLS_COMP = BINARY` y `NLS_SORT = BINARY` (los valores predeterminados de un cliente en inglés; la configuración verificada) o, en un
  servidor con `MAX_STRING_SIZE = EXTENDED`, declare cada columna agrupable y la clave estable con `COLLATE BINARY`. La colación
  predeterminada sigue a la sesión y puede ignorar la diferencia entre mayúsculas y minúsculas. La definición de la columna es, por ejemplo:

  ```sql
  "country" VARCHAR2(100) COLLATE BINARY
  ```

## MongoDB {#mongodb}

- **Servidor 4.2 o posterior**, por la etapa `$unset` que usa todo pipeline ordenado para eliminar sus campos auxiliares de posición de nulos.
- Los campos **que no distinguen mayúsculas de minúsculas** se compilan a una colación a nivel de consulta (`locale: "en"`, `strength: 2`). Un índice atiende una consulta con colación
  solo si se creó con la misma colación: `createIndex({ customer: 1 }, { collation: { locale: "en", strength: 2 } })`.
- **`contains`, `startsWith`, `endsWith`** se compilan a un `$regex` con escape (MongoDB no tiene un operador de subcadena compatible con colaciones). Una expresión regular no usa un índice con reconocimiento de colación como lo hace una igualdad, así que cuente con recorrer una colección grande y
  mida.
- **Ordenación.** La ordenación se ejecuta sobre campos auxiliares calculados que contienen la posición de los nulos, de modo que ningún índice la atiende por completo; indexe
  sus filtros ([Null ordering](semantics.html#sem-3)).
- **Las solicitudes de agrupación comparan distinguiendo mayúsculas de minúsculas.** MongoDB tiene una colación por consulta. Una solicitud de agrupación debe mantener sus
  grupos exactos, así que su pipeline no lleva colación y un filtro de usuario de la misma solicitud compara **distinguiendo** mayúsculas de minúsculas
  (la divergencia aceptada n.º 3 de GRP-2). Las demás bases de datos ignoran la diferencia entre mayúsculas y minúsculas en ese filtro.

## OpenSearch y Elasticsearch {#opensearch-and-elasticsearch}

Un solo compilador atiende a ambos. El mapeo del índice es suyo, y las consultas compiladas nombran los subcampos que declara su esquema.

- **Versión:** Elasticsearch 7.10 o posterior, OpenSearch 1.0 o posterior (por `case_insensitive` en `term` y `wildcard`).
- **Subcampo `keyword`, silencioso en un filtro.** Todo campo de texto que se filtra, ordena o agrupa necesita el subcampo `keyword`
  que declaró como `physical.search.keywordSubField`, un multicampo en el mapeo del índice. Si falta, un filtro sobre él
  no coincide con **ninguna fila** y no produce ningún error; solo falla una ordenación sobre él.
- **Ordenación y rango que no distinguen mayúsculas de minúsculas.** Declare `physical.search.normalizedSubField` y mapéelo como un `keyword` con un
  `normalizer` que ignore la diferencia entre mayúsculas y minúsculas. Esto cuesta espacio de índice y es la única forma de ordenar o comparar un campo de texto sin distinguir mayúsculas de minúsculas; el compilador
  se niega a compilar una solicitud de ese tipo para un campo que no declare uno.
- **Decimales.** Mapee un campo `decimal` como `scaled_float` con un `scaling_factor` suficiente, o como `keyword` si solo compara para
  la igualdad. Un mapeo `double` redondea en silencio.
- **Paginación profunda y recuentos.** Más allá de `max_result_window` (10,000 filas), el cliente pagina con un punto en el tiempo y `search_after`;
  establezca `Flavour` en `Elasticsearch` en **ambas** opciones, las de paginación profunda y las de exportación, para Elasticsearch, o toda exportación
  falla con HTTP 400. El recuento total de filas por encima de 10,000 se informa como desconocido, a menos que
  opte por el recuento exacto, que cuenta todas las coincidencias en cada primera solicitud.
- **`contains`** es un comodín sobre el campo `keyword`; un comodín inicial recorre el diccionario de términos, así que mídalo en índices grandes.

## Lo que queda fuera de esta página {#what-stays-out-of-this-page}

El ajuste por motor (particiones, índices de cobertura, número de shards) depende de sus datos y de su carga de trabajo. Las sentencias compiladas están en
los [fixtures de conformidad](../../spec/fixtures/), una carpeta por caso, con el texto
exacto que recibe cada base de datos; ejecute `EXPLAIN` sobre ellas con sus propias tablas.
