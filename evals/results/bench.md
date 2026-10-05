# Screening scale benchmark

| Tenders | Bids | Companies | Load (s) | Screen (s) | Leads | Lead rate | Planted recall | P@100 | Peak RSS (MB) |
|---|---|---|---|---|---|---|---|---|---|
| 1,000 | 4,319 | 262 | 0.02 | 0.048 | 40 | 4.00% | 100% | 88% | 88 |
| 10,000 | 43,766 | 2,515 | 0.11 | 0.174 | 40 | 0.40% | 100% | 88% | 124 |
| 100,000 | 438,603 | 25,150 | 1.0 | 2.31 | 409 | 0.41% | 100% | 100% | 581 |

Single process, laptop CPU, pandas + networkx. Production would run the same logic as Spark jobs on Databricks (incremental, partitioned by entity/period).
