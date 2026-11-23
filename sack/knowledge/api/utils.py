import os
import hashlib

from typing import Tuple,List,Dict,Any

import numpy as np

import pandas as pd

import fasttext

import spacy

import json

from sack.knowledge.knowledge_config import SACKKnowledgeConfig

from sack.knowledge.LLMUsage.llm_usages import extract_competition_elements_local

from sack.knowledge.kg_governor.data_profiling.model.table import Table

from sack.knowledge.kg_governor.data_profiling.model.edainsight_profile import EDAInsightProfile

from sack.knowledge.kg_governor.data_profiling.fine_grained_type_detector import FineGrainedColumnTypeDetector

from sack.knowledge.kg_governor.data_profiling.profile_creators.profile_creator import ProfileCreator

from sack.knowledge.kg_governor.data_global_schema_builder.utils.utils import generate_label

from sack.knowledge.api.edainsight_similarity import FIELD_WEIGHTS,MODULE_WEIGHTS

import glob

def _find_competition_file(comp_path: str, filename: str) -> str | None:
    candidates = [
        os.path.join(comp_path, filename),
        os.path.join(comp_path, 'rawdata', filename),
        os.path.join(comp_path, 'raw_data', filename),
        os.path.join(comp_path, 'data', filename),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def _list_competition_csv_files(comp_path: str) -> List[str]:
    # A dataset snapshot consists of train/test, never submission or derived tables.
    for directory in (comp_path, os.path.join(comp_path, 'rawdata'),
                      os.path.join(comp_path, 'raw_data'), os.path.join(comp_path, 'data')):
        files = [os.path.join(directory, name) for name in ('train.csv', 'test.csv')]
        if all(os.path.isfile(path) and os.path.getsize(path) > 0 for path in files):
            return files
    raise ValueError(f"Profile requires non-empty train.csv and test.csv in {comp_path}")


def profile_input_manifest(comp_path: str) -> Dict[str, str]:
    manifest = {}
    inputs = _list_competition_csv_files(comp_path)
    for name in ('overview.txt', 'data_description.txt'):
        path = _find_competition_file(comp_path, name)
        if path:
            inputs.append(path)
    for path in inputs:
        with open(path, 'rb') as source:
            manifest[os.path.basename(path)] = hashlib.sha256(source.read()).hexdigest()
    return manifest


def profile_single_competition(new_comp_path: str) -> Tuple[dict, List[dict]]: # 新竞赛的本地路径（如"/data/new_competition"）

    """

    处理单个新竞赛，生成competition profile和column profiles

    返回：(competition_profile_dict, column_profiles_list)

    """

    # --------------------------

    # 1. 提取竞赛元数据（复用现有逻辑）

    # --------------------------

    dataset = os.path.basename(new_comp_path)  # 新竞赛名称

    overview_file = _find_competition_file(new_comp_path, 'overview.txt')

    data_desc_file = _find_competition_file(new_comp_path, 'data_description.txt')



    # 读取overview和data_description（复用编码处理逻辑）

    overview_content = ""

    if overview_file and os.path.exists(overview_file):

        try:

            with open(overview_file, 'r', encoding='utf-8') as f:

                overview_content = f.read()

        except UnicodeDecodeError:

            with open(overview_file, 'r', encoding='latin-1') as f:

                overview_content = f.read()



    data_desc_content = ""

    if data_desc_file and os.path.exists(data_desc_file):

        try:

            with open(data_desc_file, 'r', encoding='utf-8') as f:

                data_desc_content = f.read()

        except UnicodeDecodeError:

            with open(data_desc_file, 'r', encoding='latin-1') as f:

                data_desc_content = f.read()



    # 生成嵌入（复用get_text_embedding逻辑）

    def get_text_embedding(text, model):

        # 关键修复：移除换行符（\n），并用单个空格替换多余空白，确保文本为单行

        cleaned_text = text.replace('\n', ' ').replace('\r', ' ').strip()  # 移除\n和\r，避免换行问题

        # 进一步处理：多个空格合并为一个（可选，让文本更整洁）

        cleaned_text = ' '.join(cleaned_text.split())

        # 生成嵌入

        return model.get_sentence_vector(cleaned_text).tolist()



    fasttext_competition_model = fasttext.load_model(os.path.join(SACKKnowledgeConfig.base_dir, 'embeddings/cc.en.300.bin'))

    try:

        ner_model = spacy.load('en_core_web_sm')

    except:

        import subprocess

        subprocess.call('python -m spacy download en_core_web_sm'.split(), shell=False)

        ner_model = spacy.load('en_core_web_sm')



    overview_embedding = get_text_embedding(overview_content, fasttext_competition_model)

    data_description_embedding = get_text_embedding(data_desc_content, fasttext_competition_model)



    # 提取结构化要素（复用schema和提取函数）

    competition_schema = {

        "problem_type": ["binary_classification", "multiclass_classification",

                         "regression", "object_detection", "segmentation", "nlp", "other"],

        "domain": ["finance", "healthcare", "retail", "manufacturing",

                   "education", "entertainment", "sports", "insurance", "other"],

        "evaluation_metric": ["accuracy", "auc", "mse", "f1", "mae", "rmse", "logloss", "other"],

        "data_type": ["tabular", "text", "image", "speech", "multimodal", "other"],

        "difficulty": ["beginner", "intermediate", "advanced"]

    }

    full_description = overview_content + " " + data_desc_content

    structured_elements = extract_competition_elements_local(full_description, competition_schema)



    # 组装competition profile（格式与图内竞赛一致）

    competition_profile = {

        "comp_id": f"{SACKKnowledgeConfig.data_source}/{dataset}",  # 临时ID，无需写入知识图谱

        "competition_name": dataset,

        "overview": overview_content,

        "data_description": data_desc_content,

        "overview_embedding": overview_embedding,

        "data_description_embedding": data_description_embedding,

        "structured_elements": structured_elements  # 包含problem_type/data_type等

    }



    # --------------------------

    # 2. 处理列数据（复用列类型检测和嵌入生成）

    # --------------------------

    table_profiles = []
    failures = []

    fasttext_column_model = fasttext.load_model(os.path.join(SACKKnowledgeConfig.base_dir, 'embeddings/cc.en.50.bin'))



    for csv_file in _list_competition_csv_files(new_comp_path):

        if os.path.isfile(csv_file) and os.path.getsize(csv_file) > 0:

            table_name = os.path.basename(csv_file)  # 当前表名=CSV文件名

            current_table_columns = []  # 仅存储当前CSV文件的列



            table = Table(

                data_source="new_competition",

                table_path=csv_file,

                dataset_name=dataset

            )



            try:

                header = pd.read_csv(csv_file, nrows=0, engine='python', encoding_errors='replace')

            except Exception as exc:

                raise RuntimeError(f"Cannot read profile input {csv_file}: {exc}") from exc

            for col_name in header.columns:

                try:

                    try:

                        column_df = pd.read_csv(csv_file, usecols=[col_name], na_values=[' ', '?', '-'])

                        column = column_df.squeeze("columns")

                    except:

                        column_df = pd.read_csv(

                            csv_file, usecols=[col_name], na_values=[' ', '?', '-'],

                            engine='python', encoding_errors='replace'

                        )

                        column = column_df.squeeze("columns")



                    column = pd.to_numeric(column, errors='ignore')

                    column = column.convert_dtypes()

                    column = column.astype(str) if column.dtype == object else column



                    column_type = FineGrainedColumnTypeDetector.detect_column_data_type(

                        column, fasttext_column_model, ner_model

                    )



                    column_profile_creator = ProfileCreator.get_profile_creator(

                        column, column_type, table, fasttext_column_model

                    )

                    column_profile = column_profile_creator.create_profile()



                    formatted_col_name = generate_label(col_name, 'en').get_text()

                    label_embedding = fasttext_competition_model.get_sentence_vector(

                        formatted_col_name.strip()).tolist()

                    content_embedding = column_profile.get_embedding() or [0.0] * 300



                    column_profile_dict = {

                        "col_name": col_name,

                        "data_type": column_profile.get_data_type(),

                        "label_embedding": label_embedding,

                        "content_embedding": content_embedding,

                        "dataset_name": dataset

                    }

                    current_table_columns.append(column_profile_dict)  # 仅添加到当前表的列列表



                except Exception as e:

                    failures.append({"table": table_name, "column": str(col_name),
                                     "error_type": type(e).__name__, "error": str(e)})
                    print(e)
                    print(f"Profile column failed: {col_name} ({csv_file})")

                    import traceback

                    traceback.print_exc()

                    continue



            # 将当前CSV文件对应的表信息添加到列表

            table_profiles.append({

                "table_name": table_name,

                "expected_columns": [str(name) for name in header.columns],
                "columns": current_table_columns

            })



    if failures:
        error_path = os.path.join(new_comp_path, 'profile_errors.json')
        with open(error_path, 'w', encoding='utf-8') as output:
            json.dump(failures, output, ensure_ascii=False, indent=2)
        raise RuntimeError(f"Profile incomplete: {len(failures)} column failures; see {error_path}")
    return competition_profile, table_profiles





def get_current_competition_edainsight(comp_path: str) -> Dict[str, Dict[str, Dict[str, Any]]]:

    """

    简化后：返回结构为 {eda_type: {module: {field_path: value}}}

    去掉flat/df，只保留核心的嵌套字典

    """

    eda_paths = {

        "pre_eda": os.path.join(comp_path, "pre_insight_extraction/eda_insight.json"),

        "deep_eda": os.path.join(comp_path, "deep_insight_extraction/eda_insight.json")

    }

    eda_insight = {}  # 最终结构：eda_type → module → field_path → value



    for eda_type, eda_file_path in eda_paths.items():

        eda_insight[eda_type] = {}  # 初始化module字典

        if os.path.exists(eda_file_path) and os.path.getsize(eda_file_path) > 0:

            try:

                # 1. 读取原始嵌套JSON

                with open(eda_file_path, 'r', encoding='utf-8') as f:

                    raw_json = json.load(f)



                # 2. 直接组织为module→field_path→value（关键：不再扁平化，而是按FIELD_WEIGHTS匹配字段路径）

                for module in MODULE_WEIGHTS.get(eda_type, {}).keys():

                    if module not in raw_json:

                        continue  # 跳过不存在的模块

                    module_data = raw_json[module]

                    # 递归提取字段路径（内部逻辑，不再暴露flat字典）

                    def extract_field_paths(nested_dict: Dict, parent_key: str = "", sep: str = ".") -> Dict[str, Any]:

                        items = {}

                        for k, v in nested_dict.items():

                            new_key = f"{parent_key}{sep}{k}" if parent_key else k

                            if isinstance(v, dict):

                                items.update(extract_field_paths(v, new_key, sep))

                            else:

                                items[new_key] = v

                        return items



                    # 提取当前模块的所有字段路径→值

                    field_paths = extract_field_paths(module_data)

                    # 只保留FIELD_WEIGHTS中定义的字段（过滤无关字段）

                    valid_field_paths = {fp: val for fp, val in field_paths.items() if fp in FIELD_WEIGHTS.get(module, {})}

                    eda_insight[eda_type][module] = valid_field_paths



            except Exception as e:

                print(f"Warning: Failed to get {eda_type} EDA for current competition: {e}")

                continue

        else:

            print(f"Warning: {eda_type} file {eda_file_path} does not exist or is empty")



    return eda_insight



