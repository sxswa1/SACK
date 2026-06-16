import ast
from collections import ChainMap,defaultdict
from datetime import datetime
import json
import multiprocessing as mp
import os
import pandas as pd
from glob import glob
from pathlib import Path
from typing import List, Dict, Any
import shutil

import sack.knowledge.kg_governor.pipeline_abstraction.Calls as Calls
import sack.knowledge.kg_governor.pipeline_abstraction.util as util
from tqdm import tqdm

from sack.knowledge.kg_governor.pipeline_abstraction.Calls.get_calls import FAILED_PATHS_STATS, cache_lock
from sack.knowledge.kg_governor.pipeline_abstraction.pipeline_abstraction import NodeVisitor
from sack.knowledge.kg_governor.pipeline_abstraction.datatypes import GraphInformation
from sack.knowledge.kg_governor.pipeline_abstraction.json_to_rdf import build_pipeline_rdf_page, build_default_rdf_page, build_library_rdf_page
from sack.knowledge.kg_governor.pipeline_abstraction.util import url_encode,expand_analysis_result_nodes
from sack.knowledge.knowledge_config import SACKKnowledgeConfig
from sack.knowledge.LLMUsage.llm_usages import analyze_node_phases,summarize_pipeline_structure,core_insight_extraction


def cleanup_existing_extractions():
    """清理所有已提取的内容，为重新运行做准备"""
    output_path = SACKKnowledgeConfig.pipeline_graphs_out_path
    
    print("开始清理已提取的内容...")
    
    # 1. 删除所有pipeline的ttl文件（保留目录结构）
    for root, dirs, files in os.walk(output_path):
        for file in files:
            if file.endswith('.ttl') and file not in ['library.ttl', 'default.ttl']:
                file_path = os.path.join(root, file)
                os.remove(file_path)
                print(f"删除: {file_path}")
    
    # 2. 删除core_insights目录
    core_insights_dir = os.path.join(output_path, 'core_insights')
    if os.path.exists(core_insights_dir):
        shutil.rmtree(core_insights_dir)
        print(f"删除core_insights目录: {core_insights_dir}")
    
    # 3. 删除library.ttl和default.ttl
    library_ttl = os.path.join(output_path, 'library.ttl')
    default_ttl = os.path.join(output_path, 'default.ttl')
    
    for ttl_file in [library_ttl, default_ttl]:
        if os.path.exists(ttl_file):
            os.remove(ttl_file)
            print(f"删除: {ttl_file}")
    
    # 4. 删除pipeline元数据文件（如果存在）
    for root, dirs, files in os.walk(output_path):
        for file in files:
            if file.endswith('_metadata.json') or file.endswith('_libinfo.json'):
                file_path = os.path.join(root, file)
                os.remove(file_path)
                print(f"删除元数据: {file_path}")
    
    print("清理完成！所有提取内容已被清空。")

def cleanup_with_confirmation():
    """带确认的清理函数"""
    print("警告：这将删除所有已提取的pipeline数据！")
    print("包括：")
    print("  - 所有pipeline的.ttl文件")
    print("  - core_insights目录")
    print("  - library.ttl和default.ttl")
    print("  - 所有元数据文件")
    
    response = input("确定要继续吗？(输入 'YES' 确认): ")
    if response == 'YES':
        cleanup_existing_extractions()
    else:
        print("操作已取消。")

def load_all_pipeline_metadata(output_path):
    """从所有竞赛目录中加载所有pipeline的元数据"""
    all_metadata = []

    # 遍历输出目录下的所有子目录（竞赛目录）
    for item in os.listdir(output_path):
        item_path = os.path.join(output_path, item)
        if os.path.isdir(item_path):
            # 扫描该竞赛目录下的所有metadata文件,每个pipeline对应一个metadata
            for filename in os.listdir(item_path):
                if filename.endswith('_metadata.json'):
                    filepath = os.path.join(item_path, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                            all_metadata.append(metadata)
                    except Exception as e:
                        print(f"加载pipeline元数据失败 {filepath}: {e}")

    return all_metadata

def abstract_pipelines(force_rerun: bool = False):
    if force_rerun:
        cleanup_with_confirmation()
    start_time = datetime.now()

    # 加载所有已存在的core_insight文件
    core_insights_dir = os.path.join(SACKKnowledgeConfig.pipeline_graphs_out_path, 'core_insights')
    existing_core_insights = set()

    if os.path.exists(core_insights_dir):
        for filename in os.listdir(core_insights_dir):
            if filename.endswith('_complete_analysis.json'):
                # 提取pipeline_id，假设文件名格式为 {pipeline_id}_complete_analysis.json
                pipeline_id = filename.replace('_complete_analysis.json', '')
                existing_core_insights.add(pipeline_id)

    print(f"发现 {len(existing_core_insights)} 个已成功提取核心见解的pipeline")

    # 加载所有已存在的pipeline元数据
    existing_metadata = load_all_pipeline_metadata(SACKKnowledgeConfig.pipeline_graphs_out_path)
    print(f"发现 {len(existing_metadata)} 个已处理的pipeline元数据")


    pipelines_to_process = []
    skipped_successful = 0
    datasets = list(os.scandir(SACKKnowledgeConfig.data_source_path))

    # loop through datasets & pipelines
    for dataset in tqdm(datasets, desc="扫描数据集"):
        if dataset.is_dir():
            working_file = {}
            tables = glob(os.path.join(dataset.path, '**', '*.csv'), recursive=True)

            for table in tables:
                try:
                    try:
                        working_file[Path(table).name] = pd.read_csv(table, nrows=1)
                    except:
                        working_file[Path(table).name] = pd.read_csv(table, nrows=1,
                                                                     engine='python', encoding_errors='replace')
                except Exception as e:
                    print("-<>", table, e)

            if not os.path.isdir(f'{dataset.path}/notebooks/'):
                continue
            for pipeline in os.scandir(f'{dataset.path}/notebooks'):
                if pipeline.is_dir():
                    try:
                        with open(f'{pipeline.path}/pipeline_info.json', 'r') as f:
                            pipeline_info = json.load(f)

                        pipeline_id = pipeline_info['id']

                        # 如果强制重新运行，跳过所有检查
                        if force_rerun:
                            # 直接添加到处理队列
                            for file in os.scandir(pipeline.path):
                                if '.py' in file.name:
                                    pipelines_to_process.append((
                                        working_file, dataset.name, file.path, pipeline_info,
                                        SACKKnowledgeConfig.pipeline_graphs_out_path, pipeline_id
                                    ))
                                    break
                            continue


                        ttl_filename = url_encode(pipeline_id[:200]) + '.ttl'
                        ttl_path = os.path.join(SACKKnowledgeConfig.pipeline_graphs_out_path,dataset.name, ttl_filename)

                        # 检查是否已经成功提取核心见解并完成pipeline的三元组提取（已经按预定流程完成提取的pipeline过滤）
                        if pipeline_id in existing_core_insights and os.path.exists(ttl_path):
                            skipped_successful += 1
                            continue  # 跳过已正常处理的pipeline

                        # 处理这个pipeline（基础处理已完成但核心见解提取失败）
                        for file in os.scandir(pipeline.path):
                            if '.py' in file.name:
                                pipelines_to_process.append((
                                    working_file, dataset.name, file.path, pipeline_info,
                                    SACKKnowledgeConfig.pipeline_graphs_out_path, pipeline_id
                                ))
                                break  # 每个pipeline只处理一个.py文件
                    except FileNotFoundError as e:
                        continue


    if not force_rerun:
        print(f"统计: 跳过 {skipped_successful} 个已成功提取核心见解且被处理的pipeline")

    # 处理新的pipeline
    if pipelines_to_process:
        print(f"发现 {len(pipelines_to_process)} 个pipeline需要处理")
        pool = mp.Pool(16)
        process_results = list(tqdm(pool.imap_unordered(pipeline_analysis, pipelines_to_process), total=len(pipelines_to_process)))
        pool.close()
        pool.join()

        count1= 0
        count2= 0
        for result in process_results:
            if result is None:
                continue
            if result[0] and result[1] and result[2]:
                count1+=1
                if result[2].get("success"):
                    count2+=1

        print(f"共发现 {len(pipelines_to_process)} 个pipeline需要处理")
        print(f"成功处理 {count1} 个pipeline，其中核心见解成功提取的有{count2}个")
        failed_count = count1 - count2
        if failed_count > 0:
            print(f"核心见解提取失败 {failed_count} 个pipeline")
    else:
        print("没有发现新pipeline需要处理")

    # with cache_lock:
    #     print(set(FAILED_PATHS_STATS.keys()))
    #     print("异常path: ",len(set(FAILED_PATHS_STATS.keys()))-3)
    #     print("新添加有效path: ",FAILED_PATHS_STATS['new_added_valid'])
    #     print("未知path: ",FAILED_PATHS_STATS['new_added_unknown'])
    #     print("无效path: ",FAILED_PATHS_STATS['new_added_invalid'])

        # combine the default and library graphs from individual pipelines
        # default_graph = [item[0] for item in default_and_library_graphs if item]
        # libraries = ChainMap(*[item[1] for item in default_and_library_graphs if item])
        # libs = [library.str() for library in libraries.values()]

    # library.ttl和default.ttl的整体解析
    # 递归合并两个同uri子库的contain（保留嵌套结构）
    def merge_sub_libraries(existing_subs, new_subs):
        sub_map = {sub['uri']: sub for sub in existing_subs}
        for new_sub in new_subs:
            uri = new_sub['uri']
            if uri in sub_map:
                sub_map[uri]['contain'] = merge_sub_libraries(sub_map[uri]['contain'], new_sub['contain'])
            else:
                sub_map[uri] = new_sub
        return list(sub_map.values())

    # 重新加载所有pipeline元数据（包括新处理的）
    all_metadata = load_all_pipeline_metadata(SACKKnowledgeConfig.pipeline_graphs_out_path)
    print(f"总共 {len(all_metadata)} 个pipeline元数据用于生成汇总文件")

    # 生成library.ttl和default.ttl（包含所有pipeline）
    print("生成汇总文件 library.ttl 和 default.ttl...")

    default_graph = []
    merged_libs = defaultdict(lambda: {"uri": None,"contain": [],"type": None})  # 用None初始化

    for metadata in all_metadata:
        if "pipeline_info" in metadata:
            default_graph.append(metadata["pipeline_info"])
        # 处理default_graph
        # 处理库合并
        libraries = metadata.get("libraries", {})
        for lib_name, lib in libraries.items():
            uri = lib["uri"]
            if merged_libs[uri]["uri"] is None:
                merged_libs[uri].update({"uri": uri, "type": lib["type"]})
            # 递归合并子库
            merged_libs[uri]["contain"] = merge_sub_libraries(merged_libs[uri]["contain"], lib["contain"])

    libs = list(merged_libs.values())

    # 生成library.ttl
    library_ttl_path = os.path.join(SACKKnowledgeConfig.pipeline_graphs_out_path, 'library.ttl')
    with open(library_ttl_path, 'w') as f:
        f.write(build_library_rdf_page(libs))
    print(f"生成 library.ttl，包含 {len(libs)} 个库")

    # 生成default.ttl
    default_ttl_path = os.path.join(SACKKnowledgeConfig.pipeline_graphs_out_path, 'default.ttl')
    with open(default_ttl_path, 'w') as f:
        f.write(build_default_rdf_page(default_graph))
    print(f"生成 default.ttl，包含 {len(default_graph)} 个pipeline信息")

    total_time = datetime.now() - start_time
    print(f"完成! 总时间: {total_time}")



def pipeline_analysis(args):  # 对单个pipeline的分析过程（通过遍历抽象语法树构建图的过程）
    working_file, dataset, file_path, pipeline_info, output_path, output_filename = args


    SOURCE = SACKKnowledgeConfig.data_source
    DATASET_NAME = dataset
    PYTHON_FILE_NAME = output_filename[:200] # trim filename to 200 characters to avoid OSError （pipeline的id字段作为文件名，截断文件名以确保有效）

    # 检查是否已经处理过这个pipeline（基于ttl文件存在性）
    ttl_filename = url_encode(PYTHON_FILE_NAME) + '.ttl'
    ttl_path = os.path.join(output_path, DATASET_NAME, ttl_filename)

    # # 检查元数据文件是否存在
    # metadata_filename = f"{PYTHON_FILE_NAME}_metadata.json"
    # metadata_path = os.path.join(output_path, DATASET_NAME, metadata_filename)

    # 如果ttl文件存在，说明之前处理过，只是提取核心见解失败，这里直接返回None表示已处理（对于少量无法提取核心见解的pipeline忽略）
    if os.path.exists(ttl_path):
        print(f"跳过已处理的pipeline（但可能未完成核心见解提取）: {output_filename}")
        return


    # Read pipeline file  获取py文件内容
    with open(file_path, 'r') as src_file:
        src = src_file.read()

    try:
        tree = ast.parse(src)   # 转化为抽象语法树
        total_nodes = len(list(ast.walk(tree)))
        MAX_AST_NODES = 13000  # 阈值：超过13000个节点的文件直接跳过
        if total_nodes > MAX_AST_NODES:
            print(f"[跳过] 超大型AST: {file_path} (节点数: {total_nodes} > {MAX_AST_NODES})\n")
            return
    except Exception as e:
        # with open(f'./errors.csv', 'a') as output_file:
        #     output_file.write(f'{PYTHON_FILE_NAME},{e}\n')
        print(f"AST失败 {file_path}: {str(e)}\n")
        return

    # Initialize graph information linked list and Node Visitor
    graph = GraphInformation(PYTHON_FILE_NAME, SOURCE, DATASET_NAME, libraries=None)  # 图的初始化
    node_visitor = NodeVisitor(graph_information=graph)  # 注意 python中对象的赋值是引用传递，所以graph会随着变化
    node_visitor.working_file = working_file  # 数据集加载

    # Pipeline analysis  对当前pipeline构建子图（拓扑流程）
    try:
        node_visitor.visit(tree)  # 遍历整个代码的抽象语法树，获取图
    except Exception as e:
        # with open(f'./errors.csv', 'a') as output_file:
        #     output_file.write(f'{PYTHON_FILE_NAME},{e}\n')
        import traceback
        err_msg = traceback.format_exc()
        print(f" 遍历AST失败: {file_path}, 错误堆栈:\n{err_msg}")
        return

    # Datastructures preparation for insertion to Neo4j
    head = graph.head  # 图中的第一个节点
    line = 1
    while head is not None: # 遍历图中每一个节点 为每个节点创建唯一标识
        head.generate_uri(SOURCE, DATASET_NAME, PYTHON_FILE_NAME, line)  # 创建图节点的唯一标识(s1、s2...)
        line += 1
        head = head.next

    nodes_for_labeling = []
    head = graph.head
    while head is not None: # 遍历图中每一个节点，获取每个节点信息添加到nodes中
        nodes_for_labeling.append(head.str())
        head = head.next




    # 阶段标注和核心见解提取
    print(f"Performing CoT analysis for pipeline: {output_filename}")
    analysis_result = None
    try:
        # 执行两阶段CoT分析,进行阶段标注和核心见解抽取
        analysis_result = pipeline_core_insight_analysis(file_path, nodes_for_labeling)

        # 只有所有阶段都成功时才更新节点阶段信息
        if analysis_result and analysis_result.get("success"):
            assignment_map = {}
            for assignment in analysis_result.get("node_phase_result", {}).get("node_phase_assignments", []):
                assignment_map[assignment["node_id"]] = assignment

            head = graph.head
            while head is not None:
                node_id = head.uri.split('/')[-1]
                if node_id in assignment_map:
                    head.phase = assignment_map[node_id]["phase"]
                head = head.next

            print(f"成功完成CoT分析: {output_filename}")
        else:
            failed_stage = analysis_result.get("failed_stage", "unknown") if analysis_result else "unknown"
            print(f"CoT分析失败于阶段 {failed_stage}: {output_filename}")

    except Exception as e:
        print(f"CoT analysis failed for {output_filename}: {e}")

    # 重新收集节点用于RDF生成
    nodes = []
    head = graph.head
    while head is not None:
        nodes.append(head.str())
        head = head.next

    # 构建pipeline URI
    pipeline_uri = util.create_pipeline_uri(SOURCE, DATASET_NAME, PYTHON_FILE_NAME)
    pipeline_info['uri'] = pipeline_uri
    pipeline_info['dataset'] = util.create_dataset_uri(SOURCE, DATASET_NAME)

    # Datastructures preparation for insertion to Neo4j
    file_elements = [el.str() for el in graph.files.values()]

    os.makedirs(os.path.join(output_path, DATASET_NAME), exist_ok=True)

    # 生成包含CoreInsight的RDF
    with open(ttl_path, 'w') as f:
        if analysis_result and analysis_result.get("success"):
            # 使用包含CoreInsight的RDF构建函数
            core_insights_data = analysis_result["core_insights"]
            rdf_content = build_pipeline_rdf_page(nodes, file_elements, core_insights_data, pipeline_uri)
        else:
            # 回退到普通的RDF构建
            rdf_content = build_pipeline_rdf_page(nodes, file_elements)

        f.write(rdf_content)

        # 保存完整的分析结果到JSON文件

    if analysis_result and analysis_result.get("success"):
        save_complete_analysis_result(analysis_result, output_path, DATASET_NAME, output_filename, pipeline_uri)
    save_pipeline_metadata(pipeline_info, graph.libraries, nodes, file_elements, output_path, DATASET_NAME,PYTHON_FILE_NAME)

    return pipeline_info, graph.libraries, analysis_result  # 返回pipeline的信息和用到的库包


def pipeline_core_insight_analysis(file_path: str,  nodes: List[Dict]) -> Dict[str, Any]:
    """两阶段CoT pipeline分析"""

    # 初始化空的结果结构
    analysis_result = {
        "node_phase_result": None,
        "pipeline_structure_result": None,
        "core_insights": None,
        "success": False,
        "failed_stage": None
    }

    # 读取完整源码
    with open(file_path, 'r') as f:
        full_code = f.read()

    # 第一阶段：节点标注
    print("Stage 1: Analyzing node phase assignments...")

    node_phase_result, task1_history, compressed_assignments = analyze_node_phases(nodes, full_code)

    # 严格校验第一阶段结果
    if node_phase_result is None:
        print("Stage 1 failed, aborting pipeline analysis")
        analysis_result["failed_stage"] = "node_phase_analysis"
        return analysis_result
    analysis_result["node_phase_result"] = node_phase_result
    print("Stage 1 completed successfully")


    # 第二阶段：阶段分析
    print("Stage 2: Summarizing pipeline structure based on node assignments...")
    pipeline_structure_result = summarize_pipeline_structure(full_code, task1_history)
    if pipeline_structure_result is None:
        print("Stage 2 failed, aborting pipeline analysis")
        analysis_result["failed_stage"] = "pipeline_structure_analysis"
        return analysis_result

    analysis_result["pipeline_structure_result"] = pipeline_structure_result
    print("Stage 2 completed successfully")

    # 第二阶段：基于第一阶段结果的核心见解提取
    print("Stage 3: Core insight extraction from pipeline structure...")
    core_insights = core_insight_extraction(full_code, pipeline_structure_result, compressed_assignments)
    if core_insights is None:
        print("Stage 3 failed, aborting pipeline analysis")
        analysis_result["failed_stage"] = "core_insight_extraction"
        return analysis_result

    analysis_result["core_insights"] = core_insights
    analysis_result["success"] = True
    print("Stage 3 completed successfully")

    # 在最终结果中展开所有压缩的节点信息
    return expand_analysis_result_nodes(analysis_result)


def save_complete_analysis_result(analysis_result: Dict, output_path: str,
                                  dataset_name: str, pipeline_id: str, pipeline_uri: str):
    """保存完整的分析结果"""

    insights_dir = os.path.join(output_path, 'core_insights')
    os.makedirs(insights_dir, exist_ok=True)

    complete_data = {
        "pipeline_id": pipeline_id,
        "pipeline_uri": pipeline_uri,
        "dataset_name": dataset_name,
        # 三个阶段的结果
        "pipeline_structure": analysis_result.get("pipeline_structure_result", {}).get("pipeline_structure", {}),
        "node_phase_assignments": analysis_result.get("node_phase_result", {}).get("node_phase_assignments", []),
        "core_insights": analysis_result.get("core_insights", {})
    }

    filename = f"{pipeline_id}_complete_analysis.json"
    filepath = os.path.join(insights_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(complete_data, f, ensure_ascii=False, indent=2)

    return complete_data


def save_pipeline_metadata(pipeline_info, libraries, nodes, file_elements, output_path, dataset_name, pipeline_id):
    """保存pipeline的完整元数据，用于生成library.ttl和default.ttl"""
    dataset_dir = os.path.join(output_path, dataset_name)
    os.makedirs(dataset_dir, exist_ok=True)

    # 将libraries对象转换为可序列化的格式
    serializable_libraries = {}
    for lib_name, lib_obj in libraries.items():
        serializable_libraries[lib_name] = lib_obj.str()

    # 构建完整的元数据
    metadata = {
        "pipeline_id": pipeline_id,
        "dataset_name": dataset_name,
        "pipeline_info": pipeline_info,
        "libraries": serializable_libraries,
        "nodes_count": len(nodes),
        "file_elements_count": len(file_elements),
    }

    filename = f"{pipeline_id}_metadata.json"
    filepath = os.path.join(dataset_dir, filename)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        print(f"保存pipeline元数据: {dataset_name}/{pipeline_id}")
    except Exception as e:
        print(f"保存pipeline元数据失败 {dataset_name}/{pipeline_id}: {e}")
