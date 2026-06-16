import os

import pandas as pd

from sack.knowledge.kg_governor.data_profiling.profile_creators.numerical_profile_creator import NumericalProfileCreator
from sack.knowledge.kg_governor.data_profiling.model.table import Table
from sack.knowledge.kg_governor.data_profiling.model.column_data_type import ColumnDataType
from sack.knowledge.kg_governor.data_profiling.column_embeddings.numerical_model import NumericalEmbeddingModel, NumericalScalingModel
from sack.knowledge.kg_governor.data_profiling.column_embeddings.column_embeddings_utils import load_pretrained_model
from sack.knowledge.knowledge_config import SACKKnowledgeConfig


class IntProfileCreator(NumericalProfileCreator):
    
    def __init__(self, column: pd.Series, table: Table):
        super().__init__(column, table)
        
        # set the data type and load the embedding models
        self.data_type = ColumnDataType.INT

        embedding_model_path = os.path.join(SACKKnowledgeConfig.column_embedding_models_dir, 'int/20230123140419_int_model_embedding_epoch_100.pt')
        scaling_model_path = os.path.join(SACKKnowledgeConfig.column_embedding_models_dir, 'int/20230123140419_int_model_scaling_epoch_100.pt')
        
        self.embedding_model = load_pretrained_model(NumericalEmbeddingModel, embedding_model_path)
        self.scaling_model = load_pretrained_model(NumericalScalingModel, scaling_model_path)
