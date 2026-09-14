from sklearn.experimental import enable_iterative_imputer
from datetime import datetime
import glob
import os
from pathlib import Path
import shutil
from typing import Tuple, List
import warnings
import hashlib

warnings.simplefilter('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # set tensorflow log level to FATAL

import pandas as pd
import numpy as np
from pyspark import SparkConf, SparkContext
from pyspark.sql import SparkSession
import fasttext
import spacy
import json

from sack.knowledge.kg_governor.data_profiling.fine_grained_type_detector import FineGrainedColumnTypeDetector
from sack.knowledge.kg_governor.data_profiling.profile_creators.profile_creator import ProfileCreator
from sack.knowledge.kg_governor.data_profiling.model.competition_profile import CompetitionProfile
from sack.knowledge.kg_governor.data_profiling.model.edainsight_profile import EDAInsightProfile
from sack.knowledge.kg_governor.data_profiling.model.table import Table
from sack.knowledge.kg_governor.data_profiling.utils import generate_column_id
from sack.knowledge.knowledge_config import SACKKnowledgeConfig
from sack.knowledge.LLMUsage.llm_usages import extract_competition_elements_local


def _ensure_java_runtime() -> None:
    java_home = os.environ.get("JAVA_HOME")
    java_on_path = shutil.which("java")
    if java_home or java_on_path:
        return

    raise RuntimeError(
        "Java runtime is required by PySpark but was not found. "
        "Install OpenJDK and set JAVA_HOME before running `python -m sack build-knowledge`."
    )


def _read_text_file(file_path: str) -> str:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        with open(file_path, 'r', encoding='latin-1') as f:
            return f.read()


def _find_case_file(dataset_path: str, filename: str) -> str | None:
    candidates = [
        os.path.join(dataset_path, filename),
        os.path.join(dataset_path, 'rawdata', filename),
        os.path.join(dataset_path, 'raw_data', filename),
        os.path.join(dataset_path, 'data', filename),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def _list_csv_files_for_case(dataset_path: str) -> list[str]:
    """Return one authoritative CSV set for a SACK historical case workspace."""
    preferred_dirs = [
        dataset_path,
        os.path.join(dataset_path, 'rawdata'),
        os.path.join(dataset_path, 'raw_data'),
        os.path.join(dataset_path, 'data'),
    ]
    for candidate_dir in preferred_dirs:
        if not os.path.isdir(candidate_dir):
            continue
        csv_files = [
            os.path.join(candidate_dir, name)
            for name in os.listdir(candidate_dir)
            if name.lower().endswith('.csv')
        ]
        csv_files = [path for path in csv_files if os.path.isfile(path) and os.path.getsize(path) > 0]
        if csv_files:
            return sorted(csv_files)

    excluded_dirs = {
        'notebooks',
        'data_preparation',
        'understand_background',
        'pre_eda',
        'data_cleaning',
        'deep_eda',
        'feature_engineering',
        'model_build_predict',
        'pre_insight_extraction',
        'deep_insight_extraction',
    }
    csv_files = []
    for filename in glob.glob(os.path.join(dataset_path, '**', '*.csv'), recursive=True):
        rel_parts = Path(filename).relative_to(dataset_path).parts
        if any(part in excluded_dirs for part in rel_parts[:-1]):
            continue
        if os.path.isfile(filename) and os.path.getsize(filename) > 0:
            csv_files.append(filename)
    return sorted(csv_files)


def profile_data():
    start_time = datetime.now()
    print(datetime.now(), ': Initializing Spark')
    _ensure_java_runtime()

    # initialize spark
    if SACKKnowledgeConfig.is_spark_local_mode:
        spark_local_dir = os.path.join(SACKKnowledgeConfig.base_dir, 'spark-temp')
        os.makedirs(spark_local_dir, exist_ok=True)
        SACKKnowledgeConfig.spark_executor_mem_overhead = "1g"
        spark_conf = SparkConf()
        spark_conf.setMaster(f'local[{SACKKnowledgeConfig.spark_n_workers}]')
        spark_conf.setExecutorEnv("PYTHONPATH", str(Path(SACKKnowledgeConfig.base_dir).parent))  # sack_knowledge 的父目录。
        spark_conf.set('spark.driver.memory', f'{SACKKnowledgeConfig.spark_max_memory // 2}g')
        spark_conf.set('spark.python.worker.memory', '400m')
        spark_conf.set('spark.executor.memoryOverhead', SACKKnowledgeConfig.spark_executor_mem_overhead)
        spark_conf.set('spark.task.maxFailures', '3')
        spark_conf.set('spark.executor.memory', '1536m')
        spark_conf.set('spark.local.dir', spark_local_dir)
        spark = SparkContext(conf=spark_conf)
    else:
        spark_conf = SparkConf()
        # 处理竞赛元数据：读取overview.txt和data_description.txt并保存为JSON
        spark_conf.setExecutorEnv("PYTHONPATH", str(Path(SACKKnowledgeConfig.base_dir).parent))
        spark = SparkSession.builder.appName("SACKKnowledgeBaseProfiler").config(conf=spark_conf).getOrCreate().sparkContext

        # add python dependencies
        sack_root = os.path.dirname(SACKKnowledgeConfig.base_dir)
        for pyfile in glob.glob(os.path.join(sack_root, '**', '*.py'), recursive=True):
            spark.addPyFile(pyfile)
        # add embedding model files
        for embedding_file in glob.glob(os.path.join(SACKKnowledgeConfig.base_dir, 'kg_governor', 'data_profiling',
                                                     'column_embeddings', 'pretrained_models', '**', '*.pt'),
                                        recursive=True):
            spark.addFile(embedding_file)
        # add fasttext embeddings file
        spark.addFile(os.path.join(SACKKnowledgeConfig.base_dir, 'embeddings', 'cc.en.300.bin'))


    # 在 Driver 端加载 FastText 模型，生成竞赛元数据嵌入。
    fasttext_model_path = os.path.join(SACKKnowledgeConfig.base_dir, 'embeddings', 'cc.en.300.bin')
    if not os.path.exists(fasttext_model_path):
        raise FileNotFoundError(
            f"fastText embedding model not found: {fasttext_model_path}. "
            "Place cc.en.300.bin under storage/embeddings before building knowledge."
        )
    fasttext_model = fasttext.load_model(fasttext_model_path)

    def get_text_embedding(text, model):
        words = text.split()
        if len(words) == 0:
            return [0.0] * model.get_dimension()
        word_vectors = [model.get_word_vector(word) for word in words]
        text_vector = np.mean(word_vectors, axis=0)
        return text_vector.tolist()

    # 读取 overview.txt 和 data_description.txt，生成竞赛元数据 JSON。
    competition_profile_base_dir = os.path.join(SACKKnowledgeConfig.profiles_out_path, 'competition_profiles')
    eda_profile_base_dir = os.path.join(SACKKnowledgeConfig.profiles_out_path, 'eda_insight_profiles')
    os.makedirs(competition_profile_base_dir, exist_ok=True)
    os.makedirs(eda_profile_base_dir, exist_ok=True)

    existing_competition_md5 = set()
    if os.path.exists(competition_profile_base_dir) and not SACKKnowledgeConfig.replace_existing_profiles:
        existing_competition_md5 = set(
            [Path(p).stem for p in glob.glob(os.path.join(competition_profile_base_dir, '*.json'), recursive=False)]
        )
        print(f"Loaded {len(existing_competition_md5)} existing competition profile hashes")

    existing_eda_md5 = set()
    if os.path.exists(eda_profile_base_dir) and not SACKKnowledgeConfig.replace_existing_profiles:
        existing_eda_md5 = set(
            [Path(p).stem for p in glob.glob(os.path.join(eda_profile_base_dir, '*.json'), recursive=False)]
        )
        print(f"Loaded {len(existing_eda_md5)} existing EDA profile hashes")

    competition_schema = {
        "problem_type": ["binary_classification", "multiclass_classification",
                         "regression", "object_detection", "segmentation", "nlp", "other"],
        "domain": ["finance", "healthcare", "retail", "manufacturing",
                   "education", "entertainment", "sports", "insurance", "other"],
        "evaluation_metric": ["accuracy", "auc", "mse", "f1", "mae", "rmse", "logloss", "other"],
        "data_type": ["tabular", "text", "image", "speech", "multimodal", "other"],
        "difficulty": ["beginner", "intermediate", "advanced"]
    }
    total_datasets = len(os.listdir(SACKKnowledgeConfig.data_source_path))
    skipped_competition_count = 0
    skipped_eda_count = 0
    successful_extractions = 0
    for i, dataset in enumerate(os.listdir(SACKKnowledgeConfig.data_source_path)):
        dataset_path = os.path.join(SACKKnowledgeConfig.data_source_path, dataset)
        if os.path.isdir(dataset_path):
            print(f"Processing {i + 1}/{total_datasets}: {dataset}")

            competition_id = f"{SACKKnowledgeConfig.data_source}/{dataset}"
            competition_md5 = hashlib.md5(competition_id.encode()).hexdigest()
            if not SACKKnowledgeConfig.replace_existing_profiles and competition_md5 in existing_competition_md5:
                print(f"Competition profile already exists (MD5: {competition_md5}); skipping")
                skipped_competition_count += 1
            else:

                overview_file = _find_case_file(dataset_path, 'overview.txt')
                data_desc_file = _find_case_file(dataset_path, 'data_description.txt')

                overview_content = ""
                data_desc_content = ""

                if overview_file:
                    overview_content = _read_text_file(overview_file)
                else:
                    print(f"Warning: overview.txt not found for dataset {dataset}")

                if data_desc_file:
                    data_desc_content = _read_text_file(data_desc_file)
                else:
                    print(f"Warning: data_description.txt not found for dataset {dataset}")

                overview_embedding = get_text_embedding(overview_content, fasttext_model)
                data_description_embedding = get_text_embedding(data_desc_content, fasttext_model)
                # 3. 按EDA类型初始化Profile
                overview_embedding_scaling_factor = np.max(np.abs(overview_embedding)) if overview_embedding else 1.0
                data_description_embedding_scaling_factor = np.max(
                    np.abs(data_description_embedding)) if data_description_embedding else 1.0

                full_description = overview_content + " " + data_desc_content
                print(f"The structured elements of the competition {dataset} are being extracted...")
                structured_elements = extract_competition_elements_local(full_description, competition_schema)

                if structured_elements.get("problem_type") != "other":
                    successful_extractions += 1
                _data_type = structured_elements.get("data_type")
                if _data_type != "tabular":
                    print(f"Warning: It seems that a non-table competition has been detected {dataset} : {_data_type}")


                competition_profile = CompetitionProfile(
                    competition_id=competition_id,
                    competition_name=dataset,
                    data_source=SACKKnowledgeConfig.data_source,
                    overview=overview_content,
                    data_description=data_desc_content,
                    overview_embedding=overview_embedding,
                    data_description_embedding=data_description_embedding,
                    overview_embedding_scaling_factor=overview_embedding_scaling_factor,
                    data_description_embedding_scaling_factor=data_description_embedding_scaling_factor,
                    structured_elements=structured_elements
                )
                competition_profile.save_profile(competition_profile_base_dir)
                print(f"Saved competition profile: {dataset} (MD5: {competition_md5})")

            # EDAInsight获取
            # 4. 保存EDA Profile

            eda_paths = {
                "pre_eda": os.path.join(SACKKnowledgeConfig.history_edainsight_base_path, dataset, "pre_insight_extraction/eda_insight.json"), # 直接从数据目录获取 EDAInsight。
                "deep_eda": os.path.join(SACKKnowledgeConfig.history_edainsight_base_path, dataset, "deep_insight_extraction/eda_insight.json")
            }

            # 遍历两类 EDA 文件并创建 Profile。
            for eda_type, eda_file_path in eda_paths.items():
                eda_id = f"{competition_id}_{eda_type}"
                eda_id_md5 = hashlib.md5(eda_id.encode()).hexdigest()
                if not SACKKnowledgeConfig.replace_existing_profiles and eda_id_md5 in existing_eda_md5:
                    print(f"EDA profile already exists ({eda_id}); skipping")
                    skipped_eda_count += 1
                else:
                    if os.path.exists(eda_file_path) and os.path.getsize(eda_file_path) > 0:
                        try:
                            # 读取新模板的EDA JSON
                            with open(eda_file_path, 'r', encoding='utf-8') as f:
                                eda_json = json.load(f)

                            # 按 EDA 类型初始化 Profile。
                            if eda_type == "pre_eda":
                                pre_eda_data = eda_json
                                eda_profile = EDAInsightProfile(
                                    eda_id=eda_id,
                                    competition_id=competition_id,
                                    eda_type=eda_type,
                                    pre_eda_data_quality=pre_eda_data.get("data_quality", {}),
                                    pre_eda_basic_distribution=pre_eda_data.get("basic_distribution", {}),
                                    pre_eda_basic_dimensionality=pre_eda_data.get("basic_dimensionality", {})
                                )
                            else:  # deep_eda
                                deep_eda_data = eda_json
                                eda_profile = EDAInsightProfile(
                                    eda_id=eda_id,
                                    competition_id=competition_id,
                                    eda_type=eda_type,
                                    deep_eda_feature_relationships=deep_eda_data.get("feature_relationships", {}),
                                    deep_eda_complexity=deep_eda_data.get("complexity", {}),
                                    deep_eda_special_scenarios=deep_eda_data.get("special_scenarios", {})
                                )

                            # 4. 保存EDA Profile
                            eda_profile.save_profile(eda_profile_base_dir)
                            print(f"Successfully saved {eda_type} EDA profile for dataset: {dataset}")

                        except Exception as e:
                            print(f"Warning: Failed to process {eda_type} EDA for dataset {dataset}: {e}")
                            continue
                    else:
                        print(
                            f"Warning: {eda_type} EDA file not found or empty for dataset {dataset} (path: {eda_file_path})")

    print("\n" + "="*50)
    print(datetime.now(), ': Competition and EDA profile processing completed.')
    print(f'Total datasets: {total_datasets}')
    print(f'Skipped competitions: {skipped_competition_count}')
    print(f'Skipped EDA profiles: {skipped_eda_count}')
    print(f'Successful structured extractions: {successful_extractions}')
    print("="*50)



    # get the list of columns and their associated tables
    print(datetime.now(), ': Creating tables, Getting columns')
    columns_and_tables = []

    for dataset in os.listdir(SACKKnowledgeConfig.data_source_path):
        dataset_path = os.path.join(SACKKnowledgeConfig.data_source_path, dataset)
        if not os.path.isdir(dataset_path):
            continue
        for filename in _list_csv_files_for_case(dataset_path):
            if os.path.isfile(filename) and os.path.getsize(filename) > 0:  # if not an empty file
                table = Table(data_source=SACKKnowledgeConfig.data_source,
                              table_path=filename,
                              dataset_name=dataset)
                # read only the header
                try:
                    header = pd.read_csv(table.get_table_path(), nrows=0, engine='python', encoding_errors='replace')
                except:
                    continue
                columns_and_tables.extend([(col, table) for col in header.columns])

    # delete existing profiles if necessary
    if os.path.exists(SACKKnowledgeConfig.profiles_out_path):
        if SACKKnowledgeConfig.replace_existing_profiles:
            print(datetime.now(), ': Deleting existing column profiles in:', SACKKnowledgeConfig.profiles_out_path)
            shutil.rmtree(SACKKnowledgeConfig.profiles_out_path)
        else:
            # skip existing profiles
            existing_profiles = set(
                [Path(p).stem for p in glob.glob(os.path.join(SACKKnowledgeConfig.profiles_out_path, '**', '*.json'),
                                                 recursive=True)])
            print(datetime.now(), f': Skipping {len(existing_profiles)} existing profiles.')
            for i in range(len(columns_and_tables)):
                column_id = generate_column_id(columns_and_tables[i][1].get_data_source(),
                                               columns_and_tables[i][1].get_dataset_name(),
                                               columns_and_tables[i][1].get_table_name(),
                                               str(columns_and_tables[i][0]))
                column_profile_name = hashlib.md5(column_id.encode()).hexdigest()
                if column_profile_name in existing_profiles:
                    columns_and_tables[i] = None
            columns_and_tables = [i for i in columns_and_tables if i]

    os.makedirs(SACKKnowledgeConfig.profiles_out_path, exist_ok=True)

    # profile the columns with Spark.
    num_cores = SACKKnowledgeConfig.spark_n_workers  
    num_partitions = min(num_cores * 2, len(columns_and_tables)) if len(columns_and_tables)!=0 else 1
    columns_and_tables_rdd = spark.parallelize(columns_and_tables,num_partitions)
    print(datetime.now(), f': Profiling {len(columns_and_tables)} columns')
    columns_and_tables_rdd.mapPartitions(
        lambda x: column_worker(column_names_and_tables=x, profiles_out_path=SACKKnowledgeConfig.profiles_out_path)).collect()
    spark.stop()
    print(datetime.now(), f': {len(columns_and_tables)} columns profiled and saved to {SACKKnowledgeConfig.profiles_out_path}')
    print(datetime.now(), ': Total time to profile: ', datetime.now() - start_time)


def column_worker(column_names_and_tables: List[Tuple[str, Table]], profiles_out_path: str):
    fasttext_model = fasttext.load_model(os.path.join(SACKKnowledgeConfig.base_dir, 'embeddings/cc.en.50.bin'))
    try:
        ner_model = spacy.load('en_core_web_sm')
    except:
        import subprocess

        subprocess.call('python -m spacy download en_core_web_sm'.split(), shell=False)
        ner_model = spacy.load('en_core_web_sm')
    for (column_name, table) in column_names_and_tables:
        # read the column from the table file. Use the Python engine if there are issues reading the file
        try:
            try:
                column = pd.read_csv(table.get_table_path(), usecols=[column_name],
                                     na_values=[' ', '?', '-']).iloc[:, 0]
            except:
                column = pd.read_csv(table.get_table_path(), usecols=[column_name],
                                     na_values=[' ', '?', '-'],
                                     engine='python', encoding_errors='replace').iloc[:, 0]

            column = pd.to_numeric(column, errors='ignore')
            column = column.convert_dtypes()
            column = column.astype(str) if column.dtype == object else column

            # infer the column data type
            column_type = FineGrainedColumnTypeDetector.detect_column_data_type(column, fasttext_model, ner_model)

            # collect statistics, generate embeddings, and create the column profiles
            column_profile_creator = ProfileCreator.get_profile_creator(column, column_type, table, fasttext_model)
            column_profile = column_profile_creator.create_profile()

            # store the profile
            column_profile.save_profile(profiles_out_path)
        except Exception as e:
            print(f'Warning: Skipping non-parse-able column: {column_name} in table: {table.get_table_path()}')
            print(e)
            continue
    return []
