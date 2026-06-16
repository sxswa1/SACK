import zlib
import urllib.parse
import astor  # 用于把抽象语法树转成代码
import ast
from enum import Enum
from typing import Dict, Any, List

import sack.knowledge.kg_governor.pipeline_abstraction.Calls as Calls
from sack.knowledge.kg_governor.pipeline_abstraction.Calls.get_calls import get_calls


def is_file(string):  # 判断是否表示file （csv）
    if not isinstance(string, str):
        return False
    return '.csv' in string


def format_node_text(node) -> str:  # 节点转代码（字符串）
    text = astor.to_source(node).strip()
    if isinstance(node, ast.For):  # 如果节点是for循环，就只保留for语句
        text = text.split("\n")[0]
    return text


def generate_id(dataset_name: str, table_name: str, column_name: str):
    return zlib.crc32(bytes(dataset_name + table_name + column_name, 'utf-8'))


def get_package(package_name, alias):  # 获取变量对应处理方法的描述信息
    if isinstance(package_name, Calls.Call):  # 如果已经是被调用的信息 则直接返回
        return package_name
    if package_name is None or not isinstance(package_name, str):  # 不是str无法处理
        return None
    # 如果不为空 且 是str  也就是package_name是path
    if '.' in package_name:  # 有依赖关系，也就是package_name是形如df.columns.values的格式（变量+方法）  需要先解析出变量对应的实际名（类型）再拼接得到完整方法名
        path = package_name.split('.')
        path[0] = alias.get(path[0], path[0])  # path[0]也就是取到该变量，获取该变量的实际名（也就是变量的类型） 如df对应的是DataFrame
        path = '.'.join(path)  # 拼接实际名，也就是找到了变量对应的处理方法 DataFrame.columns.values
        pack = get_calls(path)# 找到该方法被调用的信息      
    else:  # 如果没有依赖关系 那方法的调用其实是直接以方法名调用的  如datetime
        pack = get_calls(package_name) # 直接获取被调用方法的信息
        
    return pack if (pack.call_type is not None or (pack.name != '' and pack.library_path != '')) else None


def create_file_id(source: str, dataset: str, table_name: str) -> str:
    return f"sack.local/{url_encode(source)}/{url_encode(dataset)}/" \
           f"{url_encode(table_name)}"


def create_column_name(source: str, dataset: str, table_name: str, column: str):
    return f"http://sack.local/resource/{url_encode(source)}/" \
           f"{url_encode(dataset)}/{url_encode(table_name)}/" \
           f"{url_encode(column)}"




def create_import_uri(library_name):  # 创建包的唯一标识uri
    path = library_name.replace('.', '/')
    return f"http://sack.local/resource/library/{path}"


def create_import_from_uri(path, library_name):
    path = path.replace('.', '/')
    return "http://sack.local/resource/library/" \
           f"{path}/{library_name}"


def create_built_in_uri(library_name):
    path = library_name.replace('.', '/')
    return "http://sack.local/resource/library/builtin/" \
           f"{path}"


def create_file_uri(source: str, dataset_name: str, file_name: str):
    return f"http://sack.local/resource/{url_encode(source)}/" \
           f"{url_encode(dataset_name)}/{url_encode(file_name)}"

def create_source_uri(source: str):
    return f"http://sack.local/resource/{url_encode(source)}"

def create_dataset_uri(source: str, dataset_name: str):
    return f"{create_source_uri(source)}/{url_encode(dataset_name)}"


def create_pipeline_uri(source, dataset_name, file_name):
    return f"{create_dataset_uri(source, dataset_name)}/{url_encode(file_name)}"

def create_statement_uri(source: str, dataset_name: str, python_file_name: str, line_id: int): # 创建构建图节点的唯一标识
    return f"{create_pipeline_uri(source, dataset_name, python_file_name)}/s{line_id}"

def url_encode(string):  #
    return urllib.parse.quote_plus(str(string))


def parse_line_text(text: str) -> str:  # 消除换行
    return text.replace('\n', '')


def extract_library_dependencies(path):  # 拆解包的依赖关系 把一个完整的包path拆解成每一个层级的path  如matplotlib.pyplot  拆成matplotlib和matplotlib.pyplot
    path = path.split('.')
    return ['.'.join(path[:i]) for i in range(1, len(path) + 1)]


def create_core_insight_uri(pipeline_uri: str, insight_id: str) -> str:
    """创建核心见解的URI，格式：pipeline_uri/insight/insight_id"""
    return f"{pipeline_uri}/insight/{insight_id}"

class ControlFlow(Enum):
    METHOD = "http://sack.local/resource/userDefinedFunction"
    LOOP = "http://sack.local/resource/loop"
    CONDITIONAL = "http://sack.local/resource/conditional"
    IMPORT = "http://sack.local/resource/import"



def expand_analysis_result_nodes(analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    用展开格式替换分析结果中所有压缩的节点信息
    """
    expanded_result = analysis_result.copy()

    # 替换pipeline_structure_result中的节点
    if "pipeline_structure_result" in expanded_result:
        pipeline_structure = expanded_result["pipeline_structure_result"].get("pipeline_structure", {})
        for phase in pipeline_structure.get("present_phases", []):
            if "included_nodes" in phase:
                # 用展开格式替换压缩格式
                phase["included_nodes"] = expand_node_ids(phase["included_nodes"])

    # 替换core_insights中的节点
    if "core_insights" in expanded_result:
        core_insights = expanded_result["core_insights"]

        # 替换phase_insights中的节点
        for phase_name, insights in core_insights.get("phase_insights", {}).items():
            for insight in insights:
                if "implementing_node_ids" in insight:
                    # 用展开格式替换压缩格式
                    insight["implementing_node_ids"] = expand_node_ids(insight["implementing_node_ids"])

        # 替换cross_phase_insights中的节点
        for insight in core_insights.get("cross_phase_insights", []):
            if "implementing_node_ids" in insight:
                # 用展开格式替换压缩格式
                insight["implementing_node_ids"] = expand_node_ids(insight["implementing_node_ids"])

    return expanded_result


def expand_node_ids(compressed_ids: List[str]) -> List[str]:
    """
    将压缩的节点编号展开为完整列表
    例如: ["s1-s3", "s5-s6", "s8"] -> ["s1", "s2", "s3", "s5", "s6", "s8"]
    """
    expanded = []

    for item in compressed_ids:
        if '-' in item:
            # 处理范围表示
            try:
                start_str, end_str = item.split('-')
                start = int(start_str[1:])  # 去掉's'
                end = int(end_str[1:])  # 去掉's'
                expanded.extend([f"s{i}" for i in range(start, end + 1)])
            except:
                # 如果解析失败，保持原样
                expanded.append(item)
        else:
            # 单个节点
            expanded.append(item)

    return expanded
