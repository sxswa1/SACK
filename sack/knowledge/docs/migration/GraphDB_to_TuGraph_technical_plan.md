# SACK 科学知识图谱从 GraphDB 迁移到 TuGraph：完整技术方案

> 文档对象：项目负责人、后端工程师、知识图谱工程师、测试与运维人员
> 文档状态：实施方案 v1.0（基于当前仓库代码审阅）
> 建议基线：先以 TuGraph 4.5.2 做兼容性验证，实施时固定实际镜像摘要和版本，不使用 `latest` 作为生产基线
> 迁移原则：语义等价优先、API 契约优先、可回滚优先，不做一次性“大爆炸”替换

## 1. 结论先行

迁移是可行的，但它不是数据库连接地址替换，也不应通过“把 TTL 直接导入 TuGraph”完成。当前 SACK 已经把 RDF 数据模型和 GraphDB 能力嵌入到构建、装载、查询、评估子图等多个环节，实际涉及：

- RDF 三元组和 IRI 标识体系；
- SPARQL 查询、聚合、过滤、字符串函数与动态查询拼接；
- RDF-star 对“关系本身”的标注；
- Named Graph 对每条 Pipeline 子图的作用域隔离；
- GraphDB 仓库创建、删除、服务端导入、RDF Graph Store HTTP API；
- PostgreSQL/pgvector 与图查询共同组成的混合检索；
- 上层 `SACKCaseRetriever` 对现有 DataFrame 字段和排序语义的依赖。

TuGraph 是强 Schema 的标签属性图。正确迁移路线应为：

```text
原始历史案例 / Profile / Pipeline AST
                  │
                  ▼
       存储无关的规范图模型（CIR）
         ┌────────┴────────┐
         ▼                 ▼
   GraphDB RDF Sink    TuGraph LPG Sink
   （过渡期保留）       （CSV/JSON + Import）
         └────────┬────────┘
                  ▼
       统一领域查询接口 GraphStore
         ┌────────┴────────┐
         ▼                 ▼
      SPARQL 实现       Cypher 实现
                  │
                  ▼
       现有 SACKKnowledgeBase API
                  │
                  ▼
          SACKCaseRetriever / Agent
```

一期明确保留 PostgreSQL/pgvector，不把向量存储顺带迁入 TuGraph。当前向量库已经承载竞赛语义相似度、数据描述相似度、列级内容与标签向量检索；把它同时迁移只会扩大风险，并不属于 GraphDB 替换的必要条件。

## 2. 范围与非目标

### 2.1 本次范围

1. 科学知识图谱构建产物从 RDF/TTL 专属输出，演进为可同时输出 GraphDB RDF 和 TuGraph 属性图导入数据。
2. 将 GraphDB 中的 Dataset、Table、Column、EDAInsight、Pipeline、Statement、API、CoreInsight 及其关系迁移到 TuGraph。
3. 将 RDF-star、Named Graph 和常用 RDF 语义显式映射为属性图结构。
4. 为当前 `SACKKnowledgeBase` 公共方法提供 TuGraph/Cypher 实现，并保持返回字段、排序、空结果行为和数值口径。
5. 改造 GraphDB 专属的构建、导入、评估子图和查询连接逻辑。
6. 建立 GraphDB 与 TuGraph 的数据一致性、查询一致性、性能和回滚验证体系。

### 2.2 一期非目标

- 不迁移 PostgreSQL/pgvector；
- 不为任意 SPARQL 编写通用 SPARQL-to-Cypher 翻译器；
- 不重写数据画像、FastText、Spark、AST Pipeline 抽象和 CoreInsight 提取算法；
- 不借迁移机会改变相似度公式、召回权重或 Agent Gate 逻辑；
- 不直接删除 GraphDB 仓库或现有 TTL/JSON 产物；
- 不默认引入 TuGraph 存储过程，除非普通参数化 Cypher 经验证无法满足性能目标。

## 3. 当前系统的真实构建链路

### 3.1 主构建入口

当前 `python -m sack build-knowledge` 最终调用 `sack/knowledge/build_knowledge.py:24-49`，顺序是：

1. `profile_data()`：读取历史案例、竞赛描述、EDAInsight 与 CSV，生成竞赛、EDA 和列 Profile；
2. `build_data_global_schema()`：根据 Profile 生成全局数据 Schema 图和列相似关系；
3. `create_graphdb_repo()`：通过 GraphDB REST API 创建或替换仓库；
4. `populate_data_global_schema_graph()`：把全局 Schema TTL 复制到 GraphDB 服务端导入目录并轮询导入任务；
5. `populate_pipeline_graphs()`：上传默认图、库图及每条 Pipeline Named Graph；
6. 创建并填充两个 PostgreSQL/pgvector 数据库。

注意：这个入口没有调用 `abstract_pipelines()`。它默认 `pipeline_graphs_out_path` 下的 Pipeline TTL 已经提前生成。因此实施时必须把“生成 Pipeline 图”和“装载图数据库”拆成显式、可重复的独立阶段，不能继续依赖隐含前置条件。

### 3.2 数据画像

`sack/knowledge/kg_governor/data_profiling/profile_data.py` 的职责包括：

- 从 `overview.txt`、`data_description.txt` 提取竞赛描述和结构化要素；
- 生成 300 维竞赛文本嵌入；
- 读取 pre/deep EDAInsight JSON，生成 EDA Profile；
- 扫描 CSV 表和列，检测细粒度类型并生成列 Profile、列嵌入和统计量；
- 将 Profile 保存为 JSON，作为图构建和 pgvector 装载的共同上游。

这部分与 GraphDB 没有强绑定，应保持不变，只需补充规范化校验和构建批次标识。

### 3.3 全局 Schema 图构建

`build_data_global_schema.py` 和 `workers.py` 当前生成：

- `Column -> Table -> Dataset -> Source` 的 `sack:isPartOf` 层级；
- Dataset 的 overview、data description、problem type、domain、data type、difficulty；
- Table 的名称、标签、文件路径；
- Column 的数据类型、总量、去重数、缺失数、数值统计；
- Preliminary/InDepth EDAInsight 节点及约 50 个扁平字段；
- 列与列之间的 label/content similarity。

列相似关系不是普通三元组，而是 RDF-star：

```turtle
<< column_a data:hasContentSimilarity column_b >>
    data:withCertainty 0.91 .
```

`workers.py:135-143` 还会生成反向关系。因此当前图中“无向相似”实际上由两条方向相反、分值相同的关系实现。

### 3.4 Pipeline 子图构建

`pipeline_abstraction/abstract_pipelines.py` 对 Notebook 导出的 Python 文件做 AST 分析，构建：

- Pipeline 元数据；
- Statement 节点及代码文本；
- Statement 间 next、data flow、control flow；
- Statement 调用的 Function/Class/Package/Library；
- Statement 读取的 Table/Column；
- Statement 参数名与参数值；
- Pipeline 阶段标注和 CoreInsight；
- CoreInsight 与实现 Statement 的关系。

`json_to_rdf/__init__.py:134-135` 用 RDF-star 表达参数值：

```turtle
<< statement pipeline:hasParameter "sep" >>
    pipeline:withParameterValue "," .
```

每条 Pipeline TTL 被上传到以 Pipeline URI 命名的 Named Graph。`default.ttl` 保存 Pipeline 元数据，`library.ttl` 保存库层级，单 Pipeline TTL 保存 Statement、调用、数据流、参数和 CoreInsight。

### 3.5 查询和 Agent 消费链路

`sack/knowledge/api/helpers/helper.py` 通过 `SPARQLWrapper` 连接 GraphDB；`api/template.py` 约 2,000 行，包含 40 处 `query_graphdb()` 调用。查询能力主要分为：

- Dataset/Table/Column 元数据查询；
- 列相似关系、可连接/可合并表推荐、跨表路径；
- Pipeline 列表、时间/评分排序、标签聚合；
- 分类器、库调用、超参数、数据变换查询；
- 竞赛基础字段、EDAInsight、CoreInsight 和实现代码查询；
- 与 pgvector 混合的竞赛和表列相似度计算。

`sack/Agents/agent_retriever.py:37-55` 在初始化时直接创建 `SACKKnowledgeBase`，其核心运行路径依赖：

- `get_top_k_similar_competitions()`；
- `get_top_k_edainsight_similar_competitions()`；
- `get_top_k_scoring_pipelines_for_dataset()`；
- `get_core_insights_for_pipeline()`；
- `get_competition_field()`；
- `get_insight_code_snippet()`。

这些是迁移优先级最高的 P0 API。

## 4. 为什么不能直接迁移 TTL

| 差异 | 当前 GraphDB/RDF 行为 | TuGraph 目标行为 | 迁移处理 |
| --- | --- | --- | --- |
| 数据模型 | 三元组，资源可有多个 `rdf:type` | 强 Schema 标签属性图，单节点单标签 | 选定主业务标签，保留 `rdf_types` 兼容信息 |
| 关系属性 | RDF-star 给嵌套三元组加属性 | 边天然可带属性 | 相似度直接成为带 `certainty` 的边；参数改为带 `value` 的边 |
| Named Graph | Pipeline URI 是图上下文 | 一个 TuGraph 图项目内无 RDF Named Graph 语义 | 以 Pipeline 节点、`IS_PART_OF` 和 `pipeline_uid` 表示作用域 |
| Literal | RDF literal 可有 datatype/language | 属性字段类型预先声明 | 建字段目录，做明确类型转换并保留必要 raw 值 |
| 本体 | RDF/RDFS/OWL 可表达类和属性语义 | 不自动提供 RDF 推理 | 当前查询所需类型物化；未来推理单独实现 |
| 查询 | SPARQL 图模式、`GRAPH`、RDF-star | OpenCypher 路径模式 | 按领域 API 重写，禁止机械字符串翻译 |
| 导入 | Turtle/Graph Store/服务端 import | CSV/JSON + Schema 配置或 Cypher | 从规范图模型输出 TuGraph 导入包 |
| 标识 | 长 IRI 直接作为资源标识 | 主键索引键有长度限制 | `uid = sha256(uri)` 为主键，原 URI 作为普通属性 |

TuGraph 官方 Schema 文档说明它是强 Schema、单标签、带方向的属性图，并对主键/唯一索引键长度有约束。当前 Pipeline URI 由数据源、竞赛名和最长 200 字符 Pipeline ID 拼接，并可能经过百分号编码，不能假设总长度永远小于索引限制。因此所有顶点必须用固定长度的哈希主键，不能直接用完整 URI 做 TuGraph primary key。

## 5. 目标架构与组件边界

### 5.1 增加存储无关的规范图模型（CIR）

建议新增 `Canonical Intermediate Representation`，简称 CIR。它不是 RDF，也不是 Cypher，而是构建阶段的稳定数据契约：

```python
VertexRecord(
    uid: str,          # sha256(uri)，64 位十六进制
    uri: str,          # 原始 SACK IRI，完整保留
    label: str,        # TuGraph 主标签
    properties: dict,
    build_id: str,
)

EdgeRecord(
    edge_uid: str,     # sha256(edge_type + src_uid + dst_uid + discriminator)
    edge_type: str,
    src_uid: str,
    dst_uid: str,
    properties: dict,
    scope_uid: str | None,
    build_id: str,
)
```

必须先从 Profile、AST 节点、Pipeline 元数据和 CoreInsight JSON 直接生成 CIR，再由不同 Sink 输出 RDF 或 TuGraph 文件。不要把“生成 TTL 后再解析 TTL”作为长期主链路，因为：

- 当前 Turtle 是手工字符串拼接；
- RDF-star 解析库兼容性需要额外验证；
- 历史统计已经出现无效 IRI 导致 GraphDB 拒绝导入；
- TTL 解析会丢失构建阶段已有的类型信息；
- Pipeline metadata JSON 当前只保存节点数量，没有保存 `nodes` 和 `file_elements` 本体，不能单独作为完整迁移源。

历史存量可采用两条策略：

1. 推荐：修正 CIR 输出后重跑 Pipeline 图抽象，直接产出干净的 CIR/TuGraph 包；
2. 临时兜底：对已被 GraphDB 成功接收的 TTL 做一次性导出，对拒绝的 Pipeline 单独重跑。该路径只用于过渡，不成为长期代码路径。

### 5.2 增加 GraphStore 抽象

建议定义以下领域级接口，而不是一个接收任意查询字符串的薄包装：

```python
class GraphStore(Protocol):
    def healthcheck(self) -> HealthStatus: ...
    def get_datasets_info(self) -> pd.DataFrame: ...
    def get_tables_info(self, dataset: str | None) -> pd.DataFrame: ...
    def get_competition_fields(self, uid: str) -> dict: ...
    def get_competition_tables(self, uid: str) -> list[dict]: ...
    def get_top_pipelines(self, competition_uid: str, k: int | None) -> pd.DataFrame: ...
    def get_core_insights(self, pipeline_uid: str) -> pd.DataFrame: ...
    def get_insight_code(self, insight_uid: str) -> list[dict]: ...
    # 其余 API 按迁移矩阵补齐
```

实现两个后端：

- `GraphDBGraphStore`：封装当前 SPARQL 实现，作为基线和回滚通道；
- `TuGraphGraphStore`：使用参数化 Cypher；
- 可选 `ComparingGraphStore`：双读并记录差异，不把差异直接暴露给在线调用方。

`SACKKnowledgeBase` 保持为 Facade。上层 Agent 不感知底层查询语言，只根据配置获得对应的 `GraphStore`。

### 5.3 建议配置

```text
SACK_GRAPH_BACKEND=graphdb|tugraph|compare
SACK_GRAPH_READ_BACKEND=graphdb|tugraph
SACK_TUGRAPH_HTTP_URL=http://127.0.0.1:7070
SACK_TUGRAPH_BOLT_URL=bolt://127.0.0.1:7687
SACK_TUGRAPH_GRAPH=sack_kaggle_v1
SACK_TUGRAPH_USER=...
SACK_TUGRAPH_PASSWORD=...
SACK_GRAPH_BUILD_ID=...
```

密码不得写入仓库。生产环境优先选择团队已验证的 Bolt 或 RPC 接入；PoC 可先使用 REST `/cypher`，因为现有项目已经依赖 `requests`，改造最小。无论使用哪个协议，都必须统一封装认证、超时、重试、错误映射、参数化查询和指标采集。不要让业务层散落 HTTP/Bolt 调用。

## 6. TuGraph Schema 设计

### 6.1 通用标识规范

所有顶点统一包含：

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `uid` | STRING, primary | `sha256(canonical_uri).hexdigest()` |
| `uri` | STRING | 完整原始 IRI，不裁剪；业务返回仍使用它 |
| `name` | STRING, optional | 原 `schema:name` 或领域名称 |
| `display_label` | STRING, optional | 原 `rdfs:label` |
| `rdf_types_json` | STRING, optional | 多 `rdf:type` 兼容信息；JSON 数组 |
| `build_id` | STRING | 构建批次，用于审计与回滚 |
| `source_hash` | STRING, optional | 源记录哈希，用于增量和一致性验证 |

URI 规范化必须只有一个实现：统一 Unicode、URL 编码、空白和尾斜杠规则。`uid` 生成函数必须有跨平台黄金测试。不能在不同模块分别手写 URI 或哈希逻辑。

### 6.2 顶点标签

| 标签 | 主要属性 | 来源 |
| --- | --- | --- |
| `Source` | `name`, `display_label` | 全局 Schema |
| `Dataset` | `overview`, `data_description`, `problem_type`, `domain`, `data_type`, `difficulty` | Competition Profile |
| `Table` | `name`, `display_label`, `file_path` | Column Profile / Pipeline 文件引用 |
| `Column` | `name`, `data_type`, `total_count`, `distinct_count`, `missing_count`, `median`, `min_value`, `max_value`, `true_ratio` | Column Profile |
| `PreliminaryEDAInsight` | pre-EDA 映射字段，全部 optional | EDAInsight Profile |
| `InDepthEDAInsight` | deep-EDA 映射字段，全部 optional | EDAInsight Profile |
| `Pipeline` | `title`, `author`, `votes`, `written_on_raw`, `written_on_ts`, `source_url`, `score` | `pipeline_info.json` |
| `Statement` | `text`, `phase`, `ordinal`, `pipeline_uid` | AST 抽象 |
| `Library` / `Package` / `Class` / `Function` / `API` | `qualified_name`, `api_kind` | Library 树 |
| `Parameter` | `name` | Statement 参数名；全局去重 |
| `Tag` | `name`, `normalized_name` | Pipeline tags |
| `CoreInsight` | `insight_id`, `description`, `insight_type`, `effectiveness`, `evidence`, `phase` | CoreInsight JSON |
| `Phase` | `name`, `sort_order` | 固定字典 |
| `ControlFlow` | `kind` | 固定的 METHOD/LOOP/CONDITIONAL/IMPORT 资源 |
| `OntologyTerm`（可选） | `term_uri`, `term_kind` | 只有启用本体浏览/推理时才导入 |

TuGraph 单顶点单标签。对于实际出现多类型的资源，应按以下优先级选择主标签：具体业务类优先于父类，例如 `Function > API`、`Column > DataItem > DataScienceItem`。完整类型集合写入 `rdf_types_json`。当前查询依赖具体类型，不依赖父类推理，因此这个映射能保持运行语义。

### 6.3 边标签

| 边标签 | 起点 -> 终点 | 主要属性 | RDF 对应 |
| --- | --- | --- | --- |
| `IS_PART_OF` | Column->Table、Table->Dataset、Dataset->Source、Pipeline->Dataset、Statement->Pipeline、API 子项->父项 | `edge_uid`, `scope_uid` | `sack:isPartOf` |
| `HAS_CONTENT_SIMILARITY` | Column->Column | `edge_uid`, `certainty` DOUBLE | RDF-star content similarity |
| `HAS_LABEL_SIMILARITY` | Column->Column | `edge_uid`, `certainty` DOUBLE | RDF-star label similarity |
| `HAS_PRELIMINARY_EDA_INSIGHT` | Dataset->PreliminaryEDAInsight | `edge_uid` | 对应 data predicate |
| `HAS_IN_DEPTH_EDA_INSIGHT` | Dataset->InDepthEDAInsight | `edge_uid` | 对应 data predicate |
| `NEXT_STATEMENT` | Statement->Statement | `edge_uid`, `scope_uid` | `pipeline:hasNextStatement` |
| `DATA_FLOW_TO` | Statement->Statement | `edge_uid`, `scope_uid` | `pipeline:hasDataFlowTo` |
| `IN_CONTROL_FLOW` | Statement->ControlFlow | `edge_uid`, `scope_uid` | `pipeline:inControlFlow` |
| `CALLS_FUNCTION/CLASS/PACKAGE/LIBRARY/API` | Statement->对应 API 节点 | `edge_uid`, `scope_uid` | Pipeline call predicates |
| `READS_TABLE` | Statement->Table | `edge_uid`, `scope_uid` | `pipeline:readsTable` |
| `READS_COLUMN` | Statement->Column | `edge_uid`, `scope_uid` | `pipeline:readsColumn` |
| `HAS_PARAMETER` | Statement->Parameter | `edge_uid`, `value`, `value_type`, `scope_uid` | RDF-star 参数绑定 |
| `HAS_TAG` | Pipeline->Tag | `edge_uid` | `pipeline:hasTag` literal |
| `HAS_CORE_INSIGHT` | Pipeline->CoreInsight | `edge_uid`, `scope_uid` | `sack:hasCoreInsight` |
| `IMPLEMENTED_IN` | CoreInsight->Statement | `edge_uid`, `scope_uid` | `sack:implementedIn` |
| `SPANS_PHASE` | CoreInsight->Phase | `edge_uid` | `sack:spansPhase` |

### 6.4 RDF-star 映射

#### 列相似度

原 RDF-star：

```turtle
<< c1 data:hasContentSimilarity c2 >> data:withCertainty 0.91 .
```

目标属性图：

```text
(c1:Column)-[:HAS_CONTENT_SIMILARITY {
  edge_uid: sha256(...),
  certainty: 0.91
}]->(c2:Column)
```

必须保留当前正反两条边，直到所有查询都明确改为无向匹配且结果一致。不要在迁移时擅自把两条边压成一条。

#### 参数值

原 RDF-star 的对象是参数名 literal，嵌套三元组再带参数值。属性图中改为：

```text
(statement:Statement)-[:HAS_PARAMETER {
  edge_uid: sha256(...),
  value: ",",
  value_type: "string"
}]->(parameter:Parameter {name: "sep"})
```

这样能直接查询参数名和绑定值，又不会为每次绑定创建额外顶点。

### 6.5 Named Graph 映射

当前 `GRAPH ?Pipeline_id { ... }` 的真实意图是“只查询某一条 Pipeline 内部的 Statement 及其边”。在 TuGraph 中统一改为：

- Statement 通过 `IS_PART_OF` 指向 Pipeline；
- Pipeline 内部边带 `scope_uid = pipeline.uid`；
- 常用查询从 Pipeline 节点开始遍历；
- 为性能可在 Statement 上冗余 `pipeline_uid`，但 `IS_PART_OF` 仍是权威关系；
- 导入校验要求边的 `scope_uid` 与两端所属 Pipeline 一致。

例如：

```cypher
MATCH (p:Pipeline {uid: $pipeline_uid})
      <-[:IS_PART_OF]-(s:Statement)
      -[:CALLS_CLASS]->(c:Class)
RETURN s, c
```

这替代：

```sparql
GRAPH ?Pipeline_id {
  ?Statement pipeline:callsClass ?Class .
}
```

### 6.6 本体和推理

当前仓库包含本体说明文档，但主构建入口没有看到完整本体 TTL 的显式导入；当前 SPARQL 也主要查询显式 `rdf:type` 和直接谓词，没有发现依赖 `rdfs:subClassOf*` 的业务查询。因此一期不需要复刻 RDF 推理机，但必须：

1. 在 CIR 中保留原 URI、类型和谓词映射表；
2. 显式物化当前 API 使用的具体标签；
3. 用 `OntologyTerm`/`SUBCLASS_OF` 作为可选扩展，而不是把本体元数据混入业务边；
4. 若后续确认 GraphDB 仓库开启了推理规则，先导出推理前后差异，再决定离线物化闭包或增加服务层推理。

## 7. 数据类型与多值字段策略

### 7.1 类型原则

- 计数统一 `INT64`；
- 分数、比例和数值统计统一 `DOUBLE`；
- Boolean 必须是 `BOOL`，不保存字符串 `"true"/"false"`；
- 日期能可靠解析时存 `DATETIME`，同时保留 `written_on_raw`；
- 代码、描述、证据和 JSON 使用 `STRING`，不建立普通索引；
- 缺失值存 optional null，不把字符串 `"unknown"` 当作数据库空值；
- `NaN`、`INF`、`-INF` 必须在导出前按字段策略处理，不能依赖导入器隐式接受；
- pgvector 中的 300/600 维向量一期继续留在 PostgreSQL，不重复存入 TuGraph。

### 7.2 多值字段

TuGraph Schema 文档列出的基本字段类型不应被假定支持任意列表。多值业务字段按查询方式处理：

- Pipeline tags：规范化为 Tag 顶点和 `HAS_TAG` 边；
- CoreInsight spanning phases：规范化为 Phase 顶点和 `SPANS_PHASE` 边；
- RDF 多类型：低频兼容字段，JSON 字符串保存；
- EDA 分布对象：当前只在 Python 中 `json.loads`，继续保存为 JSON 字符串；
- 其他未来多值字段：只有需要图遍历/过滤时才节点化，否则使用版本化 JSON。

## 8. 查询迁移策略

### 8.1 不做通用 SPARQL 翻译

`SACKKnowledgeBase.query(rdf_query)` 是当前公开的任意 SPARQL 逃生口。TuGraph 无法无损执行它。处理方式：

1. 双运行期保留 `query_sparql()`，仅 GraphDB 后端可用；
2. 新增 `query_cypher(script, params=None)`，仅 TuGraph 后端可用；
3. 原 `query()` 标记 deprecated；GraphDB 后端暂按旧行为执行，TuGraph 后端抛出带迁移说明的明确异常；
4. 不根据字符串猜测语言，不静默翻译，不返回似是而非的结果。

### 8.2 参数化与安全

当前多处 SPARQL 用 `%`/f-string 插入 dataset、table、tag、URI 和条件。迁移时不得照搬：

- 值全部使用 Cypher 参数；
- Label、关系类型和排序字段不能参数化时，必须从固定白名单选择；
- `hops` 设置合理上限，例如 `1 <= hops <= 5`；
- 查询超时、最大结果数和分页必须在 Store 层统一控制；
- 日志记录 query name、耗时、行数、trace id，不记录密码和大段代码文本。

### 8.3 代表性查询改写

#### Dataset 与 Table 计数

```cypher
MATCH (t:Table)-[:IS_PART_OF]->(d:Dataset)
RETURN d.name AS Dataset, count(t) AS Number_of_tables
ORDER BY Dataset
```

#### 竞赛 Top-K Pipeline

```cypher
MATCH (p:Pipeline)-[:IS_PART_OF]->(d:Dataset {uid: $competition_uid})
RETURN p.uri AS Pipeline_id,
       p.title AS Pipeline,
       p.author AS Author,
       p.written_on_raw AS Written_on,
       p.votes AS Number_of_votes,
       p.score AS Score
ORDER BY p.score DESC
LIMIT $limit
```

实际落地前要验证目标 TuGraph 版本是否允许参数化 `LIMIT`；若不允许，只能对已校验的整数生成查询文本。

#### 可连接表推荐

```cypher
MATCH (d:Dataset {uid: $dataset_uid})
      <-[:IS_PART_OF]-(t1:Table)
      <-[:IS_PART_OF]-(c1:Column)
      -[sim:HAS_CONTENT_SIMILARITY]->(c2:Column)
      -[:IS_PART_OF]->(t2:Table)
      -[:IS_PART_OF]->(d2:Dataset)
WHERE t1.uid = $table_uid
RETURN t1.name AS table_name1,
       t2.name AS table_name2,
       sim.certainty AS certainty,
       d2.name AS dataset2_n,
       t2.file_path AS path
```

现有 Python `get_top_k_tables()` 会按表对累加列相似度。第一阶段保持这个口径，先让 Cypher 返回列级匹配，再复用经过修正和测试的 Python 聚合；性能不足时再下推聚合。

#### 超参数

```cypher
MATCH (p:Pipeline {uid: $pipeline_uid})
      <-[:IS_PART_OF]-(s:Statement)
      -[:CALLS_CLASS]->(classifier:Class)
MATCH (s)-[binding:HAS_PARAMETER]->(param:Parameter)
WHERE classifier.uid = $classifier_uid
RETURN param.name AS Hyperparameter, binding.value AS Value
```

#### CoreInsight 与代码片段

```cypher
MATCH (p:Pipeline {uid: $pipeline_uid})-[:HAS_CORE_INSIGHT]->(i:CoreInsight)
RETURN i.uid AS insight_uid,
       i.uri AS insight_uri,
       i.description AS description,
       i.insight_type AS insight_type,
       i.effectiveness AS effectiveness,
       i.evidence AS evidence,
       i.phase AS phase
```

```cypher
MATCH (i:CoreInsight)-[:SPANS_PHASE]->(phase:Phase)
WHERE i.uid IN $insight_uids
RETURN i.uid AS insight_uid, phase.name AS phase_name
ORDER BY i.uid ASC, phase.name ASC
```

第二条查询的结果由 Python 按 `insight_uid` 归并、去重和排序。TuGraph 4.5.2 不接受这里原先使用的多段 `MATCH`/`OPTIONAL MATCH`，且非空 `collect(DISTINCT ...)` 经 Bolt 返回字符串，不能直接当作列表。

```cypher
MATCH (i:CoreInsight {uid: $insight_uid})-[:IMPLEMENTED_IN]->(s:Statement)
RETURN s.uri AS stmt_uri, s.text AS code_text, s.ordinal AS order
ORDER BY order
```

`ordinal` 应在构建时从 `s1/s2/...` 明确生成，避免继续用查询语言正则从 URI 提取数字。

### 8.4 API 迁移优先级

| 优先级 | API/能力 | 原因 |
| --- | --- | --- |
| P0 | 候选竞赛过滤、竞赛表列、竞赛字段 | Agent 相似案例召回主链路 |
| P0 | Top Pipeline、CoreInsight、Insight 代码 | Agent 经验检索主链路 |
| P0 | EDAInsight 获取 | 阶段相似度主链路 |
| P1 | Dataset/Table 信息、图统计、表搜索 | 知识库通用 API |
| P1 | joinable/unionable 推荐、表路径 | 数据发现能力，含 RDF-star |
| P1 | Pipeline 列表、分类器、参数、库使用、标签 | Pipeline 分析能力，含 Named Graph |
| P2 | `knowledge_server.py` 的 EDA operation 服务 | 独立服务链路，含评估图复制 |
| P2 | GNN/OnDemandDataPrep 辅助脚本 | 当前主 Agent 链路之外 |
| 不兼容项 | 任意 SPARQL `query()` | 改为显式 SPARQL/Cypher 双接口 |

## 9. 构建与导入流程

### 9.1 新构建流水线

```text
Stage A  输入清点与校验
  ├─ 历史案例目录、CSV、Notebook、EDA JSON
  └─ 记录 source manifest 和 build_id

Stage B  Profile（保留现有算法）
  ├─ CompetitionProfile
  ├─ EDAInsightProfile
  └─ ColumnProfile + pgvector embeddings

Stage C  Pipeline abstraction（保留 AST/LLM 算法）
  ├─ PipelineInfo
  ├─ Statement/Call/Read/Flow/Parameter
  └─ CoreInsight

Stage D  CIR 构建
  ├─ vertices/*.jsonl
  ├─ edges/*.jsonl
  ├─ manifest.json
  └─ validation_report.json

Stage E  Sink
  ├─ RDF Sink：兼容期 TTL
  └─ TuGraph Sink：CSV/JSON + import.config

Stage F  装载
  ├─ TuGraph 新 graph project
  └─ PostgreSQL/pgvector（保持现状）

Stage G  数据与 API 校验
```

### 9.2 TuGraph 导入包

建议每个顶点标签、每个边标签一个或多个分片文件：

```text
storage/tugraph/<build_id>/
  import.config.json
  manifest.json
  vertices/
    dataset-00000.csv
    table-00000.csv
    column-00000.csv
    ...
  edges/
    is_part_of-00000.csv
    has_content_similarity-00000.csv
    ...
  reports/
    canonical_validation.json
    import_result.json
```

`manifest.json` 至少包含：

- build id、Git commit、配置摘要和生成时间；
- 每个文件的 SHA-256、行数和字节数；
- 每个标签的顶点/边数；
- skipped/rejected 记录及原因；
- URI 到 uid 规则版本；
- Schema 版本。

### 9.3 初次全量与后续增量

初次迁移：

1. 创建全新的 graph project，例如 `sack_kaggle_v1`；
2. 对中小 PoC 使用在线导入；
3. 对完整数据评估离线或 online full import；
4. `continue_on_error=false`，任何坏行都阻断该批次；
5. 校验通过后才允许切换读流量。

后续增量：

- 以 `uid/edge_uid` 做幂等 upsert；
- 记录 `build_id` 和 `source_hash`；
- 先写顶点，再写边；
- 单批失败可重放；
- 删除采用 tombstone/版本切换策略，不在首版做在线物理删除；
- Schema 变更必须增加版本和迁移脚本。

不建议延续 `replace_existing_graphdb_repo=True` 对应的“启动即删库重建”行为。TuGraph 中应创建新版本图，完成验证后切换配置，旧图保留一个回滚窗口。

## 10. PostgreSQL/pgvector 保留方案

以下逻辑一期保持不变：

- 列内容、列名、组合向量；
- 竞赛 overview 和 data description 向量；
- HNSW 索引；
- 现有相似度公式和融合权重。

仅做两项必要调整：

1. 图中的 `uri` 与 PostgreSQL 中的 `competition_id/column id` 统一通过同一个 ID codec 转换；
2. 图查询结果与向量结果 join 时使用 canonical id/uid，不在各函数中散落 `.replace("http://sack.local/resource/", "")`。

这样可以消除 `template.py` 中多处手工 URI 拼接和裁剪带来的错配风险。

## 11. 评估子图和独立服务改造

`server_utils.py`/`knowledge_server.py` 当前通过 SPARQL `CONSTRUCT`、Graph Store 下载/上传和 Named Graph 列表复制评估子图。TuGraph 不能照搬这套协议。

建议两种实现中选择一种：

### 方案 A：逻辑隔离，推荐

- 完整图只保留一份；
- 评估任务持有 Dataset/Pipeline allowlist；
- 所有查询强制带 allowlist scope；
- pgvector 通过独立测试库或 SQL scope 隔离；
- 避免为每次评估物理复制图。

### 方案 B：物理评估图

- 从 CIR 按 Dataset/Pipeline uid 选择诱导子图；
- 生成新的 TuGraph 导入包；
- 创建独立 graph project；
- 测试结束后由人工审批回收。

只有评估过程确实需要强物理隔离时才采用方案 B。不要尝试在应用层模拟 RDF Graph Store API。

## 12. 测试与一致性验证

### 12.1 先建立 GraphDB 基线

在改代码前，用固定小型数据集和完整历史数据分别记录：

- 每个公开 API 的输入、输出列、dtype、排序、空结果和异常；
- 每类顶点/边/Named Graph 数量；
- P0 查询的 p50/p95/最大耗时；
- 竞赛召回 Top-K、Pipeline Top-K、CoreInsight 集合；
- 当前已知坏数据和失败 Pipeline。

现有仓库的测试集中在 Pipeline abstraction/RDF 生成，缺少 GraphDB API 集成测试。迁移前必须补齐，否则无法定义“等价”。

### 12.2 CIR 单元校验

- `uid(uri)` 确定性、冲突检测和长 URI；
- 每个顶点恰有一个主标签；
- `src_uid/dst_uid` 必须存在；
- `certainty` 在 `[0, 1]`；
- 相似边反向对称且分值一致；
- Column 只能隶属一个权威 Table；
- Table 只能隶属一个 Dataset；
- Statement 只能隶属一个 Pipeline；
- scope 内部边不得跨 Pipeline；
- CoreInsight 的实现 Statement 必须属于同一 Pipeline；
- 计数、布尔、日期、NaN/INF 转换符合字段目录；
- `edge_uid` 唯一且重跑稳定。

### 12.3 数据层对账

按标签对比：

- 顶点总数和按类型计数；
- 边总数和按关系计数；
- Dataset/Table/Column 层级计数；
- Pipeline/Statement/CoreInsight 计数；
- 每条 Pipeline 的 Statement、Call、Read、Parameter、Insight 数；
- 列相似关系的端点和分值；
- 随机抽样属性值；
- 孤立点、悬挂边、重复边和缺失必填字段。

对多值集合比较时先排序；对浮点使用明确容差，例如 `abs(a-b) <= 1e-6`；不要直接比较数据库原始行顺序。

### 12.4 API 黄金测试

同一 fixture 同时装入 GraphDB 和 TuGraph，调用同一个领域 API：

```python
expected = normalize(graphdb_store.get_core_insights(...))
actual = normalize(tugraph_store.get_core_insights(...))
assert_frame_equal(expected, actual, check_like=True, atol=1e-6)
```

P0 API 必须 100% 通过才可进入灰度。P1 API 若因历史缺陷需要修复，必须把“旧行为”和“修正行为”分别记录在 ADR 中，不能把差异隐藏成迁移误差。

### 12.5 Agent 端到端验证

至少覆盖：

1. 当前竞赛 Profile 生成；
2. 基础相似竞赛与 EDA 相似竞赛；
3. 阶段权重融合与 Top-K；
4. 每个竞赛 Top Pipeline；
5. CoreInsight 获取和阶段预过滤；
6. Insight 对应代码片段；
7. 无结果、部分缺字段、图服务不可用和 pgvector 不可用。

验收不仅比较最终自然语言。必须比较进入 LLM 前的结构化中间结果，避免模型随机性掩盖数据差异。

### 12.6 性能门槛

先实测 GraphDB 基线，再设门槛。建议初始门槛：

- P0 查询 p95 不高于 GraphDB 基线的 1.2 倍；
- 任一 P0 查询不高于基线 2 倍；
- Top-K 结果和排序语义完全一致；
- 完整导入无 reject，重复全量构建结果哈希一致；
- 常规查询不得退化为全图扫描，关键 `uid`、外键冗余字段和常用过滤字段有执行计划证据；
- 服务连接失败应快速失败或按策略降级，不得无限重试。

## 13. 灰度、切换与回滚

### 13.1 阶段化发布

1. **Shadow build**：GraphDB 仍是唯一在线读源，后台生成并装载 TuGraph；
2. **Dual read compare**：在线请求仍返回 GraphDB 结果，同时异步调用 TuGraph 并记录结构化 diff；
3. **P0 灰度**：少量内部任务从 TuGraph 返回，失败自动回退 GraphDB；
4. **P1 灰度**：逐类启用通用 API；
5. **默认切换**：TuGraph 成为默认读源，GraphDB 保持可回滚；
6. **观察期**：至少覆盖一个完整知识构建和 Agent 使用周期；
7. **退役评审**：确认无 SPARQL 逃生口、无 GraphDB REST 调用后，才决定 GraphDB 下线。

### 13.2 回滚开关

回滚只需要修改：

```text
SACK_GRAPH_READ_BACKEND=graphdb
```

前提是过渡期：

- GraphDB 数据继续构建或同步；
- API Facade 不改签名；
- pgvector 未迁移；
- 不删除 TTL、GraphDB 仓库和旧 graph project；
- 每个 build id 都可定位到源码和导入包。

## 14. 分阶段实施计划与工作量

以下为单名熟悉 Python/图数据库工程师的粗略人日，实际取决于 TuGraph 部署、历史数据可用性和 Cypher 兼容性。

| 阶段 | 工作 | 产物 | 预计人日 |
| --- | --- | --- | ---: |
| M0 基线冻结 | API/数据/性能清点，构造 fixture | baseline manifest、黄金输出 | 3-5 |
| M1 语义设计 | CIR、ID codec、Schema、ADR | schema v1、mapping registry | 3-5 |
| M2 构建改造 | 全局 Schema/Pipeline 输出 CIR，保留 RDF sink | CIR 构建器、校验器 | 5-8 |
| M3 导出导入 | TuGraph import config、分片、manifest、装载 | 可重复全量导入 | 4-7 |
| M4 P0 查询 | GraphStore、TuGraph client、Agent 主链路查询 | P0 双后端与黄金测试 | 7-10 |
| M5 P1/P2 查询 | 通用 API、评估子图、服务改造 | 完整功能覆盖 | 6-10 |
| M6 灰度和优化 | 双读 diff、索引、执行计划、故障演练 | 切换报告、回滚演练 | 5-8 |

合计约 33-53 人日。若只完成 Agent P0 主链路且暂不迁移 legacy `knowledge_server.py` 和可视化 API，可缩小到约 22-35 人日。

## 15. 主要风险与控制措施

| 风险 | 影响 | 控制措施 |
| --- | --- | --- |
| 长 URI 超过索引键限制 | 顶点无法导入或错误去重 | 固定长度 uid 主键；原 URI 不作主键 |
| RDF-star 语义丢失 | 推荐分值或参数值错误 | 明确映射为边属性；做逐边黄金测试 |
| Named Graph 作用域丢失 | Pipeline 调用串图 | Statement->Pipeline + scope_uid 双重约束 |
| 单标签限制 | 多类型资源信息丢失 | 主标签规则 + `rdf_types_json` |
| Literal 类型改变 | 排序、聚合、空值行为变化 | 字段目录、raw 字段、DataFrame 契约测试 |
| SPARQL/Cypher 特性差异 | 查询不可执行或结果不同 | 每类查询做兼容性 spike；不做自动翻译 |
| 历史 TTL 有无效 IRI | 存量漏数 | 从 Profile/AST 重建 CIR；reject=0 才验收 |
| 当前 Pipeline metadata 不完整 | 不能仅靠 JSON 迁移 | 修改构建器保存 CIR；存量重跑或 GraphDB 导出 |
| 动态查询注入 | 安全问题 | 参数化值，label/relation 白名单 |
| 强 Schema 演进成本 | 新 EDA 字段导入失败 | Schema version + preflight + 新图版本切换 |
| 双库长期漂移 | 切换时结果不一致 | build_id、manifest、双读 diff、停止条件 |
| HA/协议版本差异 | 写入或复制行为不一致 | 固定版本；单机验证后再做 HA；演练导入和故障 |

## 16. 必须先修正或基线化的现有问题

这些问题不一定都是迁移引入的，但会影响等价性判断：

1. `build_knowledge.py` 未显式生成 Pipeline 图，流程有隐含前置条件；
2. Pipeline metadata 声称保存完整元数据，但实际仅保存 `nodes_count/file_elements_count`，没有保存内容；
3. 历史报告显示 669 个 Pipeline TTL 上传时至少 9 个因无效 IRI 被拒绝；
4. `template.py` 同时存在返回 DataFrame、SPARQL JSON binding 和直接索引 `results` 的不同假设，需要统一契约；
5. 多处查询通过字符串拼接用户/业务输入；
6. GraphDB 和 PostgreSQL 连接信息存在硬编码默认值；
7. `knowledge_server.py` 导入模块时执行 `initialize_autoeda()`，会产生隐式外部依赖；
8. 部分方法未实现或命名/参数已演进，例如 `get_most_popular_parameters()` 为 `pass`，迁移范围需明确；
9. 查询中对 URI 的拼接、去前缀和 Pipeline/Dataset 参数命名不一致，必须由 ID codec 收口；
10. 缺少知识 API 的自动化集成测试。

这些问题应先通过基线测试记录；若要顺便修复，必须单独提交并标明行为变更，不能与数据库迁移混在一个不可审阅的大提交中。

## 17. 建议代码布局

以下均为拟新增或重构路径，不代表当前已经存在：

```text
sack/knowledge/
  graph/
    model.py                  # VertexRecord / EdgeRecord / manifest
    id_codec.py               # URI 规范化、uid/edge_uid
    schema_registry.py        # 唯一 Schema/字段/关系映射来源
    validation.py             # CIR 完整性校验
    builders/
      global_schema.py        # Profile -> CIR
      pipeline.py             # AST/Pipeline/CoreInsight -> CIR
    sinks/
      rdf_sink.py             # 兼容期保留
      tugraph_sink.py         # CSV/JSON/import.config
  stores/
    base.py                   # GraphStore Protocol
    graphdb.py                # 旧 SPARQL 包装
    tugraph.py                # Cypher 实现
    comparing.py              # 双读 diff
  clients/
    tugraph_client.py         # REST/Bolt/RPC 单一封装
  migration/
    build_tugraph_package.py
    load_tugraph_package.py
    compare_backends.py
tests/
  knowledge/
    fixtures/
    test_id_codec.py
    test_canonical_graph.py
    test_tugraph_export.py
    test_graph_store_contract.py
    test_backend_parity.py
```

原 `api/template.py` 中的查询应逐步搬入两个 Store，不应继续扩展为同时拼 SPARQL 和 Cypher 的巨型文件。

## 18. 交付物与验收标准

### 18.1 交付物

- Schema/关系/字段映射注册表及 ADR；
- CIR 模型、构建器、校验器；
- GraphDB RDF sink 和 TuGraph sink；
- 可重复的 TuGraph 全量导入包和命令；
- GraphStore 双后端；
- P0/P1 API Cypher 实现；
- 数据对账、API diff 和性能报告；
- 灰度开关、监控指标、回滚手册；
- 已知差异和暂缓项清单。

### 18.2 上线门槛

只有同时满足以下条件才允许 TuGraph 成为默认读源：

- TuGraph 全量导入 reject 数为 0；
- CIR 结构完整性校验 100% 通过；
- P0 API 黄金测试 100% 通过；
- Agent 结构化中间结果一致；
- Top-K 集合和排序满足既定严格口径；
- 性能达到第 12.6 节门槛；
- 故障和回滚演练通过；
- 不再有 P0 路径直连 `SPARQLWrapper` 或 GraphDB REST URL；
- 生产凭据未进入代码、日志或导入包；
- 项目负责人、知识图谱负责人和测试负责人共同签字确认。

## 19. 实施时应验证的 TuGraph 官方资料

- [TuGraph Schema 与数据模型](https://github.com/TuGraph-family/tugraph-db/blob/master/docs/en-US/source/2.introduction/4.schema.md)
- [TuGraph 数据导入](https://github.com/TuGraph-family/tugraph-db/blob/master/docs/en-US/source/6.utility-tools/1.data-import.md)
- [TuGraph Cypher](https://github.com/TuGraph-family/tugraph-db/blob/master/docs/en-US/source/8.query/1.cypher.md)
- [TuGraph 4.5.2 Bolt Client](https://github.com/TuGraph-family/tugraph-db/blob/v4.5.2/docs/en-US/source/7.client-tools/5.bolt-client.md)
- [TuGraph 4.5.2 REST API](https://github.com/TuGraph-family/tugraph-db/blob/v4.5.2/docs/en-US/source/7.client-tools/7.restful-api.md)
- [TuGraph 4.5.2 发布页](https://github.com/TuGraph-family/tugraph-db/releases/tag/v4.5.2)

官方文档也提示 Bolt 并非支持 Neo4j 的全部高级行为。因此协议、事务、参数化、`LIMIT`、正则、可变长路径、`collect`、`OPTIONAL MATCH`、边 upsert 和 HA 写入行为都必须在最终固定版本上做自动化兼容性测试，不能只依据“支持 OpenCypher/Bolt”这一概括性描述作假设。

## 20. 当前已落地基线与服务器验证流程（2026-09-25）

部署配置更新（2026-09-28）：按用户明确要求，主实例 `7070/7687` 与冒烟实例 `17070/17688` 均改为绑定所有网卡，不限定来源 IP；管理员密码改为用户指定的固定测试密码，之后不得自动轮换。密码值不写入本文或仓库，服务器凭据文件仍保持 0600 权限。两个原 loopback 容器已停止、取消自动重启并以 `*-loopback-backup-20260928` 名称保留，不能与新容器同时启动（它们共享数据库目录）。下文 loopback 与随机密码描述是 9 月 25 日的历史部署记录，不再代表当前配置。当前配置仅用于测试；公网弱密码风险已告知用户。

当前已经实现、但尚未在生产环境切流的部分如下：

- `graph/model.py`、`id_codec.py`、`schema_registry.py`、`validation.py`：CIR、稳定标识、强 Schema 和整图校验；
- `graph/builders/global_schema.py`、`graph/builders/pipeline.py`：Profile 与无损 Pipeline metadata v2 到 CIR；
- `graph/package_writer.py`、`package_reader.py`、`merge.py`：不可覆盖的确定性包、checksum 校验和多来源合并；
- `graph/sinks/tugraph.py`：固定面向 TuGraph 4.5.2 的 JSON-line/import config 导出；
- `migration/build_profile_cir.py`、`build_pipeline_cir.py`、`merge_cir_packages.py`、`export_tugraph.py`：可独立重放的构建流水线；
- `migration/load_tugraph.py`：服务器离线装载器，默认禁止覆盖、禁止 `continue_on_error`，并记录结果与日志；
- `migration/load_tugraph_docker.py`：Docker 离线装载器，固定镜像摘要和本地 Docker context，复制包到可写工作副本，仅写全新目录；支持只读 dry-run、资源限制、完整日志及超时后仅停止本次导入容器；
- `migration/build_tugraph_smoke_fixture.py`：覆盖 P0、中文、换行、空字符串和作用域的固定服务器冒烟包；
- `migration/build_similarity_cir.py`：从现有全局 Schema TTL 严格提取 RDF-star 相似边与分值，并核验反向边；
- `migration/validate_tugraph.py`：按不可变导入包对账线上标签、关系、端点和作用域；
- `migration/check_tugraph_compatibility.py`：只读验证 P0 查询依赖的 Bolt/Cypher 子集；
- `migration/verify_tugraph_smoke_fixture.py`：从领域层验证十三项 P0 查询及 RDF-star 相似边返回契约；
- `clients/tugraph_bolt.py`、`stores/tugraph.py`、`stores/factory.py`：参数化 Bolt Client、P0 领域查询和默认关闭的后端开关。

当前 Mac 开发机为 ARM64，且没有 `lgraph_import`/Docker；因此它只承担构建与静态校验。真实导入和 Cypher 兼容性测试在 Linux 服务器执行。服务器安装前先记录 `uname -m`、发行版、TuGraph 包/镜像来源和摘要；官方 4.5.2 release 的预编译 deb/rpm 是 x86_64，若服务器不是 x86_64，必须另行确认官方镜像架构或采用可复现源码构建，不能直接套用预编译包。

截至 2026-09-25，本工作区配置指向的 `storage/profiles/kaggle_profiles`、`storage/pipeline_graphs/kaggle_pipeline_graphs` 和 `storage/knowledge_graph/data_global_schema/kaggle_data_global_schema_graph.ttl` 均不存在，因此尚未生成真实全量包。TuGraph 4.5.2 已在 Ubuntu 22.04 x86_64 服务器以独立 Docker 容器 `sack-tugraph-452` 部署；镜像摘要为 `sha256:b1b0ecc39a580a7cbdac7b4b7ce35f6a92f0981254d314bc1c0a50ca71d4df0d`，HTTP/Bolt 只绑定服务器 `127.0.0.1`，数据和日志分别持久化在 `/opt/sack-tugraph-452/data` 和 `/opt/sack-tugraph-452/log`。初始管理员密码已轮换，随机凭据仅保存在服务器 root 可读的 `/opt/sack-tugraph-452/admin.password`；不得放入仓库。

固定 16 顶点/24 边冒烟包已通过同版本一次性 Docker 容器离线导入，运行在第二个独立容器 `sack-tugraph-smoke-452` 和图 `sack_smoke_20260925`；该容器只绑定服务器本机 `17070/17688`，随机管理员密码保存在 root 可读的 `/opt/sack-tugraph-smoke-20260925/admin.password`。导入返回码 0，导入后对账、七项 Bolt/Cypher 兼容性探针、十三项领域查询验收全部通过；本地迁移测试 113 项通过。两次失败的试验数据库目录保留在 `/opt/sack-tugraph-smoke-20260925/db` 和 `db-retry1`，未覆盖或清理。**尚未完成真实数据导入、GraphDB/TuGraph parity 或 Agent 双读，不能切流。**

实测 TuGraph 4.5.2 与 Neo4j 驱动的差异必须保留在实现约束中：`$limit` 会被解析为关键字，统一使用 `$row_limit`；多个 `MATCH`/`OPTIONAL MATCH` 子句的组合不被当前服务器接受，CoreInsight 与 Phase 需分成两条查询；非空 `collect(DISTINCT ...)` 经 Bolt 返回字符串而不是 Python 列表，因此阶段查询必须逐行返回，由 Store 在 Python 中去重排序。空测试图上的 `count(n)` 曾返回 `capacity cannot be 0`，计数型对账应在完整导入后再次实测，不可仅凭空图结果判定。

当前 `migration/load_tugraph.py` 调用宿主机原生 `lgraph_import`。服务器使用的是 Docker 镜像，**不能直接照抄下方原生装载命令**；应使用 `migration/load_tugraph_docker.py`，具体参数见 [Docker 装载操作手册](Docker_import_runbook.md)。原始包只读保存，工具复制成可写工作副本（导入器会在工作目录生成 `.import_tmp`），再用同版本一次性容器运行 `lgraph_import` 到全新目录；启动服务是独立步骤。离线导入器不接受边属性 `edge_uid` 的物理唯一索引，导出器已取消该声明；边 ID 唯一性仍由 CIR 校验保证。正式验收仍须确认 reject=0、导入后对账，不得仅凭返回码切流。

装载工具更新（2026-09-28）：Docker 装载器已完成，本地知识图谱测试 129 项通过（其中 Docker 装载器 16 项）。服务器 dry-run 无写入，固定 16 顶点/24 边包实际导入返回码 0，记录在 `/opt/sack-tugraph-loader-20260928/results/import_result.json`；本次未启动新服务，也未改变既有密码与端口。当前工作区及相邻项目目录仍未找到真实三来源数据，因此下一关卡是确认源文件位置与批次，之后才做真实导入、parity 和 Agent 双读。

推荐执行顺序：

```bash
# 0. 开发机：先生成覆盖 P0、RDF-star 双向边、中文、换行、空字符串和作用域的冒烟包
python -m sack.knowledge.migration.build_tugraph_smoke_fixture \
  --output-dir <smoke-package>

# 冒烟包应先按下面第 3-7 步导入独立 smoke graph；全部通过后才处理真实包。

# 1. 开发机：分别构建并合并真实 CIR
python -m sack.knowledge.migration.build_profile_cir \
  --profiles-dir <profiles-dir> --output-dir <profile-cir> --build-id <build-id>
python -m sack.knowledge.migration.build_pipeline_cir \
  --pipeline-graphs-dir <pipeline-graphs-dir> --output-dir <pipeline-cir> --build-id <build-id>
python -m sack.knowledge.migration.build_similarity_cir \
  --global-schema-ttl <data-global-schema.ttl> \
  --profile-package <profile-cir> --output-dir <similarity-cir>
python -m sack.knowledge.migration.merge_cir_packages \
  --input-dir <profile-cir> --input-dir <similarity-cir> \
  --input-dir <pipeline-cir> --output-dir <full-cir>

# 2. 开发机：生成带 manifest 和 preflight 报告的 TuGraph 包
python -m sack.knowledge.migration.export_tugraph \
  --canonical-package <full-cir> --output-dir <tugraph-package>

# 3. 将整个 tugraph-package 目录原样传到服务器，先 dry-run
python -m sack.knowledge.migration.load_tugraph \
  --package-dir <server-package> --database-dir <new-db-dir> \
  --result-dir <new-result-dir> --graph sack_poc \
  --installed-version 4.5.2 --dry-run

# 4. 人工检查命令和目标目录后，去掉 --dry-run 执行首次装载
python -m sack.knowledge.migration.load_tugraph \
  --package-dir <server-package> --database-dir <new-db-dir> \
  --result-dir <new-result-dir> --graph sack_poc \
  --installed-version 4.5.2

# 5. 启动 TuGraph 服务后，使用只读 Bolt 账号执行导入后对账
export SACK_TUGRAPH_BOLT_URL=bolt://<server>:7687
export SACK_TUGRAPH_GRAPH=sack_poc
export SACK_TUGRAPH_USER=<read-only-user>
export SACK_TUGRAPH_PASSWORD=<read-from-secret-store>
python -m sack.knowledge.migration.validate_tugraph \
  --package-dir <server-package> --result-dir <new-validation-result-dir>

# 6. 对当前运行实例执行只读 Cypher 兼容性探针
python -m sack.knowledge.migration.check_tugraph_compatibility \
  --result-dir <new-compatibility-result-dir>

# 7. 仅当当前图是上述固定冒烟包时，验证十三项领域查询契约
python -m sack.knowledge.migration.verify_tugraph_smoke_fixture \
  --result-dir <new-smoke-verification-result-dir>
```

首次联调必须使用全新的 `database-dir` 和 `graph`；不得传 `--overwrite`。真实数据的 `data-global-schema.ttl` 必须来自本次对应的 GraphDB 构建批次；不能把不同批次的 Profile 与 TTL 混合。`build_similarity_cir` 遇到无法解析的 RDF-star、未知 Column、缺失反向边或反向分数不一致会失败；零条相似边也需要明确传 `--allow-empty`。生产导出器只接受 Profile、Similarity、Pipeline 三个范围完整合并的 CIR；`--allow-partial` 只用于明确的测试夹具。`validate_tugraph` 会对账顶点标签、关系标签、边端点组合、`scope_uid` 存在性及 Statement 作用域，结果写入 `post_import_validation.json`。`check_tugraph_compatibility` 不写图数据，验证 Bolt 往返、普通参数、中文/换行、参数化 `LIMIT`、标签属性匹配、Pipeline→Insight 路径、Phase 逐行投影和关系属性过滤，结果写入 `compatibility_report.json`。`verify_tugraph_smoke_fixture` 再从领域层验证十三项查询契约，包括 EDA 字段投影和 RDF-star 相似边双向分值，结果写入 `smoke_verification_report.json`。三个报告通过仍不等于真实数据 API parity；真实 P0 结构化输出还必须与 GraphDB 基线逐项比较。

Agent 已支持在不修改 `agent_retriever.py` 的情况下从环境构建 TuGraph GraphStore：

```bash
export SACK_GRAPH_BACKEND=tugraph
# 或只对 Agent P0 路径明确设置：SACK_AGENT_GRAPH_BACKEND=tugraph
export SACK_TUGRAPH_BOLT_URL=bolt://<server>:7687
export SACK_TUGRAPH_GRAPH=sack_poc
export SACK_TUGRAPH_USER=<reader>
export SACK_TUGRAPH_PASSWORD=<secret>
```

默认值仍是 `graphdb`。目前 TuGraph Store 只接管 Agent P0 已迁移领域操作；其他历史 `SACKKnowledgeBase` API 仍是 GraphDB 回退，不得将此阶段宣称为全量切换。
