# 011-unknown-sort-column-ignored

Count mode (CNT-3): flat: no filter; the sort model names a column the schema does not declare. The page compile refuses such a request; the count does not read the sort, so it compiles to the same artifact as `001-flat-no-filter-sort-ignored`.
