from typing import List, Dict, Any

EDAInsightTemplate = {
  "pre_eda":{
    "data_quality": {
      "missingness": {
        "overall_missing_rate": float,   # calculate_overall_missing_rate
        "column_missing_distribution": {  # analyze_column_missing_distribution
          "bins": List[str],
          "proportions": List[float]
        },
        "row_completeness": {   # analyze_row_completeness
          "complete_rows_ratio": float,
          "rows_with_any_missing_ratio": float,
          "high_missing_rows_ratio": float
        },
        "missing_pattern_type": {  # detect_missing_pattern_type
          "pattern_type": "MCAR/MAR/MNAR/COMPLETE/UNKNOWN",
          "confidence": float,
          "supporting_statistics": Dict[str, Any]
        }
      },
      "outliers": {
        "outlier_columns_ratio": float, # detect_outliers
        "avg_outlier_ratio": float, # detect_outliers
        "outlier_severity_distribution": { # classify_outlier_severity
          "mild_ratio": float,
          "moderate_ratio": float,
          "severe_ratio": float,
          "no_outliers_ratio": float
        }
      },
      "data_integrity": {
        "type_violation_ratio": float, # check_data_type_consistency
        "unique_violation_ratio": float # check_uniqueness_constraints
      }
    },

    "basic_distribution": {
      "numerical": {
        "skewness_profile": { # analyze_numerical_skewness
          "highly_skewed_ratio": float,
          "positive_skew_ratio": float,
          "negative_skew_ratio": float,
          "symmetric_ratio": float
        },
        "scale_characteristics": { # analyze_numerical_scale
          "wide_range_ratio": float,
          "unit_heterogeneity": bool
        },
        "normality_assessment": {# test_normality
          "normal_like_ratio": float,
          "tested_columns_count": int
        },
        "multimodal_assessment": { # detect_multimodal_distributions
          "multimodal_ratio": float,
          "tested_columns_count": int
        }
      },
      "categorical": { # analyze_categorical_cardinality + calculate_cardinality_variance
        "cardinality_pattern": {
          "low_cardinality_ratio": float,
          "medium_cardinality_ratio": float,
          "high_cardinality_ratio": float,
          "cardinality_distribution_type": str,
          "long_tail_prevalence": float,
        },
        "imbalance_profile": {# analyze_categorical_imbalance
          "balanced_ratio": float,
          "moderately_imbalanced_ratio": float,
          "highly_imbalanced_ratio": float
        },
        "rare_categories": { # detect_rare_categories
          "columns_with_rare_categories_ratio": float,
          "average_rare_category_density": float
        }
      }
    },
    "basic_dimensionality": {
      "samples_per_feature": float  # calculate_samples_per_feature
    }
},
  "deep_eda":{
    "feature_relationships": {
      "correlation_structure": {
        "correlation_strength": { # analyze_numerical_correlation_strength
          "weak_correlation_ratio": float,
          "moderate_correlation_ratio": float,
          "strong_correlation_ratio": float
        },
        "correlation_clustering": { # detect_correlation_clusters
          "cluster_count": int,
          "largest_cluster_proportion": float
        },
        "multicollinearity": {  # detect_multicollinearity_vif + detect_redundant_feature_pairs
          "high_multicollinearity_ratio": float,
          "redundant_pair_ratio": float
        }
      },
      "target_relationship": {  # analyze_feature_target_relationship_* (classification/regression)
        "feature_importance_distribution": {
          "high_importance_ratio": float,
          "importance_concentration_gini": float
        },
        "interaction_with_target": { # detect_interaction_effects
          "complex_interaction_ratio": float
        }
      },
      "interaction_patterns": {
        "synergistic_interactions": {  # quantify_synergistic_interactions
          "synergistic_interaction_ratio": float,
          "interaction_type_distribution": {
            "numerical_numerical": float,
            "categorical_numerical": float,
            "categorical_categorical": float
          }
        },
        "categorical_numerical_interaction": float, # quantify_categorical_numerical_interaction
        "conditional_dependencies": { # detect_conditional_dependencies
          "has_conditional_dependencies": bool,
          "conditional_dependency_strength": float
        },
        "nonlinear_relationships": {  # detect_nonlinear_relationships
          "nonlinear_ratio": float
        }
      }
    },

    "complexity": { # assess_dataset_complexity
      "dimensionality": {
        "samples_per_feature": float,
        "feature_interaction_potential": float
      },
      "sparsity_patterns": {
        "zero_dominated_ratio": float,
        "sparse_columns_ratio": float
      },
      "noise_level": {
        "signal_to_noise_estimate": float,
        "inherent_uncertainty": float
      }
    },
    "special_scenarios":{
      "temporal_properties": {  # analyze_time_series_properties
        "is_time_series": bool,
        "stationarity_strength": float,
        "periodicity_strength": float
      },
      "causal_properties": {  # estimate_causal_confounder_strength
            "confounder_strength": float
      },
      "spatial_properties": {  # analyze_spatial_correlation
        "spatial_correlation_strength": float
      },
      "high_cardinality_impact": {  # analyze_high_cardinality_impact
          "high_cardinality_ratio": float,
          "high_cardinality_impact": float
      }
    }
  }
}