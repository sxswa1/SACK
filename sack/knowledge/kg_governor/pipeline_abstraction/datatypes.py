from typing import Dict, Optional,List
import re
from dataclasses import dataclass
import sack.knowledge.kg_governor.pipeline_abstraction.Calls as Calls
import sack.knowledge.kg_governor.pipeline_abstraction.util as util
from sack.knowledge.kg_governor.pipeline_abstraction.Calls.get_calls import get_calls
from sack.knowledge.kg_governor.pipeline_abstraction.util import parse_line_text, create_import_uri, create_file_uri, create_column_name, extract_library_dependencies, create_built_in_uri


class Node:  # 定义抽象语法树中的节点
    __slots__ = ('previous', 'next', 'text', 'uri', 'data_flow',
                 'parameters', 'calls', 'read', 'control_flow','phase')

    def __init__(self, previous, text):
        self.previous = previous
        self.next = None
        self.text = text
        self.uri = ""
        self.control_flow = set()
        self.parameters = []
        self.calls = []
        self.read = []
        self.data_flow = []
        self.phase = None

    def generate_uri(self, source, dataset, file, node_id):  # 构建图节点的唯一标识（s1、s2、...）
        self.uri = util.create_statement_uri(source, dataset, file, node_id)

    def str(self): # 获取每个图节点的节点信息
        control_flows = [flow for flow in self.control_flow]
        parameters = [value.str() for value in self.parameters]
        call_array = [value.repr() for value in self.calls]
        read_array = [value.repr() for value in self.read]
        data_flow = [value.uri for value in self.data_flow]

        return {"uri": self.uri,
                "previous": self.previous.uri if self.previous is not None else None,
                "next": self.next.uri if self.next is not None else None,
                "text": self.text,
                "control_flow": control_flows,
                "parameters": parameters,
                "calls": call_array,
                "read": read_array,
                "dataFlow": data_flow,
                'phase': self.phase
                }


class AttrEdge:  # 参数映射边
    __slots__ = ('parameter', 'parameter_value')

    def __init__(self, parameter, parameter_value):
        self.parameter = parameter
        self.parameter_value = parameter_value

    def str(self):
        return {'parameter': self.parameter, 'parameter_value': self.parameter_value}


call_types = {
    Calls.CallType.FUNCTION.value: 'callsFunction',
    Calls.CallType.CLASS.value: 'callsClass',
    Calls.CallType.PACKAGE.value: 'callsPackage',
    Calls.CallType.LIBRARY.value: 'callsLibrary',
    Calls.CallType.NONE.value: 'callsAPI'
}


def get_call_type(library_type: str) -> str:
    return call_types.get(library_type)


class Library: # 库包节点  它是一个层次内容（它的contain就是下一个层级） 如  matplotlib 的 contain可能包含 pyplot
    __slots__ = ('uri', 'contain', 'type', 'call_type')

    def __init__(self, uri, library_type=None):
        self.uri = uri
        self.contain = dict()
        self.type = library_type
        self.call_type = get_call_type(library_type)

    def str(self):   # 整合成一个对该包的信息整合
        libraries = [value.str() for value in self.contain.values()] # 提取涉及的所有子包的信息（嵌套的库包节点）
        return {'uri': self.uri, 'contain': libraries, 'type': self.type}

    def repr(self):
        return {'uri': self.uri, 'call_type': self.call_type}


class File:  # 文件节点类型
    __slots__ = ('uri', 'contain')

    def __init__(self, uri):
        self.uri = uri
        self.contain = set()  # 文件节点包含的列

    def __cmp__(self, other):
        return self.uri == other.uri

    def str(self):
        columns = [value.str() for value in self.contain]
        return {'uri': self.uri, 'contain': columns}

    def repr(self):
        return {'uri': self.uri, 'type': 'readsTable'}


class Column: # 列子节点
    __slots__ = 'uri'

    def __init__(self, uri):
        self.uri = uri

    def __cmp__(self, other):
        return self.uri == other.uri

    def str(self):
        return {'uri': self.uri}

    def repr(self):
        return {'uri': self.uri, 'type': 'readsColumn'}


class GraphInformation:
    head: Optional[Node]
    tail: Optional[Node]
    files: Dict[str, File]
    libraries: Dict[str, Library]

    __slots__ = ('head', 'tail', 'files', 'libraries',
                 'python_file_name', 'source', 'dataset_name')

    def __init__(self, python_file_name: str, source: str, dataset_name: str, libraries=None):
        if libraries is None:
            libraries = dict()
        self.head = None # 头节点
        self.tail = None # 尾节点
        self.files = dict()  # 用到的文件名和文件节点的映射（文件节点又包含列节点）
        self.libraries = libraries  # 用到的库包
        self.python_file_name = python_file_name  # pipeline_id
        self.source = source  # 数据（竞赛）来源： kaggle_small
        self.dataset_name = dataset_name  # 竞赛名

    def add_node(self, text):  # 向图中添加节点
        if text.startswith('"""'):
            return

        node = Node(self.tail, parse_line_text(text))  # 前驱节点是self.tail,内容是消除换行的内容
        if self.head is None:
            self.head = self.tail = node
        else:
            self.tail.next = node  # 这不是队列的节点添加逻辑吗？
            self.tail = node

    def add_control_flow(self, control_flow): # 向图中当前节点添加控制流
        for flow in control_flow:
            self.tail.control_flow.add(flow.value)

    def add_file(self, file):  # 往当前图的尾节点添加文件子节点
        file_uri = create_file_uri(self.source, self.dataset_name, file.filename) # 创建文件的唯一标识
        file_node = File(file_uri)  # 创建一个文件节点
        self.tail.read.append(file_node) # 当前图的尾节点的read列表中添加该文件节点
        self.files[file.filename] = file_node  # 文件名和节点映射

    def add_columns(self, filename, columns):  # 往当前图的尾节点添加列子节点
        for column_name in columns:
            column_uri = create_column_name(self.source, self.dataset_name, filename, column_name)
            column = Column(column_uri) # 创建列子节点
            self.tail.read.append(column) # 当前图的尾节点的read列表中添加该列节点
            self.files.get(filename).contain.add(column) # 已有的对应文件节点的contain中添加该列节点

    def add_import_node(self, path, func=create_import_uri): # 往当前图的尾节点添加库节点
        PATH_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*$')  # 添加无效path过滤条件
        dependencies = extract_library_dependencies(path)  # 对引入的内容进行拆解分析（获取每一个以来内容path分别处理）
        container = self.libraries  # 当前整个图用到的library集合体
        for i in range(len(dependencies)): # 对当前引入内容到其所有依赖内容遍历处理
            library_path = dependencies[i]
            if not isinstance(library_path, str) or not library_path.strip():
                continue
            if not PATH_PATTERN.match(library_path):
                continue
            lib_uri = func(library_path) # 创建内容的唯一标识uri
            if '*' in lib_uri: # 这种仅出现在from... import *的情况  也就是name是* 无法判断具体对象  因此无需后续步骤
                continue

            if lib_uri not in container.keys(): # 出现的内容是新的（当前library层级没有保存过它），需要创建并维护它的信息
                package = get_calls(library_path)
                library = Library(lib_uri, package.call_type.value)  # 构建当前内容的描述信息
                container[lib_uri] = library  # 添加到container中
            else:
                library = container.get(lib_uri) # 已经存过了，直接取就行
            if i == len(dependencies) - 1: # 最后向当前节点（图队列的尾部节点）添加path对应的Library信息 （因为只有该内容是实际代码用到的 之前分析的都是依赖内容）
                self.tail.calls.append(library)  # 尾节点中的calls中添加库包节点（也就是标识当前节点实际用到了什么库包）

            container = library.contain  # 获取到当前library的下一层子library  如当前遍历的是matplotlib 则library.contain就是matplotlib.*的集合

    def add_import_from_node(self, path, name): # 用name和依赖内容的path拼接成完整path  归约到import遍历方式进行处理
        full_path = f'{path}.{name}'  # 获取path
        self.add_import_node(full_path)

    def add_package_call(self, package):
        if package is None:
            return
        self.add_import_node(package)

    def rewrite_node_flow(self):  # 尾节点和前一个节点交换顺序
        current_node = self.tail
        parent_node = self.tail.previous
        ancestor_node = parent_node.previous

        if parent_node == self.head:
            self.head = current_node

        temp = current_node.next
        current_node.next = parent_node
        parent_node.next = temp
        if ancestor_node is not None:
            ancestor_node.next = current_node

        current_node.previous = ancestor_node
        parent_node.previous = current_node

        self.tail = parent_node

    def insert_before(self, node: Node): # 摘下尾节点添加到node前边
        current_node = self.tail
        current_node.previous.next = None
        self.tail = current_node.previous

        if node == self.head:
            self.head = current_node

        current_node.previous = node.previous
        node.previous = current_node
        current_node.next = node
        if current_node.previous is not None:
            current_node.previous.next = current_node

    def add_parameter(self, parameter, value):
        edge = AttrEdge(parameter, str(value))
        self.tail.parameters.append(edge)

    def add_parameters(self, parameters: dict):  # 参数映射 也就是函数和数据集之间的映射边
        for key, value in parameters.items():
            edge = AttrEdge(key, str(value))
            self.tail.parameters.append(edge)

    def add_built_in_call(self, library):
        self.add_import_node(library, create_built_in_uri)

    def add_data_flows(self, node: Node):
        node.data_flow.append(self.tail)

    def add_concurrent_flow(self, node: Node or None):
        if node is None:
            self.tail.previous.data_flow.append(self.tail)
        else:
            node.previous.data_flow.append(self.tail)

@dataclass
class CoreInsight:
    insight_id: str
    pipeline_id: str
    pipeline_uri: str  # 新增：pipeline的完整URI
    phase: str
    insight_type: str  # DS, DOM, OPTIM, ARCH
    description: str
    implementing_node_ids: List[str]
    effectiveness_reasoning: str
    significance: str  # High/Medium/Low
    transferability: str
    evidence: str

    @property
    def generate_uri(self,) -> str:
        """核心见解的URI"""
        return  util.create_core_insight_uri(self.pipeline_uri, self.insight_id)

    def to_rdf_triples(self) -> List[str]:
        """转换为RDF三元组，建立与pipeline的关系"""
        triples = []

        # 核心见解自身的属性
        triples.append(f'<{self.generate_uri}> a sack:CoreInsight ;')
        triples.append(f'  rdfs:label "{self.description}" ;')
        triples.append(f'  sack:insightType "{self.insight_type}" ;')
        triples.append(f'  sack:significance "{self.significance}" ;')
        triples.append(f'  sack:effectiveness "{self.effectiveness_reasoning}" ;')
        triples.append(f'  sack:transferability "{self.transferability}" ;')
        triples.append(f'  sack:evidence "{self.evidence}" ;')

        # 链接到阶段
        if self.phase != "Cross-Phase":
            triples.append(f'  sack:belongsToPhase "{self.phase}" ;')
        else:
            triples.append(f'  sack:belongsToPhase "CrossPhase" ;')

        # 链接到实现节点
        for node_id in self.implementing_node_ids:
            # 构建节点的完整URI（假设节点URI格式与pipeline一致）
            node_uri = f"{self.pipeline_uri}/{node_id}"
            triples.append(f'  sack:implementedIn <{node_uri}> ;')

        # 结束核心见解的定义
        triples[-1] = triples[-1].replace(' ;', ' .')

        return triples

    def get_pipeline_relationship_triples(self) -> List[str]:
        """生成pipeline与核心见解的关系三元组"""
        triples = []

        # pipeline hasCoreInsight core_insight
        triples.append(f'<{self.pipeline_uri}> sack:hasCoreInsight <{self.generate_uri}> .')

        return triples

    @classmethod
    def from_analysis_result(cls, analysis_result: Dict, pipeline_id: str, pipeline_uri: str) -> List['CoreInsight']:
        """从分析结果创建CoreInsight对象列表"""

        insights = []
        core_insights_data = analysis_result.get("core_insights", {})

        # 处理阶段特定的见解
        phase_insights = core_insights_data.get("phase_insights", {})
        for phase, insight_list in phase_insights.items():
            for insight_data in insight_list:
                insight = cls(
                    insight_id=insight_data["insight_id"],
                    pipeline_id=pipeline_id,
                    pipeline_uri=pipeline_uri,
                    phase=phase,
                    insight_type=insight_data["type"],
                    description=insight_data["description"],
                    implementing_node_ids=insight_data["implementing_node_ids"],
                    effectiveness_reasoning=insight_data["effectiveness_reasoning"],
                    significance=insight_data["significance"],
                    transferability=insight_data.get("transferability", ""),
                    evidence=insight_data.get("evidence", "")
                )
                insights.append(insight)

        # 处理跨阶段见解
        cross_phase_insights = core_insights_data.get("cross_phase_insights", [])
        for insight_data in cross_phase_insights:
            insight = cls(
                insight_id=insight_data["insight_id"],
                pipeline_id=pipeline_id,
                pipeline_uri=pipeline_uri,
                phase="Cross-Phase",
                insight_type=insight_data["type"],
                description=insight_data["description"],
                implementing_node_ids=insight_data["implementing_node_ids"],
                effectiveness_reasoning=insight_data["effectiveness_reasoning"],
                significance=insight_data["significance"],
                transferability=insight_data.get("transferability", ""),
                evidence=insight_data.get("evidence", "")
            )
            insights.append(insight)

        return insights