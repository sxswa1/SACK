import os
import json
import hashlib
from sack.knowledge.kg_governor.data_profiling.utils import generate_competition_id
import numpy as np

class CompetitionProfile:
    def __init__(self, competition_id: str,
                 competition_name: str,
                 data_source: str,
                 overview: str,
                 data_description: str,
                 overview_embedding: list = None,
                 data_description_embedding: list = None,
                 overview_embedding_scaling_factor: float = None,
                 data_description_embedding_scaling_factor: float = None,
                 structured_elements: dict = None):
        self.competition_id = competition_id
        self.competition_name = competition_name
        self.data_source = data_source
        self.overview = overview
        self.data_description = data_description
        self.overview_embedding = overview_embedding
        self.data_description_embedding = data_description_embedding
        self.overview_embedding_scaling_factor = overview_embedding_scaling_factor
        self.data_description_embedding_scaling_factor = data_description_embedding_scaling_factor
        self.structured_elements = structured_elements
    def to_dict(self):
        return {
            'competition_id': self.competition_id,
            'competition_name': self.competition_name,
            'data_source': self.data_source,
            'overview': self.overview,
            'data_description': self.data_description,
            'overview_embedding': self.overview_embedding,
            'data_description_embedding': self.data_description_embedding,
            'overview_embedding_scaling_factor': self.overview_embedding_scaling_factor,
            'data_description_embedding_scaling_factor': self.data_description_embedding_scaling_factor,
            'structured_elements': self.structured_elements
        }

    def save_profile(self, competition_profile_base_dir):
        os.makedirs(competition_profile_base_dir, exist_ok=True)
        profile_name = hashlib.md5(self.competition_id.encode()).hexdigest()
        with open(os.path.join(competition_profile_base_dir, f'{profile_name}.json'), 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=4)

    @staticmethod
    def load_profile(competition_profile_path):
        with open(competition_profile_path, 'r', encoding='utf-8') as f:
            profile_dict = json.load(f)
        return CompetitionProfile(
            competition_id=profile_dict.get('competition_id'),
            competition_name=profile_dict.get('competition_name'),
            data_source=profile_dict.get('data_source'),
            overview=profile_dict.get('overview'),
            data_description=profile_dict.get('data_description'),
            overview_embedding=profile_dict.get('overview_embedding'),
            data_description_embedding=profile_dict.get('data_description_embedding'),
            overview_embedding_scaling_factor=profile_dict.get('overview_embedding_scaling_factor'),
            data_description_embedding_scaling_factor=profile_dict.get('data_description_embedding_scaling_factor'),
            structured_elements=profile_dict.get('structured_elements')
        )

    def get_competition_id(self) -> str:
        return self.competition_id

    def get_competition_name(self) -> str:
        return self.competition_name

    def get_data_source(self) -> str:
        return self.data_source

    def get_overview(self) -> str:
        return self.overview

    def get_data_description(self) -> str:
        return self.data_description

    def get_overview_embedding(self) -> list:
        return self.overview_embedding

    def get_data_description_embedding(self) -> list:
        return self.data_description_embedding

    def get_overview_embedding_scaling_factor(self) -> float:
        return self.overview_embedding_scaling_factor

    def get_data_description_embedding_scaling_factor(self) -> float:
        return self.data_description_embedding_scaling_factor

    def set_overview_embedding(self, embedding: list):
        self.overview_embedding = embedding

    def set_data_description_embedding(self, embedding: list):
        self.data_description_embedding = embedding

    def set_overview_embedding_scaling_factor(self, factor: float):
        self.overview_embedding_scaling_factor = factor

    def set_data_description_embedding_scaling_factor(self, factor: float):
        self.data_description_embedding_scaling_factor = factor
