import hashlib
import json
import os
from typing import Dict, Optional


class EDAInsightProfile:
    """Profile model for persisted EDAInsight fields."""

    def __init__(
        self,
        eda_id: str,
        competition_id: str,
        eda_type: str,
        pre_eda_data_quality: Optional[Dict] = None,
        pre_eda_basic_distribution: Optional[Dict] = None,
        pre_eda_basic_dimensionality: Optional[Dict] = None,
        deep_eda_feature_relationships: Optional[Dict] = None,
        deep_eda_complexity: Optional[Dict] = None,
        deep_eda_special_scenarios: Optional[Dict] = None,
    ):
        self.eda_id = eda_id
        self.competition_id = competition_id
        self.eda_type = eda_type
        self.pre_eda_data_quality = pre_eda_data_quality or {}
        self.pre_eda_basic_distribution = pre_eda_basic_distribution or {}
        self.pre_eda_basic_dimensionality = pre_eda_basic_dimensionality or {}
        self.deep_eda_feature_relationships = deep_eda_feature_relationships or {}
        self.deep_eda_complexity = deep_eda_complexity or {}
        self.deep_eda_special_scenarios = deep_eda_special_scenarios or {}

    def to_dict(self) -> Dict:
        base_dict = {
            "eda_id": self.eda_id,
            "competition_id": self.competition_id,
            "eda_type": self.eda_type,
        }
        if self.eda_type == "pre_eda":
            base_dict.update(
                {
                    "pre_eda_data_quality": self.pre_eda_data_quality,
                    "pre_eda_basic_distribution": self.pre_eda_basic_distribution,
                    "pre_eda_basic_dimensionality": self.pre_eda_basic_dimensionality,
                }
            )
        else:
            base_dict.update(
                {
                    "deep_eda_feature_relationships": self.deep_eda_feature_relationships,
                    "deep_eda_complexity": self.deep_eda_complexity,
                    "deep_eda_special_scenarios": self.deep_eda_special_scenarios,
                }
            )
        return base_dict

    def save_profile(self, eda_profile_base_dir: str):
        os.makedirs(eda_profile_base_dir, exist_ok=True)
        profile_filename = f"{hashlib.md5(self.eda_id.encode()).hexdigest()}.json"
        profile_path = os.path.join(eda_profile_base_dir, profile_filename)
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=4)

    @staticmethod
    def load_profile(eda_profile_path: str) -> "EDAInsightProfile":
        with open(eda_profile_path, "r", encoding="utf-8") as f:
            profile_dict = json.load(f)
        eda_type = profile_dict.get("eda_type")
        if eda_type == "pre_eda":
            return EDAInsightProfile(
                eda_id=profile_dict.get("eda_id"),
                competition_id=profile_dict.get("competition_id"),
                eda_type=eda_type,
                pre_eda_data_quality=profile_dict.get("pre_eda_data_quality", {}),
                pre_eda_basic_distribution=profile_dict.get("pre_eda_basic_distribution", {}),
                pre_eda_basic_dimensionality=profile_dict.get("pre_eda_basic_dimensionality", {}),
            )
        return EDAInsightProfile(
            eda_id=profile_dict.get("eda_id"),
            competition_id=profile_dict.get("competition_id"),
            eda_type=eda_type,
            deep_eda_feature_relationships=profile_dict.get("deep_eda_feature_relationships", {}),
            deep_eda_complexity=profile_dict.get("deep_eda_complexity", {}),
            deep_eda_special_scenarios=profile_dict.get("deep_eda_special_scenarios", {}),
        )

    def get_eda_id(self) -> str:
        return self.eda_id

    def get_competition_id(self) -> str:
        return self.competition_id

    def get_eda_type(self) -> str:
        return self.eda_type

    def get_pre_eda_data_quality(self) -> Dict:
        return self.pre_eda_data_quality

    def get_pre_eda_basic_distribution(self) -> Dict:
        return self.pre_eda_basic_distribution

    def get_pre_eda_basic_dimensionality(self) -> Dict:
        return self.pre_eda_basic_dimensionality

    def get_deep_eda_feature_relationships(self) -> Dict:
        return self.deep_eda_feature_relationships

    def get_deep_eda_complexity(self) -> Dict:
        return self.deep_eda_complexity

    def get_deep_eda_special_scenarios(self) -> Dict:
        return self.deep_eda_special_scenarios
