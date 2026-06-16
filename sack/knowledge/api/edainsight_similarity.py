import json

import numpy as np

from typing import Dict, List, Any, Tuple



# ====================== 1. 权重与算法配置（复用原有配置，无修改） ======================



# 知识图谱字段映射（复用原有配置，无修改）

KG_FIELD_MAPPING = {

    # pre_eda - data_quality 部分

    "eda_pre_miss_overall_rate": ("pre_eda", "data_quality", "missingness.overall_missing_rate", "float"),

    "eda_pre_miss_col_dist_props_json": ("pre_eda", "data_quality", "missingness.column_missing_distribution.proportions", "json"),

    "eda_pre_miss_row_complete_ratio": ("pre_eda", "data_quality", "missingness.row_completeness.complete_rows_ratio", "float"),

    "eda_pre_miss_row_any_ratio": ("pre_eda", "data_quality", "missingness.row_completeness.rows_with_any_missing_ratio", "float"),

    "eda_pre_miss_row_high_ratio": ("pre_eda", "data_quality", "missingness.row_completeness.high_missing_rows_ratio", "float"),

    "eda_pre_miss_pattern_type": ("pre_eda", "data_quality", "missingness.missing_pattern_type.pattern_type", "string"),

    "eda_pre_miss_pattern_conf": ("pre_eda", "data_quality", "missingness.missing_pattern_type.confidence", "float"),

    "eda_pre_outlier_col_ratio": ("pre_eda", "data_quality", "outliers.outlier_columns_ratio", "float"),

    "eda_pre_outlier_avg_ratio": ("pre_eda", "data_quality", "outliers.avg_outlier_ratio", "float"),

    "eda_pre_outlier_severity_dist_json": ("pre_eda", "data_quality", "outliers.outlier_severity_distribution", "json"),

    "eda_pre_integrity_type_viol_ratio": ("pre_eda", "data_quality", "data_integrity.type_violation_ratio", "float"),

    "eda_pre_integrity_unique_viol_ratio": ("pre_eda", "data_quality", "data_integrity.unique_violation_ratio", "float"),



    # pre_eda - basic_distribution 部分

    "eda_pre_num_skew_high_ratio": ("pre_eda", "basic_distribution", "numerical.skewness_profile.highly_skewed_ratio", "float"),

    "eda_pre_num_skew_pos_ratio": ("pre_eda", "basic_distribution", "numerical.skewness_profile.positive_skew_ratio", "float"),

    "eda_pre_num_skew_neg_ratio": ("pre_eda", "basic_distribution", "numerical.skewness_profile.negative_skew_ratio", "float"),

    "eda_pre_num_skew_sym_ratio": ("pre_eda", "basic_distribution", "numerical.skewness_profile.symmetric_ratio", "float"),

    "eda_pre_num_scale_wide_ratio": ("pre_eda", "basic_distribution", "numerical.scale_characteristics.wide_range_ratio", "float"),

    "eda_pre_num_scale_unit_hetero": ("pre_eda", "basic_distribution", "numerical.scale_characteristics.unit_heterogeneity", "boolean"),

    "eda_pre_num_norm_normal_ratio": ("pre_eda", "basic_distribution", "numerical.normality_assessment.normal_like_ratio", "float"),

    "eda_pre_num_norm_tested_count": ("pre_eda", "basic_distribution", "numerical.normality_assessment.tested_columns_count", "int"),

    "eda_pre_num_multi_ratio": ("pre_eda", "basic_distribution", "numerical.multimodal_assessment.multimodal_ratio", "float"),

    "eda_pre_num_multi_tested_count": ("pre_eda", "basic_distribution", "numerical.multimodal_assessment.tested_columns_count", "int"),

    "eda_pre_cat_card_low_ratio": ("pre_eda", "basic_distribution", "categorical.cardinality_pattern.low_cardinality_ratio", "float"),

    "eda_pre_cat_card_medium_ratio": ("pre_eda", "basic_distribution", "categorical.cardinality_pattern.medium_cardinality_ratio", "float"),

    "eda_pre_cat_card_high_ratio": ("pre_eda", "basic_distribution", "categorical.cardinality_pattern.high_cardinality_ratio", "float"),

    "eda_pre_cat_card_dist_type": ("pre_eda", "basic_distribution", "categorical.cardinality_pattern.cardinality_distribution_type", "string"),

    "eda_pre_cat_card_long_tail": ("pre_eda", "basic_distribution", "categorical.cardinality_pattern.long_tail_prevalence", "float"),

    "eda_pre_cat_imbal_balanced_ratio": ("pre_eda", "basic_distribution", "categorical.imbalance_profile.balanced_ratio", "float"),

    "eda_pre_cat_imbal_moderate_ratio": ("pre_eda", "basic_distribution", "categorical.imbalance_profile.moderately_imbalanced_ratio", "float"),

    "eda_pre_cat_imbal_high_ratio": ("pre_eda", "basic_distribution", "categorical.imbalance_profile.highly_imbalanced_ratio", "float"),

    "eda_pre_cat_rare_col_ratio": ("pre_eda", "basic_distribution", "categorical.rare_categories.columns_with_rare_categories_ratio", "float"),

    "eda_pre_cat_rare_avg_density": ("pre_eda", "basic_distribution", "categorical.rare_categories.average_rare_category_density", "float"),



    # pre_eda - basic_dimensionality 部分

    "eda_pre_dim_samples_per_feature": ("pre_eda", "basic_dimensionality", "samples_per_feature", "float"),



    # deep_eda - feature_relationships 部分

    "eda_deep_corr_weak_ratio": ("deep_eda", "feature_relationships", "correlation_structure.correlation_strength.weak_correlation_ratio", "float"),

    "eda_deep_corr_moderate_ratio": ("deep_eda", "feature_relationships", "correlation_structure.correlation_strength.moderate_correlation_ratio", "float"),

    "eda_deep_corr_strong_ratio": ("deep_eda", "feature_relationships", "correlation_structure.correlation_strength.strong_correlation_ratio", "float"),

    "eda_deep_corr_cluster_count": ("deep_eda", "feature_relationships", "correlation_structure.correlation_clustering.cluster_count", "int"),

    "eda_deep_corr_cluster_largest_prop": ("deep_eda", "feature_relationships", "correlation_structure.correlation_clustering.largest_cluster_proportion", "float"),

    "eda_deep_corr_multi_high_ratio": ("deep_eda", "feature_relationships", "correlation_structure.multicollinearity.high_multicollinearity_ratio", "float"),

    "eda_deep_corr_multi_redundant_ratio": ("deep_eda", "feature_relationships", "correlation_structure.multicollinearity.redundant_pair_ratio", "float"),

    "eda_deep_target_imp_high_ratio": ("deep_eda", "feature_relationships", "target_relationship.feature_importance_distribution.high_importance_ratio", "float"),

    "eda_deep_target_imp_gini": ("deep_eda", "feature_relationships", "target_relationship.feature_importance_distribution.importance_concentration_gini", "float"),

    "eda_deep_target_interact_complex_ratio": ("deep_eda", "feature_relationships", "target_relationship.interaction_with_target.complex_interaction_ratio", "float"),

    "eda_deep_interact_synergy_ratio": ("deep_eda", "feature_relationships", "interaction_patterns.synergistic_interactions.synergistic_interaction_ratio", "float"),

    "eda_deep_interact_synergy_type_dist_json": ("deep_eda", "feature_relationships", "interaction_patterns.synergistic_interactions.interaction_type_distribution", "json"),

    "eda_deep_interact_cat_num": ("deep_eda", "feature_relationships", "interaction_patterns.categorical_numerical_interaction", "float"),

    "eda_deep_interact_cond_deps": ("deep_eda", "feature_relationships", "interaction_patterns.conditional_dependencies.has_conditional_dependencies", "boolean"),

    "eda_deep_interact_cond_strength": ("deep_eda", "feature_relationships", "interaction_patterns.conditional_dependencies.conditional_dependency_strength", "float"),

    "eda_deep_interact_nonlinear_ratio": ("deep_eda", "feature_relationships", "interaction_patterns.nonlinear_relationships.nonlinear_ratio", "float"),



    # deep_eda - complexity 部分

    "eda_deep_complex_dim_samples_per_feature": ("deep_eda", "complexity", "dimensionality.samples_per_feature", "float"),

    "eda_deep_complex_dim_interact_potential": ("deep_eda", "complexity", "dimensionality.feature_interaction_potential", "float"),

    "eda_deep_complex_sparse_zero_ratio": ("deep_eda", "complexity", "sparsity_patterns.zero_dominated_ratio", "float"),

    "eda_deep_complex_sparse_col_ratio": ("deep_eda", "complexity", "sparsity_patterns.sparse_columns_ratio", "float"),

    "eda_deep_complex_noise_snr": ("deep_eda", "complexity", "noise_level.signal_to_noise_estimate", "float"),

    "eda_deep_complex_noise_uncertainty": ("deep_eda", "complexity", "noise_level.inherent_uncertainty", "float"),



    # deep_eda - special_scenarios 部分

    "eda_deep_special_temp_is_ts": ("deep_eda", "special_scenarios", "temporal_properties.is_time_series", "boolean"),

    "eda_deep_special_temp_stationarity": ("deep_eda", "special_scenarios", "temporal_properties.stationarity_strength", "float"),

    "eda_deep_special_temp_periodicity": ("deep_eda", "special_scenarios", "temporal_properties.periodicity_strength", "float"),

    "eda_deep_special_causal_confounder": ("deep_eda", "special_scenarios", "causal_properties.confounder_strength", "float"),

    "eda_deep_special_spatial_corr": ("deep_eda", "special_scenarios", "spatial_properties.spatial_correlation_strength", "float"),

    "eda_deep_special_high_card_ratio": ("deep_eda", "special_scenarios", "high_cardinality_impact.high_cardinality_ratio", "float"),

    "eda_deep_special_high_card_impact": ("deep_eda", "special_scenarios", "high_cardinality_impact.high_cardinality_impact", "float"),

}





MODULE_WEIGHTS = {

    "pre_eda": {

        "data_quality": 0.45,

        "basic_distribution": 0.5,

        "basic_dimensionality": 0.05

    },

    "deep_eda": {

        "feature_relationships": 0.45,

        "complexity": 0.35,

        "special_scenarios": 0.2

    }

}



FIELD_WEIGHTS = {

    # pre_eda.data_quality

    "data_quality": {

        "missingness.overall_missing_rate": 0.15,

        "missingness.column_missing_distribution.proportions": 0.075,

        "missingness.row_completeness.complete_rows_ratio": 0.025,

        "missingness.row_completeness.rows_with_any_missing_ratio":0.025,

        "missingness.row_completeness.high_missing_rows_ratio":0.025,

        "missingness.missing_pattern_type.pattern_type": 0.1,

        "missingness.missing_pattern_type.confidence": 0.025,

        "outliers.outlier_columns_ratio": 0.15,

        "outliers.avg_outlier_ratio": 0.125,

        "outliers.outlier_severity_distribution": 0.1,

        "data_integrity.type_violation_ratio": 0.1,

        "data_integrity.unique_violation_ratio": 0.075

    },

    # pre_eda.basic_distribution

    "basic_distribution": {

        "numerical.skewness_profile.highly_skewed_ratio": 0.1,

        "numerical.skewness_profile.positive_skew_ratio": 0.08,

        "numerical.skewness_profile.negative_skew_ratio": 0.08,

        "numerical.skewness_profile.symmetric_ratio": 0.08,

        "numerical.scale_characteristics.wide_range_ratio": 0.05,

        "numerical.scale_characteristics.unit_heterogeneity": 0.03,

        "numerical.normality_assessment.normal_like_ratio": 0.08,

        "numerical.normality_assessment.tested_columns_count": 0.03,

        "numerical.multimodal_assessment.multimodal_ratio": 0.08,

        "numerical.multimodal_assessment.tested_columns_count": 0.03,

        "categorical.cardinality_pattern.low_cardinality_ratio": 0.05,

        "categorical.cardinality_pattern.medium_cardinality_ratio": 0.05,

        "categorical.cardinality_pattern.high_cardinality_ratio": 0.05,

        "categorical.cardinality_pattern.cardinality_distribution_type": 0.03,

        "categorical.cardinality_pattern.long_tail_prevalence": 0.03,

        "categorical.imbalance_profile.balanced_ratio": 0.03,

        "categorical.imbalance_profile.moderately_imbalanced_ratio": 0.03,

        "categorical.imbalance_profile.highly_imbalanced_ratio": 0.03,

        "categorical.rare_categories.columns_with_rare_categories_ratio": 0.03,

        "categorical.rare_categories.average_rare_category_density": 0.03

    },

    "basic_dimensionality": {

        "samples_per_feature": 1.0

    },

    # deep_eda.feature_relationships（省略原有内容，保持与用户提供的一致）

    "feature_relationships": {

        "correlation_structure.correlation_strength.weak_correlation_ratio": 0.08,

        "correlation_structure.correlation_strength.moderate_correlation_ratio": 0.08,

        "correlation_structure.correlation_strength.strong_correlation_ratio": 0.08,

        "correlation_structure.correlation_clustering.cluster_count": 0.05,

        "correlation_structure.correlation_clustering.largest_cluster_proportion": 0.05,

        "correlation_structure.multicollinearity.high_multicollinearity_ratio": 0.08,

        "correlation_structure.multicollinearity.redundant_pair_ratio": 0.08,

        "target_relationship.feature_importance_distribution.high_importance_ratio": 0.1,

        "target_relationship.feature_importance_distribution.importance_concentration_gini": 0.1,

        "target_relationship.interaction_with_target.complex_interaction_ratio": 0.06,

        "interaction_patterns.synergistic_interactions.synergistic_interaction_ratio": 0.05,

        "interaction_patterns.synergistic_interactions.interaction_type_distribution": 0.05,

        "interaction_patterns.categorical_numerical_interaction": 0.04,

        "interaction_patterns.conditional_dependencies.has_conditional_dependencies": 0.03,

        "interaction_patterns.conditional_dependencies.conditional_dependency_strength": 0.03,

        "interaction_patterns.nonlinear_relationships.nonlinear_ratio": 0.04

    },

    "complexity": {

        "dimensionality.samples_per_feature": 0.2,

        "dimensionality.feature_interaction_potential": 0.2,

        "sparsity_patterns.zero_dominated_ratio": 0.15,

        "sparsity_patterns.sparse_columns_ratio": 0.15,

        "noise_level.signal_to_noise_estimate": 0.15,

        "noise_level.inherent_uncertainty": 0.15

    },

    "special_scenarios": {

        "temporal_properties.is_time_series": 0.15,

        "temporal_properties.stationarity_strength": 0.15,

        "temporal_properties.periodicity_strength": 0.15,

        "causal_properties.confounder_strength": 0.15,

        "spatial_properties.spatial_correlation_strength": 0.15,

        "high_cardinality_impact.high_cardinality_ratio": 0.15,

        "high_cardinality_impact.high_cardinality_impact": 0.1

    }

}



# 相似度算法函数（复用原有实现，无修改）

def relative_error_similarity(x1, x2):

    if x1 == "unknown" or x2 == "unknown":

        return 1.0 if x1 == x2 else 0.0

    try:

        x1, x2 = float(x1), float(x2)

        max_val = max(abs(x1), abs(x2), 1e-6)

        sim = 1.0 - abs(x1 - x2) / max_val

        return max(0.0, sim)

    except (ValueError, TypeError):

        return 0.0



def boolean_similarity(b1, b2):

    if b1 == "unknown" or b2 == "unknown":

        return 1.0 if b1 == b2 else 0.0

    return 1.0 if b1 == b2 else 0.0



def missing_pattern_similarity(p1, p2):

    if p1 == "unknown" or p2 == "unknown":

        return 1.0 if p1 == p2 else 0.0

    pattern_map = {"MCAR": 0, "MAR": 1, "MNAR": 2, "COMPLETE": 3, "UNKNOWN": 4}

    if p1 not in pattern_map or p2 not in pattern_map:

        return 0.0

    idx1, idx2 = pattern_map[p1], pattern_map[p2]

    if idx1 == idx2:

        return 1.0

    elif (idx1, idx2) in [(0,1), (1,0)]:

        return 0.7

    elif (idx1, idx2) in [(1,2), (2,1)]:

        return 0.5

    else:

        return 0.0



def cardinality_dist_type_similarity(t1, t2):

    if t1 == "unknown" or t2 == "unknown":

        return 1.0 if t1 == t2 else 0.0

    long_tail_types = {"long_tail", "heavy_tail", "power_law"}

    uniform_types = {"uniform", "balanced"}

    if t1 == t2:

        return 1.0

    elif (t1 in long_tail_types and t2 in long_tail_types) or (t1 in uniform_types and t2 in uniform_types):

        return 0.6

    else:

        return 0.0



def json_vector_cosine_similarity(json1, json2):

    if json1 == "unknown" or json2 == "unknown":

        return 1.0 if json1 == json2 else 0.0

    try:

        vec1 = np.array(json1) if isinstance(json1, (list, dict)) else np.array(eval(json1))

        vec2 = np.array(json2) if isinstance(json2, (list, dict)) else np.array(eval(json2))

        if isinstance(vec1, np.ndarray) and vec1.dtype == 'object':

            if isinstance(eval(json1), dict):

                keys = sorted(eval(json1).keys())

                vec1 = np.array([eval(json1)[k] for k in keys])

                vec2 = np.array([eval(json2).get(k, 0.0) for k in keys])

        dot_product = np.dot(vec1, vec2)

        norm1 = np.linalg.norm(vec1)

        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:

            return 0.0

        return dot_product / (norm1 * norm2)

    except (SyntaxError, ValueError, TypeError, KeyError) as e:

        return 0.0



# 算法映射表（复用原有配置，无修改）

ALGORITHM_MAPPING = {

    "missingness.missing_pattern_type.pattern_type": missing_pattern_similarity,

    "categorical.cardinality_pattern.cardinality_distribution_type": cardinality_dist_type_similarity,

    "numerical.scale_characteristics.unit_heterogeneity": boolean_similarity,

    "interaction_patterns.conditional_dependencies.has_conditional_dependencies": boolean_similarity,

    "temporal_properties.is_time_series": boolean_similarity,

    "missingness.column_missing_distribution.proportions": json_vector_cosine_similarity,

    "outliers.outlier_severity_distribution": json_vector_cosine_similarity,

    "interaction_patterns.synergistic_interactions.interaction_type_distribution": json_vector_cosine_similarity

}





def calculate_field_similarity(field_path: str, value1: Any, value2: Any) -> float:

    """计算单个字段的相似度（复用算法映射）"""

    algorithm = ALGORITHM_MAPPING.get(field_path, relative_error_similarity)

    return algorithm(value1, value2)



def calculate_module_similarity(module: str, data1: Dict[str, Any], data2: Dict[str, Any]) -> float:

    """计算单个模块的相似度（加权字段相似度）"""

    module_similarity = 0.0

    total_weight = 0.0

    for field_path, weight in FIELD_WEIGHTS.get(module, {}).items():

        if field_path not in data1 or field_path not in data2:

            continue

        field_sim = calculate_field_similarity(field_path, data1[field_path], data2[field_path])

        module_similarity += field_sim * weight

        total_weight += weight

    return module_similarity / total_weight if total_weight > 0 else 0.0



def calculate_eda_similarity(eda_type: str, data1: Dict[str, Dict[str, Any]], data2: Dict[str, Dict[str, Any]]) -> Tuple[float, Dict[str, float]]:

    """

    修改点：新增返回各模块的相似度

    返回：(当前EDA类型的整体相似度, 模块相似度字典)

    模块相似度结构：{module: 模块相似度, ...}

    """

    eda_similarity = 0.0

    total_weight = 0.0

    module_sims = {}  # 存储各模块的相似度



    for module, weight in MODULE_WEIGHTS.get(eda_type, {}).items():

        if module not in data1 or module not in data2:

            module_sims[module] = 0.0  # 模块无数据，相似度设为0

            continue



        # 计算模块相似度

        module_sim = calculate_module_similarity(module, data1[module], data2[module])

        module_sims[module] = module_sim



        # 累加计算EDA类型的整体相似度（原逻辑）

        eda_similarity += module_sim * weight

        total_weight += weight



    eda_similarity = eda_similarity / total_weight if total_weight > 0 else 0.0

    return eda_similarity, module_sims  # 返回EDA类型相似度+模块相似度



def calculate_stage_similarity(

        current_eda_data: Dict[str, Dict[str, Dict[str, Any]]],

        target_eda_data: Dict[str, Dict[str, Dict[str, Any]]]

) -> Dict[str, Dict[str, float]]:

    """

    剥离加权逻辑：仅计算各模块原始相似度，不做加权求和

    返回：相似度明细字典 {eda_type: {module: 模块相似度, ...}, ...}

    """

    # 仅存储各模块的原始相似度明细，移除加权相关变量

    similarity_detail = {}



    # 遍历所有EDA类型（不再依赖stage_weights，而是遍历MODULE_WEIGHTS中的类型）

    for eda_type in MODULE_WEIGHTS.keys():

        similarity_detail[eda_type] = {}  # 初始化当前EDA类型的模块相似度



        data1 = current_eda_data.get(eda_type, {})

        data2 = target_eda_data.get(eda_type, {})



        if not data1 or not data2:

            # 该EDA类型无数据，模块相似度设为0

            for module in MODULE_WEIGHTS[eda_type].keys():

                similarity_detail[eda_type][module] = 0.0

            continue



        # 仅计算原始模块相似度，不做加权求和

        _, module_sims = calculate_eda_similarity(eda_type, data1, data2)

        similarity_detail[eda_type].update(module_sims)



        # 补充MODULE_WEIGHTS中定义但未计算的模块（设为0）

        for module in MODULE_WEIGHTS[eda_type].keys():

            if module not in similarity_detail[eda_type]:

                similarity_detail[eda_type][module] = 0.0



    return similarity_detail