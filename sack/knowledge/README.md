# SACK Knowledge Module

This directory contains the SACK case knowledge construction and retrieval components.

## Main Components

- `api/`: retrieval APIs for similar cases, fields, pipelines, and CoreInsight records.
- `kg_governor/data_profiling/`: profiling for historical case datasets and EDAInsight summaries.
- `kg_governor/pipeline_abstraction/`: AST-based pipeline abstraction and CoreInsight graph generation.
- `kg_governor/data_global_schema_builder/`: global schema graph construction from generated profiles.
- `storage_utils/`: GraphDB and PostgreSQL/pgvector loading utilities.
- `build_knowledge.py`: orchestration entry point for building the SACK knowledge artifacts.
- `knowledge_config.py`: local paths and service configuration.

## Inputs

The module expects historical cases under:

```text
data/eda_competitions/<case_name>/
  rawdata/
  notebooks/
  pre_insight_extraction/eda_insight.json
  deep_insight_extraction/eda_insight.json
```

The source data and generated outputs are not included in this artifact.

## Outputs

Generated artifacts are written under `storage/` by default:

```text
storage/profiles/
storage/pipeline_graphs/
storage/knowledge_graph/
storage/current_comp/
```

These paths are ignored by git in the public artifact.

## Services

Live retrieval and full knowledge loading require:

- GraphDB for RDF graph storage and SPARQL queries.
- PostgreSQL with pgvector for vector similarity search.
- Local embedding/model files referenced by `knowledge_config.py`.

## Build

From the repository root:

```bash
python -m sack build-knowledge
```

For lightweight timing and inventory checks, see:

```bash
python scripts/profile_sack_kb_build_time.py --help
```
