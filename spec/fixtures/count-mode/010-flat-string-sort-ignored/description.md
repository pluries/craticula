# 010-flat-string-sort-ignored

Count mode (CNT-2, CNT-3): flat: no filter; the sort model names a case-insensitive string column and is ignored. On MongoDB the page compile would attach a collation for that sort; the count artifact carries none (finding of the #3863 review).

Expected artifacts are those of `001-flat-no-filter-sort-ignored`: the sort, whatever its column, never changes the count.
