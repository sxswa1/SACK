from sack.runtime_support import float32_bits
import torch
import numpy as np

from sack.knowledge.kg_governor.data_profiling.profile_creators.profile_creator import ProfileCreator
from sack.knowledge.kg_governor.data_profiling.model.column_profile import ColumnProfile


class NumericalProfileCreator(ProfileCreator):

    def create_profile(self):
        self._calculate_stats()
        self._generate_embedding()

        column_profile = ColumnProfile(column_id=self.column_id, dataset_name=self.dataset_name,
                                       dataset_id=self.dataset_id, path=self.path, table_name=self.table_name,
                                       table_id=self.table_id, column_name=self.column_name, data_source=self.data_source,
                                       data_type=self.data_type.value, total_values=self.total_values_count,
                                       distinct_values_count=self.distinct_values_count,
                                       missing_values_count=self.missing_values_count, min_value=self.min,
                                       max_value=self.max, mean=self.mean, median=self.median, iqr=self.iqr,
                                       embedding=self.embedding, embedding_scaling_factor=self.embedding_scaling_factor)
        return column_profile

    def _calculate_stats(self):
        summary = self.column.describe().dropna()
        self.mean = float(summary['mean']) if 'mean' in summary.index else None
        self.std = float(summary['std']) if 'std' in summary.index else None
        self.min = float(summary['min']) if 'min' in summary.index else None
        self.max = float(summary['max']) if 'max' in summary.index else None
        self.median = float(summary['50%']) if '50%' in summary.index else None
        self.iqr = float(summary['75%'] - summary['25%']) if '75%' in summary.index else None


    def _preprocess_column_for_embedding_model(self, device='cpu') -> torch.tensor:
        non_missing = self.column.dropna()
        non_missing = non_missing.astype(np.float32)
        if len(non_missing) > 10000:
            sample = non_missing.sample(int(0.1 * len(non_missing)))
        else:
            sample = non_missing.sample(min(len(non_missing), 1000))

        bin_repr = [float32_bits(i) for i in sample.values]
        input_tensor = torch.FloatTensor(bin_repr).to(device)
        return input_tensor
