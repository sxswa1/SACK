# SACK

This repository contains the SACK artifact source code for the accompanying paper. It is a source-only release: benchmark data, generated knowledge artifacts, runtime databases, logs, API keys, and local experiment outputs are intentionally excluded.

## Project handoff

Start with the [Chinese project handoff guide](docs/project-handoff.md) for the original SACK design, code walkthroughs, GraphDB-to-TuGraph implementation boundaries, deployment, troubleshooting, and validated Titanic results. The guide distinguishes the migration baseline from this PR's shared workflow fixes and includes the later Kaggle scores.

## Contents

- `sack/`: SACK agents, prompts, tools, runtime state, command-line entry points, and core execution flow.
- `sack/knowledge/`: SACK case knowledge construction and retrieval components, including data profiling, pipeline abstraction, graph generation, GraphDB utilities, and PostgreSQL/pgvector utilities.
- `sack/Tools/`: reusable data cleaning, feature engineering, modeling, EDA, debugging, and evaluation utilities.
- `sack/Agents/`: phase agents for reading, planning, development, review, summarization, and case retrieval.
- `scripts/`: measurement and profiling scripts used for artifact reporting.
- `reports/`: small paper-supporting timing summaries. Large raw timing outputs are not included.

## Environment

Create a Python environment and install the repository requirements:

```bash
pip install -r requirements.txt
```

The full knowledge-building and live case-retrieval path additionally requires:

- Java
- GraphDB
- PostgreSQL
- pgvector
- local embedding/model assets expected by the SACK knowledge module

## Basic Commands

Run a SACK task:

```bash
python -m sack run --competition <competition_name>
```

Build the SACK case knowledge artifacts:

```bash
python -m sack build-knowledge
```

Generate EDAInsight for historical cases:

```bash
python -m sack generate-edainsights
```

## Expected Data Layout

Current tasks should be placed under:

```text
data/competitions/<competition_name>/rawdata/
```

Historical cases for knowledge construction should be placed under:

```text
data/eda_competitions/<historical_case_name>/rawdata/
data/eda_competitions/<historical_case_name>/notebooks/
```

These directories are intentionally not included in this repository.

## Artifact Notes

This release is intended for code inspection, reproducibility review, and independent setup. Large generated assets can be rebuilt from user-provided data with the commands above.
