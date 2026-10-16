from sack.knowledge.api.template import *
from sack.knowledge.api.helpers.helper import *
from collections import Counter
from sack.knowledge.knowledge_config import SACKKnowledgeConfig
import pandas as pd
import os
import math
from sack.knowledge.api.utils import profile_single_competition, profile_input_manifest, get_current_competition_edainsight
from sack.knowledge.storage_utils.get_current_comp_eda_files import copy_eda_files
from sack.knowledge.stores.factory import create_agent_graph_store
from tqdm import tqdm
import json




class SACKKnowledgeBase:
    def __init__(self,
                 endpoint: str = 'http://localhost:7200',
                 db: str = 'sack_knowledge',

                 pg_host: Optional[str] = None,# PostgreSQL配置
                 pg_user: Optional[str] = None,
                 pg_password: Optional[str] = None,
                 pg_competition_db: str = SACKKnowledgeConfig.competition_embeddings_db_name,  # 竞赛嵌入库名
                 pg_column_db: str = SACKKnowledgeConfig.column_embeddings_db_name,  # 列嵌入库名
                 pg_port: Optional[str] = None,
                 graph_store=None,
                 graph_backend: str = None,
                 ):
        # Explicit arguments win; deployments can supply credentials without
        # changing Agent call sites or putting secrets in the repository.
        pg_host = pg_host if pg_host is not None else os.environ.get('SACK_PG_HOST', 'localhost')
        pg_user = pg_user if pg_user is not None else os.environ.get('SACK_PG_USER', 'postgres')
        pg_port = pg_port if pg_port is not None else os.environ.get('SACK_PG_PORT', SACKKnowledgeConfig.postgresql_port)
        if pg_password is None:
            pg_password = os.environ.get('SACK_PG_PASSWORD')
            if pg_password is None:
                password_file = os.environ.get('SACK_PG_PASSWORD_FILE')
                if password_file:
                    with open(password_file, encoding='utf-8') as credentials:
                        pg_password = credentials.read().strip()
                else:
                    pg_password = 'postgres'
        self.conn = connect_to_graphdb(endpoint, graphdb_repo=db)
        self.graph_store = (
            graph_store
            if graph_store is not None
            else create_agent_graph_store(backend=graph_backend)
        )
        self.pg_competition_conn = connect_to_postgres(host=pg_host, user=pg_user, password=pg_password, dbname=pg_competition_db,port=pg_port)
        self.pg_col_conn = connect_to_postgres(host= pg_host, user= pg_user, password= pg_password, dbname= pg_column_db, port= pg_port)
        self.pg_competition_table = pg_competition_db
        self.pg_column_table = pg_column_db

        

    def get_datasets_info(self, show_query: bool = False):
        return get_datasets_info(self.conn, show_query).sort_values('Dataset', ignore_index=True, ascending=True)

    def get_tables_info(self, dataset: str = '', show_query: bool = False):
        if not dataset:
            print('Showing all available table(s): ')
        else:
            print("Showing table(s) for '{}' dataset: ".format(dataset))
        return get_tables_info(self.conn, dataset, show_query).sort_values('Dataset', ignore_index=True, ascending=True)

    def recommend_k_joinable_tables(self, table: pd.Series, k: int = 5, show_query: bool = False):
        if not isinstance(table, pd.Series):
            raise ValueError("table needs to be a type 'pd.Series'")
        # if not isinstance(dataset, str):
        #     raise ValueError("dataset needs to be a type 'str'")
        if not isinstance(k, int):
            raise ValueError("k needs to be a type 'int'")
        elif isinstance(table, pd.Series) and isinstance(k, int):
            dataset = table["Dataset"]
            table = table["Table"]
            recommendations = recommend_tables(self.conn, dataset, table, k, 'data:hasContentSimilarity',
                                               show_query)
            recommendations['Score'] = list(map(lambda x: round(x, 2), [float(i) / max(recommendations['Score'].
                                                       tolist()) for i in (recommendations['Score'].tolist())]))

            print('Showing the top-{} joinable table recommendations:'.format(len(recommendations)))
            return recommendations

    def recommend_k_unionable_tables(self, table: pd.Series, k: int = 5, show_query: bool = False):
        if not isinstance(table, pd.Series):
            raise ValueError("table needs to be a type 'pd.Series'")
        # if not isinstance(dataset, str):
        #     raise ValueError("dataset needs to be a type 'str'")
        if not isinstance(k, int):
            raise ValueError("k needs to be a type 'int'")
        elif isinstance(table, pd.Series) and isinstance(k, int):
            dataset = table["Dataset"]
            table = table["Table"]
            recommendations = recommend_tables(self.conn, dataset, table, k, 'data:hasLabelSimilarity',
                                               show_query)
            recommendations['Score'] = list(map(lambda x: round(x, 2), [float(i) / max(recommendations['Score'].
                                                tolist()) for i in (recommendations['Score'].tolist())]))

            print('Showing the top-{} unionable table recommendations:'.format(len(recommendations)))
            return recommendations

    def get_table_info(self, table, show_query: bool = False):
        dataset = table["Dataset"]
        if 'Recommended_table' in table.keys():
            table = table["Recommended_table"]
        else:
            table = table["Table"]
        return get_table_info(self.conn, dataset, table, show_query)

    def show_graph_info(self, show_query: bool = False):
        print('Information captured: ')
        return show_graph_info(self.conn, show_query)

    def search_tables_on(self, conditions: list, show_query: bool = False):

        def parsed_conditions(user_conditions):
            error_message = 'conditions need to be in encapsulated in list.\n' \
                            'lists in the list are associated by an \"and\" condition.\n' \
                            'String in each tuple will be joined by an \"or\" condition.\n' \
                            ' For instance [[a,b],[c]]'
            if not isinstance(user_conditions, list):
                raise TypeError(error_message)
            else:
                for l in user_conditions:
                    if not isinstance(l, list):
                        raise TypeError(error_message)
                    else:
                        for s in l:
                            if not isinstance(s, str):
                                raise TypeError(error_message)

            i = 1
            filters = []
            statements = []
            for t in user_conditions:
                sts = '?column' + str(i) + ' rdf:type sack:Column.' \
                                           '\n?column' + str(i) + ' sack:isPartOf ?table.' \
                                                                  '\n?column' + str(
                    i) + ' rdfs:label ?label' + str(i) + '.'

                statements.append(sts)
                or_conditions = '|'.join(t)
                regex = 'regex(?label' + str(i) + ', "' + or_conditions + '", "i")'
                filters.append(regex)
                i += 1
            return '\n'.join(statements), ' && '.join(filters)

        data = search_tables_on(self.conn, parsed_conditions(conditions), show_query)
        print('Showing recommendations as per the following conditions:\nCondition = ', conditions)
        df = pd.DataFrame(list(data), columns=['Dataset', 'Table', 'Number_of_columns',
                                                 'Number_of_rows', 'Path_to_table']).sort_values('Number_of_rows',
                                                                                                 ignore_index=True,
                                                                                               ascending=False)
        df['Number_of_rows'] = df['Number_of_rows'].apply(lambda x: int(x))
        df['Number_of_columns'] = df['Number_of_columns'].apply(lambda x: int(x))
        return df

    def get_path_between_tables(self, source_table: pd.Series, target_table: pd.Series, hops: int,
                                relation: str = 'data:hasContentSimilarity', show_query: bool = False):
        return get_path_between_tables(self.conn, source_table, target_table, hops, relation, show_query)

    def query(self, rdf_query: str):
        return query_sack_knowledge(self.conn, rdf_query)

    def get_top_scoring_ml_model(self, dataset: str = '', show_query=False):
        return get_top_scoring_ml_model(self.conn, dataset, show_query)

    def get_pipelines_info(self, author: str = '', show_query=False):
        return get_pipelines_info(self.conn, author, show_query).sort_values('Number_of_votes', ignore_index=True,
                                                                             ascending=False)

    def get_most_recent_pipeline(self, dataset: str = '', show_query=False):
        return get_most_recent_pipeline(self.conn, dataset, show_query)

    def get_top_k_scoring_pipelines_for_dataset(self, dataset: str = '', k: int = None, show_query=False):
        if self.graph_store is not None:
            return self.graph_store.get_top_pipelines(dataset or None, k)
        return get_top_k_scoring_pipelines_for_dataset(self.conn, dataset, k, show_query)

    def get_most_popular_parameters(self, library: str, parameters='all'):
        pass

    def search_classifier(self, dataset: str = '', show_query=False):
        return search_classifier(self.conn, dataset, show_query)

    def get_hyperparameters(self, classifier: pd.Series, show_query=False):
        pipeline_name = classifier['Pipeline']
        classifier = classifier['Classifier']
        return get_hyperparameters(self.conn, pipeline_name, classifier, show_query)

    def get_top_k_library_used(self, dataset: str = '', k: int = 5, show_query=False):
        return get_library_usage(self.conn, dataset, k, show_query)

    def get_top_used_libraries(self, k: int = 5, task: str = 'classification', show_query: bool = False):
        supported_tasks = ['classification', 'regression', 'visualization', 'clustering']
        if task not in supported_tasks:
            raise ValueError(' invalid task, try using one of the following tasks: \n'
                             'classification, regression, visualization or clustering!')
        else:
            library_info = get_top_used_libraries(self.conn, task, show_query)
            if len(library_info) == 0:
                print('No library found for {}'.format(task))
                return
            library_info['Module'] = library_info['Module'].apply(lambda module: module.replace('/', '.'))
            # fetch top k libraries by maximum occurrence
            libraries = library_info['Library']
            library_count = Counter(libraries)
            if k > len(library_count):
                k = len(library_count)
                if k == 1:
                    print('Single library was found for {}: '.format(task))
                else:
                    print('Maximum {} libraries were found for {}: '.format(k, task))
            else:
                if k == 1:
                    print('Showing the top used library for {}: '.format(task))
                else:
                    print('Showing the top {} libraries for {}: '.format(k, task))
            libraries = sorted(library_count, key=library_count.get, reverse=True)[:k]

            for i in libraries[:len(libraries)-1]:
                print(i + ',', end=' ')
            print(libraries[-1])
            for k, v in library_info.to_dict('index').items():
                if v['Library'] not in libraries:
                    library_info = library_info.drop(k)
            return library_info.sort_values(by=['Library']).reset_index(drop=True)

    def get_pipelines_calling_libraries(self, components: list, show_query: bool = False):
        return get_pipelines_calling_libraries(self.conn, components, show_query)

    def get_pipelines_for_deep_learning(self, show_query: bool = False):
        return get_pipelines_for_deep_learning(self.conn, show_query)

    def recommend_transformations(self, show_query: bool = False):
        return recommend_transformations(self.conn, show_query)

    def get_pipelines_by_tags(self, tag: str = '', show_query: bool = False):
        return get_pipelines_by_tags(self.conn, tag, show_query)

    def show_pipeline_usage_by_task(self, show_query: bool = False):
        usage = dict()
        usage['classification'] = sum(get_pipelines_by_tags(self.conn, tag='classification', show_query=show_query)['Number_of_pipelines'].tolist())
        usage['clustering'] = sum(get_pipelines_by_tags(self.conn, tag='clustering', show_query=show_query)['Number_of_pipelines'].tolist())
        usage['visualization'] = sum(get_pipelines_by_tags(self.conn, tag='visualization', show_query=show_query)['Number_of_pipelines'].tolist())
        usage['cleaning'] = sum(get_pipelines_by_tags(self.conn, tag='cleaning', show_query=show_query)['Number_of_pipelines'].tolist())
        usage['regression'] = sum(get_pipelines_by_tags(self.conn, tag='regression', show_query=show_query)['Number_of_pipelines'].tolist())
        usage['deep learning'] = sum(get_pipelines_by_tags(self.conn, tag='deep learning', show_query=show_query)['Number_of_pipelines'].tolist()) + \
                        sum(get_pipelines_by_tags(self.conn, tag='neural networks', show_query=show_query)['Number_of_pipelines'].tolist())

        tasks = list(usage.keys())
        data = list(usage.values())
        colors = ("red", "orange", "yellow", "limegreen", "seagreen", "dodgerblue")

        def func(pct):
            return "{:.1f}%".format(pct)

        wp = {'linewidth': 0, 'edgecolor': "black"}
        label_data = [str(i) + " pipelines" for i in data]
        fig, ax = plt.subplots(figsize=(10, 8))
        wedges, texts, autotexts = ax.pie(data,
                                          autopct=lambda pct: func(pct),
                                          colors=colors,
                                          labels=label_data,
                                          textprops=dict(color="black"),
                                          wedgeprops=wp)
        ax.legend(wedges, tasks,
                  loc="center left",
                  bbox_to_anchor=(1.2, 0, 0.5, 1), fontsize=15)

        plt.setp(autotexts, size=10, weight='bold')
        plt.title("Pipeline usage by tasks", fontsize=15)
        plt.show()

    def show_top_k_models_by_task(self, task: str, k: int = 5, show_query: bool = False):
        if task == 'classification':
            plot_top_k_classifiers(self.conn, k, show_query)

        elif task == 'regression':
            plot_top_k_regressors(self.conn, k, show_query)

        else:
            raise ValueError(' invalid task, try using one of the following tasks: \n'
                                 'classification or regression')

    def generate_competition_profile(
            self,
            comp_id: str,
            persist_path: Optional[str] = None,
            force_regenerate: bool = False,
            source_path: Optional[str] = None,
    ) -> Dict:
        """
        独立算子：生成并校验竞赛的current_comp，支持持久化和读取

        参数：
            comp_id: 竞赛ID（用于拼接竞赛路径）
            persist_path: 持久化保存路径（None则不持久化）
            force_regenerate: 是否强制重新生成（即使有持久化文件，默认False）

        返回：
            Dict: 校验后的current_comp字典
        """
        # 1. 拼接竞赛路径
        comp_path = source_path or os.path.join(SACKKnowledgeConfig.current_comp_path, comp_id)

        # 2. 校验竞赛路径有效性（公共逻辑抽离）
        if not os.path.exists(comp_path):
            raise FileNotFoundError(f"竞赛路径不存在：{comp_path}")
        if not os.path.isdir(comp_path) and not comp_path.endswith(('.json', '.csv')):
            raise ValueError(f"无效的竞赛路径（需文件夹或json/csv文件）：{comp_path}")

        input_manifest = profile_input_manifest(comp_path)
        # 3. 持久化文件路径（用comp_id命名，避免冲突）
        persist_file = None
        if persist_path:
            os.makedirs(persist_path, exist_ok=True)  # 确保目录存在
            persist_file = os.path.join(persist_path, f"{os.path.basename(comp_id)}_profile.json")

        # 4. 优先读取持久化文件（如果存在且不强制重新生成）
        if not force_regenerate and persist_file and os.path.exists(persist_file):
            try:
                with open(persist_file, 'r', encoding='utf-8') as f:
                    current_comp = json.load(f)
                print(f"从持久化文件读取竞赛profile：{persist_file}")
                # 读取后仍校验（防止文件被篡改）
                self._validate_current_comp(current_comp)
                if current_comp.get('input_manifest') != input_manifest:
                    raise ValueError('Profile input changed or legacy cache has no input hashes')
                return current_comp
            except Exception as e:
                print(f"读取持久化profile失败，将重新生成：{str(e)}")

        # 5. 生成竞赛profile
        try:
            competition_profile_dict, column_profiles_list = profile_single_competition(new_comp_path=comp_path)
            current_comp = {
                "comp_id": competition_profile_dict["comp_id"],
                "overview": competition_profile_dict["overview"],
                "data_description": competition_profile_dict["data_description"],
                "overview_embedding": competition_profile_dict["overview_embedding"],
                "data_description_embedding": competition_profile_dict["data_description_embedding"],
                "problem_type": competition_profile_dict["structured_elements"]["problem_type"],
                "data_type": competition_profile_dict["structured_elements"]["data_type"],
                "tables": column_profiles_list,
                "input_manifest": input_manifest,
                "profile_schema_version": 2,
            }
            print(f"成功生成竞赛profile：{current_comp.get('comp_id', '未知ID')}")
        except Exception as e:
            raise RuntimeError(f"生成竞赛profile失败：{str(e)}") from e

        # 6. 校验current_comp完整性（抽离为私有方法）
        self._validate_current_comp(current_comp)

        # 7. 持久化保存（如果指定了路径）
        if persist_file:
            try:
                with open(persist_file, 'w', encoding='utf-8') as f:
                    # 处理numpy数组等不可序列化类型（如果有）
                    json.dump(current_comp, f, ensure_ascii=False, indent=2,
                              default=lambda x: x.tolist() if hasattr(x, 'tolist') else x)
                print(f"竞赛profile已持久化到：{persist_file}")
            except Exception as e:
                print(f"持久化profile失败：{str(e)}")

        return current_comp

    def _validate_current_comp(self, current_comp: Dict) -> None:
        """
        私有方法：校验current_comp的完整性（原公共校验逻辑）
        """
        # 基础字段校验
        required_fields = ["comp_id", "overview_embedding", "data_description_embedding", "tables"]
        for field in required_fields:
            if field not in current_comp:
                raise ValueError(f"生成的current_comp缺少必需字段：{field}")

        if not current_comp.get('tables'):
            raise ValueError('Profile contains no tables')
        # 列嵌入字段校验
        for table in current_comp.get("tables", []):
            columns = table.get('columns', [])
            if not columns:
                raise ValueError(f"Profile table has no columns: {table.get('table_name')}")
            if 'expected_columns' in table:
                actual = [column.get('col_name') for column in columns]
                if sorted(actual) != sorted(table['expected_columns']):
                    raise ValueError(f"Profile column coverage incomplete: {table.get('table_name')}")
            for col in table.get("columns", []):
                if "label_embedding" not in col or "content_embedding" not in col:
                    raise ValueError(f"表 {table.get('table_name')} 的列 {col.get('col_name')} 缺少嵌入字段")
                if current_comp.get('profile_schema_version') == 2:
                    for field in ('label_embedding', 'content_embedding'):
                        vector = col[field]
                        if (not isinstance(vector, list) or len(vector) != 300 or
                                any(not isinstance(value, (int, float)) or isinstance(value, bool)
                                    or not math.isfinite(value) for value in vector)):
                            raise ValueError(f"Invalid {field} in {table.get('table_name')}/{col.get('col_name')}")



    def get_top_k_similar_competitions(
            self,
            comp_id: Optional[str] = None,  # 可选：传入comp_id或直接传入current_comp
            current_comp: Optional[Dict] = None,
            k: int = 5,
            return_all: bool = False,
            show_query: bool = False
    ) -> pd.DataFrame:
        """
        API方法：通过新竞赛路径获取Top-K相似竞赛

        参数：
            comp_id: 新竞赛的名称（如竞赛数据文件夹或元数据文件路径）
            k: 返回Top-K数量（默认5）
            show_query: 是否打印查询语句（默认False）

        返回：
            pd.DataFrame: 相似竞赛结果（含ID、名称、各项得分）
        """
        # 优先使用传入的current_comp，否则用comp_id生成（兼容原有逻辑）
        if current_comp is None:
            if comp_id is None:
                raise ValueError("必须传入comp_id或current_comp中的一个")
            # 这里可以调用独立算子（也可让外部提前调用，这里做兼容）
            current_comp = self.generate_competition_profile(comp_id=comp_id)
        else:
            # 校验传入的current_comp（防止无效数据）
            self._validate_current_comp(current_comp)


        # 4. 构造配置并调用核心函数（与原逻辑一致）
        core_config = {
            "graphdb_conn": self.conn,
            "graph_store": self.graph_store,
            "pg_competition_conn": self.pg_competition_conn,
            "pg_col_conn": self.pg_col_conn,
            "pg_competition_table": self.pg_competition_table,
            "pg_column_table": self.pg_column_table,
        }

        result_df = get_top_k_similar_competitions_core(
            config=core_config,
            current_comp=current_comp,
            semantic_weight=SACKKnowledgeConfig.competition_semantic_weight,
            data_weight=SACKKnowledgeConfig.competition_data_weight,
            show_query=show_query
        )

        # 5. 结果处理（与原逻辑一致）
        if result_df.empty:
            print("未找到符合条件的相似竞赛")
            return pd.DataFrame(
                columns=[
                    "Competition_ID", "Competition_Name", "Semantic_Score",
                    "Data_Macro_Score", "Data_Micro_Score", "Fused_Data_Score", "Total_Score"
                ]
            )

        if return_all:
            # 返回所有结果，不截断
            result_df = result_df.reset_index(drop=True).fillna(0)
            print(f"\n返回所有{len(result_df)}条相似竞赛结果")
        else:
            # 原有逻辑：返回Top-K结果
            result_df = result_df.head(k).reset_index(drop=True).fillna(0)
            print(f"\n返回Top-{k}条相似竞赛结果")

        # 6. 输出反馈
        print(f"\n=== 相似竞赛推荐结果 ===")
        print(
            f"Top-{k}竞赛（语义权重：{SACKKnowledgeConfig.competition_semantic_weight} | 数据权重：{SACKKnowledgeConfig.competition_data_weight}）")
        print(
            result_df[["Competition_ID", "Total_Score", "Semantic_Score", "Fused_Data_Score"]].to_string(index=False))

        return result_df

    def get_core_insights_for_pipeline(
            self,
            pipeline_uri: str,  # 改为接收pipeline的完整URI
            show_query: bool = False
    ) -> pd.DataFrame:
        """
        API方法：根据pipeline的完整URI获取其对应的所有核心见解（CoreInsight）

        参数：
            pipeline_uri: pipeline的完整URI（如"http://sack.local/resource/kaggle/titanic/p1"）
            show_query: 是否打印SPARQL查询语句（默认False）

        返回：
            pd.DataFrame: 包含列[Insight_ID, Description, Insight_Type, Effectiveness, Evidence, Phase, Spanning_Phases]
        """
        # 1. 参数校验（确保是合法URI）
        if not pipeline_uri or not isinstance(pipeline_uri, str) or not pipeline_uri.startswith(
                ("http://", "https://")):
            raise ValueError("pipeline_uri必须为非空字符串且以http://或https://开头")

        if self.graph_store is not None:
            return self.graph_store.get_core_insights(pipeline_uri)

        # 2. 构建配置
        core_config = {
            "graphdb_conn": self.conn,
            "graph_store": self.graph_store,
            "pg_competition_conn": self.pg_competition_conn,
            "pg_col_conn": self.pg_col_conn
        }

        # 3. 调用核心函数
        try:
            insights_df = get_core_insights_for_pipeline_core(
                config=core_config,
                pipeline_uri=pipeline_uri,  # 传入URI
                show_query=show_query
            )
        except Exception as e:
            raise RuntimeError(f"获取核心见解失败：{str(e)}") from e

        # 4. 结果处理（不变）
        if insights_df.empty:
            print("未查询到任何核心见解")
            return pd.DataFrame(
                columns=["Insight_ID", "Description", "Insight_Type", "Effectiveness", "Evidence", "Phase",
                         "Spanning_Phases"]
            )

        print(f"\n=== 核心见解查询结果 ===")
        print(f"目标pipeline URI：{pipeline_uri}")
        print(f"共找到 {len(insights_df)} 条核心见解")

        return insights_df

    def get_competition_field(
            self,
            competition_uri: str,
            field: str,
            show_query: bool = False
    ) -> Optional[str]:
        """
        API方法：根据竞赛名和目标字段，获取知识图谱中该竞赛的对应字段内容
        """
        if not competition_uri or not isinstance(competition_uri, str) or not competition_uri.startswith(
                ("http://", "https://")):
            raise ValueError(f"competition_uri {competition_uri} 必须为非空字符串且以http://或https://开头")
        if not field or not isinstance(field, str):
            raise ValueError("field必须为非空字符串")

        if self.graph_store is not None:
            return self.graph_store.get_competition_field(competition_uri, field)

        core_config = {
            "graphdb_conn": self.conn,
            "graph_store": self.graph_store,
        }

        try:
            field_value = get_competition_field_core(
                config=core_config,
                competition_uri=competition_uri,
                field=field,
                show_query=show_query
            )
        except Exception as e:
            raise RuntimeError(f"获取竞赛字段失败：{str(e)}") from e

        if field_value:
            print(f"\n=== 竞赛字段查询结果 ===")
            print(f"竞赛URI：{competition_uri}")
            print(f"字段({field})内容：\n{field_value[:500]}...")
        else:
            print(f"\n=== 竞赛字段查询结果 ===")
            print(f"竞赛URI：{competition_uri}")
            print(f"字段({field})：未找到内容")

        return field_value

    def get_insight_code_snippet(
            self,
            insight_uri: str,
            show_query: bool = False
    ) -> Optional[List[Dict]]:
        """
        API方法：根据核心见解URI，获取按编号排序的完整代码段（含编号、statement URI和代码内容）
        """
        if not insight_uri or not isinstance(insight_uri, str):
            raise ValueError("insight_uri必须为非空字符串（格式：pipeline_uri/insight/insight_id）")

        if self.graph_store is not None:
            snippets = self.graph_store.get_insight_code(insight_uri)
            return [
                {
                    "stmt_uri": {"type": "uri", "value": item["stmt_uri"]},
                    "code_text": {"type": "literal", "value": item["code_text"]},
                    "order": {
                        "datatype": "http://www.w3.org/2001/XMLSchema#integer",
                        "type": "literal",
                        "value": str(item["order"]),
                    },
                }
                for item in snippets
            ] or None

        core_config = {
            "graphdb_conn": self.conn,
            "graph_store": self.graph_store,
        }

        try:
            ordered_code_snippets = get_insight_code_snippet_core(
                config=core_config,
                insight_uri=insight_uri,
                show_query=show_query
            )
        except Exception as e:
            raise RuntimeError(f"获取见解代码段失败：{str(e)}") from e

        # 格式化输出（按编号顺序展示）
        if ordered_code_snippets:
            print(f"\n=== 见解代码段查询结果 ===")
            print(f"见解URI：{insight_uri}")
            print("代码段（按执行顺序）：")
            for item in ordered_code_snippets:
                print(f"[{item['order']['value']}] {item['code_text']['value']}")
                print(f"  (来源：{item['stmt_uri']['value']})  # 显示URI末尾的编号部分")
        else:
            print(f"\n=== 见解代码段查询结果 ===")
            print(f"见解URI：{insight_uri}")
            print("代码段：未找到对应实现")

        return ordered_code_snippets

    def get_edainsight_for_competitions(self, competition_uri,eda_type,show_query=False):
        # 1. 参数校验（确保是合法URI）
        if not competition_uri or not isinstance(competition_uri, str) or not competition_uri.startswith(
                ("http://", "https://")):
            raise ValueError("competition_uri必须为非空字符串且以http://或https://开头")

        if self.graph_store is not None:
            return self.graph_store.get_eda_insight(competition_uri, eda_type)

        # 2. 构建配置
        core_config = {
            "graphdb_conn": self.conn,
            "graph_store": self.graph_store,
        }

        # 3. 调用核心函数
        try:
            insights_df = get_edainsight_for_competitions_core(
                config=core_config,
                eda_type=eda_type,
                competition_uri=competition_uri,
                show_query=show_query
            )
        except Exception as e:
            raise RuntimeError(f"获取EDAInsight失败：{str(e)}") from e

        # 4. 结果处理（完善用户原有代码的日志和空值处理）
        if not isinstance(insights_df, dict):
            raise TypeError('EDA core must return a module/field dictionary')
        if not insights_df:
            print("未查询到任何EDAInsight")
            return {}

        print(f"\n=== EDAInsight查询结果 ===")
        print(f"目标竞赛URI：{competition_uri}")
        print(f"EDA类型：{eda_type}")
        print(f"共找到 {len(insights_df)} 个EDAInsight字段")

        return insights_df



    def get_top_k_edainsight_similar_competitions(self,
                                                  comp_id: Optional[str] = None,  # 可选：传入comp_id或直接传入current_comp
                                                  current_comp: Optional[Dict] = None,  # 新增：独立算子的输出
                                                  k: int = 5,
                                                  return_all: bool = False,
                                                  show_query: bool = False) -> pd.DataFrame:

        # 优先使用传入的current_comp，否则用comp_id生成（兼容原有逻辑）
        if current_comp is None:
            if comp_id is None:
                raise ValueError("必须传入comp_id或current_comp中的一个")
            # 调用独立算子（仅生成基础profile，无需持久化可传None）
            current_comp = self.generate_competition_profile(comp_id=comp_id)
        else:
            # 仅校验必要字段（该算子只需要comp_id/problem_type/data_type）
            required_fields = ["comp_id", "problem_type", "data_type"]
            for field in required_fields:
                if field not in current_comp:
                    raise ValueError(f"current_comp缺少必需字段：{field}")
        if comp_id:
            comp_path = os.path.join(SACKKnowledgeConfig.current_comp_path, comp_id)
        else:

            parts = current_comp["comp_id"].split('/')
            # 过滤掉分割后可能出现的空字符串（比如字符串以/结尾时）
            non_empty_parts = [part for part in parts if part]
            # 如果过滤后还有内容，返回最后一个，否则返回空字符串
            comp_path = os.path.join(SACKKnowledgeConfig.current_comp_path, non_empty_parts[-1])


        # 参数校验（无修改）
        if not os.path.exists(comp_path):
            raise FileNotFoundError(f"竞赛路径不存在：{comp_path}")
        if not os.path.isdir(comp_path):
            raise ValueError(f"无效的竞赛路径（需文件夹）：{comp_path}")


        # 提取current_comp_info（适配核心函数入参）
        current_comp_info = {
            "comp_id": current_comp["comp_id"],
            "problem_type": current_comp["problem_type"],
            "data_type": current_comp["data_type"]
        }

        # 获取当前竞赛EDAInsight（简化后的核心结构）
        current_comp_edainsight = get_current_competition_edainsight(comp_path)# 直接从当前竞赛数据里获取拷贝的edainsight

        # 调用核心函数
        core_config = {
            "graphdb_conn": self.conn,
            "graph_store": self.graph_store,
        }
        results = get_top_k_edainsight_similar_competitions_core(
            config=core_config,
            current_comp_info=current_comp_info,
            current_comp_edainsight=current_comp_edainsight,
            show_query=show_query
        )
        if return_all:
            # 若return_all为True，使用所有结果
            top_k_results = results
            print(f"返回所有{len(results)}条相似竞赛结果")
        else:
            # 否则返回top-k结果（原有逻辑）
            top_k_results = results[:k]
            print(f"返回Top-{k}条相似竞赛结果")
        # 转换为DataFrame（修改点：处理模块相似度字段）
        result_data = []
        for item in top_k_results:
            comp_uri = item["comp_uri"]
            comp_id = comp_uri.split("/")[-1]
            # 基础字段
            row = {
                "Competition_ID": comp_uri
            }

            # 添加模块相似度字段（从result_dict中提取）
            for key, value in item.items():
                if key not in ["comp_uri"]:  # 排除基础字段
                    row[key] = value

            result_data.append(row)

        result_df = pd.DataFrame(result_data)

        return result_df
