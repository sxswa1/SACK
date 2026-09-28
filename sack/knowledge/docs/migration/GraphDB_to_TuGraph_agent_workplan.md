# GraphDB → TuGraph 改造智能体工作大纲

> 使用对象：负责实际改造代码的智能体或工程代理
> 本文件是执行约束，不替代技术方案。开始工作前必须完整阅读同目录的 `GraphDB_to_TuGraph_technical_plan.md`。
> 核心目标：在不改变 SACK 领域算法和 Agent 业务语义的前提下，引入 TuGraph 后端，完成可验证、可灰度、可回滚的迁移。

## 0. 不可偏离的总原则

1. **不要做大爆炸替换。** GraphDB 后端必须在迁移和观察期继续可用。
2. **不要把 TTL 解析作为长期主链路。** 新主链路从 Profile、AST/Pipeline 对象和 CoreInsight JSON 直接生成规范图记录。
3. **不要迁移 pgvector。** 一期继续使用 PostgreSQL/pgvector，保持向量算法、索引和融合权重不变。
4. **不要编写通用 SPARQL-to-Cypher 翻译器。** 按领域 API 分别实现 GraphDB 和 TuGraph 查询。
5. **不要改变公开返回契约。** DataFrame 列名、dtype、排序、空结果和异常必须先有黄金测试，再做实现。
6. **不要用完整 URI 作为 TuGraph 主键。** 统一使用 `sha256(canonical_uri)`；完整 URI 作为普通属性保留。
7. **不要丢失 RDF-star 语义。** 列相似度与参数绑定必须映射到带属性的边。
8. **不要丢失 Named Graph 作用域。** Pipeline 内部顶点/边必须能由 Pipeline 节点和 `scope_uid` 唯一界定。
9. **不要依赖未验证的 TuGraph/Neo4j 兼容性。** 所用 Cypher、Bolt、事务和 upsert 特性都要在固定版本上跑兼容测试。
10. **不要执行破坏性在线操作。** 不删除 GraphDB 仓库，不覆盖生产 TuGraph 图，不清理历史 TTL/JSON，不提交凭据。
11. **不要把已有缺陷静默包装成迁移差异。** 发现旧行为有问题时，先记录基线和 ADR，再决定是否单独修复。
12. **每个里程碑必须可独立回退。** 没有测试、manifest、验证报告和回滚路径，不得宣布完成。

## 1. 开工前阅读顺序

按顺序阅读，不能只搜索关键字后直接改代码：

1. `sack/knowledge/docs/migration/GraphDB_to_TuGraph_technical_plan.md`
2. `sack/knowledge/build_knowledge.py`
3. `sack/knowledge/knowledge_config.py`
4. `sack/knowledge/storage_utils/graphdb_utils.py`
5. `sack/knowledge/storage_utils/embedding_store_utils.py`
6. `sack/knowledge/kg_governor/data_profiling/profile_data.py`
7. `sack/knowledge/kg_governor/data_global_schema_builder/build_data_global_schema.py`
8. `sack/knowledge/kg_governor/data_global_schema_builder/workers.py`
9. `sack/knowledge/kg_governor/data_global_schema_builder/utils/utils.py`
10. `sack/knowledge/kg_governor/pipeline_abstraction/abstract_pipelines.py`
11. `sack/knowledge/kg_governor/pipeline_abstraction/datatypes.py`
12. `sack/knowledge/kg_governor/pipeline_abstraction/json_to_rdf/__init__.py`
13. `sack/knowledge/api/helpers/helper.py`
14. `sack/knowledge/api/template.py`
15. `sack/knowledge/api/api.py`
16. `sack/Agents/agent_retriever.py`
17. `sack/knowledge/server_utils.py`
18. `sack/knowledge/knowledge_server.py`
19. `reports/sack_kb_build_time_summary.md`
20. 现有 Pipeline abstraction 测试目录。

阅读后先输出一份简短审计记录，至少包含：

- 当前 Git commit、工作树状态和 Python 环境；
- 可用的历史数据、Profile、TTL、metadata、CoreInsight 数量；
- GraphDB、PostgreSQL、TuGraph 是否可连接；
- 当前失败/缺失数据；
- 即将处理的里程碑和明确不处理的范围。

如果没有完整历史数据或服务，也可以做 fixture 和单元测试，但必须把未做的集成验证标为 blocked，不得声称迁移完成。

## 2. 权威语义与不变量

### 2.1 身份不变量

```text
canonical_uri = normalize(original_sack_uri)
uid = sha256(canonical_uri UTF-8).hexdigest()
edge_uid = sha256(edge_type + NUL + src_uid + NUL + dst_uid + NUL + discriminator).hexdigest()
```

要求：

- URI 规范化只能有一个公共实现；
- 相同输入跨进程、跨平台、跨批次得到相同 uid；
- 不使用 Python `hash()`；
- 不使用 CRC32 作为数据库权威 ID；
- 原始 URI 完整保留并原样返回给调用方；
- 任何哈希冲突都视为构建失败，不能自动覆盖。

### 2.2 图结构不变量

- 一个 VertexRecord 只有一个 TuGraph 主标签；
- Column 恰好有一个权威 Table；
- Table 恰好有一个 Dataset；
- Dataset 恰好有一个 Source；
- Pipeline 恰好有一个 Dataset；
- Statement 恰好有一个 Pipeline；
- CoreInsight 恰好有一个 Pipeline；
- `IMPLEMENTED_IN` 的 Statement 与 CoreInsight 必须属于同一 Pipeline；
- Pipeline 内部边 `scope_uid` 必须等于该 Pipeline uid；
- 相似度边 `certainty` 在 `[0, 1]`；
- 当前语义下，每条相似边必须有同类型、同分值的反向边；
- 顶点先于边装载，所有边端点必须存在；
- 每次构建都有 `schema_version` 和 `build_id`。

### 2.3 API 不变量

- P0 API 返回字段名不变；
- 排序规则显式，不依赖数据库默认顺序；
- 数值类型和空结果行为与基线一致；
- Top-K 的 K、并列分数和归一化规则不变；
- pgvector 相似度和融合权重不变；
- Agent Gate 输入结构不变；
- 连接失败必须返回明确错误或按配置回退，不能返回伪造空结果。

## 3. 明确的目标代码结构

优先按以下结构实施。若仓库约定要求调整路径，可以调整，但职责边界不能合并回巨型 `template.py`：

```text
sack/knowledge/
  graph/
    __init__.py
    model.py
    id_codec.py
    schema_registry.py
    validation.py
    builders/
      __init__.py
      global_schema.py
      pipeline.py
    sinks/
      __init__.py
      rdf_sink.py
      tugraph_sink.py
  stores/
    __init__.py
    base.py
    graphdb.py
    tugraph.py
    comparing.py
  clients/
    __init__.py
    tugraph_client.py
  migration/
    build_tugraph_package.py
    load_tugraph_package.py
    compare_backends.py
tests/knowledge/
  fixtures/
  test_id_codec.py
  test_canonical_graph.py
  test_tugraph_export.py
  test_graph_store_contract.py
  test_backend_parity.py
```

`api/api.py` 继续作为用户 Facade。`api/template.py` 的旧函数逐步委托给 `GraphDBGraphStore`，不能一开始就删除，以降低回归面。

## 4. 里程碑 M0：冻结基线

### 4.1 目标

定义“迁移等价”的可执行标准。在没有基线前禁止写 TuGraph 业务查询。

### 4.2 任务

- [ ] 清点历史案例、Profile、Pipeline TTL、metadata 和 CoreInsight JSON；
- [ ] 记录 GraphDB 仓库配置和是否启用推理；
- [ ] 选一个最小 fixture，必须覆盖：Dataset/Table/Column、两类相似度、Pipeline、Statement、API call、参数、CoreInsight、EDAInsight；
- [ ] 选一个真实小型历史案例作为集成样本；
- [ ] 为 P0 API 保存规范化黄金输出；
- [ ] 为 P1 API 建立方法清单和当前状态；
- [ ] 记录每类实体/关系数量；
- [ ] 记录 P0 查询性能；
- [ ] 记录现有异常、空结果和历史坏 TTL；
- [ ] 给所有基线文件写 manifest 和 checksum。

### 4.3 P0 黄金输出

- [ ] `filter_candidate_competitions`
- [ ] `get_competition_tables`
- [ ] `get_top_k_similar_competitions`
- [ ] `get_edainsight_for_competitions`
- [ ] `get_top_k_edainsight_similar_competitions`
- [ ] `get_top_k_scoring_pipelines_for_dataset`
- [ ] `get_core_insights_for_pipeline`
- [ ] `get_competition_field`
- [ ] `get_insight_code_snippet`
- [ ] `SACKCaseRetriever.retrieve_similar_competitions`
- [ ] `SACKCaseRetriever.retrieve_core_insights`
- [ ] 阶段预过滤和 Gate 前的结构化输入。

### 4.4 完成定义

- 黄金输出可由自动化测试读取；
- 无服务时测试会明确 skip，而不是吞异常；
- 基线报告区分“预期行为”和“已知缺陷”；
- 工作树未混入大规模实现改动。

## 5. 里程碑 M1：ID Codec、Schema Registry 与 CIR

### 5.1 先实现 ID Codec

- [ ] `normalize_uri()`；
- [ ] `vertex_uid()`；
- [ ] `edge_uid()`；
- [ ] `resource_id_to_uri()` / `uri_to_resource_id()`；
- [ ] 超长 URI、中文、空格、`+`、`%`、斜杠、换行测试；
- [ ] 与现有 `create_*_uri()` 结果的兼容测试；
- [ ] 禁止业务代码继续手写 URI 前缀裁剪。

不要擅自改变现有 URI 格式。先规范化“同一逻辑资源必须生成同一现有 URI”，再哈希。

### 5.2 Schema Registry

Schema Registry 是唯一字段来源，至少描述：

```python
VertexSchema(
    label="Column",
    primary="uid",
    properties={...},
    required={...},
    indexes={...},
)

EdgeSchema(
    label="HAS_CONTENT_SIMILARITY",
    src_labels={"Column"},
    dst_labels={"Column"},
    properties={...},
    uniqueness="pair",
)
```

要求：

- [ ] 生成器、校验器和 TuGraph import config 都从 Registry 读取；
- [ ] 不在多个文件重复维护 EDA 字段类型；
- [ ] 对 optional/required、默认值、索引和端点约束有明确声明；
- [ ] Schema 有版本号；
- [ ] Registry 变更触发快照测试。

### 5.3 CIR 模型

- [ ] `VertexRecord` 和 `EdgeRecord` 使用 dataclass/Pydantic 等显式模型；
- [ ] 构造时做字段、类型和空值校验；
- [ ] 输出 JSONL 时字段顺序稳定；
- [ ] 支持分片流式写入，不能把完整大图全部放入内存；
- [ ] manifest 记录文件哈希、行数、标签计数、构建配置；
- [ ] 对重复顶点采用确定性的 merge 规则；
- [ ] 属性冲突默认报错，不能 last-write-wins 静默覆盖。

### 5.4 完成定义

- ID、Registry、CIR 单元测试全部通过；
- fixture 可生成稳定、可重复的 CIR；
- 连续两次构建文件哈希一致；
- 尚未改变生产 GraphDB 行为。

## 6. 里程碑 M2：构建链路改造

### 6.1 全局 Schema Builder

从以下 Profile 直接生成 CIR：

- CompetitionProfile；
- EDAInsightProfile；
- ColumnProfile。

逐项完成：

- [ ] Source/Dataset/Table/Column 顶点；
- [ ] 两类 EDAInsight 顶点；
- [ ] 层级 `IS_PART_OF` 边；
- [ ] Dataset->EDAInsight 边；
- [ ] Column 的 typed properties；
- [ ] label/content similarity 边和 `certainty`；
- [ ] 反向相似边；
- [ ] NaN/INF/null 策略；
- [ ] 现有 RDF sink 由 CIR 生成或与 CIR 并行对账。

不要先生成 `Triplet` 字符串再反向解析。可以暂时保留旧 `Triplet` 路径做对账，但 CIR 必须从原始对象生成。

### 6.2 Pipeline Builder

直接使用 `nodes`、`file_elements`、`pipeline_info`、`graph.libraries` 和 `analysis_result` 生成 CIR：

- [ ] Pipeline 顶点及 Dataset 归属；
- [ ] Statement 顶点、ordinal 和 Pipeline 归属；
- [ ] NEXT/DATA_FLOW/CONTROL_FLOW；
- [ ] API 层级顶点；
- [ ] CALLS_*；
- [ ] READS_TABLE/READS_COLUMN；
- [ ] Parameter 顶点和带 value 的 HAS_PARAMETER 边；
- [ ] Tag 顶点和 HAS_TAG；
- [ ] CoreInsight、HAS_CORE_INSIGHT、IMPLEMENTED_IN；
- [ ] Phase/SPANS_PHASE；
- [ ] 所有 Pipeline 内部边的 scope_uid。

同时修正 metadata 输出，使它真正保存或引用完整的规范记录。不能只保存节点数量。

### 6.3 构建入口

将构建步骤显式化，例如：

```text
profile
abstract-pipelines
build-canonical-graph
export-graphdb
export-tugraph
load-graphdb
load-tugraph
populate-embeddings
validate
```

要求：

- [ ] 每个阶段可单独执行和恢复；
- [ ] 输入/输出路径由配置给出；
- [ ] 跳过阶段必须在日志和 manifest 可见；
- [ ] `build-knowledge` 组合命令不能再假设 Pipeline TTL 已经存在；
- [ ] 不默认删除数据库；
- [ ] dry-run 能完成校验但不连接外部服务。

### 6.4 完成定义

- fixture 的 RDF 和 CIR 语义对账通过；
- 真实小案例构建无悬挂边；
- Pipeline 参数、作用域和 CoreInsight 手工抽样正确；
- 现有 RDF 单测仍通过，或差异有明确 ADR。

## 7. 里程碑 M3：TuGraph 导出和装载

### 7.1 导出器

- [ ] 按标签生成顶点分片；
- [ ] 按关系生成边分片；
- [ ] 正确 CSV/JSON 转义换行、引号、分隔符和 Unicode；
- [ ] 生成 `import.config`；
- [ ] Schema 来自 Registry；
- [ ] 文件顺序、字段顺序和分片规则稳定；
- [ ] manifest 记录 checksum、count、bytes；
- [ ] 生成 preflight 报告；
- [ ] 任一校验失败不生成“成功”标志。

### 7.2 索引原则

必须有：

- 每个顶点标签的 `uid` primary；
- 常用精确过滤字段的必要索引；
- Statement `pipeline_uid` 索引（若查询计划证明确有必要）；
- 关系 `edge_uid`/pair uniqueness 的明确策略。

禁止：

- 对 overview、data_description、代码文本建普通索引；
- 用完整 URI 做 primary；
- 未经执行计划验证就批量加索引；
- 依赖非唯一长字符串索引提供精确唯一性。

### 7.3 Loader

- [ ] 支持指定新的 graph project；
- [ ] 默认拒绝覆盖已存在图；
- [ ] 覆盖必须是显式参数且有人类审批；
- [ ] `continue_on_error=false`；
- [ ] 记录命令、版本、耗时、返回码和 reject；
- [ ] 导入后自动跑 count/integrity 查询；
- [ ] 不把密码写到命令日志；
- [ ] PoC、全量、HA 使用不同配置档。

### 7.4 固定版本兼容性测试

对最终选择的 TuGraph 版本验证：

- [ ] 基本 MATCH/CREATE；
- [ ] 参数化字符串、数值、布尔和 map；
- [x] 参数化 `LIMIT`：使用 `$row_limit`，不可使用关键字 `$limit`；
- [x] 多段 `MATCH`/`OPTIONAL MATCH`：当前 4.5.2 实测不支持，业务查询已拆成两次读取；
- [x] `collect(DISTINCT ...)`：非空结果经 Bolt 作为字符串返回，业务查询改为逐行返回并在 Python 聚合；
- [ ] 正则与字符串函数；
- [ ] 固定和可变长度路径；
- [ ] 边属性查询；
- [ ] 边 upsert/唯一性；
- [ ] 大字符串、Unicode 和换行；
- [ ] REST/Bolt 超时、认证和连接恢复；
- [ ] HA 环境的写入和复制行为（如适用）。

### 7.5 完成定义

- 小案例导入 reject=0；
- 两次导入/重建结果一致；
- count 和 integrity 对账通过；
- 没有对现有 GraphDB 或生产图做破坏性修改。

## 8. 里程碑 M4：GraphStore 与 P0 查询

### 8.1 Client 层

`TuGraphClient` 必须统一处理：

- 认证和 token 刷新或 Bolt session；
- graph project 名；
- 参数化查询；
- 连接/读取/总超时；
- 可重试与不可重试错误分类；
- 有上限的指数退避；
- 返回列与类型解析；
- query name、耗时、行数、错误码指标；
- 凭据和敏感文本脱敏；
- healthcheck。

禁止每个 Store 方法自己写 HTTP 登录或自行解析不一致的响应。

### 8.2 Store Contract

先写同一套契约测试，再实现两个后端：

```python
@pytest.mark.parametrize("store", [graphdb_store, tugraph_store])
def test_get_core_insights_contract(store, fixture_ids):
    result = store.get_core_insights(fixture_ids.pipeline_uid)
    assert list(result.columns) == EXPECTED_COLUMNS
    ...
```

### 8.3 P0 实现顺序

严格按顺序，每完成一项就跑双后端黄金测试：

1. [ ] 按 uid/uri 获取 Dataset 基础字段；
2. [ ] 获取 Dataset 下 Table/Column；
3. [ ] 候选竞赛 problem_type/data_type 过滤；
4. [ ] 获取 EDAInsight；
5. [ ] 获取 Top Pipeline；
6. [ ] 获取 Pipeline CoreInsight；
7. [ ] 获取 Insight 实现代码；
8. [ ] 组合 `get_top_k_similar_competitions()`，保持 pgvector；
9. [ ] 组合 EDA 相似度；
10. [ ] Agent Retriever 端到端。

### 8.4 查询实现约束

- 值用参数，不用 f-string；
- 关系类型来自枚举白名单；
- `LIMIT/hops` 若需插值，必须先转 int 并校验范围；
- 结果必须显式排序；
- 数据库字段名与公共 DataFrame 字段名分离；
- 空列表、空 DataFrame 和 `None` 按旧契约返回；
- 不捕获裸 `except` 后返回空结果；
- 查询失败要带 query name 和可诊断上下文，但不得泄漏凭据。

### 8.5 完成定义

- P0 Store Contract 100% 通过；
- P0 GraphDB/TuGraph 黄金结果一致；
- Agent 进入 LLM 前的结构化结果一致；
- 图后端可通过配置切换；
- TuGraph 故障时的回退行为有测试。

## 9. 里程碑 M5：P1/P2 查询迁移

### 9.1 P1 查询清单

- [ ] `get_datasets_info`
- [ ] `get_tables_info`
- [ ] `get_table_info`
- [ ] `show_graph_info`
- [ ] `search_tables_on`
- [ ] `recommend_k_joinable_tables`
- [ ] `recommend_k_unionable_tables`
- [ ] `get_path_between_tables`
- [ ] `get_pipelines_info`
- [ ] `get_most_recent_pipeline`
- [ ] `search_classifier`
- [ ] `get_hyperparameters`
- [ ] `get_top_k_library_used`
- [ ] `get_top_used_libraries`
- [ ] `get_pipelines_calling_libraries`
- [ ] `get_pipelines_for_deep_learning`
- [ ] `recommend_transformations`
- [ ] `get_pipelines_by_tags`
- [ ] 图表类方法所需的结构化查询。

### 9.2 特殊注意

#### joinable/unionable

- 保持列级 certainty 聚合到表对的原算法；
- 防止同一表对重复边造成分数膨胀；
- 分母为 0、空推荐、只有自身表时要有测试；
- 先保持 Python 聚合，再基于性能证据下推。

#### path_between_tables

- 关系类型只能是白名单中的 similarity edge；
- hops 有上限；
- 保持原查询“相似边 + 同表内换列”的路径语义；
- 不能误改成纯 Column 相似边连续路径；
- Graphviz 只是表现层，查询层先返回稳定路径记录。

#### Pipeline 聚合

- 原 `GRAPH ?Pipeline` 限定必须改成 Pipeline->Statement 作用域；
- 库名/module 提取尽量在构建时保存 `qualified_name/root_library/module`，不要每次查询正则切 URI；
- tags 使用 Tag 节点，不用逗号字符串模糊包含。

#### 参数

- 参数名来自 Parameter 顶点；
- 参数值来自 HAS_PARAMETER 边；
- 同名参数在不同 Statement/Pipeline 中不能串值。

### 9.3 P2

- [ ] 评估子图先选择“逻辑 allowlist”或“物理新图”，写 ADR；
- [ ] 替代 SPARQL CONSTRUCT 和 Graph Store 下载/上传；
- [ ] 去除模块 import 时的隐式服务初始化；
- [ ] 核查 GNN/OnDemandDataPrep 是否仍在运行路径；
- [ ] 未迁移的 legacy 功能必须有明确开关和文档。

### 9.4 任意查询接口

- [ ] 新增 `query_sparql()`；
- [ ] 新增 `query_cypher()`；
- [ ] `query()` deprecate；
- [ ] TuGraph 下调用旧 `query(rdf_query)` 必须给出明确不兼容错误；
- [ ] 禁止自动识别和静默翻译。

## 10. 里程碑 M6：双读、性能、灰度和回滚

### 10.1 ComparingGraphStore

比较逻辑必须：

- 异步或有严格额外耗时预算；
- 在线返回仍由主后端决定；
- 对集合排序、浮点容差、时间和 null 做标准化；
- 记录 query name、输入摘要、差异类型和 build id；
- 不记录大段代码/描述全文；
- 可按 API、用户/任务和采样率开关。

差异分类：

```text
MISSING_ROW
EXTRA_ROW
FIELD_MISMATCH
ORDER_MISMATCH
TYPE_MISMATCH
ERROR_MISMATCH
TIMEOUT
```

### 10.2 性能

- [ ] 对 P0/P1 查询采集 p50/p95/max；
- [ ] 查看执行计划并保存证据；
- [ ] 检查是否使用 uid/index；
- [ ] 检查全图扫描；
- [ ] 测试高基数 Column/Similarity/Pipeline；
- [ ] 测试并发读取；
- [ ] 测试连接池和长时间运行；
- [ ] 性能优化提交不得改变结果口径。

### 10.3 故障演练

- [ ] TuGraph 不可达；
- [ ] 认证失效；
- [ ] Cypher 超时；
- [ ] PostgreSQL 不可达；
- [ ] GraphDB 不可达；
- [ ] 两个图后端 build id 不一致；
- [ ] 导入中断；
- [ ] 部分批次失败；
- [ ] 配置切回 GraphDB。

### 10.4 上线门槛

- [ ] 全量导入 reject=0；
- [ ] P0 parity=100%；
- [ ] Agent 结构化中间结果 parity=100%；
- [ ] P0 p95 达标；
- [ ] 双读观察期无未解释差异；
- [ ] 回滚演练通过；
- [ ] 生产凭据扫描通过；
- [ ] 所有 P0 路径不再直连 GraphDB；
- [ ] 人类负责人签字。

## 11. 测试策略

### 11.1 测试金字塔

```text
ID/Schema/CIR 单元测试
          ▼
Builder/Sink 快照与属性测试
          ▼
GraphStore 契约测试
          ▼
GraphDB ↔ TuGraph parity 集成测试
          ▼
SACKCaseRetriever 端到端测试
          ▼
全量数据对账与性能测试
```

### 11.2 必测边界

- 空 Dataset、空 Table、空 Column；
- 同名 Table 位于不同 Dataset；
- 同名 Column 位于不同 Table；
- 中文、引号、换行、反斜杠、百分号、超长 URI；
- 缺失 overview/data_description；
- `score=0`；
- 无 tags、无 parameters、无 CoreInsight；
- Cross-Phase Insight 和多个 spanning phases；
- 参数值为字符串、数字、布尔、列表/对象字符串；
- NaN/INF；
- 一条 Pipeline 引用同一 API 多次；
- 相似度阈值边界；
- duplicate/replay；
- 部分历史 TTL 无效但源 Profile/AST 可重建；
- GraphDB 返回顺序与 TuGraph 不同。

### 11.3 禁止的测试捷径

- 不得只断言结果非空；
- 不得只比较行数；
- 不得把 DataFrame 全部转字符串后比较；
- 不得用 LLM 最终文本一致代替结构化结果一致；
- 不得在测试里吞异常；
- 不得把真实生产密码放进 fixture；
- 不得让集成测试默认删除数据库。

## 12. 代码与提交纪律

每个提交只完成一种可解释变化，推荐顺序：

1. baseline tests；
2. id codec；
3. schema registry/CIR；
4. global builder；
5. pipeline builder；
6. TuGraph sink；
7. loader；
8. client；
9. P0 Store methods；
10. Agent integration；
11. P1/P2；
12. dual read/metrics；
13. docs and rollout。

每个提交说明必须包含：

- 修改的行为；
- 保持不变的行为；
- 测试命令和结果；
- 数据/Schema 版本影响；
- 回滚方式；
- 未解决风险。

不要顺手格式化或重写无关的 2,000 行文件；不要覆盖用户已有修改；不要把生成的大型 CSV、数据库文件、密码或日志提交到 Git。

## 13. 每轮工作报告模板

```markdown
### 本轮目标

### 已完成
- 代码：
- 测试：
- 文档/ADR：

### 语义校验
- GraphDB 基线：
- TuGraph 结果：
- 差异及解释：

### 风险与阻塞

### 下一步

### 可回滚点
```

只报告实际运行过的测试。若测试因服务/数据缺失未运行，要写“未运行”及原因，不能写“应当通过”。

## 14. 需要立即停止并请求人工决策的情况

遇到以下任一情况，停止扩大改动范围，保留证据并请求负责人决策：

1. 固定 TuGraph 版本不支持 P0 查询所需的核心 Cypher 语义；
2. 发现 GraphDB 实际启用了会影响业务结果的推理规则；
3. 同一 URI 在现有数据中对应多个不可兼容的业务类型；
4. 同一规范顶点的属性存在不可自动合并的冲突；
5. GraphDB 与源 Profile/AST 的权威性冲突；
6. 必须修改相似度公式、权重、Top-K 或 Agent Gate 才能继续；
7. 必须删除/覆盖现有数据库或历史产物；
8. 需要把 pgvector 一并迁移；
9. P0 parity 无法达到 100%，且差异不是已批准的缺陷修复；
10. 预计工作明显超出已批准范围；
11. 需要生产凭据或外部系统权限；
12. 工作树中存在与当前改造重叠且无法安全保留的用户修改。

## 15. 最终完成检查表

### 架构

- [ ] CIR 是构建权威中间层；
- [ ] GraphDB 和 TuGraph 都通过 GraphStore；
- [ ] PostgreSQL/pgvector 保持独立；
- [ ] Facade 和 Agent 不感知查询语言。

### 语义

- [ ] URI/uid 可逆关联；
- [ ] RDF-star 两类映射完整；
- [ ] Named Graph 作用域完整；
- [ ] 多值、类型、null、日期和长文本策略落实；
- [ ] 本体/推理差异有明确结论。

### 数据

- [ ] manifest/checksum 完整；
- [ ] 全量 reject=0；
- [ ] 无悬挂边、冲突顶点和错误 scope；
- [ ] 各标签计数对账；
- [ ] 重建确定性通过。

### 查询

- [ ] P0 全部迁移；
- [ ] P1/P2 状态逐项明确；
- [ ] 所有值参数化；
- [ ] 动态 label/relation 白名单；
- [ ] 查询有超时、分页/上限和指标；
- [ ] 任意 SPARQL 接口没有被伪兼容。

### 测试

- [ ] 单元、契约、parity、端到端、性能、故障测试通过；
- [ ] Agent 的结构化中间结果一致；
- [ ] 执行计划已审查；
- [ ] 未运行项为 0 或已获书面豁免。

### 上线与运维

- [ ] 固定版本和镜像摘要；
- [ ] 凭据外置；
- [ ] 新图版本发布，不原地覆盖；
- [ ] 双读观察完成；
- [ ] 回滚开关和演练完成；
- [ ] GraphDB 退役是独立的后续决策。

完成上述检查前，不得宣称“GraphDB 已成功迁移至 TuGraph”。准确表述应是当前到达的阶段，例如“TuGraph P0 双读已通过，尚未默认切流”或“全量导入已完成，P1 查询仍在迁移”。

## 16. 当前施工断点（2026-09-25）

部署配置更新（2026-09-28）：用户已明确要求两个实例使用固定测试密码，禁止自动轮换；主实例 `7070/7687`、冒烟实例 `17070/17688` 均绑定所有网卡且不限制来源 IP。密码值不写入仓库，服务器凭据文件保持 0600。下文 loopback/随机密码描述属于历史基线。保留的 `*-loopback-backup-20260928` 容器已停止且 restart=no，禁止同时启动共享同一数据库目录的旧、新容器。

接手续做时先核对以下事实，不得重复造一套模型或绕过 CIR：

- M1/M2 的 CIR、标识编码、Schema Registry、校验、Profile/Pipeline 构建器、RDF-star TTL 相似度提取器、无损 metadata v2、包读写和合并器已经存在；
- M3 导出器已经按 TuGraph 4.5.2 官方 `schema/files` 格式生成 JSON-line、`import.config.json`、`manifest.json` 和 `validation_report.json`；
- 服务器装载器、确定性冒烟包、导入后只读校验器、Cypher 兼容性探针和 P0 冒烟查询校验器已存在，分别生成导入日志、`post_import_validation.json`、`compatibility_report.json` 与 `smoke_verification_report.json`；
- 边文件必须按“关系标签 + source label + target label”拆分，不能把多种端点的 `IS_PART_OF` 混入一个文件；
- 顶点 primary 固定为 64 字符 `uid`，完整 URI 只作为普通属性；
- RDF-star 相似度转为带 `certainty` 的正反两条边，Named Graph 转为 `scope_uid`；
- 真实全量包必须合并 Profile、Similarity、Pipeline 三个 CIR 来源；Similarity 来源只能使用与 Profile 同一构建批次的全局 Schema TTL，不能静默跳过；
- 生产 `export_tugraph` 默认检查这三个来源；不要为真实图使用 `--allow-partial`，也不要在未确认源图确实无相似边时使用 `build_similarity_cir --allow-empty`；
- 服务器装载器默认 `overwrite=false`、`continue_on_error=false`，目标固定为 TuGraph 4.5.2；
- 本地新增测试通过；旧 `kg_governor` 基线仍为 `149 passed, 38 failed, 17 skipped`，38 项是迁移前既有失败，不能误报为本轮回归；
- 当前工作区没有配置路径下的 Profile、Pipeline metadata 和全局 Schema TTL；不能凭空声称已生成真实全量包。TuGraph 4.5.2 Docker 容器已在 Ubuntu 22.04 x86_64 服务器部署，镜像摘要为 `sha256:b1b0ecc39a580a7cbdac7b4b7ce35f6a92f0981254d314bc1c0a50ca71d4df0d`，仅绑定 `127.0.0.1:7070/7687`；初始管理员密码已轮换，凭据仅在服务器 root 可读文件中；
- 隔离测试图 `sack_compat_20260924` 的七项只读 Bolt/Cypher 探针全部通过；固定 16 顶点/24 边冒烟包已在第二个独立容器 `sack-tugraph-smoke-452` 的 `sack_smoke_20260925` 图中成功导入。导入后对账、七项兼容性探针和十三项领域查询验收全部通过，本地迁移测试 113 项通过；这仍不是真实数据 parity；
- 原始冒烟包必须保持只读，但 `lgraph_import` 需要在当前工作目录创建 `.import_tmp`，所以 Docker 导入需使用可写工作副本；4.5.2 离线导入拒绝边属性 `edge_uid` 的物理唯一索引，导出器已移除该声明，CIR 仍检查边 ID 唯一；
- 实测 `$limit` 会报解析错误，改用 `$row_limit`；多段 `MATCH`/`OPTIONAL MATCH` 不受支持，CoreInsight/Phase 查询必须拆分；`collect(DISTINCT ...)` 通过 Bolt 返回字符串，阶段值必须逐行查询并由 Python 聚合；
- TuGraph Bolt Client、GraphStore 及 Agent P0 查询分派已建立，默认仍为 GraphDB；当前尚未完成真实数据导入、GraphDB/TuGraph parity、全部历史 API 迁移和 Agent 双读。

下一工作包：

1. 先确认当前容器状态；用户指定固定测试密码，禁止自动轮换；不要覆盖 `sack_compat_20260924` 或 `default`，不要泄漏服务器凭据；
2. Docker 装载器 `migration/load_tugraph_docker.py` 已完成并经服务器实际导入验证；按 [Docker 装载操作手册](Docker_import_runbook.md) 使用全新目录，不重复实现装载器。当前 `load_tugraph.py` 只适用于宿主机原生二进制；
3. 保留已通过的三个冒烟报告作为基线，不要反复覆盖测试图。两次失败试验目录 `db` 和 `db-retry1` 暂时保留供诊断；清理须单独核实目标；
4. 找到真实 Profile、Pipeline metadata 和匹配批次的全局 Schema TTL，再构建三来源完整 CIR 包；
5. 在全新目录和图上导入真实数据，重复对账和兼容性检查，并比较 GraphDB/TuGraph 的结构化中间结果，禁止只比最终自然语言；
6. 完成只读账号、Agent 双读、回滚演练后才讨论切流。

装载工具验收更新（2026-09-28）：本地 129 项知识图谱测试通过，其中 Docker 装载器 16 项。实际 dry-run 未创建目录，固定冒烟包通过装载器导入全新目录，返回码 0；报告 `/opt/sack-tugraph-loader-20260928/results/import_result.json`。未启动新服务、未改密码与端口。复制后须再次核验包及 manifest，源包在准备期间发生变化必须拒绝导入。真实数据未找到，禁止把装载器验收误报为真实图 parity 或切流完成。

如果服务器不是 x86_64，不得直接安装官方 release 中的 x86_64 deb/rpm；先确认官方 ARM64 镜像，或建立可复现的源码构建方案并获得负责人确认。
