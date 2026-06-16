import pandas as pd
import numpy as np
from typing import List, Dict, Any
from sklearn.neighbors import KernelDensity
from scipy.signal import find_peaks
from scipy import stats
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.feature_selection import f_classif, f_regression
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.tools.tools import add_constant
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import r2_score, accuracy_score
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

import pandas as pd
import numpy as np
from typing import List, Dict, Any
from sklearn.neighbors import KernelDensity
from scipy.signal import find_peaks
from scipy import stats
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.feature_selection import f_classif, f_regression
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.tools.tools import add_constant
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import r2_score, accuracy_score
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

def calculate_overall_missing_rate(data: pd.DataFrame) -> float:
    """
    Calculate the overall missing rate (percentage of missing values) in the entire dataset.

    Args:
        data (pd.DataFrame): The input DataFrame.

    Returns:
        float: The overall missing rate as a value between 0 and 1.
    """
    if data.empty:
        return 0.0

    total_cells = data.shape[0] * data.shape[1]
    missing_cells = data.isna().sum().sum()

    return round(missing_cells / total_cells, 4) if total_cells > 0 else 0.0


def analyze_column_missing_distribution(data: pd.DataFrame,
                                        bins: List[float] = [0.0, 0.1, 0.3, 0.5, 1.0]) -> Dict[str, List[float]]:
    """
    Analyze the distribution of missing rates across columns.

    Args:
        data (pd.DataFrame): The input DataFrame.
        bins (List[float], optional): Bin edges for categorizing missing rates.
                                      Defaults to [0.0, 0.1, 0.3, 0.5, 1.0].

    Returns:
        Dict[str, List[float]]: Dictionary with bin labels and proportions of columns in each bin.
    """
    if data.empty or data.shape[1] == 0:
        return {"bins": ["0-0%"], "proportions": [1.0]}

    # Calculate missing rate for each column
    col_missing_rates = data.isna().mean()

    # Create bin labels
    bin_labels = []
    for i in range(len(bins) - 1):
        label = f"{int(bins[i] * 100)}-{int(bins[i + 1] * 100)}%"
        bin_labels.append(label)

    # Calculate proportions
    proportions = []
    for i in range(len(bins) - 1):
        low, high = bins[i], bins[i + 1]
        if i == len(bins) - 2:  # Last bin includes the upper bound
            mask = (col_missing_rates >= low) & (col_missing_rates <= high)
        else:
            mask = (col_missing_rates >= low) & (col_missing_rates < high)
        proportion = mask.mean()
        proportions.append(round(proportion, 4))

    return {
        "bins": bin_labels,
        "proportions": proportions
    }


def detect_missing_pattern_type(data: pd.DataFrame,
                                significance_level: float = 0.05) -> Dict[str, Any]:
    """
    简化版：检测缺失数据模式（MCAR/MAR/MNAR），仅保留核心逻辑和检索必要信息
    核心逻辑：基于缺失指标与观测数据的相关性判断，去除冗余方法和复杂聚类
    """
    if data.empty or data.isna().sum().sum() == 0:
        return {
            "pattern_type": "COMPLETE",
            "confidence": 1.0,
            "supporting_statistics": {
                "missing_rate": 0.0,
                "significant_correlation_ratio": 0.0
            }
        }

    # 核心指标：整体缺失率
    missing_rate = round(data.isna().mean().mean(), 4)
    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()

    # 边界情况：无数值列或数值列过少，用启发式判断
    if len(numeric_cols) < 2:
        column_missing_variation = round(data.isna().mean().std(), 4)
        if column_missing_variation < 0.1:
            pattern_type = "MCAR"
            confidence = 0.7
        elif column_missing_variation < 0.3:
            pattern_type = "MAR"
            confidence = 0.6
        else:
            pattern_type = "MNAR"
            confidence = 0.6
        return {
            "pattern_type": pattern_type,
            "confidence": confidence,
            "supporting_statistics": {
                "missing_rate": missing_rate,
                "column_missing_variation": column_missing_variation
            }
        }

    # 核心逻辑：缺失指标与观测数据的相关性检验（简化版）
    missing_indicators = data[numeric_cols].isna().astype(int)
    significant_correlations = 0
    total_valid_tests = 0

    for col in numeric_cols:
        # 该列的缺失指标
        col_missing = missing_indicators[col]
        if col_missing.sum() == 0 or col_missing.sum() == len(col_missing):
            continue  # 无缺失或全缺失，无需检验

        # 用其他数值列的观测值，检验与当前列缺失状态的相关性
        for other_col in numeric_cols:
            if col == other_col:
                continue
            # 取当前列未缺失时，其他列的观测值（避免数据泄露）
            valid_obs = data.loc[col_missing == 0, other_col].dropna()
            if len(valid_obs) < 10:
                continue  # 样本量不足，跳过

            # 分组：当前列缺失/未缺失的其他列数据
            group_missing = data.loc[col_missing == 1, other_col].dropna()
            if len(group_missing) < 5:
                continue

            # 简化检验：Mann-Whitney U检验（非参数，通用）
            try:
                _, p_value = stats.mannwhitneyu(valid_obs, group_missing, alternative='two-sided')
                total_valid_tests += 1
                if p_value < significance_level:
                    significant_correlations += 1
            except:
                continue

    # 基于显著相关比例判断缺失模式
    if total_valid_tests == 0:
        pattern_type = "UNKNOWN"
        confidence = 0.5
        sig_ratio = 0.0
    else:
        sig_ratio = round(significant_correlations / total_valid_tests, 4)
        if sig_ratio < 0.1:  # 极少显著相关 → 缺失与观测数据独立 → MCAR
            pattern_type = "MCAR"
            confidence = round(1 - sig_ratio, 4)
        elif sig_ratio < 0.5:  # 部分显著相关 → 缺失依赖观测数据 → MAR
            pattern_type = "MAR"
            confidence = 0.7
        else:  # 大量显著相关 → 缺失依赖未观测数据 → MNAR
            pattern_type = "MNAR"
            confidence = 0.7

    return {
        "pattern_type": pattern_type,
        "confidence": confidence,
        "supporting_statistics": {
            "missing_rate": missing_rate,
            "significant_correlation_ratio": sig_ratio
        }
    }


def analyze_row_completeness(data: pd.DataFrame) -> Dict[str, float]:
    """
    Analyze row-level completeness statistics.

    Args:
        data (pd.DataFrame): The input DataFrame.

    Returns:
        Dict[str, float]: Dictionary with row completeness metrics.
    """
    if data.empty:
        return {
            "complete_rows_ratio": 0.0,
            "rows_with_any_missing_ratio": 0.0,
            "high_missing_rows_ratio": 0.0
        }

    n_rows = data.shape[0]

    # Complete rows (no missing values)
    complete_rows = (data.isna().sum(axis=1) == 0).sum()
    complete_rows_ratio = round(complete_rows / n_rows, 4) if n_rows > 0 else 0.0

    # Rows with any missing values
    rows_with_any_missing = (data.isna().sum(axis=1) > 0).sum()
    rows_with_any_missing_ratio = round(rows_with_any_missing / n_rows, 4) if n_rows > 0 else 0.0

    # Rows with high missing rate (>50%)
    row_missing_rates = data.isna().mean(axis=1)
    high_missing_rows = (row_missing_rates > 0.5).sum()
    high_missing_rows_ratio = round(high_missing_rows / n_rows, 4) if n_rows > 0 else 0.0

    return {
        "complete_rows_ratio": complete_rows_ratio,
        "rows_with_any_missing_ratio": rows_with_any_missing_ratio,
        "high_missing_rows_ratio": high_missing_rows_ratio
    }





def detect_outliers(data: pd.DataFrame,
                    method: str = 'iqr',  # 简化：仅保留最常用的IQR方法
                    threshold: float = 1.5) -> Dict[str, Any]:
    """简化：
    1. 移除多种检测方法，仅保留IQR（最通用）
    2. 移除异常值具体索引，保留数量和比例
    3. 简化返回结构
    """

    def _detect_outliers_iqr(col_data: pd.Series, threshold: float = 1.5) -> int:
        """简化：仅返回异常值数量（而非索引）"""
        if len(col_data) < 4:
            return 0
        Q1, Q3 = col_data.quantile(0.25), col_data.quantile(0.75)
        IQR = Q3 - Q1
        if IQR == 0:
            return 0
        lower, upper = Q1 - threshold * IQR, Q3 + threshold * IQR
        return len(col_data[(col_data < lower) | (col_data > upper)])

    if data.empty:
        return {
            "outlier_columns_ratio": 0.0,
            "total_outliers": 0,
            "avg_outlier_ratio": 0.0
        }

    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols:
        return {
            "outlier_columns_ratio": 0.0,
            "total_outliers": 0,
            "avg_outlier_ratio": 0.0
        }

    total_outliers = 0
    outlier_counts = []
    for col in numeric_cols:
        col_data = data[col].dropna()
        if len(col_data) < 4:
            outlier_counts.append(0)
            continue
        count = _detect_outliers_iqr(col_data, threshold)
        total_outliers += count
        outlier_counts.append(count / len(col_data))  # 列内异常值比例

    outlier_columns_ratio = np.mean([c > 0 for c in outlier_counts])  # 有异常值的列占比
    avg_outlier_ratio = np.mean(outlier_counts) if outlier_counts else 0.0  # 整体平均异常值比例

    return {
        "outlier_columns_ratio": round(outlier_columns_ratio, 4),
        "total_outliers": total_outliers,
        "avg_outlier_ratio": round(avg_outlier_ratio, 4)
    }


def classify_outlier_severity(data: pd.DataFrame) -> Dict[str, float]:
    """
    简化核心：保留异常值严重程度比例（对检索有区分度），移除冗余参数和列级细节
    功能：统计数值列中不同异常值严重程度的占比，支撑数据质量相似度匹配
    """
    if data.empty:
        return {
            "mild_ratio": 0.0,
            "moderate_ratio": 0.0,
            "severe_ratio": 0.0,
            "no_outliers_ratio": 0.0
        }

    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols:
        return {
            "mild_ratio": 0.0,
            "moderate_ratio": 0.0,
            "severe_ratio": 0.0,
            "no_outliers_ratio": 0.0
        }

    severity_counts = {"mild": 0, "moderate": 0, "severe": 0, "none": 0}
    for col in numeric_cols:
        col_data = data[col].dropna()
        if len(col_data) < 4:
            severity_counts["none"] += 1
            continue

        # 固定IQR方法（无需灵活配置，保证结果一致性）
        Q1, Q3 = col_data.quantile(0.25), col_data.quantile(0.75)
        IQR = Q3 - Q1
        if IQR == 0:
            severity_counts["none"] += 1
            continue

        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        outlier_ratio = ((col_data < lower_bound) | (col_data > upper_bound)).sum() / len(col_data)

        # 简化阈值（聚焦核心区分度）
        if outlier_ratio == 0:
            severity_counts["none"] += 1
        elif outlier_ratio < 0.05:
            severity_counts["mild"] += 1
        elif outlier_ratio < 0.20:
            severity_counts["moderate"] += 1
        else:
            severity_counts["severe"] += 1

    total = len(numeric_cols)
    return {
        "mild_ratio": round(severity_counts["mild"] / total, 4),
        "moderate_ratio": round(severity_counts["moderate"] / total, 4),
        "severe_ratio": round(severity_counts["severe"] / total, 4),
        "no_outliers_ratio": round(severity_counts["none"] / total, 4)
    }


def check_data_type_consistency(data: pd.DataFrame) -> Dict[str, float]:
    """
    简化核心：保留类型违规比例（核心指标），删除列级详细问题描述（对检索无意义）
    功能：统计存在数据类型不一致的列占比，支撑数据质量相似度匹配
    """
    if data.empty or len(data.columns) == 0:
        return {"type_violation_ratio": 0.0}

    problematic_cols = 0
    for col in data.columns:
        col_data = data[col].dropna()
        if len(col_data) == 0:
            continue

        # 仅检测核心类型不一致场景（聚焦检索所需的关键差异）
        if data[col].dtype == 'object':
            # 检测字符串列中混有数值的情况（最常见的类型问题）
            has_string = any(isinstance(val, str) for val in col_data)
            has_numeric = any(isinstance(val, (int, float, np.integer, np.floating)) for val in col_data)
            if has_string and has_numeric:
                problematic_cols += 1
        elif data[col].dtype in [np.int64, np.float64]:
            # 检测数值列中存在非数值的情况
            try:
                pd.to_numeric(data[col], errors='raise')
            except (ValueError, TypeError):
                problematic_cols += 1

    return {
        "type_violation_ratio": round(problematic_cols / len(data.columns), 4)
    }


def check_uniqueness_constraints(data: pd.DataFrame) -> Dict[str, float]:
    """
    简化核心：保留唯一性违规比例（核心指标），删除重复值细节（对检索无意义）
    功能：统计存在重复值的关键列占比，支撑数据质量相似度匹配
    """
    if data.empty or len(data.columns) == 0:
        return {"unique_violation_ratio": 0.0}

    # 聚焦关键列（ID/Key类列，对竞赛数据质量影响最大）
    id_patterns = ['id', 'ID', 'Id', 'key', 'Key', 'code', 'Code']
    candidate_cols = [col for col in data.columns if any(pattern in col.lower() for pattern in id_patterns)]
    # 无匹配列时，默认检查所有列（保证通用性）
    if not candidate_cols:
        candidate_cols = data.columns.tolist()

    duplicate_cols = 0
    for col in candidate_cols:
        col_data = data[col].dropna()
        if len(col_data) == 0:
            continue
        # 仅判断是否存在重复（无需统计具体重复数/值）
        if col_data.nunique() < len(col_data):
            duplicate_cols += 1

    total_candidate = len(candidate_cols)
    return {
        "unique_violation_ratio": round(duplicate_cols / total_candidate, 4),
    }



def analyze_numerical_skewness(data: pd.DataFrame) -> Dict[str, Any]:
    """简化：
    1. 移除均值/标准差等细节统计量
    2. 仅保留分类比例（对检索有区分度）
    """
    if data.empty:
        return {
            "skewness_classification": {
                "highly_skewed_ratio": 0.0,
                "positive_skew_ratio": 0.0,
                "negative_skew_ratio": 0.0,
                "symmetric_ratio": 0.0
            }
        }

    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols:
        return {
            "skewness_classification": {
                "highly_skewed_ratio": 0.0,
                "positive_skew_ratio": 0.0,
                "negative_skew_ratio": 0.0,
                "symmetric_ratio": 0.0
            }
        }

    skewness_list = []
    for col in numeric_cols:
        col_data = data[col].dropna()
        skewness_list.append(stats.skew(col_data) if len(col_data) >= 3 else 0.0)

    skewness_array = np.array(skewness_list)
    return {
        "skewness_classification": {
            "highly_skewed_ratio": round(np.mean(np.abs(skewness_array) > 1), 4),
            "positive_skew_ratio": round(np.mean(skewness_array > 0.5), 4),
            "negative_skew_ratio": round(np.mean(skewness_array < -0.5), 4),
            "symmetric_ratio": round(np.mean(np.abs(skewness_array) <= 0.5), 4)
        }
    }



def analyze_numerical_scale(data: pd.DataFrame) -> Dict[str, Any]:
    """简化：
    1. 移除log_range等细节指标
    2. 保留宽范围比例和单位异质性（对检索有价值）
    """
    if data.empty:
        return {
            "scale_classification": {
                "wide_range_ratio": 0.0,
                "unit_heterogeneity": False
            }
        }

    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols:
        return {
            "scale_classification": {
                "wide_range_ratio": 0.0,
                "unit_heterogeneity": False
            }
        }

    has_positive = False
    has_negative = False
    wide_range_flags = []

    for col in numeric_cols:
        col_data = data[col].dropna()
        if len(col_data) < 2:
            continue
        min_val, max_val = col_data.min(), col_data.max()
        data_range = max_val - min_val

        has_positive |= (col_data > 0).any()
        has_negative |= (col_data < 0).any()
        wide_range_flags.append(data_range > 1000)  # 直接判断是否为宽范围（>10^3）

    wide_range_ratio = np.mean(wide_range_flags) if wide_range_flags else 0.0
    return {
        "scale_classification": {
            "wide_range_ratio": round(wide_range_ratio, 4),
            "unit_heterogeneity": has_positive and has_negative
        }
    }



def test_normality(data: pd.DataFrame, alpha: float = 0.05) -> Dict[str, Any]:
    """简化：仅保留整体正态比例，移除列级细节"""
    if data.empty:
        return {
            "normality_summary": {
                "normal_like_ratio": 0.0,
                "tested_columns_count": 0
            }
        }

    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols:
        return {
            "normality_summary": {
                "normal_like_ratio": 0.0,
                "tested_columns_count": 0
            }
        }

    normal_flags = []
    for col in numeric_cols:
        col_data = data[col].dropna()
        if len(col_data) < 8:
            continue  # 样本量不足则不参与统计
        try:
            _, p_value = stats.shapiro(col_data) if len(col_data) < 5000 else stats.normaltest(col_data)
            normal_flags.append(p_value > alpha)
        except:
            continue

    tested_count = len(normal_flags)
    normal_ratio = np.mean(normal_flags) if tested_count > 0 else 0.0
    return {
        "normality_summary": {
            "normal_like_ratio": round(normal_ratio, 4),
            "tested_columns_count": tested_count
        }
    }


def detect_multimodal_distributions(data: pd.DataFrame,
                                    bandwidth: float = None) -> Dict[str, Any]:
    """
    简化：仅保留核心检索指标（多峰列占比），移除列级细节和冗余分类
    """
    if data.empty:
        return {
            "multimodal_summary": {
                "multimodal_ratio": 0.0,  # 仅保留多峰列占比（>1个峰）
                "tested_columns_count": 0
            }
        }

    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols:
        return {
            "multimodal_summary": {
                "multimodal_ratio": 0.0,
                "tested_columns_count": 0
            }
        }

    multimodal_flags = []
    for col in numeric_cols:
        col_data = data[col].dropna()
        if len(col_data) < 20 or col_data.std() == 0:
            multimodal_flags.append(False)
            continue

        # 标准化+KDE核心逻辑保留（保证结果一致性）
        standardized = (col_data - col_data.mean()) / col_data.std()
        if bandwidth is None:
            n = len(standardized)
            bandwidth = np.power(4 / (3 * n), 1 / 5)  # Silverman's rule

        grid = np.linspace(standardized.min(), standardized.max(), 200)
        try:
            kde = KernelDensity(bandwidth=bandwidth, kernel='gaussian')
            kde.fit(standardized.values.reshape(-1, 1))
            density = np.exp(kde.score_samples(grid.reshape(-1, 1)))
            peaks, _ = find_peaks(density, prominence=0.1 * density.max())
            multimodal_flags.append(len(peaks) > 1)
        except:
            multimodal_flags.append(False)

    tested_count = len(multimodal_flags)
    multimodal_ratio = np.mean(multimodal_flags) if tested_count > 0 else 0.0
    return {
        "multimodal_summary": {
            "multimodal_ratio": round(multimodal_ratio, 4),
            "tested_columns_count": tested_count
        }
    }



def analyze_categorical_cardinality(data: pd.DataFrame,
                                    high_cardinality_threshold: int = 100,
                                    low_cardinality_threshold: int = 10) -> Dict[str, Any]:
    """
    简化：移除列级基数、冗余统计量，仅保留核心分类比例（检索关键区分指标）
    """
    if data.empty:
        return {
            "cardinality_classification": {
                "low_cardinality_ratio": 0.0,
                "medium_cardinality_ratio": 0.0,
                "high_cardinality_ratio": 0.0
            }
        }

    # 简化分类列判断（仅保留显式分类类型，避免数值列误判增加复杂度）
    categorical_cols = data.select_dtypes(include=['object', 'category']).columns.tolist()
    if not categorical_cols:
        return {
            "cardinality_classification": {
                "low_cardinality_ratio": 0.0,
                "medium_cardinality_ratio": 0.0,
                "high_cardinality_ratio": 0.0
            }
        }

    # 仅计算分类比例，移除均值/标准差等冗余统计
    cardinality_array = np.array([data[col].nunique() for col in categorical_cols])
    return {
        "cardinality_classification": {
            "low_cardinality_ratio": round(np.mean(cardinality_array <= low_cardinality_threshold), 4),
            "medium_cardinality_ratio": round(np.mean((cardinality_array > low_cardinality_threshold) &
                                                     (cardinality_array <= high_cardinality_threshold)), 4),
            "high_cardinality_ratio": round(np.mean(cardinality_array > high_cardinality_threshold), 4)
        }
    }


def analyze_categorical_imbalance(data: pd.DataFrame) -> Dict[str, Any]:
    """
    简化：移除列级细节指标，仅保留整体不平衡分类比例（检索核心需求）
    """
    if data.empty:
        return {
            "imbalance_classification": {
                "balanced_ratio": 0.0,
                "moderately_imbalanced_ratio": 0.0,
                "highly_imbalanced_ratio": 0.0
            }
        }

    # 简化分类列判断
    categorical_cols = data.select_dtypes(include=['object', 'category']).columns.tolist()
    if not categorical_cols:
        return {
            "imbalance_classification": {
                "balanced_ratio": 0.0,
                "moderately_imbalanced_ratio": 0.0,
                "highly_imbalanced_ratio": 0.0
            }
        }

    imbalance_levels = []
    for col in categorical_cols:
        value_counts = data[col].value_counts(normalize=True)
        if len(value_counts) == 0:
            imbalance_levels.append("balanced")
            continue
        dominant_proportion = value_counts.iloc[0]
        # 保留原判断阈值（保证区分度）
        if dominant_proportion < 0.7:
            imbalance_levels.append("balanced")
        elif dominant_proportion < 0.9:
            imbalance_levels.append("moderately_imbalanced")
        else:
            imbalance_levels.append("highly_imbalanced")

    total = len(imbalance_levels)
    return {
        "imbalance_classification": {
            "balanced_ratio": round(imbalance_levels.count("balanced") / total, 4),
            "moderately_imbalanced_ratio": round(imbalance_levels.count("moderately_imbalanced") / total, 4),
            "highly_imbalanced_ratio": round(imbalance_levels.count("highly_imbalanced") / total, 4)
        }
    }



def detect_rare_categories(data: pd.DataFrame,
                           rare_threshold: float = 0.01) -> Dict[str, Any]:
    """
    简化：移除列级细节，仅保留核心汇总指标（检索关键：是否有稀有类+密度）
    """
    if data.empty:
        return {
            "rare_category_summary": {
                "columns_with_rare_categories_ratio": 0.0,
                "average_rare_category_density": 0.0
            }
        }

    # 简化分类列判断
    categorical_cols = data.select_dtypes(include=['object', 'category']).columns.tolist()
    if not categorical_cols:
        return {
            "rare_category_summary": {
                "columns_with_rare_categories_ratio": 0.0,
                "average_rare_category_density": 0.0
            }
        }

    has_rare_list = []
    rare_density_list = []
    for col in categorical_cols:
        value_counts = data[col].value_counts(normalize=True)
        if len(value_counts) == 0:
            has_rare_list.append(False)
            continue
        # 仅计算核心指标：是否有稀有类+总密度
        rare_categories = value_counts[value_counts < rare_threshold]
        has_rare = len(rare_categories) > 0
        has_rare_list.append(has_rare)
        if has_rare:
            rare_density_list.append(rare_categories.sum())

    return {
        "rare_category_summary": {
            "columns_with_rare_categories_ratio": round(np.mean(has_rare_list), 4),
            "average_rare_category_density": round(np.mean(rare_density_list) if rare_density_list else 0.0, 4)
        }
    }


def calculate_cardinality_variance(data: pd.DataFrame,
                                   include_numeric_as_categorical: bool = True,
                                   categorical_threshold: int = 20) -> Dict[str, Any]:
    """
    简化：保留检索关键指标（长尾占比+分布类型），移除冗余统计量，简化计算逻辑
    """
    if data.empty:
        return {
            "cardinality_distribution_type": "unknown",
            "long_tail_prevalence": 0.0
        }

    # 分类列识别逻辑保留（兼容低基数数值列）
    categorical_cols = []
    cardinality_values = []
    for col in data.columns:
        if data[col].dtype in ['object', 'category']:
            cardinality = data[col].nunique()
            categorical_cols.append(col)
            cardinality_values.append(cardinality)
        elif include_numeric_as_categorical and data[col].dtype in [np.int64, np.float64]:
            unique_count = data[col].nunique()
            if unique_count <= categorical_threshold:
                cardinality_values.append(unique_count)

    if not cardinality_values:
        return {
            "cardinality_distribution_type": "unknown",
            "long_tail_prevalence": 0.0
        }

    cardinality_array = np.array(cardinality_values)
    mean_card = cardinality_array.mean()
    std_card = cardinality_array.std() if len(cardinality_array) > 1 else 0.0

    # 简化长尾占比计算（核心检索指标）
    long_tail_prevalence = np.mean(cardinality_array > (mean_card + 2 * std_card)) if std_card > 0 else 0.0

    # 简化分布类型判断（移除log-log回归，用简单heuristic保证效率）
    if len(cardinality_array) >= 5:
        gini = (2 * np.sum(np.arange(1, len(cardinality_array)+1) * np.sort(cardinality_array)) /
                (len(cardinality_array) * np.sum(cardinality_array)) - 1)
        cv = std_card / mean_card if mean_card > 0 else 0.0
        if gini > 0.6:
            dist_type = "power_law"
        elif cv < 0.5:
            dist_type = "uniform"
        else:
            dist_type = "normal_like"
    else:
        dist_type = "unknown"

    return {
        "cardinality_distribution_type": dist_type,
        "long_tail_prevalence": round(long_tail_prevalence, 4)
    }


def calculate_samples_per_feature(data: pd.DataFrame, target_column: str = None) -> float:
    """
    Calculate the ratio of samples to features (n_samples / n_features) - core dimensionality metric.
    Excludes target column from feature count if provided (pure feature dimensionality assessment).

    Args:
        data (pd.DataFrame): The input DataFrame containing the dataset to analyze.
        target_column (str, optional): Target column name (to exclude from feature count). Defaults to None.

    Returns:
        float: Samples per feature ratio (rounded to 4 decimal places; 0.0 for invalid cases).
    """
    if data.empty:
        return 0.0

    # 计算有效样本数（非空行）
    n_samples = len(data.dropna(how='all'))  # 排除全空行
    if n_samples == 0:
        return 0.0

    # 计算有效特征数（排除目标列和全空列）
    feature_cols = data.columns.tolist()
    if target_column and target_column in feature_cols:
        feature_cols.remove(target_column)  # 排除目标列（不算特征）

    # 过滤全空列（无实际信息，不算有效特征）
    valid_feature_cols = []
    for col in feature_cols:
        non_null_count = data[col].notna().sum()
        if non_null_count > 0:  # 至少有一个非空值的列才视为有效特征
            valid_feature_cols.append(col)
    n_features = len(valid_feature_cols)

    if n_features == 0:
        return 0.0

    # 计算样本特征比（保留4位小数）
    samples_per_feature = n_samples / n_features
    return round(samples_per_feature, 4)



def analyze_numerical_correlation_strength(data: pd.DataFrame) -> Dict[str, float]:
    """
    Analyze the strength of correlations between numerical columns (fixed Spearman method for consistency).

    Args:
        data (pd.DataFrame): The input DataFrame.

    Returns:
        Dict[str, float]: Dictionary with proportions of correlation pairs in different strength levels.
    """
    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()

    if len(numeric_cols) < 2:
        return {
            "weak_correlation_ratio": 0.0,
            "moderate_correlation_ratio": 0.0,
            "strong_correlation_ratio": 0.0
        }

    # Fixed Spearman method (most robust for retrieval consistency)
    corr_matrix = data[numeric_cols].corr(method='spearman')
    upper_triangle = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
    corr_values = upper_triangle.values.flatten()
    corr_values = corr_values[~np.isnan(corr_values)]

    if len(corr_values) == 0:
        return {
            "weak_correlation_ratio": 0.0,
            "moderate_correlation_ratio": 0.0,
            "strong_correlation_ratio": 0.0
        }

    # Fixed thresholds for consistent classification
    weak_threshold = 0.3
    strong_threshold = 0.7

    weak_correlation_ratio = (np.abs(corr_values) < weak_threshold).mean()
    moderate_correlation_ratio = ((np.abs(corr_values) >= weak_threshold) & (np.abs(corr_values) < strong_threshold)).mean()
    strong_correlation_ratio = (np.abs(corr_values) >= strong_threshold).mean()

    return {
        "weak_correlation_ratio": round(weak_correlation_ratio, 4),
        "moderate_correlation_ratio": round(moderate_correlation_ratio, 4),
        "strong_correlation_ratio": round(strong_correlation_ratio, 4)
    }


def detect_correlation_clusters(data: pd.DataFrame,
                                correlation_threshold: float = 0.7) -> Dict[str, Any]:
    """
    Detect clusters of highly correlated numerical columns.

    Args:
        data (pd.DataFrame): The input DataFrame.
        correlation_threshold (float, optional): Threshold for considering two columns as correlated.
                                                Defaults to 0.7.

    Returns:
        Dict[str, Any]: Dictionary with cluster count and the proportion of columns in the largest cluster.
    """
    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()

    if len(numeric_cols) < 2:
        return {
            "cluster_count": 0,
            "largest_cluster_proportion": 0.0  # Rename for clarity
        }

    corr_matrix = data[numeric_cols].corr(method='spearman').abs()
    distance_matrix = 1 - corr_matrix
    np.fill_diagonal(distance_matrix.values, 0)

    try:
        Z = linkage(squareform(distance_matrix), method='average')
        clusters = fcluster(Z, t=1 - correlation_threshold, criterion='distance')
    except:
        clusters = range(1, len(numeric_cols) + 1)

    unique_clusters, counts = np.unique(clusters, return_counts=True)
    cluster_count = len(unique_clusters)
    largest_cluster_proportion = counts.max() / len(numeric_cols) if cluster_count > 0 else 0.0

    return {
        "cluster_count": int(cluster_count),
        "largest_cluster_proportion": round(largest_cluster_proportion, 4)
    }


def detect_multicollinearity_vif(data: pd.DataFrame) -> Dict[str, float]:
    """
    Detect multicollinearity using Variance Inflation Factor (VIF) (fixed threshold for consistency).

    Args:
        data (pd.DataFrame): The input DataFrame.

    Returns:
        Dict[str, float]: Dictionary with proportion of columns with high multicollinearity.
    """
    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    vif_threshold = 10.0  # Fixed threshold for retrieval consistency

    if len(numeric_cols) < 2:
        return {"high_multicollinearity_ratio": 0.0}

    data_numeric = data[numeric_cols].dropna()
    if data_numeric.shape[0] < 2:
        return {"high_multicollinearity_ratio": 0.0}

    vif_data = add_constant(data_numeric)
    high_vif_count = 0

    for i, col in enumerate(numeric_cols):
        try:
            vif = variance_inflation_factor(vif_data.values, i + 1)
            if vif > vif_threshold:
                high_vif_count += 1
        except:
            continue

    high_multicollinearity_ratio = high_vif_count / len(numeric_cols) if numeric_cols else 0.0
    return {"high_multicollinearity_ratio": round(high_multicollinearity_ratio, 4)}



def analyze_feature_target_relationship_classification(data: pd.DataFrame,
                                                       target_column: str) -> Dict[str, float]:
    """
    Analyze feature-target relationship for classification (fixed ANOVA F-value method).

    Args:
        data (pd.DataFrame): The input DataFrame.
        target_column (str): The name of the target column.

    Returns:
        Dict[str, float]: Dictionary with high importance ratio and importance concentration (Gini).
    """
    if target_column not in data.columns:
        return {"high_importance_ratio": 0.0, "importance_concentration_gini": 0.0}

    X = data.drop(columns=[target_column])
    numeric_cols = X.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) == 0:
        return {"high_importance_ratio": 0.0, "importance_concentration_gini": 0.0}

    X_numeric = X[numeric_cols].fillna(X[numeric_cols].mean())
    y = data[target_column]

    try:
        f_values, _ = f_classif(X_numeric, y)
    except:
        return {"high_importance_ratio": 0.0, "importance_concentration_gini": 0.0}

    # Fixed normalization and high-importance threshold (5x mean)
    importances = f_values / f_values.sum() if f_values.sum() > 0 else np.zeros_like(f_values)
    mean_importance = importances.mean()
    high_importance_ratio = (importances > 5 * mean_importance).mean() if mean_importance > 0 else 0.0

    # Calculate Gini for importance concentration (key for retrieval)
    sorted_importances = np.sort(importances)
    n = len(sorted_importances)
    if n == 0 or sorted_importances.sum() == 0:
        gini = 0.0
    else:
        cum_importances = np.cumsum(sorted_importances)
        lorenz_curve = cum_importances / cum_importances[-1]
        uniform_line = np.arange(1, n + 1) / n
        gini = np.sum(uniform_line - lorenz_curve) / n

    return {
        "high_importance_ratio": round(high_importance_ratio, 4),
        "importance_concentration_gini": round(gini, 4)
    }


def analyze_feature_target_relationship_regression(data: pd.DataFrame,
                                                   target_column: str) -> Dict[str, float]:
    """
    Analyze feature-target relationship for regression (fixed F-regression method).

    Args:
        data (pd.DataFrame): The input DataFrame.
        target_column (str): The name of the target column.

    Returns:
        Dict[str, float]: Dictionary with high importance ratio and importance concentration (Gini).
    """
    if target_column not in data.columns:
        return {"high_importance_ratio": 0.0, "importance_concentration_gini": 0.0}

    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    numeric_cols = [col for col in numeric_cols if col != target_column]
    if len(numeric_cols) == 0:
        return {"high_importance_ratio": 0.0, "importance_concentration_gini": 0.0}

    X = data[numeric_cols].fillna(data[numeric_cols].mean())
    y = data[target_column]

    try:
        f_values, _ = f_regression(X, y)
    except:
        # Fallback to correlation if F-regression fails (fixed fallback logic)
        f_values = []
        for col in numeric_cols:
            valid_data = data[[col, target_column]].dropna()
            corr = valid_data[col].corr(valid_data[target_column]) if len(valid_data) >= 2 else 0.0
            f_values.append(abs(corr) if not np.isnan(corr) else 0.0)
        f_values = np.array(f_values)

    importances = f_values / f_values.sum() if f_values.sum() > 0 else np.zeros_like(f_values)
    mean_importance = importances.mean()
    high_importance_ratio = (importances > 5 * mean_importance).mean() if mean_importance > 0 else 0.0

    # Calculate Gini for importance concentration
    sorted_importances = np.sort(importances)
    n = len(sorted_importances)
    if n == 0 or sorted_importances.sum() == 0:
        gini = 0.0
    else:
        cum_importances = np.cumsum(sorted_importances)
        lorenz_curve = cum_importances / cum_importances[-1]
        uniform_line = np.arange(1, n + 1) / n
        gini = np.sum(uniform_line - lorenz_curve) / n

    return {
        "high_importance_ratio": round(high_importance_ratio, 4),
        "importance_concentration_gini": round(gini, 4)
    }


def detect_interaction_effects(data: pd.DataFrame,
                               target_column: str,
                               problem_type: str = 'classification') -> Dict[str, float]:
    """
    Detect potential interaction effects between features (fixed decision tree parameters).

    Args:
        data (pd.DataFrame): The input DataFrame.
        target_column (str): The name of the target column.
        problem_type (str, optional): 'classification' or 'regression'. Defaults to 'classification'.

    Returns:
        Dict[str, float]: Dictionary with the ratio of complex interactions detected.
    """
    if target_column not in data.columns:
        return {"complex_interaction_ratio": 0.0}

    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    numeric_cols = [col for col in numeric_cols if col != target_column]
    if len(numeric_cols) < 2:
        return {"complex_interaction_ratio": 0.0}

    X = data[numeric_cols].fillna(data[numeric_cols].mean())
    y = data[target_column]

    # Fixed decision tree parameters for consistency
    if problem_type == 'classification':
        dt = DecisionTreeClassifier(max_depth=5, random_state=42)
    else:
        dt = DecisionTreeRegressor(max_depth=5, random_state=42)

    try:
        dt.fit(X, y)
        importances = dt.feature_importances_
    except:
        return {"complex_interaction_ratio": 0.0}

    # Fixed Gini threshold for interaction judgment
    sorted_importances = np.sort(importances)
    n = len(sorted_importances)
    if n == 0 or sorted_importances.sum() == 0:
        gini = 0.0
    else:
        cum_importances = np.cumsum(sorted_importances)
        lorenz_curve = cum_importances / cum_importances[-1]
        uniform_line = np.arange(1, n + 1) / n
        gini = np.sum(uniform_line - lorenz_curve) / n

    # Fixed mapping from Gini to interaction ratio
    complex_interaction_ratio = 1 - (gini / 0.5) if gini < 0.5 else 0.0
    return {"complex_interaction_ratio": round(complex_interaction_ratio, 4)}



def detect_nonlinear_relationships(data: pd.DataFrame,
                                   target_column: str,
                                   problem_type: str = 'classification') -> Dict[str, float]:
    """
    Detect nonlinear relationships between features and target (fixed model parameters for consistency).

    Args:
        data (pd.DataFrame): The input DataFrame.
        target_column (str): The name of the target column.
        problem_type (str, optional): 'classification' or 'regression'. Defaults to 'classification'.

    Returns:
        Dict[str, float]: Dictionary with the ratio of nonlinear relationships detected.
    """
    if target_column not in data.columns:
        return {"nonlinear_ratio": 0.0}

    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    numeric_cols = [col for col in numeric_cols if col != target_column]
    if len(numeric_cols) == 0:
        return {"nonlinear_ratio": 0.0}

    X = data[numeric_cols].fillna(data[numeric_cols].mean())
    y = data[target_column]

    # Fixed model parameters for retrieval consistency
    if problem_type == 'classification':
        linear_model = LogisticRegression(max_iter=1000, random_state=42)
        tree_model = DecisionTreeClassifier(max_depth=5, random_state=42)
    else:
        linear_model = LinearRegression()
        tree_model = DecisionTreeRegressor(max_depth=5, random_state=42)

    try:
        linear_model.fit(X, y)
        tree_model.fit(X, y)

        # Fixed evaluation metrics
        if problem_type == 'classification':
            linear_score = accuracy_score(y, linear_model.predict(X))
            tree_score = accuracy_score(y, tree_model.predict(X))
        else:
            linear_score = r2_score(y, linear_model.predict(X))
            tree_score = r2_score(y, tree_model.predict(X))

        # Simplified nonlinear ratio calculation
        if linear_score <= 0:
            nonlinear_ratio = 1.0 if tree_score > 0.5 else 0.0
        else:
            improvement = (tree_score - linear_score) / linear_score
            nonlinear_ratio = min(1.0, max(0.0, improvement))

    except:
        nonlinear_ratio = 0.0

    return {"nonlinear_ratio": round(nonlinear_ratio, 4)}


def detect_redundant_feature_pairs(data: pd.DataFrame) -> Dict[str, float]:
    """
    Detect redundant feature pairs (fixed Spearman correlation threshold = 0.9).

    Args:
        data (pd.DataFrame): The input DataFrame.

    Returns:
        Dict[str, float]: Dictionary with proportion of redundant feature pairs.
    """
    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) < 2:
        return {"redundant_pair_ratio": 0.0}

    # Fixed correlation threshold and method for consistency
    corr_matrix = data[numeric_cols].corr(method='spearman').abs()
    upper_triangle = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
    corr_values = upper_triangle.values.flatten()
    corr_values = corr_values[~np.isnan(corr_values)]

    if len(corr_values) == 0:
        return {"redundant_pair_ratio": 0.0}

    redundant_count = (corr_values >= 0.9).sum()
    total_pairs = len(corr_values)
    redundant_pair_ratio = redundant_count / total_pairs

    return {"redundant_pair_ratio": round(redundant_pair_ratio, 4)}



def estimate_feature_interaction_potential(data: pd.DataFrame) -> float:
    """
    Estimate feature interaction potential (simplified unsupervised method based on correlation structure).

    Args:
        data (pd.DataFrame): The input DataFrame.

    Returns:
        float: Estimated interaction potential (0 = low, 1 = high).
    """
    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) < 2:
        return 0.0

    numeric_data = data[numeric_cols].dropna()
    if len(numeric_data) < 10:
        return 0.0

    # Simplified logic: low average correlation = high interaction potential
    corr_matrix = numeric_data.corr().abs()
    upper_triangle = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
    avg_correlation = upper_triangle.stack().mean()

    if pd.isna(avg_correlation):
        return 0.5

    # Inverse mapping to interaction potential (0-1 range)
    interaction_potential = 1.0 - min(1.0, avg_correlation)
    return round(interaction_potential, 4)


def analyze_sparsity(data: pd.DataFrame) -> Dict[str, float]:
    """
    Combined analysis of zero-dominated and sparse columns (fixed thresholds for consistency).

    Args:
        data (pd.DataFrame): The input DataFrame.

    Returns:
        Dict[str, float]: Ratios of zero-dominated columns and sparse columns.
    """
    if data.empty or len(data.columns) == 0:
        return {
            "zero_dominated_ratio": 0.0,
            "sparse_columns_ratio": 0.0
        }

    zero_dominated_count = 0
    sparse_count = 0
    n_cols = len(data.columns)

    for col in data.columns:
        col_data = data[col].dropna()
        if len(col_data) == 0:
            continue

        # Zero-dominated: >=90% zeros (numeric columns only)
        if pd.api.types.is_numeric_dtype(col_data):
            zero_ratio = (col_data == 0).sum() / len(col_data)
            if zero_ratio >= 0.9:
                zero_dominated_count += 1

        # Sparse: <=10% non-zero/non-empty values
        if pd.api.types.is_numeric_dtype(col_data):
            non_sparse_count = ((col_data != 0) & (~col_data.isna())).sum()
        else:
            non_sparse_count = ((col_data != "") & (~col_data.isna())).sum()
        sparsity_ratio = non_sparse_count / len(data[col])
        if sparsity_ratio <= 0.1:
            sparse_count += 1

    return {
        "zero_dominated_ratio": round(zero_dominated_count / n_cols, 4),
        "sparse_columns_ratio": round(sparse_count / n_cols, 4)
    }



def estimate_signal_to_noise(data: pd.DataFrame) -> float:
    """
    Estimate signal-to-noise ratio (fixed PCA method for consistency).

    Args:
        data (pd.DataFrame): The input DataFrame.

    Returns:
        float: Signal-to-noise ratio (capped at 10.0, higher = more signal).
    """
    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) < 2:
        return 2.5  # Default moderate SNR

    numeric_data = data[numeric_cols].dropna()
    if len(numeric_data) < 10:
        return 2.5

    try:
        # Fixed PCA parameters for consistency
        scaler = StandardScaler()
        scaled_data = scaler.fit_transform(numeric_data)
        pca = PCA(n_components=min(5, len(numeric_cols)))
        pca.fit(scaled_data)

        explained_var = pca.explained_variance_ratio_
        signal_var = explained_var[:2].sum()  # First 2 components = signal
        noise_var = explained_var[2:].sum() if len(explained_var) > 2 else 0.001

        snr = min(10.0, signal_var / noise_var)
        return round(snr, 2)

    except:
        return 2.5


def estimate_inherent_uncertainty(data: pd.DataFrame,
                                  target_column: str = None) -> float:
    """
    Estimate inherent uncertainty (simplified to entropy-based method for consistency).

    Args:
        data (pd.DataFrame): The input DataFrame.
        target_column (str, optional): Target column for supervised estimation.
                                       If None, uses unsupervised feature diversity.

    Returns:
        float: Estimated uncertainty (0 = low, 1 = high).
    """
    if data.empty:
        return 0.1

    # Supervised: Target entropy (fixed discretization for numeric targets)
    if target_column and target_column in data.columns:
        target_data = data[target_column].dropna()
        if len(target_data) < 5:
            return 0.5

        # Unified entropy calculation for numeric/categorical targets
        if pd.api.types.is_numeric_dtype(target_data):
            n_bins = min(10, len(target_data) // 5)
            discretized = pd.cut(target_data, bins=n_bins, labels=False)
        else:
            discretized = target_data

        value_counts = discretized.value_counts(normalize=True)
        entropy = -np.sum(value_counts * np.log2(value_counts + 1e-10))
        max_entropy = np.log2(len(value_counts)) if len(value_counts) > 1 else 1.0
        return round(min(1.0, entropy / max_entropy), 4)

    # Unsupervised: Average feature diversity
    diversity_scores = []
    for col in data.columns[:10]:  # Limit to top 10 columns for efficiency
        col_data = data[col].dropna()
        if len(col_data) < 5:
            continue
        unique_ratio = min(1.0, col_data.nunique() / len(col_data))
        diversity_scores.append(unique_ratio)

    return round(np.mean(diversity_scores) if diversity_scores else 0.5, 4)


def assess_dataset_complexity(data: pd.DataFrame,
                              target_column: str = None) -> Dict[str, Any]:
    """
    Simplified dataset complexity assessment (core metrics for retrieval).

    Args:
        data (pd.DataFrame): The input DataFrame.
        target_column (str, optional): Target column for supervised assessments.

    Returns:
        Dict[str, Any]: Core complexity metrics (dimensionality, sparsity, noise).
    """
    if data.empty:
        return {
            "dimensionality": {
                "samples_per_feature": 0.0,
                "feature_interaction_potential": 0.0
            },
            "sparsity_patterns": {
                "zero_dominated_ratio": 0.0,
                "sparse_columns_ratio": 0.0
            },
            "noise_level": {
                "signal_to_noise_estimate": 2.5,
                "inherent_uncertainty": 0.1
            }
        }

    # Reuse simplified helper functions
    samples_per_feature = calculate_samples_per_feature(data)
    interaction_potential = estimate_feature_interaction_potential(data)
    sparsity_results = analyze_sparsity(data)
    signal_to_noise = estimate_signal_to_noise(data)
    inherent_uncertainty = estimate_inherent_uncertainty(data, target_column=target_column)

    return {
        "dimensionality": {
            "samples_per_feature": samples_per_feature,
            "feature_interaction_potential": interaction_potential
        },
        "sparsity_patterns": {
            "zero_dominated_ratio": sparsity_results["zero_dominated_ratio"],
            "sparse_columns_ratio": sparsity_results["sparse_columns_ratio"]
        },
        "noise_level": {
            "signal_to_noise_estimate": signal_to_noise,
            "inherent_uncertainty": inherent_uncertainty
        }
    }


def quantify_synergistic_interactions(data: pd.DataFrame,
                                      target_column: str = None,
                                      problem_type: str = 'classification') -> Dict[str, float]:
    """
    Simplified synergistic interaction quantification (fixed heuristic for consistency).

    Args:
        data (pd.DataFrame): The input DataFrame.
        target_column (str, optional): Target column for supervised analysis.
        problem_type (str, optional): 'classification' or 'regression'. Defaults to 'classification'.

    Returns:
        Dict[str, float]: Core interaction metrics (ratio + type distribution).
    """
    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = [col for col in data.columns if col not in numeric_cols and
                        data[col].dtype in ['object', 'category']]
    if target_column:
        numeric_cols = [col for col in numeric_cols if col != target_column]
        categorical_cols = [col for col in categorical_cols if col != target_column]

    n_numeric = len(numeric_cols)
    n_categorical = len(categorical_cols)
    total_cols = n_numeric + n_categorical

    if total_cols < 2:
        return {
            "synergistic_interaction_ratio": 0.0,
            "interaction_type_distribution": {
                "numerical_numerical": 0.0,
                "categorical_numerical": 0.0,
                "categorical_categorical": 0.0
            }
        }

    # Simplified interaction ratio (fixed heuristic)
    if target_column and target_column in data.columns:
        # Supervised: Use feature importance CV as proxy
        X = data.drop(columns=[target_column])
        y = data[target_column]
        X_encoded = pd.get_dummies(X, drop_first=True)

        if len(X_encoded) < 20:
            synergistic_ratio = 0.3
        else:
            try:
                model = RandomForestClassifier(n_estimators=50, max_depth=5,
                                               random_state=42) if problem_type == 'classification' else \
                    RandomForestRegressor(n_estimators=50, max_depth=5, random_state=42)
                model.fit(X_encoded, y)
                importances = model.feature_importances_
                mean_importance = importances.mean()
                cv_importance = importances.std() / mean_importance if mean_importance > 0 else 1.0
                synergistic_ratio = round(1 - min(1.0, cv_importance), 4)
            except:
                synergistic_ratio = 0.3
    else:
        # Unsupervised: Use nonlinear correlation ratio
        if n_numeric >= 2:
            nonlinear_corr_count = 0
            total_pairs = min(10, n_numeric * (n_numeric - 1) // 2)  # Limit pairs for efficiency
            pair_idx = 0
            for i in range(n_numeric):
                for j in range(i + 1, n_numeric):
                    if pair_idx >= total_pairs:
                        break
                    col1, col2 = numeric_cols[i], numeric_cols[j]
                    data_pair = data[[col1, col2]].dropna()
                    if len(data_pair) < 10:
                        continue
                    pearson, _ = stats.pearsonr(data_pair[col1], data_pair[col2])
                    spearman, _ = stats.spearmanr(data_pair[col1], data_pair[col2])
                    if abs(pearson - spearman) > 0.2:
                        nonlinear_corr_count += 1
                    pair_idx += 1
            synergistic_ratio = round(min(1.0, nonlinear_corr_count / total_pairs if total_pairs > 0 else 0.0), 4)
        else:
            synergistic_ratio = 0.0

    # Simplified type distribution (based on column counts, no random sampling)
    total_possible_pairs = total_cols * (total_cols - 1) // 2
    if total_possible_pairs == 0:
        type_dist = {"numerical_numerical": 0.0, "categorical_numerical": 0.0, "categorical_categorical": 0.0}
    else:
        nn_pairs = n_numeric * (n_numeric - 1) // 2
        cc_pairs = n_categorical * (n_categorical - 1) // 2
        nc_pairs = n_numeric * n_categorical
        type_dist = {
            "numerical_numerical": round(nn_pairs / total_possible_pairs, 4),
            "categorical_numerical": round(nc_pairs / total_possible_pairs, 4),
            "categorical_categorical": round(cc_pairs / total_possible_pairs, 4)
        }

    return {
        "synergistic_interaction_ratio": synergistic_ratio,
        "interaction_type_distribution": type_dist
    }


def detect_conditional_dependencies(data: pd.DataFrame,
                                    target_column: str = None) -> Dict[str, Any]:
    """
    Simplified conditional dependency detection (fixed partial correlation heuristic).

    Args:
        data (pd.DataFrame): The input DataFrame.
        target_column (str, optional): Target column for focused analysis.

    Returns:
        Dict[str, Any]: Core conditional dependency metrics (existence + strength).
    """
    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    if target_column:
        numeric_cols = [col for col in numeric_cols if col != target_column]

    if len(numeric_cols) < 3:
        return {
            "has_conditional_dependencies": False,
            "conditional_dependency_strength": 0.0
        }

    # Simplified: Sample triples and calculate partial correlation strength
    sampled_cols = np.random.choice(numeric_cols, min(5, len(numeric_cols)), replace=False)
    conditional_strengths = []

    for i in range(len(sampled_cols)):
        for j in range(i + 1, len(sampled_cols)):
            col1, col2 = sampled_cols[i], sampled_cols[j]
            # Try all other columns as conditioners
            for k in range(len(sampled_cols)):
                if k == i or k == j:
                    continue
                cond_col = sampled_cols[k]

                # Calculate partial correlation (residual-based)
                try:
                    # Regress col1/col2 on conditioner
                    X_cond = data[[cond_col]].dropna()
                    if len(X_cond) < 10:
                        continue
                    # Col1 residuals
                    reg1 = LinearRegression().fit(X_cond, data.loc[X_cond.index, col1].dropna())
                    residuals1 = data.loc[X_cond.index, col1].dropna() - reg1.predict(X_cond)
                    # Col2 residuals
                    reg2 = LinearRegression().fit(X_cond, data.loc[X_cond.index, col2].dropna())
                    residuals2 = data.loc[X_cond.index, col2].dropna() - reg2.predict(X_cond)
                    # Correlate residuals
                    if len(residuals1) >= 5 and len(residuals2) >= 5:
                        partial_corr, _ = stats.pearsonr(residuals1, residuals2)
                        conditional_strengths.append(abs(partial_corr))
                except:
                    continue

    if not conditional_strengths:
        return {
            "has_conditional_dependencies": False,
            "conditional_dependency_strength": 0.0
        }

    avg_strength = np.mean(conditional_strengths)
    return {
        "has_conditional_dependencies": avg_strength > 0.3,  # Fixed threshold for consistency
        "conditional_dependency_strength": round(avg_strength, 4)
    }

def quantify_categorical_numerical_interaction(data: pd.DataFrame, target_column: str = None) -> float:
    """
    Quantify interaction strength between categorical and numerical features (fixed heuristic).

    Args:
        data (pd.DataFrame): Input DataFrame.
        target_column (str, optional): Target column for supervised assessment. Defaults to None.

    Returns:
        float: Categorical-numerical interaction strength (0-1).
    """
    categorical_cols = [col for col in data.columns if data[col].dtype in ['object', 'category']]
    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    if target_column:
        categorical_cols = [col for col in categorical_cols if col != target_column]
        numeric_cols = [col for col in numeric_cols if col != target_column]

    if len(categorical_cols) == 0 or len(numeric_cols) == 0:
        return 0.0

    # 采样5对类别-数值列，避免计算量过大
    sample_pairs = []
    for cat_col in categorical_cols[:3]:
        for num_col in numeric_cols[:3]:
            sample_pairs.append((cat_col, num_col))
    sample_pairs = sample_pairs[:5]  # 最多5对

    interaction_scores = []
    for cat_col, num_col in sample_pairs:
        try:
            # 分组统计：类别分组后数值列的分布差异（方差比）
            grouped = data.groupby(cat_col)[num_col].agg(['mean', 'std']).dropna()
            if len(grouped) < 2:
                continue

            # 方差比（组间方差/组内方差）→ 差异越大，交互越强
            overall_mean = data[num_col].mean()
            between_var = np.sum(grouped['mean'].count() * (grouped['mean'] - overall_mean) ** 2) / len(grouped)
            within_var = grouped['std'].mean() ** 2
            score = min(1.0, between_var / (within_var + 0.001))
            interaction_scores.append(score)
        except:
            continue

    return round(np.mean(interaction_scores) if interaction_scores else 0.0, 4)


def analyze_time_series_properties(data: pd.DataFrame, time_column: str = None) -> Dict[str, Any]:
    """
    Simplified time series property analysis (stationarity + periodicity).

    Args:
        data (pd.DataFrame): Input DataFrame (time series data).
        time_column (str, optional): Time column name (if not provided, auto-detect). Defaults to None.

    Returns:
        Dict[str, Any]: Time series core properties.
    """
    # 自动检测时间列（datetime类型或唯一值排序后连续）
    if not time_column:
        time_cols = [col for col in data.columns if pd.api.types.is_datetime64_any_dtype(data[col])]
        time_column = time_cols[0] if time_cols else None

    if not time_column or time_column not in data.columns:
        return {
            "is_time_series": False,
            "stationarity_strength": 0.0,
            "periodicity_strength": 0.0
        }

    # 确保时间列排序
    ts_data = data.sort_values(time_column).reset_index(drop=True)
    numeric_cols = ts_data.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols:
        return {
            "is_time_series": True,
            "stationarity_strength": 0.0,
            "periodicity_strength": 0.0
        }

    # 平稳性：ADF检验p值转换（p值越小，越平稳）
    def adf_stationarity_score(series):
        try:
            from statsmodels.tsa.stattools import adfuller
            adf_result = adfuller(series.dropna())
            p_value = adf_result[1]
            return min(1.0, max(0.0, 1 - p_value))  # p<0.05 → 得分>0.95
        except:
            return 0.5  # 默认中等平稳

    # 周期性：自相关函数（ACF）峰值强度
    def periodicity_score(series):
        try:
            from statsmodels.tsa.stattools import acf
            series_clean = series.dropna()
            if len(series_clean) < 30:
                return 0.0
            acf_vals = acf(series_clean, nlags=min(20, len(series_clean)//2))
            # 排除lag=0的自相关，取最大峰值
            peak_val = max(acf_vals[1:]) if len(acf_vals) > 1 else 0.0
            return min(1.0, peak_val)
        except:
            return 0.0

    # 对前3个数值列取平均（避免单列偏差）
    stationarity_scores = [adf_stationarity_score(ts_data[col]) for col in numeric_cols[:3]]
    periodicity_scores = [periodicity_score(ts_data[col]) for col in numeric_cols[:3]]

    return {
        "is_time_series": True,
        "stationarity_strength": round(np.mean(stationarity_scores), 4),
        "periodicity_strength": round(np.mean(periodicity_scores), 4)
    }


def analyze_spatial_correlation(data: pd.DataFrame, spatial_cols: List[str] = None) -> float:
    """
    Simplified spatial correlation analysis (distance-based similarity).

    Args:
        data (pd.DataFrame): Input DataFrame (spatial data with coordinates).
        spatial_cols (List[str], optional): Spatial coordinate columns (e.g., ["lat", "lon"]). Defaults to None.

    Returns:
        float: Spatial correlation strength (0-1; 0=no spatial pattern, 1=strong spatial clustering).
    """
    # 自动检测空间列（命名包含lat/lon/coord/x/y）
    if not spatial_cols:
        spatial_pattern = r'lat|lon|coord|x|y'
        spatial_cols = [col for col in data.columns if pd.Series(col.lower()).str.contains(spatial_pattern).any()]
    if len(spatial_cols) < 2:
        return 0.0

    # 计算空间距离矩阵（采样前1000个样本，避免计算量过大）
    sample_data = data[spatial_cols].dropna().head(1000)
    if len(sample_data) < 50:
        return 0.0

    # 计算距离与数值特征的相关性（假设数值特征是空间关联的代理）
    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols:
        return 0.0

    # 空间距离（欧氏距离）
    from scipy.spatial.distance import pdist, squareform
    dist_matrix = squareform(pdist(sample_data))
    dist_flat = dist_matrix[np.triu_indices(len(sample_data), k=1)]  # 上三角矩阵，避免重复

    # 数值特征相似度（归一化后差值）
    num_col = numeric_cols[0]  # 取第一个数值列作为代理
    num_vals = sample_data[num_col].values if num_col in sample_data.columns else data[num_col].values[:len(sample_data)]
    num_vals_norm = (num_vals - num_vals.mean()) / (num_vals.std() + 0.001)
    num_diff_flat = []
    for i in range(len(sample_data)):
        for j in range(i+1, len(sample_data)):
            num_diff_flat.append(abs(num_vals_norm[i] - num_vals_norm[j]))

    # 空间相关性：距离与数值差异的负相关（距离越近，差异越小→相关性越强）
    if len(dist_flat) > 0 and len(num_diff_flat) > 0:
        corr, _ = stats.pearsonr(dist_flat, num_diff_flat)
        spatial_corr_strength = min(1.0, max(0.0, -corr))  # 负相关→转为正强度
    else:
        spatial_corr_strength = 0.0

    return round(spatial_corr_strength, 4)

def estimate_causal_confounder_strength(data: pd.DataFrame, target_column: str, treatment_column: str) -> float:
    """
    Simplified causal confounder strength estimation (residual-based partial correlation).

    Args:
        data (pd.DataFrame): Input DataFrame.
        target_column (str): Outcome column (Y).
        treatment_column (str): Treatment column (X).

    Returns:
        float: Confounder strength (0-1; 0=no confounders, 1=strong confounders).
    """
    # 验证输入列存在
    if target_column not in data.columns or treatment_column not in data.columns:
        return 0.0

    # 筛选潜在混杂因子（数值列，排除处理和结果列）
    confounder_cols = [col for col in data.select_dtypes(include=[np.number]).columns
                       if col not in [target_column, treatment_column]]
    if len(confounder_cols) < 1:
        return 0.0

    # 计算处理-结果的原始相关性
    treatment_data = data[treatment_column].dropna()
    target_data = data.loc[treatment_data.index, target_column].dropna()
    if len(treatment_data) < 30 or len(target_data) < 30:
        return 0.0
    raw_corr, _ = stats.pearsonr(treatment_data, target_data)
    raw_corr_abs = abs(raw_corr)

    # 计算控制混杂因子后的偏相关（残差法）
    try:
        # 用混杂因子预测处理和结果
        confounder_data = data.loc[treatment_data.index, confounder_cols].dropna()
        if len(confounder_data) < 20:
            return 0.3  # 默认中等混杂

        # 处理列残差
        reg_treatment = LinearRegression().fit(confounder_data, data.loc[confounder_data.index, treatment_column])
        treatment_residuals = data.loc[confounder_data.index, treatment_column] - reg_treatment.predict(confounder_data)

        # 结果列残差
        reg_target = LinearRegression().fit(confounder_data, data.loc[confounder_data.index, target_column])
        target_residuals = data.loc[confounder_data.index, target_column] - reg_target.predict(confounder_data)

        # 偏相关
        partial_corr, _ = stats.pearsonr(treatment_residuals, target_residuals)
        partial_corr_abs = abs(partial_corr)

        # 混杂强度：原始相关与偏相关的差值（差值越大，混杂越强）
        confounder_strength = min(1.0, max(0.0, raw_corr_abs - partial_corr_abs))
    except:
        confounder_strength = 0.3  # 默认中等混杂

    return round(confounder_strength, 4)


def analyze_high_cardinality_impact(data: pd.DataFrame, target_column: str = None) -> Dict[str, float]:
    """
    Analyze impact of high-cardinality categorical features (fixed threshold: ≥20 unique values).

    Args:
        data (pd.DataFrame): Input DataFrame.
        target_column (str, optional): Target column for supervised impact assessment. Defaults to None.

    Returns:
        Dict[str, float]: High-cardinality impact metrics (0-1).
    """
    categorical_cols = [col for col in data.columns if col != target_column and
                        data[col].dtype in ['object', 'category']]
    if not categorical_cols:
        return {"high_cardinality_ratio": 0.0, "high_cardinality_impact": 0.0}

    # 高基数判断（固定阈值≥20个唯一值）
    high_card_cols = [col for col in categorical_cols if data[col].nunique() >= 20]
    high_card_ratio = len(high_card_cols) / len(categorical_cols)

    # 影响强度（监督模式：编码后特征重要性；无监督模式：唯一值占比方差）
    if target_column and target_column in data.columns:
        try:
            # 简单编码（One-Hot前5个高基数列，避免维度爆炸）
            encode_cols = high_card_cols[:5]
            X_encoded = pd.get_dummies(data[encode_cols], drop_first=True, dummy_na=True)
            y = data[target_column]

            # 用决策树评估特征重要性
            model = DecisionTreeClassifier(max_depth=3, random_state=42) if y.nunique() <= 10 else \
                DecisionTreeRegressor(max_depth=3, random_state=42)
            model.fit(X_encoded, y)
            importances = model.feature_importances_
            high_card_impact = min(1.0, importances.mean() * 10)  # 归一化到0-1
        except:
            high_card_impact = 0.3  # 默认中等影响
    else:
        # 无监督：高基数列的唯一值占比方差（方差越大，影响越显著）
        unique_ratios = [min(1.0, data[col].nunique() / len(data[col])) for col in high_card_cols]
        high_card_impact = np.var(unique_ratios) if unique_ratios else 0.0

    return {
        "high_cardinality_ratio": round(high_card_ratio, 4),
        "high_cardinality_impact": round(high_card_impact, 4)
    }
