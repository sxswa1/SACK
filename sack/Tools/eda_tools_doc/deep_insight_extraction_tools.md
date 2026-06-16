## analyze_numerical_correlation_strength

**Name:** analyze_numerical_correlation_strength  
**Description:** Analyze the strength of correlations between numerical columns (fixed Spearman method for consistency). Calculates the proportion of correlation pairs that are weak, moderate, or strong.  
**Applicable Situations:** Understanding feature relationships, identifying redundant features, preliminary multicollinearity detection

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.

**Required:** `data`  
**Result:** Dictionary with three metrics:
  - "weak_correlation_ratio": proportion of correlation pairs with absolute correlation <0.3
  - "moderate_correlation_ratio": proportion of correlation pairs with 0.3 ≤ absolute correlation <0.7
  - "strong_correlation_ratio": proportion of correlation pairs with absolute correlation ≥0.7  
**Notes:**
- Only considers numerical columns
- Uses fixed Spearman correlation (robust to non-normal distributions)
- Uses absolute correlation values
- Pairs with missing correlation (due to constant columns or full NaNs) are excluded
- High strong_correlation_ratio may indicate potential multicollinearity

---

## detect_correlation_clusters

**Name:** detect_correlation_clusters  
**Description:** Detect clusters of highly correlated numerical columns. Identifies groups of features that are highly correlated with each other using hierarchical clustering.  
**Applicable Situations:** Understanding feature grouping, identifying redundant feature sets, dimensionality reduction planning

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.
- `correlation_threshold`:
  - **Type:** `number`
  - **Description:** Threshold for considering two columns as correlated (absolute correlation).
  - **Default:** `0.7`

**Required:** `data`  
**Result:** Dictionary with:
  - "cluster_count": number of distinct correlation clusters found
  - "largest_cluster_proportion": proportion of columns in the largest cluster (0-1)  
**Notes:**
- Uses hierarchical clustering with average linkage
- Converts correlation matrix to distance matrix (distance = 1 - |correlation|)
- Only considers numerical columns (Spearman correlation)
- High cluster_count with small largest_cluster_proportion suggests distributed correlations
- Low cluster_count with large largest_cluster_proportion suggests one dominant correlation group
- Clustering failures fallback to each column as individual cluster

---

## detect_multicollinearity_vif

**Name:** detect_multicollinearity_vif  
**Description:** Detect multicollinearity using Variance Inflation Factor (VIF). VIF measures how much the variance of a regression coefficient is inflated due to multicollinearity.  
**Applicable Situations:** Regression analysis preparation, linear model feature selection, identifying redundant features in linear models

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.

**Required:** `data`  
**Result:** Dictionary with:
  - "high_multicollinearity_ratio": proportion of numerical columns with high multicollinearity (0-1)  
**Notes:**
- Fixed VIF threshold = 10.0 (indicates high multicollinearity)
- Requires complete data (drops rows with missing values)
- Only considers numerical columns
- High VIF features may need to be removed or transformed in linear models
- Skips columns where VIF calculation fails (returns valid ratio based on successful calculations)

---

## analyze_feature_target_relationship_classification

**Name:** analyze_feature_target_relationship_classification  
**Description:** Analyze the relationship between numerical features and target for classification problems using ANOVA F-values.  
**Applicable Situations:** Classification problem analysis, feature importance assessment, feature selection for classification

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing both features and target.
- `target_column`:
  - **Type:** `string`
  - **Description:** The name of the target column.

**Required:** `data`, `target_column`  
**Result:** Dictionary with:
  - "high_importance_ratio": proportion of features with importance > 5× average importance (0-1)
  - "importance_concentration_gini": Gini coefficient of feature importance distribution (0=equal, 1=concentrated)  
**Notes:**
- Uses ANOVA F-test for feature importance calculation
- Only considers numerical features (categorical features require encoding first)
- Missing values are filled with column means
- High importance_concentration_gini indicates predictive power is concentrated in few features
- High high_importance_ratio indicates many features are strongly related to target
- F-test failure returns 0.0 for both metrics

---

## analyze_feature_target_relationship_regression

**Name:** analyze_feature_target_relationship_regression  
**Description:** Analyze the relationship between numerical features and target for regression problems using F-statistics.  
**Applicable Situations:** Regression problem analysis, feature importance assessment, feature selection for regression

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing both features and target.
- `target_column`:
  - **Type:** `string`
  - **Description:** The name of the target column.

**Required:** `data`, `target_column`  
**Result:** Dictionary with:
  - "high_importance_ratio": proportion of features with importance > 5× average importance (0-1)
  - "importance_concentration_gini": Gini coefficient of feature importance distribution (0=equal, 1=concentrated)  
**Notes:**
- Uses F-regression for feature importance calculation
- Falls back to absolute correlation if F-test fails
- Only considers numerical features
- Missing values are filled with column means
- High importance_concentration_gini indicates predictive power is concentrated in few features
- High high_importance_ratio indicates many features are strongly predictive of the target

---

## detect_interaction_effects

**Name:** detect_interaction_effects  
**Description:** Detect potential interaction effects between numerical features using decision trees.  
**Applicable Situations:** Feature engineering planning, identifying complex relationships, model selection (tree-based vs linear)

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing both features and target.
- `target_column`:
  - **Type:** `string`
  - **Description:** The name of the target column.
- `problem_type`:
  - **Type:** `string`
  - **Description:** Type of problem.
  - **Enum:** `classification` | `regression`
  - **Default:** `classification`

**Required:** `data`, `target_column`  
**Result:** Dictionary with:
  - "complex_interaction_ratio": estimated proportion of complex feature interactions (0-1)  
**Notes:**
- Uses fixed decision tree parameters (max_depth=5, random_state=42) for consistency
- Decision tree feature importance distribution serves as proxy for interaction complexity
- Low Gini coefficient of feature importance suggests more evenly distributed interactions
- Only considers numerical features
- Missing values are filled with column means
- This is a heuristic measure (not definitive) – use as exploratory indicator

---

## detect_nonlinear_relationships

**Name:** detect_nonlinear_relationships  
**Description:** Detect nonlinear relationships between numerical features and target by comparing linear and tree-based model performance.  
**Applicable Situations:** Model selection (linear vs tree-based), understanding relationship complexity, feature engineering planning

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing both features and target.
- `target_column`:
  - **Type:** `string`
  - **Description:** The name of the target column.
- `problem_type`:
  - **Type:** `string`
  - **Description:** Type of problem.
  - **Enum:** `classification` | `regression`
  - **Default:** `classification`

**Required:** `data`, `target_column`  
**Result:** Dictionary with:
  - "nonlinear_ratio": estimated proportion of nonlinear relationships (0-1)  
**Notes:**
- Fixed model parameters for consistency (Logistic/Linear Regression, Decision Tree max_depth=5)
- Compares in-sample performance (accuracy for classification, R² for regression)
- Nonlinear ratio = normalized performance improvement of tree model over linear model
- Only considers numerical features
- Missing values are filled with column means
- High nonlinear_ratio (>0.5) suggests tree-based models may outperform linear models

---

## detect_redundant_feature_pairs

**Name:** detect_redundant_feature_pairs  
**Description:** Detect pairs of highly redundant numerical features using fixed Spearman correlation threshold.  
**Applicable Situations:** Feature selection, dimensionality reduction, removing redundant information

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.

**Required:** `data`  
**Result:** Dictionary with:
  - "redundant_pair_ratio": proportion of all possible numerical feature pairs that are redundant (0-1)  
**Notes:**
- Fixed Spearman correlation threshold = 0.9 (strong redundancy)
- Only considers numerical columns
- Uses upper triangle of correlation matrix (avoids duplicate pairs)
- Pairs with missing correlation values are excluded
- High redundant_pair_ratio (>0.3) suggests significant feature redundancy

---

## estimate_feature_interaction_potential

**Name:** estimate_feature_interaction_potential  
**Description:** Estimate the potential for feature interactions in the dataset using unsupervised correlation structure analysis.  
**Applicable Situations:** Feature engineering planning, model complexity assessment, understanding feature relationships

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.

**Required:** `data`  
**Result:** A float value between 0 and 1 representing feature interaction potential (0=low, 1=high)  
**Notes:**
- Simplified unsupervised logic: low average feature correlation = high interaction potential
- Only considers numerical columns (drops rows with missing values)
- Requires at least 2 numerical columns and 10 valid samples
- Returns 0.0 for insufficient data, 0.5 for ambiguous correlation structure
- High values (>0.7) suggest complex feature engineering (e.g., interaction terms) may be beneficial

---

## analyze_sparsity

**Name:** analyze_sparsity  
**Description:** Combined analysis of zero-dominated and sparse columns (fixed thresholds for consistency).  
**Applicable Situations:** Data quality assessment, feature selection, identifying sparse data patterns

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.

**Required:** `data`  
**Result:** Dictionary with:
  - "zero_dominated_ratio": proportion of numerical columns with ≥90% zero values (0-1)
  - "sparse_columns_ratio": proportion of columns with ≤10% non-zero/non-empty values (0-1)  
**Notes:**
- Zero-dominated columns: numeric columns with ≥90% zero values (after dropping NaNs)
- Sparse columns: ≤10% non-zero (numeric) or non-empty (non-numeric) values (including NaNs)
- Returns 0.0 ratios for empty datasets or no columns
- Sparse columns may be candidates for removal unless domain-relevant (e.g., transaction data)

---

## estimate_signal_to_noise

**Name:** estimate_signal_to_noise  
**Description:** Estimate the signal-to-noise ratio in the dataset using fixed PCA method.  
**Applicable Situations:** Data quality assessment, model selection, understanding data clarity

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.

**Required:** `data`  
**Result:** A float value representing estimated signal-to-noise ratio (capped at 10.0, higher = more signal)  
**Notes:**
- Fixed PCA parameters: StandardScaler preprocessing, max 5 components
- Signal = explained variance of first 2 PCA components; Noise = explained variance of remaining components
- Only considers numerical columns (drops rows with missing values)
- Default return value = 2.5 (moderate signal) for insufficient data (<2 numeric columns or <10 samples)
- High SNR (>5.0) suggests clean, informative data; Low SNR (<1.0) suggests noisy data

---

## estimate_inherent_uncertainty

**Name:** estimate_inherent_uncertainty  
**Description:** Estimate the inherent uncertainty in the dataset using entropy-based method (supervised) or feature diversity (unsupervised).  
**Applicable Situations:** Setting model expectations, understanding data predictability, project planning

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.
- `target_column`:
  - **Type:** `string`
  - **Description:** Target column for supervised estimation. If None, uses unsupervised feature diversity.
  - **Default:** `None`

**Required:** `data`  
**Result:** A float value between 0 and 1 representing inherent uncertainty (0=low, 1=high)  
**Notes:**
- Supervised mode (with target): Normalized entropy of target distribution (discretized for numeric targets)
- Unsupervised mode (no target): Average unique value ratio across top 10 columns
- Returns 0.1 for empty datasets, 0.5 for insufficient target samples (<5)
- High uncertainty (>0.7) suggests lower predictability; Low uncertainty (<0.3) suggests more predictable data

---

## calculate_samples_per_feature

**Name:** calculate_samples_per_feature  
**Description:** Calculate the ratio of valid samples to valid features (n_samples / n_features) - core dimensionality metric for preliminary data exploration.  
**Applicable Situations:** Preliminary dimensionality assessment, data cleaning planning, overfitting risk pre-judgment

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.
- `target_column`:
  - **Type:** `string`
  - **Description:** Target column name (excluded from feature count to get pure feature dimensionality).
  - **Default:** `None`

**Required:** `data`  
**Result:** A float value representing the samples per feature ratio (e.g., 10.5 means 10.5 samples per feature on average; rounded to 4 decimal places)  
**Notes:**
- Valid samples: Rows with at least one non-null value (excludes all-null rows)
- Valid features: Columns with at least one non-null value (excludes all-null columns)
- Target column is automatically excluded from feature count if provided (avoids target-included dimensionality bias)
- Returns 0.0 for empty datasets, datasets with no valid features, or no valid samples
- Low ratios (<10): High overfitting risk, suggest prioritizing feature cleaning (e.g., remove redundant/empty columns)
- High ratios (>100): Low dimensionality pressure, simple models may suffice
- Pure preliminary exploration tool: No data modification, only raw statistical calculation

---

## assess_dataset_complexity

**Name:** assess_dataset_complexity  
**Description:** Perform simplified dataset complexity assessment by integrating core metrics.  
**Applicable Situations:** Overall dataset evaluation, project planning, comparing datasets

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.
- `target_column`:
  - **Type:** `string`
  - **Description:** Target column for supervised complexity metrics.
  - **Default:** `None`

**Required:** `data`  
**Result:** Dictionary with three main complexity dimensions:
  - "dimensionality": samples_per_feature (float), feature_interaction_potential (0-1)
  - "sparsity_patterns": zero_dominated_ratio (0-1), sparse_columns_ratio (0-1)
  - "noise_level": signal_to_noise_estimate (float), inherent_uncertainty (0-1)  
**Notes:**
- It reuse the following core utility tools to avoid duplicate calculations:
  - 'calculate_samples_per_feature' (sample feature ratio)
  - 'estimate_feature_interaction_potential'  (feature interaction potential)
  - 'analyze_sparsity' (sparsity metric)
  - 'estimate_signal_to_noise' (signal-to-noise ratio)
  - 'estimate_inherent_uncertainty' (inherent uncertainty)
- Provides holistic view of dataset complexity (no redundant calculations)
- High complexity across dimensions suggests need for sophisticated modeling
- Use individual sub-metrics for targeted insights (e.g., sparsity for feature selection)
- Empty datasets return default low-complexity values

---

## quantify_synergistic_interactions

**Name:** quantify_synergistic_interactions  
**Description:** Quantify synergistic interactions between features using fixed heuristic methods.  
**Applicable Situations:** Feature engineering, model interpretability, identifying complex relationships

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.
- `target_column`:
  - **Type:** `string`
  - **Description:** Target column for supervised analysis. If None, uses unsupervised method.
  - **Default:** `None`
- `problem_type`:
  - **Type:** `string`
  - **Description:** Problem type for supervised analysis.
  - **Enum:** `classification` | `regression`
  - **Default:** `classification`

**Required:** `data`  
**Result:** Dictionary with:
  - "synergistic_interaction_ratio": estimated proportion of synergistic interactions (0-1)
  - "interaction_type_distribution": proportions of interaction types (numerical-numerical, categorical-numerical, categorical-categorical)  
**Notes:**
- Supervised mode: Uses random forest feature importance coefficient of variation as proxy
- Unsupervised mode: Uses nonlinear correlation (Pearson vs Spearman difference)
- Interaction type distribution based on column type counts (no random sampling)
- Requires at least 2 features for meaningful analysis (returns 0.0 ratio otherwise)
- High ratio (>0.5) suggests interaction terms may improve model performance

---

## detect_conditional_dependencies

**Name:** detect_conditional_dependencies  
**Description:** Detect conditional dependencies between numerical features using fixed partial correlation heuristic.  
**Applicable Situations:** Causal inference, feature selection, understanding complex relationships

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.
- `target_column`:
  - **Type:** `string`
  - **Description:** Target column for focused analysis (not used in core logic).
  - **Default:** `None`

**Required:** `data`  
**Result:** Dictionary with:
  - "has_conditional_dependencies": Boolean indicating if conditional dependencies were detected (threshold >0.3)
  - "conditional_dependency_strength": average strength of detected dependencies (0-1)  
**Notes:**
- Conditional dependency = relationship between two features depends on a third
- Uses residual-based partial correlation (regresses features on conditioner, correlates residuals)
- Samples up to 5 numerical columns for efficiency (avoids computational overhead)
- Requires at least 3 numerical columns and 10 valid samples
- Returns False and 0.0 for insufficient data
- Results are exploratory (not causal proof) – validate with domain knowledge

---

## quantify_categorical_numerical_interaction

**Name:** quantify_categorical_numerical_interaction  
**Description:** Quantify the interaction strength between categorical and numerical features using fixed heuristic.  
**Applicable Situations:** Feature engineering, model selection, identifying cross-type feature relationships

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.
- `target_column`:
  - **Type:** `string`
  - **Description:** Target column for supervised assessment (not used in core logic).
  - **Default:** `None`

**Required:** `data`  
**Result:** A float value between 0 and 1 representing categorical-numerical interaction strength (0=low, 1=high)  
**Notes:**
- Uses "grouped variance ratio" heuristic: category-wise numerical distribution差异
- Samples up to 5 categorical-numerical pairs for efficiency
- High strength (>0.4) suggests need for cross-type interaction features (e.g., cat×num)
- Returns 0.0 if no categorical or numerical features exist
- Robust to missing values (automatically dropped in group calculations)

---

## analyze_time_series_properties

**Name:** analyze_time_series_properties  
**Description:** Simplified time series property analysis (stationarity and periodicity).  
**Applicable Situations:** Time series modeling, forecasting method selection, temporal pattern recognition

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame (potential time series data).
- `time_column`:
  - **Type:** `string`
  - **Description:** Name of time column (auto-detected if not provided).
  - **Default:** `None`

**Required:** `data`  
**Result:** Dictionary with:
  - "is_time_series": Boolean indicating if data is identified as time series
  - "stationarity_strength": Stationarity score (0=non-stationary, 1=perfectly stationary)
  - "periodicity_strength": Periodicity score (0=no periodicity, 1=strong periodicity)  
**Notes:**
- Auto-detects time columns (datetime type or name containing lat/lon/coord/x/y)
- Stationarity: Based on ADF test (p-value converted to 0-1 score)
- Periodicity: Based on ACF (Auto-Correlation Function) peak strength
- Samples up to 3 numerical columns for aggregate scores
- Non-stationary data (>0.5) suggests need for differencing/normalization
- Strong periodicity (>0.6) suggests need for seasonal decomposition

---

## analyze_spatial_correlation

**Name:** analyze_spatial_correlation  
**Description:** Simplified spatial correlation analysis (distance-based similarity).  
**Applicable Situations:** Spatial data modeling, geospatial feature engineering, clustering analysis

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame (potential spatial data with coordinates).
- `spatial_cols`:
  - **Type:** `List[string]`
  - **Description:** List of spatial coordinate columns (e.g., ["lat", "lon"]). Auto-detected if not provided.
  - **Default:** `None`

**Required:** `data`  
**Result:** A float value between 0 and 1 representing spatial correlation strength (0=no spatial pattern, 1=strong clustering)  
**Notes:**
- Auto-detects spatial columns (name contains lat/lon/coord/x/y)
- Uses Euclidean distance and numerical feature similarity to quantify spatial pattern
- Samples up to 1000 rows to avoid computational overload
- High spatial correlation (>0.5) suggests need for spatial features (e.g., distance to centroid)
- Returns 0.0 if no valid spatial coordinates or numerical features exist

---

## estimate_causal_confounder_strength

**Name:** estimate_causal_confounder_strength  
**Description:** Simplified estimation of causal confounder strength (residual-based partial correlation).  
**Applicable Situations:** Causal inference tasks, treatment effect estimation, confounding variable identification

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing treatment, outcome, and potential confounders.
- `target_column`:
  - **Type:** `string`
  - **Description:** Outcome column (Y) in causal analysis.
- `treatment_column`:
  - **Type:** `string`
  - **Description:** Treatment column (X) in causal analysis.

**Required:** `data`, `target_column`, `treatment_column`  
**Result:** A float value between 0 and 1 representing confounder strength (0=no confounders, 1=strong confounders)  
**Notes:**
- Confounder strength = difference between raw treatment-outcome correlation and partial correlation (controlling confounders)
- Uses numerical columns as potential confounders (automatically selected)
- Requires at least 30 valid samples for treatment and outcome columns
- High confounder strength (>0.4) suggests need for causal adjustment (e.g., propensity score matching)
- Results are heuristic; use as exploratory indicator for causal analysis

---

## analyze_high_cardinality_impact

**Name:** analyze_high_cardinality_impact  
**Description:** Analyze the proportion and impact of high-cardinality categorical features (fixed threshold: ≥20 unique values).  
**Applicable Situations:** Categorical feature engineering, encoding strategy selection, high-cardinality data handling

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.
- `target_column`:
  - **Type:** `string`
  - **Description:** Target column for supervised impact assessment. If None, uses unsupervised method.
  - **Default:** `None`

**Required:** `data`  
**Result:** Dictionary with:
  - "high_cardinality_ratio": proportion of categorical columns that are high-cardinality (0-1)
  - "high_cardinality_impact": estimated impact of high-cardinality features on modeling (0-1)  
**Notes:**
- Fixed high-cardinality threshold: ≥20 unique values
- Supervised mode: Uses decision tree feature importance to quantify impact
- Unsupervised mode: Uses unique value ratio variance to quantify impact
- Samples up to 5 high-cardinality columns to avoid computational overload
- High impact (>0.5) suggests need for specialized encoding (e.g., Target Encoding, Embedding)