import argparse
from datetime import datetime
import glob
import json
import multiprocessing as mp
import os
import random
import string
import shutil

from pyspark import SparkConf, SparkContext
from pyspark.sql import SparkSession
from tqdm import tqdm

from sack.knowledge.kg_governor.data_global_schema_builder.workers import column_metadata_worker, column_pair_similarity_worker
from sack.knowledge.kg_governor.data_global_schema_builder.utils.word_embeddings import WordEmbeddings
from sack.knowledge.kg_governor.data_global_schema_builder.utils.utils import generate_label, RDFResource, Triplet
from sack.knowledge.kg_governor.data_profiling.model.column_profile import ColumnProfile
from sack.knowledge.kg_governor.data_profiling.model.edainsight_profile import EDAInsightProfile
from sack.knowledge.knowledge_config import SACKKnowledgeConfig


class DataGlobalSchemaBuilder:
    def __init__(self, column_profiles_path, out_graph_path, is_spark_local_mode, label_sim_threshold,
                 embedding_sim_threshold, boolean_sim_threshold):
        self.column_profiles_base_dir = column_profiles_path
        self.graph_output_path = out_graph_path
        self.out_graph_base_dir = os.path.dirname(self.graph_output_path)
        if os.path.exists(self.graph_output_path):
            renamed_graph = f'{self.out_graph_base_dir}/OLD_{datetime.now().strftime("%Y_%m_%d_%H_%M")}_{self.graph_output_path.split("/")[-1]}'
            print(f'Found existing graph at: {self.graph_output_path}. Renaming to: {renamed_graph}')
            os.rename(self.graph_output_path, renamed_graph)
        self.tmp_graph_base_dir = os.path.join(self.out_graph_base_dir, 'tmp')  # for intermediate results
        if os.path.exists(self.tmp_graph_base_dir):
            shutil.rmtree(self.tmp_graph_base_dir)
        os.makedirs(self.tmp_graph_base_dir)

        self.competition_profiles_path = os.path.join(SACKKnowledgeConfig.profiles_out_path, 'competition_profiles')
        self.eda_profile_path = os.path.join(SACKKnowledgeConfig.profiles_out_path, 'eda_insight_profiles')

        self.memory_size = 24  # total RAM - 1 GB
        self.is_spark_local_mode = is_spark_local_mode

        self.label_sim_threshold = label_sim_threshold
        self.embedding_sim_threshold = embedding_sim_threshold
        self.boolean_sim_threshold = boolean_sim_threshold

        self.ontology = {'sack_knowledge': 'http://sack.local/ontology/',
                         'sackData': 'http://sack.local/ontology/data/',
                         'sackResource': 'http://sack.local/resource/',
                         'schema': 'http://schema.org/',
                         'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
                         'rdfs': 'http://www.w3.org/2000/01/rdf-schema#'}

        # get list of column profiles and their data type
        column_data_types = [str(i.name) for i in os.scandir(column_profiles_path) if i.is_dir()]
        column_profile_paths = []
        print('Column Type Breakdown:')
        for data_type in column_data_types:
            if data_type == "competition_profiles" or data_type == "eda_insight_profiles":
                continue
            type_path = os.path.join(column_profiles_path, data_type)
            profiles = [os.path.join(type_path, i) for i in os.listdir(type_path) if i.endswith('.json')]
            column_profile_paths.extend(profiles)
            print(f'\t{data_type}: {len(profiles)}')
        print('Total:', len(column_profile_paths))
        print('Reading column profiles ...')
        pool = mp.Pool(os.cpu_count() - 1)
        self.column_profiles = list(tqdm(pool.imap_unordered(ColumnProfile.load_profile, column_profile_paths),
                                         total=len(column_profile_paths)))
        if not self.column_profiles:
            raise ValueError(
                f"No column profiles found under {column_profiles_path}. "
                "Run profiling first and check for skipped-column errors."
            )
        max_columns = int(os.environ.get("SACK_SCHEMA_MAX_COLUMNS", "0"))
        if max_columns > 0 and len(self.column_profiles) > max_columns:
            print(f"Limiting schema build to {max_columns} columns for smoke testing.")
            self.column_profiles = self.column_profiles[:max_columns]

        self.word_embedding_path = os.path.join(SACKKnowledgeConfig.base_dir, 'embeddings/glove.6B.100d.txt')
        # make sure the word embeddings are initialized
        self.word_embedding = WordEmbeddings(self.word_embedding_path)

        if not self.is_spark_local_mode:
            self.spark = (SparkSession.builder
                          .appName("KGBuilder")
                          .getOrCreate()
                          .sparkContext)
            # add python dependencies
            for pyfile in glob.glob(
                    os.path.join(SACKKnowledgeConfig.base_dir, 'kg_governor/data_global_schema_builder/**/*.py'),
                    recursive=True):
                self.spark.addPyFile(pyfile)
            # self.spark.addPyFile('../../data_profiling/src/data/column_profile.py')
        else:
            self.spark = SparkContext(conf=SparkConf().setMaster(f'local[8]') .set('spark.driver.memory', f'{self.memory_size}g').set("spark.broadcast.compress", "true"))

    def _load_competition_profiles(self):
        """Load competition profiles."""
        competition_profiles = {}
        if not os.path.exists(self.competition_profiles_path):
            print(f"Warning: Competition profiles path does not exist: {self.competition_profiles_path}")
            return competition_profiles

        try:
            for filename in os.listdir(self.competition_profiles_path):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.competition_profiles_path, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        profile_data = json.load(f)
                    competition_id = profile_data.get('competition_id')
                    if competition_id:
                        competition_profiles[competition_id] = profile_data
            print(f"Loaded {len(competition_profiles)} competition profiles")
        except Exception as e:
            print(f"Error loading competition profiles: {e}")

        return competition_profiles

    def _load_eda_insight_profiles(self):
        """Load EDAInsight profiles grouped by competition id."""
        eda_profiles = {}
        if not os.path.exists(self.eda_profile_path):
            print(f"Warning: EDA Insight profiles path not found: {self.eda_profile_path}")
            return eda_profiles

        try:
            for filename in os.listdir(self.eda_profile_path):
                if filename.endswith('.json'):
                    profile_path = os.path.join(self.eda_profile_path, filename)
                    eda_profile = EDAInsightProfile.load_profile(profile_path)
                    competition_id = eda_profile.get_competition_id()
                    if not competition_id:
                        print(f"Warning: EDA profile {filename} missing competition_id, skipping")
                        continue
                    if competition_id not in eda_profiles:
                        eda_profiles[competition_id] = []
                    eda_profiles[competition_id].append(eda_profile)
            print(f"Loaded EDA profiles for {len(eda_profiles)} competitions (key: competition_id)")
        except Exception as e:
            print(f"Error loading EDA Insight profiles: {e}")
        return eda_profiles



    def build_membership_and_metadata_subgraph(self):

        # generate column metadata triples in parallel
        ontology = self.ontology
        tmp_graph_dir = self.tmp_graph_base_dir

        # mapPartitions so we don't end up with too many subgraph files (compared to .map())
        total_profiles = len(self.column_profiles)
        max_objects_per_partition = 300  # 单个分区最多300个对象（体积≈942 KiB） #
        num_partitions = (total_profiles + max_objects_per_partition - 1) // max_objects_per_partition
        column_profile_paths_rdd = self.spark.parallelize(self.column_profiles,numSlices=num_partitions)
        column_profile_paths_rdd.mapPartitions(lambda x: column_metadata_worker(column_profiles=x,
                                                                                ontology=ontology,
                                                                                triples_output_tmp_dir=tmp_graph_dir)).collect()

        # 加载竞赛元数据
        competition_profiles = self._load_competition_profiles()
        eda_insight_profiles = self._load_eda_insight_profiles()

        self.eda_field_mapping = {
            "pre_eda": {
                # pre_eda.data_quality
                ("data_quality", "missingness.overall_missing_rate"): ("eda_pre_miss_overall_rate", "float"),
                ("data_quality", "missingness.column_missing_distribution.proportions"): ("eda_pre_miss_col_dist_props_json", "json"),
                ("data_quality", "missingness.row_completeness.complete_rows_ratio"): ("eda_pre_miss_row_complete_ratio", "float"),
                ("data_quality", "missingness.row_completeness.rows_with_any_missing_ratio"): ("eda_pre_miss_row_any_ratio", "float"),
                ("data_quality", "missingness.row_completeness.high_missing_rows_ratio"): ("eda_pre_miss_row_high_ratio", "float"),
                ("data_quality", "missingness.missing_pattern_type.pattern_type"): ("eda_pre_miss_pattern_type", "string"),
                ("data_quality", "missingness.missing_pattern_type.confidence"): ("eda_pre_miss_pattern_conf", "float"),
                ("data_quality", "outliers.outlier_columns_ratio"): ("eda_pre_outlier_col_ratio", "float"),
                ("data_quality", "outliers.avg_outlier_ratio"): ("eda_pre_outlier_avg_ratio", "float"),
                ("data_quality", "outliers.outlier_severity_distribution"): ("eda_pre_outlier_severity_dist_json", "json"),
                ("data_quality", "data_integrity.type_violation_ratio"): ("eda_pre_integrity_type_viol_ratio", "float"),
                ("data_quality", "data_integrity.unique_violation_ratio"): ("eda_pre_integrity_unique_viol_ratio", "float"),

                # pre_eda.basic_distribution
                ("basic_distribution", "numerical.skewness_profile.highly_skewed_ratio"): ("eda_pre_num_skew_high_ratio", "float"),
                ("basic_distribution", "numerical.skewness_profile.positive_skew_ratio"): ("eda_pre_num_skew_pos_ratio", "float"),
                ("basic_distribution", "numerical.skewness_profile.negative_skew_ratio"): ("eda_pre_num_skew_neg_ratio", "float"),
                ("basic_distribution", "numerical.skewness_profile.symmetric_ratio"): ("eda_pre_num_skew_sym_ratio", "float"),
                ("basic_distribution", "numerical.scale_characteristics.wide_range_ratio"): ("eda_pre_num_scale_wide_ratio", "float"),
                ("basic_distribution", "numerical.scale_characteristics.unit_heterogeneity"): ("eda_pre_num_scale_unit_hetero", "boolean"),
                ("basic_distribution", "numerical.normality_assessment.normal_like_ratio"): ("eda_pre_num_norm_normal_ratio", "float"),
                ("basic_distribution", "numerical.normality_assessment.tested_columns_count"): ("eda_pre_num_norm_tested_count", "int"),
                ("basic_distribution", "numerical.multimodal_assessment.multimodal_ratio"): ("eda_pre_num_multi_ratio", "float"),
                ("basic_distribution", "numerical.multimodal_assessment.tested_columns_count"): ("eda_pre_num_multi_tested_count", "int"),
                ("basic_distribution", "categorical.cardinality_pattern.low_cardinality_ratio"): ("eda_pre_cat_card_low_ratio", "float"),
                ("basic_distribution", "categorical.cardinality_pattern.medium_cardinality_ratio"): ("eda_pre_cat_card_medium_ratio", "float"),
                ("basic_distribution", "categorical.cardinality_pattern.high_cardinality_ratio"): ("eda_pre_cat_card_high_ratio", "float"),
                ("basic_distribution", "categorical.cardinality_pattern.cardinality_distribution_type"): ("eda_pre_cat_card_dist_type", "string"),
                ("basic_distribution", "categorical.cardinality_pattern.long_tail_prevalence"): ("eda_pre_cat_card_long_tail", "float"),
                ("basic_distribution", "categorical.imbalance_profile.balanced_ratio"): ("eda_pre_cat_imbal_balanced_ratio", "float"),
                ("basic_distribution", "categorical.imbalance_profile.moderately_imbalanced_ratio"): ("eda_pre_cat_imbal_moderate_ratio", "float"),
                ("basic_distribution", "categorical.imbalance_profile.highly_imbalanced_ratio"): ("eda_pre_cat_imbal_high_ratio", "float"),
                ("basic_distribution", "categorical.rare_categories.columns_with_rare_categories_ratio"): ("eda_pre_cat_rare_col_ratio", "float"),
                ("basic_distribution", "categorical.rare_categories.average_rare_category_density"): ("eda_pre_cat_rare_avg_density", "float"),

                # pre_eda.basic_dimensionality
                ("basic_dimensionality", "samples_per_feature"): ("eda_pre_dim_samples_per_feature", "float"),
            },
            "deep_eda": {
                # deep_eda.feature_relationships
                ("feature_relationships", "correlation_structure.correlation_strength.weak_correlation_ratio"): ("eda_deep_corr_weak_ratio", "float"),
                ("feature_relationships", "correlation_structure.correlation_strength.moderate_correlation_ratio"): ("eda_deep_corr_moderate_ratio", "float"),
                ("feature_relationships", "correlation_structure.correlation_strength.strong_correlation_ratio"): ("eda_deep_corr_strong_ratio", "float"),
                ("feature_relationships", "correlation_structure.correlation_clustering.cluster_count"): ("eda_deep_corr_cluster_count", "int"),
                ("feature_relationships", "correlation_structure.correlation_clustering.largest_cluster_proportion"): ("eda_deep_corr_cluster_largest_prop", "float"),
                ("feature_relationships", "correlation_structure.multicollinearity.high_multicollinearity_ratio"): ("eda_deep_corr_multi_high_ratio", "float"),
                ("feature_relationships", "correlation_structure.multicollinearity.redundant_pair_ratio"): ("eda_deep_corr_multi_redundant_ratio", "float"),
                ("feature_relationships", "target_relationship.feature_importance_distribution.high_importance_ratio"): ("eda_deep_target_imp_high_ratio", "float"),
                ("feature_relationships","target_relationship.feature_importance_distribution.importance_concentration_gini"): ("eda_deep_target_imp_gini", "float"),
                ("feature_relationships", "target_relationship.interaction_with_target.complex_interaction_ratio"): ("eda_deep_target_interact_complex_ratio", "float"),
                ("feature_relationships","interaction_patterns.synergistic_interactions.synergistic_interaction_ratio"): ("eda_deep_interact_synergy_ratio", "float"),
                ("feature_relationships","interaction_patterns.synergistic_interactions.interaction_type_distribution"): ("eda_deep_interact_synergy_type_dist_json", "json"),
                ("feature_relationships", "interaction_patterns.categorical_numerical_interaction"): ("eda_deep_interact_cat_num", "float"),
                ("feature_relationships","interaction_patterns.conditional_dependencies.has_conditional_dependencies"): ("eda_deep_interact_cond_deps", "boolean"),
                ("feature_relationships","interaction_patterns.conditional_dependencies.conditional_dependency_strength"): ("eda_deep_interact_cond_strength", "float"),
                ("feature_relationships", "interaction_patterns.nonlinear_relationships.nonlinear_ratio"): ("eda_deep_interact_nonlinear_ratio", "float"),

                # deep_eda.complexity
                ("complexity", "dimensionality.samples_per_feature"): ("eda_deep_complex_dim_samples_per_feature", "float"),
                ("complexity", "dimensionality.feature_interaction_potential"): ("eda_deep_complex_dim_interact_potential", "float"),
                ("complexity", "sparsity_patterns.zero_dominated_ratio"): ("eda_deep_complex_sparse_zero_ratio", "float"),
                ("complexity", "sparsity_patterns.sparse_columns_ratio"): ("eda_deep_complex_sparse_col_ratio", "float"),
                ("complexity", "noise_level.signal_to_noise_estimate"): ("eda_deep_complex_noise_snr", "float"),
                ("complexity", "noise_level.inherent_uncertainty"): ("eda_deep_complex_noise_uncertainty", "float"),

                # deep_eda.special_scenarios
                ("special_scenarios", "temporal_properties.is_time_series"): ("eda_deep_special_temp_is_ts", "boolean"),
                ("special_scenarios", "temporal_properties.stationarity_strength"): ("eda_deep_special_temp_stationarity", "float"),
                ("special_scenarios", "temporal_properties.periodicity_strength"): ("eda_deep_special_temp_periodicity", "float"),
                ("special_scenarios", "causal_properties.confounder_strength"): ("eda_deep_special_causal_confounder", "float"),
                ("special_scenarios", "spatial_properties.spatial_correlation_strength"): ("eda_deep_special_spatial_corr", "float"),
                ("special_scenarios", "high_cardinality_impact.high_cardinality_ratio"): ("eda_deep_special_high_card_ratio", "float"),
                ("special_scenarios", "high_cardinality_impact.high_cardinality_impact"): ("eda_deep_special_high_card_impact", "float"),
            }
        }



        # generate table and dataset membership triples
        membership_triples = []
        tables = set()
        competitions = set()
        sources = set()
        for column_profile in self.column_profiles:
            if column_profile.get_table_id() in tables:
                continue
            # table -> dataset membership and metadata
            tables.add(column_profile.get_table_id())
            table_node = RDFResource(column_profile.get_table_id(), self.ontology['sackResource'])
            competition_node = RDFResource(column_profile.get_dataset_id(), self.ontology['sackResource'])
            table_label = generate_label(column_profile.get_table_name(), 'en')
            membership_triples.append(Triplet(table_node, RDFResource('isPartOf', self.ontology['sack_knowledge']),
                                              RDFResource(competition_node)))
            membership_triples.append(Triplet(table_node, RDFResource('name', self.ontology['schema']),
                                              RDFResource(column_profile.get_table_name())))
            membership_triples.append(Triplet(table_node, RDFResource('label', self.ontology['rdfs']),
                                              RDFResource(table_label)))
            membership_triples.append(Triplet(table_node, RDFResource('hasFilePath', self.ontology['sackData']),
                                              RDFResource(column_profile.get_path())))
            membership_triples.append(Triplet(table_node, RDFResource('type', self.ontology['rdf']),
                                              RDFResource('Table', self.ontology['sack_knowledge'])))

            if column_profile.get_dataset_id() in competitions:
                continue
            # dataset -> source membership and metadata
            competitions.add(column_profile.get_dataset_id())
            competition_id = column_profile.get_dataset_id()
            source_node = RDFResource(column_profile.get_data_source(), self.ontology['sackResource'])
            competition_label = generate_label(column_profile.get_dataset_name(), 'en')
            competition_metadata = competition_profiles.get(competition_id, {})
            current_comp_eda_profiles = eda_insight_profiles.get(competition_id, [])


            membership_triples.append(Triplet(competition_node, RDFResource('isPartOf', self.ontology['sack_knowledge']),
                                              RDFResource(source_node)))
            membership_triples.append(Triplet(competition_node, RDFResource('name', self.ontology['schema']),
                                              RDFResource(column_profile.get_dataset_name())))
            membership_triples.append(Triplet(competition_node, RDFResource('label', self.ontology['rdfs']),
                                              RDFResource(competition_label)))
            membership_triples.append(Triplet(competition_node, RDFResource('type', self.ontology['rdf']),
                                              RDFResource('Dataset', self.ontology['sack_knowledge'], False)))

            # 娣诲姞绔炶禌鐨刼verview鍜宒ata_description
            if competition_metadata.get('overview'):
                membership_triples.append(
                    Triplet(competition_node, RDFResource('hasOverview', self.ontology['sackData']),
                            RDFResource(competition_metadata['overview'])))
            if competition_metadata.get('data_description'):
                membership_triples.append(
                    Triplet(competition_node, RDFResource('hasDataDescription', self.ontology['sackData']),
                            RDFResource(competition_metadata['data_description'])))
            # 添加竞赛的overview和data_description
            structured_elements = competition_metadata.get('structured_elements', {})
            if structured_elements.get('problem_type'):
                membership_triples.append(
                    Triplet(competition_node, RDFResource('hasProblemType', self.ontology['sackData']),
                            RDFResource(structured_elements['problem_type'])))
            if structured_elements.get('domain'):
                membership_triples.append(
                    Triplet(competition_node, RDFResource('hasDomain', self.ontology['sackData']),
                            RDFResource(structured_elements['domain'])))
            if structured_elements.get('data_type'):
                membership_triples.append(
                    Triplet(competition_node, RDFResource('hasDataType', self.ontology['sackData']),
                            RDFResource(structured_elements['data_type'])))
            if structured_elements.get('difficulty'):
                membership_triples.append(
                    Triplet(competition_node, RDFResource('hasDifficulty', self.ontology['sackData']),
                            RDFResource(structured_elements['difficulty'])))

            # 添加结构化要素
            for eda_profile in current_comp_eda_profiles:
                eda_type = eda_profile.get_eda_type()
                eda_id = eda_profile.get_eda_id()
                eda_uri = eda_id
                eda_node_type = "PreliminaryEDAInsight" if eda_type == "pre_eda" else "InDepthEDAInsight"

                # 构建EDA节点三元组
                eda_node = RDFResource(eda_uri, self.ontology['sackResource'])

                # 构建EDA节点三元组
                membership_triples.append(
                    Triplet(eda_node,RDFResource('type', self.ontology['rdf']),
                    RDFResource(eda_node_type, self.ontology['sack_knowledge'], False)
                ))
                membership_triples.append(
                    Triplet(eda_node,RDFResource('name', self.ontology['schema']),
                    RDFResource(f"{column_profile.get_dataset_name()}_{eda_type}")
                ))
                membership_triples.append(
                    Triplet(eda_node,RDFResource('label', self.ontology['rdfs']),
                    RDFResource(generate_label(f"{column_profile.get_dataset_name()} {eda_type.replace('_', ' ').title()} Insight",'en'))
                ))

                # 3. 构建EDA节点基础三元组（类型、名称、label）
                field_mapping = self.eda_field_mapping.get(eda_type, {})
                for (module, field_path), (storage_attr, field_type) in field_mapping.items():
                    try:
                        # 鏍规嵁EDA绫诲瀷鑾峰彇妯″潡鏁版嵁
                        if eda_type == "pre_eda":
                            if module == "data_quality":
                                module_data = eda_profile.get_pre_eda_data_quality()
                            elif module == "basic_distribution":
                                module_data = eda_profile.get_pre_eda_basic_distribution()
                            elif module == "basic_dimensionality":
                                module_data = eda_profile.get_pre_eda_basic_dimensionality()
                            else:
                                module_data = {}
                        else:  # deep_eda
                            if module == "feature_relationships":
                                module_data = eda_profile.get_deep_eda_feature_relationships()
                            elif module == "complexity":
                                module_data = eda_profile.get_deep_eda_complexity()
                            elif module == "special_scenarios":
                                module_data = eda_profile.get_deep_eda_special_scenarios()
                            else:
                                module_data = {}

                        if not module_data:
                            continue

                        value = module_data
                        for segment in field_path.split("."):
                            value = value.get(segment) if isinstance(value, dict) else None
                            if value is None:
                                break

                        if value is None:
                            continue

                        # 解析嵌套字段值（支持多级路径，如"missingness.overall_missing_rate"）
                        if field_type == "json":
                            value_str = json.dumps(value, ensure_ascii=False)
                        else:
                            if isinstance(value, bool):
                                value_str = str(value).lower()
                            else:
                                value_str = str(value)

                        predicate = RDFResource(storage_attr, self.ontology['sackData'])
                        membership_triples.append(Triplet(eda_node, predicate, RDFResource(value_str)))

                    except Exception as e:
                        print(f"Warning: Failed to process EDA field {module}.{field_path} for {eda_id}: {e}")
                        continue

                edge_predicate = "hasPreliminaryEDAInsight" if eda_type == "pre_eda" else "hasInDepthEDAInsight"
                membership_triples.append(
                    Triplet(competition_node,RDFResource(edge_predicate, self.ontology['sackData']),
                    eda_node
                ))



            if column_profile.get_data_source() in sources:
                continue
            # source metadata
            sources.add(column_profile.get_data_source())
            source_label = generate_label(column_profile.get_data_source(), 'en')
            membership_triples.append(Triplet(source_node, RDFResource('name', self.ontology['schema']),
                                              RDFResource(column_profile.get_data_source())))
            membership_triples.append(Triplet(source_node, RDFResource('label', self.ontology['rdfs']),
                                              RDFResource(source_label)))
            membership_triples.append(Triplet(source_node, RDFResource('type', self.ontology['rdf']),
                                              RDFResource('Source', self.ontology['sack_knowledge'], False)))
        filename = ''.join(random.choices(string.ascii_letters + string.digits, k=15)) + '.nt'
        with open(os.path.join(self.tmp_graph_base_dir, filename), 'w', encoding='utf-8') as f:
            for triple in membership_triples:
                f.write(f"{triple}\n")

    def generate_similarity_triples(self):

        column_profiles = self.column_profiles
        ontology = self.ontology
        tmp_graph_dir = self.tmp_graph_base_dir
        word_embedding = self.word_embedding
        column_profile_indexes = list(range(len(self.column_profiles)))
        random.shuffle(column_profile_indexes)
        column_profile_indexes_rdd = self.spark.parallelize(column_profile_indexes)
        label_sim_threshold = self.label_sim_threshold
        embedding_sim_threshold = self.embedding_sim_threshold
        boolean_sim_threshold = self.boolean_sim_threshold
        column_profile_indexes_rdd.map(
            lambda x: column_pair_similarity_worker(column_idx=x,
                                                    column_profiles=column_profiles,
                                                    ontology=ontology,
                                                    triples_output_tmp_dir=tmp_graph_dir,
                                                    label_sim_threshold=label_sim_threshold,
                                                    embedding_sim_threshold=embedding_sim_threshold,
                                                    boolean_sim_threshold=boolean_sim_threshold,
                                                    word_embedding=word_embedding)).collect()

    def build_graph(self):
        for tmp_file in os.listdir(self.tmp_graph_base_dir):
            with open(os.path.join(self.tmp_graph_base_dir, tmp_file), 'r') as f:
                content = f.read()
            with open(self.graph_output_path, 'a+') as f:
                f.write(content)
        # remove the intermediate results
        shutil.rmtree(self.tmp_graph_base_dir)


def build_data_global_schema():
    start_all = datetime.now()
    knowledge_graph_builder = DataGlobalSchemaBuilder(column_profiles_path=SACKKnowledgeConfig.profiles_out_path,
                                                      out_graph_path=SACKKnowledgeConfig.data_global_schema_graph_out_path,
                                                      is_spark_local_mode=SACKKnowledgeConfig.is_spark_local_mode,
                                                      label_sim_threshold=SACKKnowledgeConfig.col_label_sim_threshold,
                                                      embedding_sim_threshold=SACKKnowledgeConfig.col_embedding_sim_threshold,
                                                      boolean_sim_threshold=SACKKnowledgeConfig.col_boolean_sim_threshold)

    # Membership (e.g. table -> dataset) and metadata (e.g. min, max) triples
    print(datetime.now(), "[1] Building Membership and Metadata triples\n")
    start_schema = datetime.now()
    knowledge_graph_builder.build_membership_and_metadata_subgraph()
    end_schema = datetime.now()
    print(datetime.now(), "[1] Done.\tTime taken: " + str(end_schema - start_schema), '\n')

    skip_schema_similarity = os.environ.get("SACK_SKIP_SCHEMA_SIMILARITY", "").lower() in {"1", "true", "yes"}
    if skip_schema_similarity:
        print(datetime.now(), "[2] Skipping column-column similarities because SACK_SKIP_SCHEMA_SIMILARITY is set\n")
    else:
        print(datetime.now(), "[2] Computing column-column similarities\n")
        start_schema_sim = datetime.now()
        knowledge_graph_builder.generate_similarity_triples()
        end_schema_sim = datetime.now()
        print(datetime.now(), "[2] Done.\tTime taken: " + str(end_schema_sim - start_schema_sim), '\n')

    print(datetime.now(), '[3] Combining intermediate subgraphs from workers\n')
    knowledge_graph_builder.build_graph()

    end_all = datetime.now()
    print(datetime.now(), f'\nDone. Graph saved to: {SACKKnowledgeConfig.data_global_schema_graph_out_path}.')

    print(datetime.now(), "Done. Total time to build graph: " + str(end_all - start_all))
