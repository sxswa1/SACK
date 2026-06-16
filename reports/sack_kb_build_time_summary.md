# SACK Case Knowledge Base Build Timing Summary

## Measurement Setup

- Branch: `test`
- Python environment: `/root/miniconda3/envs/sack_env/bin/python`
- Data source layout: `data_sources/*/notebooks` linked into matching `data/eda_competitions/*/notebooks`
- Data/profile representative case: `playground-series-s3e11`
- Pipeline abstraction representative case: `santander-customer-satisfaction`
- Target extrapolation scale: 69 TTL-backed historical cases
- Timing script: `scripts/profile_sack_kb_build_time.py`
- Full raw result: `storage/timing/sack_kb_build_time/sack_kb_build_time_result.json`
- Full generated report: `storage/timing/sack_kb_build_time/sack_kb_build_time_report.md`

## Artifact Inventory

| Item | Count / Size |
| --- | ---: |
| Historical case directories under `data/eda_competitions` | 79 |
| Cases with CSV files | 78 |
| Cases with complete pre/deep EDAInsight | 70 |
| Cases with notebooks directory | 69 |
| Cases with notebook pipeline metadata | 69 |
| Source notebook pipelines | 695 |
| Cases with pipeline TTL artifacts | 69 |
| Profile JSON files | 12,510 |
| Competition profile JSON files | 70 |
| EDAInsight profile JSON files | 123 |
| Pipeline TTL files | 669 |
| Pipeline metadata files | 667 |
| CoreInsight analysis JSON files | 617 |
| Pipeline TTL total size | 278.41 MB |

The paper-level case count of 69 corresponds to historical cases that already have pipeline TTL artifacts.

## Timed Results

| Stage | Measurement Mode | Time |
| --- | --- | ---: |
| Single-case data/metadata/EDA/column profiling | Rerun on `playground-series-s3e11` only | 142.11 s |
| Metadata + EDA profile substage | Parsed from single-case profile log | 99.18 s |
| Column profiling substage | Parsed from single-case profile log; 66 columns | 36.08 s |
| Single-case pipeline abstraction | Rerun on `santander-customer-satisfaction`; 7 source pipelines | 874.08 s |
| Pipeline abstraction per pipeline | 874.08 s / 7 processed pipelines | 124.87 s |
| Full membership/metadata schema integration | Rerun over existing profiles; column-column similarity skipped | 15.13 s |
| GraphDB schema TTL import | 21.76 MB schema TTL imported into `kaggle_timing_schema` | 12.99 s |
| GraphDB pipeline TTL upload | 669 TTL files attempted into `kaggle_timing_pipeline`; 9 upload errors observed in stdout tail due to invalid IRI values | 164.24 s |
| PostgreSQL/pgvector DB creation | Timing DBs `kaggle_timing_column_embeddings` and `kaggle_timing_competition_embeddings` | 1.24 s |
| PostgreSQL/pgvector embedding population | Existing 12,510 profile JSON files; FastText model loaded from local storage | 55.43 s |

## Extrapolation to 69 Cases

| Estimate | Value |
| --- | ---: |
| Single-case profile cost | 2.37 min |
| 69-case profile cost | 2.72 h |
| Metadata + EDA profile substage for 69 cases | 1.90 h |
| Column profiling substage for 69 cases | 41.50 min |
| Pipeline abstraction cost per source pipeline | 2.08 min |
| Pipeline abstraction estimate for 669 historical TTL artifacts | 23.20 h |
| Pipeline abstraction estimate by 69-case representative-case scaling | 16.75 h |
| Full membership/metadata schema integration | 15.13 s |
| Profile + measured schema integration estimate | 2.73 h |
| GraphDB schema import + pipeline upload | 2.95 min |
| PostgreSQL DB creation + embedding population | 56.67 s |

## Notes for Paper Wording

A defensible phrasing is:

> We measured SACK case-level profiling on one representative historical case and extrapolated it to the 69 historical cases with generated pipeline artifacts. Pipeline abstraction was measured on a source-notebook case with seven pipelines and extrapolated both by pipeline count and by case count. Full schema integration, GraphDB loading, and PostgreSQL/pgvector embedding storage were measured on the available full artifact set. GraphDB pipeline upload completed traversal of all 669 TTL files, but several historical TTL files contain invalid IRI values and were rejected by GraphDB; this is reported as partial success rather than a clean import.

## Caveats

- Pipeline abstraction cost is sensitive to notebook length, AST size, LLM latency, and retry behavior.
- The global schema timing intentionally skipped O(n^2) column-column similarity with `SACK_SKIP_SCHEMA_SIMILARITY=1`; the measured value represents membership/metadata schema integration.
- The GraphDB pipeline upload error count is taken from the captured stdout tail, so it should be treated as a lower bound on rejected TTL files unless full logs are retained.
