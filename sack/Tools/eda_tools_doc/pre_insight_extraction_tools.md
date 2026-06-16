## calculate_overall_missing_rate

**Name:** calculate_overall_missing_rate  
**Description:** Calculate the overall missing rate (percentage of missing values) in the entire dataset. This tool provides a high-level view of data completeness.  
**Applicable Situations:** Initial data quality assessment, understanding overall data completeness

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.

**Required:** `data`  
**Result:** A float value between 0 and 1 representing the overall missing rate (e.g., 0.15 means 15% of cells are missing)  
**Notes:**
- Returns 0.0 for empty DataFrames
- This metric gives a quick overview but doesn't show the distribution of missing values
- High missing rates (>0.3) may indicate serious data quality issues
- Always use with column-wise missing analysis for a complete picture

---

## analyze_column_missing_distribution

**Name:** analyze_column_missing_distribution  
**Description:** Analyze how missing values are distributed across columns. This tool categorizes columns based on their missing rates and shows the proportion of columns in each category.  
**Applicable Situations:** Understanding missing value patterns, identifying columns with excessive missing data

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.
- `bins`:
  - **Type:** `array`
  - **Description:** Bin edges for categorizing missing rates. Each value should be between 0 and 1.
  - **Default:** `[0.0, 0.1, 0.3, 0.5, 1.0]`

**Required:** `data`  
**Result:** Dictionary with two keys: "bins" (list of bin labels) and "proportions" (list of column proportions in each bin)  
**Notes:**
- Useful for identifying if missingness is concentrated in a few columns or spread across many
- Default bins: 0-10%, 10-30%, 30-50%, 50-100% missing
- Columns with >50% missing may need special treatment or removal
- Adjust bins based on dataset size and domain knowledge

---

## detect_missing_pattern_type

**Name:** detect_missing_pattern_type  
**Description:** Detect the type of missing data pattern: Missing Completely At Random (MCAR), Missing At Random (MAR), or Missing Not At Random (MNAR). Understanding missingness mechanism is crucial for selecting appropriate imputation methods.  
**Applicable Situations:** Data quality assessment, imputation strategy selection, understanding data collection issues

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.
- `significance_level`:
  - **Type:** `number`
  - **Description:** Significance level for statistical tests in correlation-based detection.
  - **Default:** `0.05`

**Required:** `data`  
**Result:** Dictionary with:
  - "pattern_type": Detected pattern (MCAR, MAR, MNAR, COMPLETE, or UNKNOWN)
  - "confidence": Confidence score between 0 and 1
  - "supporting_statistics": Additional statistics supporting the conclusion (missing_rate, significant_correlation_ratio/column_missing_variation)  
**Notes:**
- MCAR: Missingness is independent of both observed and unobserved data
- MAR: Missingness depends only on observed data
- MNAR: Missingness depends on unobserved data (most problematic)
- Uses correlation-based test (Mann-Whitney U) to check if missingness correlates with observed values
- For datasets with <2 numeric columns, uses heuristic based on column missing rate variation
- Results should be interpreted cautiously as missing mechanism detection is challenging
- Higher confidence scores indicate more reliable pattern identification

---

## analyze_row_completeness

**Name:** analyze_row_completeness  
**Description:** Analyze row-level data completeness. This tool calculates what proportion of rows are complete, have any missing values, or have high missing rates.  
**Applicable Situations:** Understanding missing value patterns at row level, deciding between column-wise and row-wise imputation

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.

**Required:** `data`  
**Result:** Dictionary with three metrics:
  - "complete_rows_ratio": proportion of rows with no missing values
  - "rows_with_any_missing_ratio": proportion of rows with at least one missing value
  - "high_missing_rows_ratio": proportion of rows with >50% missing values  
**Notes:**
- High "complete_rows_ratio" (>0.9) suggests imputation may be straightforward
- High "high_missing_rows_ratio" suggests many rows may need to be removed
- Helps decide between row-wise vs column-wise imputation strategies
- Consider domain implications of removing rows with high missing rates

---

## detect_outliers

**Name:** detect_outliers  
**Description:** Detect outliers in numerical columns using the IQR (Interquartile Range) method. This tool provides aggregate metrics of outlier contamination across all numerical columns.  
**Applicable Situations:** Data quality assessment, anomaly detection, data cleaning preparation

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.
- `threshold`:
  - **Type:** `number`
  - **Description:** Multiplier for IQR (typical: 1.5 for moderate outliers).
  - **Default:** `1.5`

**Required:** `data`  
**Result:** Dictionary with:
  - "outlier_columns_ratio": Proportion of numerical columns containing outliers
  - "total_outliers": Total number of outlier instances across all numerical columns
  - "avg_outlier_ratio": Average proportion of outliers per numerical column  
**Notes:**
- IQR method is robust to non-normal distributions, ideal for general use
- Automatically processes all numerical columns (int64, float64)
- Requires at least 4 non-missing values per column for reliable detection
- Columns with no variability (IQR=0) are treated as having no outliers
- Results are aggregate (no column-level details) for efficient similarity comparison

---

## classify_outlier_severity

**Name:** classify_outlier_severity  
**Description:** Classify the severity of outlier contamination in numerical columns based on outlier proportion. Helps prioritize outlier treatment strategies.  
**Applicable Situations:** Assessing outlier impact, planning outlier handling strategies

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.

**Required:** `data`  
**Result:** Dictionary with proportions of numerical columns in each severity category:
  - "mild_ratio": columns with <5% outliers
  - "moderate_ratio": columns with 5-20% outliers
  - "severe_ratio": columns with >20% outliers
  - "no_outliers_ratio": columns with no outliers  
**Notes:**
- Uses IQR method with 1.5 multiplier for consistent outlier detection
- Severity thresholds are optimized for similarity comparison across datasets
- Mild outliers: Typically retain; Moderate: Consider handling; Severe: Investigate data quality
- Columns with <4 non-missing values are classified as "no_outliers"

---

## check_data_type_consistency

**Name:** check_data_type_consistency  
**Description:** Check for data type inconsistencies within columns. Identifies columns with mixed data types (e.g., strings in numeric columns) that may affect analysis.  
**Applicable Situations:** Data quality validation, identifying parsing or ingestion issues

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.

**Required:** `data`  
**Result:** Dictionary with:
  - "type_violation_ratio": Proportion of columns with type inconsistencies
**Notes:**
- Common issues detected: strings in numeric columns, mixed string/numeric in object columns
- Empty or all-NA columns are not considered problematic
- Type inconsistencies often indicate data entry or parsing errors
- Aggregate ratio supports efficient similarity comparison between datasets

---

## check_uniqueness_constraints

**Name:** check_uniqueness_constraints  
**Description:** Check candidate ID/Key columns for duplicate values. Identifies potential violations of uniqueness constraints.  
**Applicable Situations:** Data integrity validation, identifying potential primary key columns

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.

**Required:** `data`  
**Result:** Dictionary with:
  - "unique_violation_ratio": Proportion of candidate ID columns with duplicate values
  - "duplicate_columns_ratio": Same as unique_violation_ratio (for field compatibility)  
**Notes:**
- Automatically identifies candidate ID columns (names containing 'id', 'key', 'code' in any case)
- If no candidate columns are found, returns 0.0 for both metrics
- Duplicates are determined by non-NA values (NA values are not counted as duplicates)
- Consider business context: some duplicates (e.g., transaction IDs) may be legitimate

---

## analyze_numerical_skewness

**Name:** analyze_numerical_skewness  
**Description:** Analyze skewness characteristics of numerical columns. Provides aggregate classification of distribution asymmetry for similarity comparison.  
**Applicable Situations:** Understanding data distribution shape, planning data transformations, identifying non-normal distributions

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.

**Required:** `data`  
**Result:** Dictionary with:
  - "skewness_classification": Proportions of numerical columns in different skewness categories:
    - "highly_skewed_ratio": |skewness| > 1
    - "positive_skew_ratio": skewness > 0.5
    - "negative_skew_ratio": skewness < -0.5
    - "symmetric_ratio": |skewness| ≤ 0.5  
**Notes:**
- Uses Fisher-Pearson coefficient of skewness
- Requires at least 3 non-missing values per column for reliable calculation
- Highly skewed data may benefit from log or power transformations
- Aggregate proportions support efficient comparison of distribution characteristics across datasets

---

## analyze_numerical_scale

**Name:** analyze_numerical_scale  
**Description:** Analyze the scale and range characteristics of numerical columns. Identifies wide-range columns and mixed positive/negative values.  
**Applicable Situations:** Feature scaling planning, identifying columns with extreme ranges, detecting mixed units

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.

**Required:** `data`  
**Result:** Dictionary with:
  - "scale_classification":
    - "wide_range_ratio": Proportion of numerical columns with range > 1000
    - "unit_heterogeneity": Boolean indicating if any column contains both positive and negative values  
**Notes:**
- Wide-range columns may dominate distance-based algorithms (e.g., KNN)
- Unit heterogeneity affects certain transformations (e.g., log transformation for negative values)
- Automatically skips columns with <2 non-missing values
- Results focus on key scale characteristics for efficient similarity comparison

---

## test_normality

**Name:** test_normality  
**Description:** Test numerical columns for normality and provide aggregate metrics of normal-like distributions.  
**Applicable Situations:** Checking distribution assumptions, planning statistical analyses, identifying transformation needs

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.
- `alpha`:
  - **Type:** `number`
  - **Description:** Significance level for normality tests.
  - **Default:** `0.05`

**Required:** `data`  
**Result:** Dictionary with:
  - "normality_summary":
    - "normal_like_ratio": Proportion of numerical columns that follow normal distribution (p-value > alpha)
    - "tested_columns_count": Number of numerical columns with sufficient data for testing  
**Notes:**
- Uses Shapiro-Wilk test for n < 5000, falls back to D'Agostino's K^2 test for larger datasets
- Requires at least 8 non-missing values per column for meaningful testing
- "normal_like" means failing to reject the null hypothesis of normality
- Aggregate ratio supports efficient comparison of distribution characteristics across datasets

---

## detect_multimodal_distributions

**Name:** detect_multimodal_distributions  
**Description:** Detect multimodal (≥2 peaks) distributions in numerical columns using kernel density estimation. Provides aggregate metrics of multimodality.  
**Applicable Situations:** Identifying complex distributions, detecting subpopulations, understanding data heterogeneity

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.
- `bandwidth`:
  - **Type:** `number`
  - **Description:** Bandwidth for kernel density estimation. If None, uses Silverman's rule of thumb.
  - **Default:** `None`

**Required:** `data`  
**Result:** Dictionary with:
  - "multimodal_summary":
    - "multimodal_ratio": Proportion of numerical columns with multimodal distributions
    - "tested_columns_count": Number of numerical columns with sufficient data for detection  
**Notes:**
- Uses Gaussian kernel density estimation for reliable peak detection
- Requires at least 20 non-missing values and non-zero standard deviation per column
- Multimodal distributions may indicate mixed subpopulations
- Aggregate ratio supports efficient similarity comparison between datasets

---

## analyze_categorical_cardinality

**Name:** analyze_categorical_cardinality  
**Description:** Analyze the cardinality (number of unique values) of categorical columns. Provides aggregate classification of cardinality levels for similarity comparison.  
**Applicable Situations:** Feature engineering planning, encoding strategy selection, identifying potential ID columns

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.
- `high_cardinality_threshold`:
  - **Type:** `integer`
  - **Description:** Threshold for high cardinality classification.
  - **Default:** `100`
- `low_cardinality_threshold`:
  - **Type:** `integer`
  - **Description:** Threshold for low cardinality classification.
  - **Default:** `10`

**Required:** `data`  
**Result:** Dictionary with:
  - "cardinality_classification":
    - "low_cardinality_ratio": Proportion of categorical columns with ≤ low_cardinality_threshold unique values
    - "medium_cardinality_ratio": Proportion of categorical columns with unique values between thresholds
    - "high_cardinality_ratio": Proportion of categorical columns with > high_cardinality_threshold unique values  
**Notes:**
- Automatically identifies categorical columns (object, category types)
- Numeric columns are not treated as categorical (avoids misclassification)
- High-cardinality features often require target encoding or embedding
- Low-cardinality features are suitable for one-hot encoding
- Aggregate proportions support efficient comparison of categorical data characteristics

---

## analyze_categorical_imbalance

**Name:** analyze_categorical_imbalance  
**Description:** Analyze class imbalance in categorical columns. Provides aggregate classification of imbalance levels for similarity comparison.  
**Applicable Situations:** Understanding data representativeness, planning sampling strategies, identifying potential bias

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.

**Required:** `data`  
**Result:** Dictionary with:
  - "imbalance_classification":
    - "balanced_ratio": Proportion of categorical columns with dominant class < 70%
    - "moderately_imbalanced_ratio": Proportion of categorical columns with dominant class 70-90%
    - "highly_imbalanced_ratio": Proportion of categorical columns with dominant class ≥ 90%  
**Notes:**
- Automatically identifies categorical columns (object, category types)
- Imbalance is determined by the proportion of the most frequent category
- High imbalance may require oversampling, undersampling, or class-weighted models
- Aggregate proportions support efficient similarity comparison between datasets

---

## detect_rare_categories

**Name:** detect_rare_categories  
**Description:** Detect rare categories in categorical columns. Provides aggregate metrics of rare category prevalence for similarity comparison.  
**Applicable Situations:** Data cleaning, feature engineering, handling sparse categorical data

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.
- `rare_threshold`:
  - **Type:** `number`
  - **Description:** Threshold for considering a category rare (proportion of total).
  - **Default:** `0.01` (1%)

**Required:** `data`  
**Result:** Dictionary with:
  - "rare_category_summary":
    - "columns_with_rare_categories_ratio": Proportion of categorical columns containing rare categories
    - "average_rare_category_density": Average proportion of rare categories per categorical column  
**Notes:**
- Automatically identifies categorical columns (object, category types)
- Rare categories are those with occurrence proportion < rare_threshold
- High rare category density may indicate data sparsity or need for category grouping
- Aggregate metrics support efficient similarity comparison between datasets

---

## calculate_cardinality_variance

**Name:** calculate_cardinality_variance  
**Description:** Analyze the distribution pattern of cardinality across categorical columns. Identifies long-tail cardinality distributions for similarity comparison.  
**Applicable Situations:** Categorical data analysis, feature engineering, encoding strategy selection

**Parameters:**
- `data`:
  - **Type:** `pd.DataFrame`
  - **Description:** The input DataFrame containing the dataset to analyze.
- `include_numeric_as_categorical`:
  - **Type:** `boolean`
  - **Description:** Whether to include low-cardinality numeric columns as categorical.
  - **Default:** `True`
- `categorical_threshold`:
  - **Type:** `integer`
  - **Description:** Maximum unique values for numeric columns to be considered categorical.
  - **Default:** `20`

**Required:** `data`  
**Result:** Dictionary with:
  - "cardinality_distribution_type": Type of cardinality distribution ('power_law', 'uniform', 'normal_like', 'unknown')
  - "long_tail_prevalence": Proportion of columns with exceptionally high cardinality (beyond mean + 2*std)  
**Notes:**
- Power law distribution is common in real-world categorical data (few high-cardinality, many low-cardinality columns)
- Long tail prevalence indicates need for mixed encoding strategies
- Low-cardinality numeric columns are included by default for comprehensive analysis
- Results focus on key distribution characteristics for efficient similarity comparison

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