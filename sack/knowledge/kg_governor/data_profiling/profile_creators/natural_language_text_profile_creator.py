import os
import random
import numpy as np
import pandas as pd
import torch
import fasttext

fasttext.FastText.eprint = lambda *args, **kwargs: None
from nltk.tokenize import TweetTokenizer

from sack.knowledge.kg_governor.data_profiling.profile_creators.textual_profile_creator import TextualProfileCreator
from sack.knowledge.kg_governor.data_profiling.model.table import Table
from sack.knowledge.kg_governor.data_profiling.model.column_data_type import ColumnDataType
from sack.knowledge.kg_governor.data_profiling.column_embeddings.natural_language_model import NaturalLanguageEmbeddingModel, \
    NaturalLanguageScalingModel
from sack.knowledge.kg_governor.data_profiling.column_embeddings.column_embeddings_utils import load_pretrained_model
from sack.knowledge.knowledge_config import SACKKnowledgeConfig


class NaturalLanguageTextProfileCreator(TextualProfileCreator):

    def __init__(self, column: pd.Series, table: Table, fasttext_model: fasttext.FastText):
        super().__init__(column, table)

        # set the data type and load the embedding models
        self.data_type = ColumnDataType.NATURAL_LANGUAGE_TEXT

        self.fasttext_model = fasttext_model

        embedding_model_path = os.path.join(
            SACKKnowledgeConfig.column_embedding_models_dir,
            'natural_language_text/20230113132355_natural_language_text_model_embedding_epoch_94.pt',
        )
        scaling_model_path = os.path.join(
            SACKKnowledgeConfig.column_embedding_models_dir,
            'natural_language_text/20230113132355_natural_language_text_model_scaling_epoch_94.pt',
        )

        self.embedding_model = load_pretrained_model(NaturalLanguageEmbeddingModel, embedding_model_path)
        self.scaling_model = load_pretrained_model(NaturalLanguageScalingModel, scaling_model_path)

    def _preprocess_column_for_embedding_model(self, device='cpu') -> torch.tensor:

        non_missing = self.column.dropna()
        if len(non_missing) > 10000:
            sample = non_missing.sample(int(0.1 * len(non_missing)))
        else:
            sample = non_missing.sample(min(len(non_missing), 1000))

        tokenizer = TweetTokenizer()
        input_values = []
        for text in sample.values:
            tokens = tokenizer.tokenize(text)
            tokens = random.sample(tokens, min(100, len(tokens)))
            fasttext_words = [self.fasttext_model.get_word_vector(word) for word in tokens if
                              self.fasttext_model.get_word_id(word) != -1]
            if fasttext_words:
                input_values.append(np.average(fasttext_words, axis=0))

        input_tensor = torch.FloatTensor(np.array(input_values)).to(device)
        return input_tensor

