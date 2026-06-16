import sys
from pathlib import Path


parent_dir = str(Path(__file__).resolve().parent.parent)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from sack.knowledge.knowledge_config import SACKKnowledgeConfig
from sack.knowledge.kg_governor.data_profiling.profile_data import profile_data
from sack.knowledge.kg_governor.data_global_schema_builder.build_data_global_schema import build_data_global_schema
from sack.knowledge.storage_utils.graphdb_utils import (
    create_graphdb_repo,
    populate_data_global_schema_graph,
    populate_pipeline_graphs,
)
from sack.knowledge.storage_utils.embedding_store_utils import (
    create_columns_embedding_db,
    create_competition_embedding_db,
    populate_embeddings,
)


def main():
    profile_data()
    build_data_global_schema()

    create_graphdb_repo(SACKKnowledgeConfig.graphdb_endpoint, SACKKnowledgeConfig.graphdb_repo_name)

    populate_data_global_schema_graph(
        SACKKnowledgeConfig.data_global_schema_graph_out_path,
        SACKKnowledgeConfig.graphdb_repo_name,
        SACKKnowledgeConfig.graphdb_endpoint,
        SACKKnowledgeConfig.graphdb_import_path,
    )
    populate_pipeline_graphs(
        SACKKnowledgeConfig.pipeline_graphs_out_path,
        SACKKnowledgeConfig.graphdb_endpoint,
        SACKKnowledgeConfig.graphdb_repo_name,
    )

    create_columns_embedding_db(SACKKnowledgeConfig.column_embeddings_db_name)
    create_competition_embedding_db(SACKKnowledgeConfig.competition_embeddings_db_name)

    populate_embeddings(
        SACKKnowledgeConfig.profiles_out_path,
        SACKKnowledgeConfig.column_embeddings_db_name,
        SACKKnowledgeConfig.competition_embeddings_db_name,
    )


if __name__ == "__main__":
    main()

