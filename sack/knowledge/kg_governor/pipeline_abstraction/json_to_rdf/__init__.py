import json
from functools import reduce
from typing import List


def create_prefix() -> str:
    return '\n'.join([
        "@prefix pipeline: <http://sack.local/ontology/pipeline/> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix sack: <http://sack.local/ontology/> .",
        "\n"
    ])


def create_statement_uri(uri: str) -> str:
    return f'<{uri}> a sack:Statement;\n'


def add_to_dict(dict, index, value):
    dict[index].append(value)
    return dict


def library_call_to_rdf(libraries: List[dict]) -> str:
    try:
        objects = reduce(lambda l, x: add_to_dict(l, x['call_type'], x['uri']), libraries, {
            'callsFunction': [],
            'callsClass': [],
            'callsPackage': [],
            'callsLibrary': [],
            'callsAPI': []
        })
    
        return ''.join([
            build_library_call_to_rdf(call_type, libs) for call_type, libs in objects.items()
        ])
    except:
        print(libraries)

def build_library_call_to_rdf(call_type: str, libraries: List[str]) -> str:
    if len(libraries) == 0:
        return ""
    return f'\tpipeline:{call_type} {", ".join([f"<{lib}>" for lib in libraries])};\n'


def read_to_rdf(reads: List[dict]) -> str:
    objects = reduce(lambda l, x: add_to_dict(l, x['type'], x['uri']), reads, {
        'readsTable': [],
        'readsColumn': [],
    })

    return ''.join([
        build_read_to_rdf(read_type, read) for read_type, read in objects.items()
    ])


def build_read_to_rdf(read_type: str, reads: List[dict]) -> str:
    if len(reads) == 0:
        return ""
    return f'\tpipeline:{read_type} {", ".join([f"<{read}>" for read in reads])};\n'


def has_text_to_rdf(text: str) -> str:
    return f'\tpipeline:hasText {escape_characters(text)};\n'


def has_parameter_to_rdf(parameters: List[dict]) -> str:
    if len(parameters) == 0:
        return ""
    return f'\tpipeline:hasParameter ' \
           f'{", ".join([create_quoted_parameter_value(param) for param in parameters])};\n'


def create_quoted_value(word: str) -> str:
    return json.dumps(word)


def create_quoted_parameter_value(param: dict) -> str:
    value = param['parameter']
    return create_quoted_value(value)


def has_dataflow_to_rdf(flows: List[str]) -> str:
    if len(flows) == 0:
        return ""
    return f'\tpipeline:hasDataFlowTo {", ".join([f"<{lib}>" for lib in flows])};\n'


def next_statement_to_rdf(statement: str or None) -> str:
    if statement is None:
        return ''
    return f'\tpipeline:hasNextStatement <{statement}>;\n'


def control_flow_to_rdf(control_flows: List[str]) -> str:
    if len(control_flows) == 0:
        return ""
    return f'\tpipeline:inControlFlow {", ".join([f"<{flow}>" for flow in control_flows])};\n'


def build_statement_rdf(statement: dict) -> str: # 创建当前node相关的RDF三元组 （通过定义<当前节点> + 批量 关系 <目标节点>; 的字符串拼接的方式实现）
    statement_uri = statement['uri']
    parts = statement_uri.split('/')
    pipeline_uri = '/'.join(parts[:-1])

    base_triples = [
        create_statement_uri(statement_uri),
        library_call_to_rdf(statement['calls']),
        read_to_rdf(statement['read']),
        has_text_to_rdf(statement['text']),
        control_flow_to_rdf(statement['control_flow']),
        has_parameter_to_rdf(statement['parameters']),
        has_dataflow_to_rdf(statement['dataFlow']),
        has_phase_to_rdf(statement.get('phase')),
        next_statement_to_rdf(statement['next']),
        f'\tsack:isPartOf <{pipeline_uri}> ;'  # Node是Pipeline的组成部分
    ]

    triples_string = ''.join(base_triples)
    triples_string = triples_string.rsplit(';', 1)[0] + ' .\n'

    return triples_string


def build_table_rdf(uri: str) -> str:
    return f'<{uri}> a sack:Table .\n'


def build_column_rdf(table_uri: str, column_uri: str) -> str:
    return f'<{column_uri}> a sack:Column;\n' \
           f'\tsack:isPartOf <{table_uri}> .\n'


def build_parameter_rdf(statement_uri: str, parameter: str, parameter_value: str) -> str:
    return f'<<<{statement_uri}> pipeline:hasParameter {escape_characters(parameter)}>> pipeline:withParameterValue {escape_characters(parameter_value)} .\n'


def build_library_rdf(library: dict) -> str:
    return f"<{library['uri']}> a <{create_library_uri(library['type'])}> .\n"


def build_sub_library_rdf(library: dict, parent_uri: str) -> str:
    return f"<{library['uri']}> a <{create_library_uri(library['type'])}>;\n" \
           f"\tsack:isPartOf <{parent_uri}> .\n"


def create_library_uri(uri: str or None):
    return 'http://sack.local/ontology/API' if uri is None else uri


def build_pipeline_rdf(pipeline: dict) -> str:
    return ''.join([
        pipeline_uri_to_rdf(pipeline['uri']),
        title_to_rdf(pipeline['title']),
        author_to_rdf(pipeline['author']),
        votes_to_rdf(pipeline['votes']),
        date_to_rdf(pipeline['date']),
        tags_to_rdf(pipeline['tags']),
        source_to_rdf(pipeline['url']),
        score_to_rdf(pipeline['score']),
        dataset_to_rdf(pipeline['dataset'])
    ])


def pipeline_uri_to_rdf(uri: str):
    return f"<{uri}> a sack:Pipeline;\n"


def escape_characters(word: str) -> str:
    return json.dumps(word)


def title_to_rdf(title: str) -> str:
    return f"\trdfs:label {escape_characters(title)};\n"


def author_to_rdf(author: str) -> str:
    return f"\tpipeline:isWrittenBy {escape_characters(author)};\n"


def votes_to_rdf(votes: int) -> str:
    return f"\tpipeline:hasVotes {votes};\n"


def date_to_rdf(date: str) -> str:
    return f"\tpipeline:isWrittenOn {escape_characters(date)};\n"


def tags_to_rdf(tags: List[str]) -> str:
    if len(tags) == 0:
        return ""
    return f'\tpipeline:hasTag {", ".join([create_quoted_value(tag) for tag in tags])};\n'


def source_to_rdf(source: str) -> str:
    return f"\tpipeline:hasSourceURL {escape_characters(source)};\n"


def score_to_rdf(score: float) -> str:
    if score:
        return f"\tpipeline:hasScore {score};\n"
    else:
        return ""

def dataset_to_rdf(dataset: str) -> str:
    return f"\tsack:isPartOf <{dataset}> .\n"


def build_pipeline_rdf_page(statements: List[dict], datasets: List[dict],
                            core_insights_data: dict = None, pipeline_uri: str = None) -> str:
    """pipeline完整 RDF 页面"""

    parts = [
        create_prefix(),  # 创建前缀
        build_statement_rdf_part(statements),  # node rdf三元组化
        '\n',
        build_datasets_rdf_part(datasets)  # dataset rdf三元组化
    ]

    # 添加CoreInsight部分（如果存在）
    if core_insights_data and pipeline_uri:
        parts.extend([
            '\n',
            build_core_insight_rdf_part(core_insights_data, pipeline_uri),  # core_insight rdf三元组化
            '\n',
            build_pipeline_insight_relationships(core_insights_data, pipeline_uri)  # pipeline与insight的关系
        ])

    return ''.join(parts)

def build_parameter_rdf_part(statement_uri: str, parameters: List[dict]):
    return '\n'.join([
        build_parameter_rdf(statement_uri, param['parameter'], param['parameter_value']) for param in parameters
    ])


def build_statement_rdf_part(statements: List[dict]) -> str:
    return '\n'.join(['\n'.join([
        build_statement_rdf(statement),
        build_parameter_rdf_part(statement['uri'], statement['parameters'])
    ]) for statement in statements])


def build_column_rdf_part(parent: str, columns: List[dict]) -> str:
    return '\n'.join([build_column_rdf(parent, column['uri']) for column in columns])


def build_datasets_rdf_part(datasets: List[dict]) -> str:
    return '\n'.join('\n'.join([
        build_table_rdf(table['uri']),
        build_column_rdf_part(table['uri'], table['contain'])
    ]) for table in datasets)


def build_library_rdf_page(libraries: List[dict]) -> str:
    return ''.join([
        create_prefix(),
        build_library_part(libraries)
    ])


def build_library_part(libraries: List[dict]) -> str:
    return '\n'.join(['\n'.join([
        build_library_rdf(library),
        build_sub_libraries_part(library['uri'], library['contain'])
    ]) for library in libraries])


def build_sub_libraries_part(parent_library: str, sub_libraries: List[dict]) -> str:
    return ''.join(['\n'.join([
        build_sub_library_rdf(library, parent_library),
        build_sub_libraries_part(library['uri'], library['contain'])
    ]) for library in sub_libraries])


def build_default_rdf_page(pipelines: List[dict]) -> str:
    return ''.join([
        create_prefix(),
        build_pipeline_part(pipelines),
        "\n"
    ])


def build_pipeline_part(pipelines: List[dict]) -> str:
    return '\n'.join([
        build_pipeline_rdf(pipeline) for pipeline in pipelines
    ])


def has_phase_to_rdf(phase: str) -> str:
    """添加阶段信息的三元组"""
    if not phase or phase == "Unknown":
        return ""
    return f'\tpipeline:hasPhase {escape_characters(phase)};\n'


def build_core_insight_rdf_part(core_insights_data: dict, pipeline_uri: str) -> str:
    """构建CoreInsight的RDF部分"""
    triples = []

    # 处理阶段特定的见解
    phase_insights = core_insights_data.get("phase_insights", {})
    for phase, insights in phase_insights.items():
        for insight in insights:
            triples.append(build_single_core_insight_rdf(insight, phase, pipeline_uri))

    # 处理跨阶段见解
    cross_phase_insights = core_insights_data.get("cross_phase_insights", [])
    for insight in cross_phase_insights:
        triples.append(build_single_core_insight_rdf(
            insight,
            "Cross-Phase",
            pipeline_uri,
            spanning_phases=insight.get("spanning_phases", [])
        ))

    return '\n'.join([t for t in triples if t])  # 过滤掉空字符串


def build_single_core_insight_rdf(insight: dict, phase: str, pipeline_uri: str,
                                  spanning_phases: List[str] = None) -> str:
    """构建单个CoreInsight的RDF三元组"""

    insight_id = insight.get("insight_id", "")
    if not insight_id:
        return ""

    # 构建CoreInsight的URI
    insight_uri = f"{pipeline_uri}/insight/{insight_id}"

    triples = [
        f'<{insight_uri}> a sack:CoreInsight ;',
        f'  rdfs:label {escape_characters(insight.get("description", ""))} ;',
        f'  sack:insightType {escape_characters(insight.get("type", ""))} ;',
        # f'  sack:significance {escape_characters(insight.get("significance", ""))} ;',
        f'  sack:effectiveness {escape_characters(insight.get("effectiveness_reasoning", ""))} ;',
        # f'  sack:transferability {escape_characters(insight.get("transferability", ""))} ;',
        f'  sack:evidence {escape_characters(insight.get("evidence", ""))} ;'
    ]

    # 链接到阶段
    if phase and phase != "Cross-Phase":
        triples.append(f'  sack:belongsToPhase {escape_characters(phase)} ;')
    elif phase == "Cross-Phase":
        triples.append(f'  sack:belongsToPhase "CrossPhase" ;')
        # 对于跨阶段见解，记录跨越的阶段
        if spanning_phases:
            for span_phase in spanning_phases:
                triples.append(f'  sack:spansPhase {escape_characters(span_phase)} ;')

    # 链接到实现节点
    implementing_nodes = insight.get("implementing_node_ids", [])
    for node_id in implementing_nodes:
        node_uri = f"{pipeline_uri}/{node_id}"
        triples.append(f'  sack:implementedIn <{node_uri}> ;')

    # 结束
    triples[-1] = triples[-1].replace(' ;', ' .')

    return '\n'.join(triples) + '\n'


def build_pipeline_insight_relationships(core_insights_data: dict, pipeline_uri: str) -> str:
    """构建pipeline与core_insight的hasCoreInsight关系"""
    triples = []

    # 处理阶段特定的见解
    phase_insights = core_insights_data.get("phase_insights", {})
    for phase, insights in phase_insights.items():
        for insight in insights:
            insight_id = insight.get("insight_id", "")
            if insight_id:
                insight_uri = f"{pipeline_uri}/insight/{insight_id}"
                triples.append(f'<{pipeline_uri}> sack:hasCoreInsight <{insight_uri}> .')

    # 处理跨阶段见解
    cross_phase_insights = core_insights_data.get("cross_phase_insights", [])
    for insight in cross_phase_insights:
        insight_id = insight.get("insight_id", "")
        if insight_id:
            insight_uri = f"{pipeline_uri}/insight/{insight_id}"
            triples.append(f'<{pipeline_uri}> sack:hasCoreInsight <{insight_uri}> .')

    return '\n'.join(triples) + '\n' if triples else ''
