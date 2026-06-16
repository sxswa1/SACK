# Contains all project configs
import os
import sys
from pathlib import Path

SACK_ROOT = Path(__file__).resolve().parent.parent
if str(SACK_ROOT) not in sys.path:
    sys.path.insert(0, str(SACK_ROOT))

from sack.paths import (
    EDA_COMPETITION_DATA_DIR,
    HISTORICAL_CASE_DIR,
    SACK_KNOWLEDGE_CURRENT_COMP_DIR,
    SACK_KNOWLEDGE_STORAGE_DIR,
    env_path,
)


class SACKKnowledgeConfig:
    ####### Data source configs #######
    # name of the data source e.g. kaggle
    data_source = 'kaggle'
    # Historical case workspaces. Each case is a SACK EDA workspace under data/eda_competitions by default.
    data_source_path = env_path(
        "SACK_HISTORICAL_CASE_PATH",
        Path(os.environ.get("SACK_SACK_KNOWLEDGE_DATA_SOURCE_PATH", HISTORICAL_CASE_DIR)),
    )

    ####### General configs #######
    # unified SACK storage root
    base_dir = str(SACK_KNOWLEDGE_STORAGE_DIR)
    knowledge_package_dir = str(Path(__file__).resolve().parent)
    column_embedding_models_dir = os.path.join(
        knowledge_package_dir,
        'kg_governor',
        'data_profiling',
        'column_embeddings',
        'pretrained_models',
    )
    # name of the corresponding repository on GraphDB to load the knowledge graph
    graphdb_repo_name = data_source
    # graphdb endpoint (defaults to http://localhost:7200 )
    graphdb_endpoint = 'http://localhost:7200'
    # graphdb server imports directory to load big graphs (defaults to ~/graphdb-import)
    graphdb_import_path = os.path.expanduser('~/graphdb-import/')
    # whether to replace existing GraphDB repository
    replace_existing_graphdb_repo = True
    # name of the database on Postgres to load the column embeddings
    column_embeddings_db_name = f'{data_source}_column_embeddings'
    # name of the database on Postgres to load the competition embeddings
    competition_embeddings_db_name = f'{data_source}_competition_embeddings'

    ####### Spark configs #######
    # whether to run Spark in local or cluster mode.
    is_spark_local_mode = True
    # number of workers (processes) to use when profiling columns. Defaults to the number of threads.
    spark_n_workers = 4
    # maximum memory in GB to be used by Spark
    spark_max_memory =  2

    ####### Data profiling configs #######
    # directory to save the generated column profiles.
    profiles_out_path = env_path(
        "SACK_SACK_KNOWLEDGE_PROFILES_OUT_PATH",
        Path(base_dir) / 'profiles' / f'{data_source}_profiles',
    )
    # whether to replace existing profiles if found
    replace_existing_profiles = False

    ####### Pipeline abstraction configs #######
    # path to generate the pipeline subgraphs before loading it to GraphDB
    pipeline_graphs_out_path = env_path(
        "SACK_SACK_KNOWLEDGE_PIPELINE_GRAPHS_PATH",
        Path(base_dir) / 'pipeline_graphs' / f'{data_source}_pipeline_graphs',
    )

    ####### data global schema construction configs #######
    # path to generate the data global schema graph before loading it to GraphDB
    data_global_schema_graph_out_path = env_path(
        "SACK_SACK_KNOWLEDGE_SCHEMA_GRAPH_OUT_PATH",
        Path(base_dir) / 'knowledge_graph' / 'data_global_schema' / f'{data_source}_data_global_schema_graph.ttl',
    )
    # column similarity thresholds. Columns having equal or higher similarities will have a relationship in the graph
    # label similarity threshold (column name)
    col_label_sim_threshold = 0.75
    # embedding similarity threshold (column values)
    col_embedding_sim_threshold = 0.75
    # boolean similarity threshold (similarity between boolean columns).
    col_boolean_sim_threshold = 0.75

    postgresql_port = 5432

    competition_semantic_weight = 0.6
    competition_data_weight = 0.4
    history_edainsight_base_path = env_path("SACK_EDA_COMPETITION_DATA_PATH", EDA_COMPETITION_DATA_DIR)
    current_comp_path = env_path("SACK_SACK_KNOWLEDGE_CURRENT_COMP_PATH", SACK_KNOWLEDGE_CURRENT_COMP_DIR)
