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

SACK automatically loads `.env` from the repository root when the package is
imported, including CLI and direct Python API use. Existing process environment
variables take precedence. Create your local configuration once:

```bash
cp .env.example .env
```

Edit `.env` to set the TuGraph connection, graph name and existing account
password. The template selects `tugraph`; without backend configuration, the
default remains `graphdb`. `.env` is ignored by Git. No manual `source` or
`export` is needed. The file is located relative to the installed source, not
the current working directory, and changes take effect in a new process.
PostgreSQL/pgvector and model assets are still needed for case retrieval;
model API credentials continue to use `sack/api_key.txt`.

Model names are configured independently in `.env`:

```dotenv
SACK_MODEL_GENERAL=qwen-plus
SACK_MODEL_CODER=qwen3.7-plus
SACK_MODEL_VISION=qwen3.6-flash
SACK_MODEL_EMBEDDING=text-embedding-v3
```

Reader, Planner, Reviewer, Summarizer, Retriever and knowledge extraction inherit
`GENERAL`; Developer, debugging and LLM-assisted tests inherit `CODER`.
Optional `SACK_MODEL_READER/PLANNER/REVIEWER/SUMMARIZER/RETRIEVER/KNOWLEDGE/DEVELOPER/DEBUG/TEST`
overrides are listed in `.env.example`. Explicit constructor model arguments
still win. The legacy knowledge embedding client has its own
`SACK_MODEL_KNOWLEDGE_EMBEDDING` setting and keeps its existing default.
Endpoints remain in `sack/api_key.txt`: line 2 for general text/embeddings, line 3
for code/debug/test and line 4 for vision. Routing follows the caller's role,
even when several roles use the same model ID. These settings select models;
they do not adapt provider-specific request parameters automatically.
Changing the tool embedding model requires compatible 1024-dimensional vectors
and rebuilding the affected Chroma cache before reuse. Restart the process
after editing configuration.

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

## Experiment report MCP

For client setup, see the [WorkBuddy and Codex configuration guide](docs/mcp-client-setup.md),
including HTTPS bearer authentication, connection checks and troubleshooting.

Expose completed reports to WorkBuddy, Codex and other MCP clients using the
read-only service in [the MCP deployment guide](docs/mcp-reports.md). Install
`requirements-mcp.txt` in a separate Python 3.10+ environment; the service does
not need the training stack or database credentials. Streamable HTTP supports
independent concurrent clients; stdio is also available.

The MCP lists the existing `data/competitions/<competition>/` directories,
including tasks without final reports. New `python -m sack run` executions
reuse those workspaces and save completion metadata beside `research_report.md`.
Lightweight report snapshots retain older versions without copying the project.
Only a successful pipeline return with a report generated in that same run
publishes a new report. Restored historical reports retain their source and
acceptance evidence; EDA status alone does not prove pipeline completion.
Server deployments update the fixed repository in place using Git. Generated
data, reports, EDA process state and credentials stay out of source control.

## Artifact Notes

This release is intended for code inspection, reproducibility review, and independent setup. Large generated assets can be rebuilt from user-provided data with the commands above.
