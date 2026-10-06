# Titanic 修复与验证记录（2026-10-02）

## 最终结论（第十二版，2026-10-05 完成测试）

GraphDB 与 TuGraph 已用相同业务源码、模型配置和原始输入顺序完成完整测试，真实严格验收均 accepted=true/errors=[]。GraphDB 于 10-04 23:04:33、TuGraph 于 10-05 01:37:21 北京时间非主动退出 0。本地最终回归 221 passed；两后端 262 个不可变清单源码与本地一致，完整目录 266 个非运行产物文件两边一致。

两边完整 DSP、独立 EDA、两类完整洞察、train12/test11 全列 300 维有限 profile、有效处理数据和 418 行二分类预测均通过，原始数据哈希未变。processed 数据为 train891/test418 行，GraphDB 各38/TuGraph 各12 个匹配真实预测特征。标准化 id/Survived 与 Kaggle 原始 PassengerId/Survived 不同，未提交 Kaggle；不能据此宣称后端全面等价。

最终摘要和精简证据：[最终验证](sack-titanic-fix12-final-validation-20261005.md)、[最终 JSON](sack-titanic-fix12-final-evidence-20261005.json)。以下为按时间保留的历史过程，早期测试数量、四小时上限、旧版通过和“未提交”状态均属于当时记录；以本节及最终证据为准。

Draft PR：https://github.com/sxswa1/SACK/pull/1 。分支 `codex/titanic-workflow-fix`，基于 `codex/tugraph-migration`。原失败诊断已在前置提交中保存；完整修复与最终验证作为本 PR 的后续提交交付。

## 已完成的修复

- 用 AST 提取上一阶段函数体，替代固定行数截取；删除完整输出语句，避免破坏多行代码；执行前校验最终拼接脚本。
- Data Preparation 明确没有前驱阶段，避免读入末阶段旧代码；失败保留 State，避免日志出现二次异常。
- 优先直接解析纯 JSON 和非贪婪 JSON 围栏；Reviewer 按角色校验分数，最多修复一次格式，保存原始回复和每次解析结果。缺失分数是格式错误，不再补为真实 0 分。实际代码执行失败仍为 0 分。
- EDA 汇总拒绝列表或含糊 JSON；缺少模板字段、unknown 或必需工具输出时不能作为有效洞察通过。
- 限制包含 HELP 重生成在内的代码循环次数。
- profile 使用当前 DSP 输入目录，仅选择 train/test，缓存绑定 CSV 和描述文件哈希；校验列覆盖与 300 维有限数值向量，保存列失败详情并拒绝不完整 profile。
- 数值/日期预处理用标准库编码 IEEE 754 float32，统计值统一转 Python float，减少标量与依赖兼容问题。
- GraphDB 的公共 EDA 接口保留核心返回的字典结构；保留现有部署所需的 PostgreSQL 环境覆盖及 TuGraph 列去重。
- 首轮真实重测发现 Data Preparation 的 CSV 预览将逗号转成制表符，并将 split 后的行用空字符串拼接，导致生成代码推断错误分隔符。现在直接展示原文件文本，保留分隔符、引号和行边界，并进行 UTF-8/检测编码/GB18030 回退。

SSH 恢复后已补读旧 TuGraph 日志，确认数值列异常是 `ModuleNotFoundError: No module named 'bitstring'`，发生在数值 profile 模块导入阶段。标准库编码移除了该缺失依赖；列覆盖检查另行防止异常被静默跳过。

## 已通过验证

`PYTHONDONTWRITEBYTECODE=1 /Users/mac/miniconda3/envs/sack-tugraph-test/bin/python -m pytest -q -p no:cacheprovider sack/knowledge/tests`

结果：172 passed（包含 CSV 预览、Planner 重试、EDA 工具显式关键字校验、Reviewer 按角色合并、无代码调试回复及工具原生 JSON 输出回归）。包含真实代码生成方法的三类脚本拼接与执行、纯 JSON Reviewer 4/5 分保留、无效 schema 拒绝、格式修复次数上限、profile 漏列失败记录、缓存失效和图谱接口测试，以及逗号/制表符/GB18030 源文本预览。依赖服务/模型调用使用替身，不能据此宣称完整流程成功或后端全面等价。

此外，在 PyTorch 2.3.0 环境使用仓库真实预训练权重验证 Pclass、id、Age（含缺失值）与 Fare 四组数值样例：均生成 300 维有限向量。fastText 仅替代类型注解，不替代数值模型。临时脚本与结果随后被本机临时目录清理；已由服务器两后端真实 CSV 的完整 profile 预检补充验证，精简证据保存在本报告同目录。

修改的 Python 文件均通过 AST 语法检查，`git diff --check` 通过。原工作区及原始数据未修改。

## SSH 恢复与重跑准备

此前 `60.204.211.83:22` 在 SSH 版本交换前断开；部分后续命令因自动权限审核超时未执行。2026-10-02 再次连接已返回 `SSH_OK`。GraphDB、TuGraph 和 PostgreSQL 实际端口与服务均正常。

已准备独立重跑目录和源码包：`/private/tmp/sack-backend-compare-20261002-fix`；目标服务器目录 `/opt/sack-backend-compare-20261002-fix`，准备脚本拒绝覆盖已有目录，启动脚本拒绝重复付费运行。预检通过后再顺序执行 GraphDB 和 TuGraph，每个任务仍保持四小时限制。旧监控和旧运行没有恢复或重启。

两后端新工作区已创建，修复源码清单哈希与原始数据哈希一致。两边八项预检均通过：真实 profile 均覆盖 train 12/12 列、test 11/11 列，数值列没有遗漏；元数据提取替代为固定值，避免预检付费请求。精简证据保存于 `sack-titanic-fix-preflight-20261002.json`。

七项已测图谱/融合检索结果语义一致；pipelines 与 insights 的字符串顺序导致精确哈希不同。两次独立 profile 的元数据、列集合和类型一致，保存内容向量的差异上限为 1.7881393432617188e-07，精确哈希仍不同。不能将预检描述为所有结果逐字相等或后端全面等价。

第一次 GraphDB 修复重测在独立 EDA 的 Data Preparation 中，生成代码明确从坏的预览推断 `sep='\t'`，遇到列不一致及 `UnboundLocalError: column_info referenced before assignment`。确认预览缺陷后主动停止该尝试；旧目录保留日志及 `stopped_reason.json`，原始数据哈希未变。systemd 包装命令在主动停止时返回 0，但没有洞察或预测文件，该次不能算流程成功。TuGraph 未在该版本启动付费任务。

预览修复通过回归后，使用新目录 `/opt/sack-backend-compare-20261002-fix2` 重新准备两个工作区；仍按 GraphDB、TuGraph 顺序验收，避免两套模型任务争用内存。

第二版两后端再次通过八项 profile/检索预检与真实 CSV 源文本预览检查。GraphDB 完整流程已通过 Data Preparation、Understand Background、Preliminary Exploratory Data Analysis 和 Data Cleaning。Data Preparation 的 Planner/Developer 均为 5 分，两回复的本地解析各一次成功，无错误文件。

18:52 初步洞察首轮质量检查未通过：38 个未知字段、17 项缺少的工具结果。实际脚本成功执行，但生成代码仅将 EDA 工具返回值保存到变量，没有打印或保存供汇总器读取，输出文件为空。Reviewer 的 4/4 分已正常解析；质量门禁拒绝将该轮视为有效洞察，并要求输出工具结果后重试。正在验证后续轮次；完整洞察与预测仍待验收。

完整重测仍需要验证退出码、初步/深度洞察、完整 profile、预测文件及原数据哈希。通过后再按用户要求提交和推送代码修复；当前不能声称这一步已完成。

## 第二版重试失败与第三版修复

PEDA 第二轮未知字段降至 8 个，但正态性、多峰分布、类别不平衡三项工具未执行；第三轮补出缺失模式支撑统计，仍遗漏这三项工具。19:05:43 日志确认 PEDA 三次阶段尝试耗尽、质量分为 0，并开始整段 EDA 重跑。代码检查确认 `eda_planner.py` 的重试分支无论原评分高低都直接返回旧计划，导致反馈无法修正工具遗漏。

已修复 EDAPlanner：重试时加入旧计划、Reviewer 建议与洞察质量反馈，重新生成并保存 Markdown/JSON 计划。新增真实 `_execute` 方法测试，验证原评分 0 和 4 均会依据缺失工具反馈生成新计划；166 项测试通过。主动停止第二版已知缺陷运行，写入 `stopped_reason.json`，保留日志；该次不能算完整成功。TuGraph 未启动完整付费运行。

第三版使用新目录 `/opt/sack-backend-compare-20261002-fix3`，源码哈希及两套原始数据再次核对一致。两后端八项 profile/检索预检、CSV 预览检查和结果比较均已完成，两边仍覆盖 train 12/12 列、test 11/11 列。精简证据已更新到本报告同目录的预检 JSON。GraphDB 全流程于 19:08:55 启动；TuGraph 仍待 GraphDB 验收后启动。

第三版 Data Preparation 首次生成代码用 cp1252 读取描述文本，发生 UnicodeDecodeError；自动调试后成功执行并清除错误文件，原数据哈希未变。Reviewer Planner/Developer 均为 5 分，两条回复各一次本地解析成功，无格式修复。19:15:32 进入 Understand Background。其余阶段及最终预测尚未验收。

19:56 定时检查：Understand Background Reader 5 分，Preliminary EDA Planner/Developer 5/5 分，Data Cleaning 4.5/4 分，均已推进。PEDA 首轮评审 4/4 分，但洞察质量仍有 18 个未知字段，缺少异常值、严重程度、偏度、尺度、正态性和多峰分布六项工具结果，门禁要求重试。实际 Planner 历史已包含 `REVISE THE PREVIOUS PLAN` 与质量反馈，新版重新规划逻辑已在服务器执行。GraphDB 仍活跃，尚无最终结果；TuGraph 完整任务尚未启动。

20:06 定时检查：PEDA 重试后通过，Planner/Developer 5/5 分，洞察 validation 的 unknown_fields_count 为 0，missing_schema_fields 和 missing_tool_outputs 均为空；原始数据哈希未变。20:03:19 进入 IEDA Insight Extraction，当前正在制定深度洞察计划，尚未完成代码执行及最终验收。TuGraph 完整任务尚未启动。

20:16 定时检查：IEDA 首轮脚本已执行成功、Reviewer 5/5 分，但首轮洞察有 7 个未知字段，缺少条件依赖、时间序列、空间相关及因果混杂四项输出，门禁要求重试。第二轮重新规划后脚本于 20:16:33 成功执行，尚在评审。此真实运行未复现旧的深度脚本拼接语法错误，但深度洞察完整性和后续 DSP 尚未验收。GraphDB 服务活跃，TuGraph 完整运行尚未启动。

20:26 定时检查：IEDA 第二轮洞察剩余 3 个未知字段，高基数工具结果仍缺失；第三轮脚本已执行到汇总。输出中有被生成代码 try/except 捕获的 TypeError：`analyze_high_cardinality_impact` 被传入不支持的 `high_cardinality_threshold`。工具源码与文档均明确固定阈值 ≥20，只有 data/target_column 两个参数；此处是生成代码参数错误，进程成功不代表工具全部成功。等待该轮质量校验，不因此重启当前付费任务。GraphDB 服务活跃，TuGraph 尚未启动。

## 第三版 IEDA 失败与第四版修复

20:28:08 IEDA 三轮后仍有两个未知字段，均为高基数分析结果；质量门禁明确失败，随后开始整段 EDA 重跑。20:36 定时检查确认原因后主动停止，保留 stopped_reason.json 和日志。第三版不能算完整成功，TuGraph 未启动完整任务。

增加执行前 EDA 工具显式关键字校验：从真实 eda_tools.py 源码提取签名，检查生成脚本中直接导入的工具调用（支持导入别名），不支持的关键字写入阶段错误并进入既有调试分支。即使生成代码 try/except 捕获异常，也不能绕过该校验。校验不执行工具、模型或数据库，不推断动态 **kwargs。新增回归验证真实框架在 subprocess 前拒绝隐藏的错误参数，并允许有效参数及无关函数调用；168 项测试通过，git diff --check 通过。

第四版新目录为 `/opt/sack-backend-compare-20261002-fix4`，正在以统一源码准备隔离重测；仍先执行两后端预检，再运行 GraphDB，完整验收后才启动 TuGraph。

20:46 定时检查：第四版两后端八项预检、源 CSV 预览检查均通过，精简 JSON 已刷新至第四版。GraphDB 于 20:42:42 启动完整流程；Data Preparation 生成代码检测 overview.txt 为 MacRoman、置信度 0.64，因自设低于 0.7 的检查主动退出（错误写在 stdout，stderr 为空），当前自动调试中。CSV 均检测为 ASCII。此次尚未阶段失败，不改动运行源码或重复启动；TuGraph 尚未启动完整任务。

20:56 定时检查：自动调试已解决 Data Preparation 的退出问题，该阶段 Planner/Developer 5/5 分，错误文件不存在；Understand Background Reader 5 分。20:55:53 已进入 Preliminary Exploratory Data Analysis。两处原始数据哈希均未变，GraphDB 服务活跃，TuGraph 完整任务尚未启动。

21:06 定时检查：第四版 Preliminary EDA 通过，Planner/Developer 5/4 分，21:05:12 进入 Data Cleaning。GraphDB 仍活跃，没有完整结果；TuGraph 完整任务未启动。本轮没有新的确定代码缺陷，不修改源码或重复测试。

21:16 定时检查：Data Cleaning 脚本无错误文件，Reviewer Planner/Developer 5/5 分，仍在汇总阶段。GraphDB 服务活跃，没有最终结果，TuGraph 未启动；本轮没有新失败或需要干预的问题。

21:26 定时检查：第四版已进入 PEDA 洞察汇总，脚本无执行错误文件，输出 4316 字节，Reviewer Planner/Developer 5/5 分。quality validation 尚未生成，不能将该评分视为洞察完整性通过。GraphDB 活跃，TuGraph 未启动；继续等待汇总，不重复运行。

21:36 定时检查：第四版 PEDA 完整性通过，unknown_fields_count=0、missing_schema_fields=[]、missing_tool_outputs=[]，Reviewer 5/5 分。已进入 IEDA。深度脚本首次 json.dump 遇到 NumPy bool_ 无法序列化，进入自动调试；第二次执行后错误文件已清除，原异常保存在 all_error_messages.txt，未出现此前的拼接语法错误。深度洞察及后续 DSP 仍待验收，不改动运行源码，TuGraph 尚未启动。

21:46 定时检查：IEDA 首轮质量检查仍有 5 个未知字段（条件依赖强度、时间序列与空间属性），缺少时间序列及空间相关工具结果，已正常重试。第二轮脚本 21:44:59 执行成功，无错误文件，输出 1841 字节，当前评审中。没有新的确定框架缺陷，继续等待质量校验；GraphDB 活跃，TuGraph 未启动。

## 第四版 Reviewer 冲突与第五版修复

21:47:45 IEDA 第二轮在 Reviewer 合并阶段抛出 `ReplyFormatError: Conflicting reviewer values for agent planner`，引发整段 EDA 重跑。每次评审请求只针对一个角色，但模型回复包含其他角色评分，原归一化仅检查目标评分存在，仍把附带评分送入合并。21:56 定时检查确认堆栈后停止第四版，保留日志及 stopped_reason.json；不能算完整成功，TuGraph 未启动。

修复 normalize_review：提供 expected_role 时只保留该角色评分和建议，防止其他角色的附带评价覆盖其专属请求；不指定角色时仍验证所有评分，同一角色自身冲突及缺失目标评分继续拒绝。新增真实 Reviewer 解析与合并回归，两份回复含相互冲突的其他角色评分和建议时，仍保留本角色的原始 3/4 分及各自建议，不调用格式修复模型；缺失目标评分仍报错。169 项测试和 git diff --check 通过。

第五版新目录为 `/opt/sack-backend-compare-20261002-fix5`，统一源码隔离重测准备中，先两后端预检、后 GraphDB 全流程；TuGraph 待 GraphDB 完整验收。

22:06 定时检查：第五版两后端八项预检、CSV 预览和结果比较均通过，精简 JSON 已刷新至第五版。GraphDB 于 22:03:57 启动，当前 Data Preparation Developer 生成代码中，服务活跃，没有最终结果；TuGraph 完整运行未启动。没有新的确定错误，不改动当前源码或重复启动。

22:16 定时检查：第五版 Data Preparation 5/5、Understand Background 5 分，各角色评审均一次本地解析成功；原始数据哈希未变。22:12:30 已进入 Preliminary EDA，当前 Developer 生成代码中。GraphDB 活跃，没有最终结果，TuGraph 未启动，无新失败或干预需求。

22:26 定时检查：第五版 Preliminary EDA 已结束并于 22:25:54 进入 Data Cleaning，GraphDB 服务活跃，完整结果尚未生成。继续当前运行，未修改测试源码、未重复启动任务。

22:36 定时检查：第五版 Data Cleaning 5/5 分，无阶段错误文件，22:35:29 已进入 PEDA Insight Extraction。当前规划中，GraphDB 活跃，未见新失败标记；TuGraph 完整任务未启动。继续等待洞察质量验收。

## 第五版调试器异常与第六版修复

22:46:32 第五版 PEDA 因调试器 `correct_code_matches[-1]` 抛出 IndexError 中断，随后整段 EDA 重跑；修正回复没有 Python 代码围栏。此前生成脚本 JSON 输出失败是 `numpy.bool_` 无法序列化。已主动停止第五版并保留停止原因与日志，TuGraph 未启动完整任务。

修复 Tools/debug.py：无修正代码或仅空白代码时保存原回复和调试历史，返回现有 HELP 信号进入有总次数限制的重新生成，而不是索引空列表。修复 Tools/eda_tools.py：统一包装本模块定义的公共工具结果，递归将 NumPy 标量和数组转为同值的 Python 原生值，保留工具名称、文档及签名；统计计算不变。新增两种无代码回复回归，以及真实 analyze_numerical_scale 函数的 bool_/嵌套值 JSON 序列化回归；172 项测试、git diff --check 通过。

第六版新目录 `/opt/sack-backend-compare-20261002-fix6`，统一源码隔离重测准备中。新增真实工具导入和 JSON 输出预检，两后端均检查后再做原八项 profile/检索预检，全部通过才启动 GraphDB 全流程；TuGraph 仍待 GraphDB 完整验收。

第六版工作区准备完成，源码与原始数据一致性核对通过。启动驱动已运行；服务器实际导入 GraphDB 工作区 EDA 工具后 JSON 序列化检查通过（无付费调用），GraphDB 八项预检已通过，TuGraph 预检进行中。定时任务已切换到第六版，PR 已记录两项新增修改及理由。

22:56 定时检查：第六版两后端真实工具 JSON 输出检查、原八项 profile/检索预检、CSV 预览与结果对照均通过，精简 JSON 已更新至第六版。GraphDB 全流程于 22:56:06 启动，目前 Data Preparation 规划中，服务活跃、无最终结果。TuGraph 完整任务未启动。

23:06 定时检查：第六版仍在 Data Preparation 代码测试调试，三项检查反复未通过，涉及 sample_submission 的 id 列命名及目标列集合不一致。尚未出现阶段最终失败或新框架异常；自动调试继续，GraphDB 服务活跃，无最终结果，TuGraph 未启动。不修改运行中源码或重复任务。

23:16 定时检查：Data Preparation 自动调试已使全部阶段数据检查通过（失败数 0），not_pass_information 文件已清除，Developer 正常结束，现进入 Reviewer。GraphDB 服务活跃，无最终结果；继续等待阶段评分及后续流程，不干预或重复启动。

23:26 定时检查：第六版 Data Preparation 4/4、Understand Background 5 分，均已推进，当前 Preliminary EDA Developer 生成代码中。两处原始数据哈希未变，GraphDB 服务活跃，没有完整结果，TuGraph 未启动，无新失败或干预需求。

23:36 定时检查：第六版已推进至 Data Cleaning，当前 Developer 生成代码中，GraphDB 服务活跃，尚无完整结果。继续当前运行，不修改源码或重复启动任务。

23:46 定时检查：第六版已推进至 PEDA Insight Extraction 规划，GraphDB 服务活跃，尚无完整结果或新失败标记；继续等待洞察生成和质量检查，TuGraph 完整运行仍未启动。

10 月 3 日 00:06 定时检查：第六版 PEDA 第二轮完整性通过，unknown_fields_count=0、missing_schema_fields=[]、missing_tool_outputs=[]，Reviewer Planner/Developer 5/5。00:01:50 已进入 IEDA，当前深度汇总中，Reviewer 4/4；深度质量校验尚未生成，不能视作完整通过。GraphDB 服务活跃，无最终结果；TuGraph 完整运行未启动。

10 月 3 日 00:16 定时检查：IEDA 第二轮质量校验仍有 30 个未知字段及缺失字段/工具结果，已进入第三轮规划。读取真实脚本发现结果写入多个 ieda_*.txt，阶段 stdout 输出文件为 0 字节；Summarizer 实际只读取阶段 _output.txt，因此不能使用这些另存结果，质量门禁正常拒绝。此前字符串 Sex 传入 Pearson 相关的错误已由自动调试编码解决；目前未发现新的框架异常，继续观察已有带质量反馈的重试，不修改运行源码或提前重启。GraphDB 活跃，无最终结果，TuGraph 未启动。

10 月 3 日 00:26 定时检查：00:23:13 IEDA 第三轮仍有 31 个未知字段及缺少字段/工具结果，阶段 score=0，整段 EDA 自动重试（remaining retries=2）。第三轮脚本仍只将分析结果写入 ieda_*.txt；Reviewer Developer 2 分，指出遗漏计划工具。现有通用约束已要求 print 输出，质量反馈也明确要求 print 必需工具结果，当前证据属于生成代码未遵循输出约定与工具覆盖，而非新的解析器/数据库异常。保留本轮日志，继续既有有界整体重试，不因模型未遵循要求就覆盖运行源码。尚未最终退出，TuGraph 未启动。

10 月 3 日 02:02 实际检查：第二次整体 EDA 于 01:32:13 再次在深度洞察未通过，最后质量结果 11 个未知字段，缺少数值相关、时间序列与空间工具结果。进入第三次整体 EDA（remaining retries=1），已推进 Data Cleaning 汇总。服务仍活跃、无退出码或最终结果，四小时限制未到；继续当前有界重试，TuGraph 完整任务仍未启动。旧质量文件在新轮次完成前不可视为新轮次结果。

## 第六版四小时超时与第七版提示约定修复

第六版 GraphDB 于 10 月 3 日 02:56:07 非主动停止超时，exit_code=1，systemd Result=timeout。第三次整体 EDA 最终初步/深度均 unknown=0、缺失字段和工具结果为空，EDA status=success；DSP 刚开始即被四小时限制终止。accept.py 验收 accepted=false：没有 DSP 完成记录、处理数据、最终 profile 和预测。原始数据哈希未变，TuGraph 完整任务未启动。不能算完整成功。

发现提示约定冲突：EDAPlanner 重试允许结果 printed or saved，而汇总器只读 stdout；规划提示禁止非时间数据调用时间工具，但模板要求相应字段，且现有工具自身会检测不适用并返回明确结果。第七版统一要求成功调用将工具名与真实结果打印到 stdout，不能仅存其他文件；规划覆盖模板字段并使用工具自身不适用检测，禁止虚构列或统计值。Developer 系统提示保留该输出约定，使重试与历史经验也受其约束；明确不应捕获异常后填入编造常量，并允许数值相关工具必需的复制数据编码。172 项测试通过，Planner 回归增加 stdout 约定检查。新隔离目录 /opt/sack-backend-compare-20261002-fix7 准备中，仍先两后端预检后 GraphDB，完整验收后才启动 TuGraph。

第七版准备与完整源码清单核对通过，manifest sha256=6a08f012b05eedb11bea65365b272712f9bca938968dbf214e383cc952cdfdfa。大文件上传中断后改为复用服务器已有的 23 个大资源，逐项 SHA256 与本地完全一致，其余源码由小型包覆盖；prepare.py 再次验证全部 263 文件及两处原始数据。驱动 PID 792038 已脱离 SSH 启动，两后端 CSV 预览通过，GraphDB 实际 EDA 工具 JSON 检查通过，profile/检索预检进行中；尚未启动完整任务。现有预检报告仍是第六版历史结果，第七版全部预检结束后应刷新。定时任务已切换第七版，PR 已记录每项新增修改及第六版超时失败，代码仍未提交推送。第六版验收备份 reports/sack-titanic-fix6-graphdb-acceptance-20261003.json。

10 月 3 日 07:45 实际检查：第七版两后端真实 EDA 工具 JSON、CSV 预览、八项 profile/检索预检均通过，两后端 train 12/12、test 11/11 列覆盖已核对，精简报告刷新为第七版。GraphDB 于 06:30:34 启动；初步洞察第一轮完整性通过（unknown=0，缺少字段及工具结果为空），07:34:37 进入深度洞察；深度第一轮 7 个未知字段，涉及复杂度和因果混杂，已进入正常带反馈重试。GraphDB 活跃、无最终退出或结果，TuGraph 全流程未启动。不改运行源码，不重复启动。

## 第七版 Feature Engineering 失败与第八版工具修复

第七版 GraphDB 于 10 月 3 日 09:27:28 非主动失败退出 1，运行 2 小时 56 分 54 秒，并非四小时超时。EDA 两类洞察最终 unknown=0、字段/必需工具结果完整，profile train12/test11 且原始数据未变，DSP 清洗数据已生成，但 Feature Engineering 三轮失败，processed 数据与预测缺失；acceptance=false，TuGraph 全流程未启动。

实际工具 create_polynomial_features 将 sklearn 输出的一次项与原始数据 concat，只在 poly_df 内去重，没有消除原始数据与一次项重名。导致 age/fare_log 等重复列，生成代码取列得到 DataFrame 无 dtype，改用 dtypes 后布尔判定仍歧义，最后 scale_features 拒绝重复 fare_log。第八版用 PolynomialFeatures.powers_ 排除次数为 1 的重复项，保留原列、索引和非线性项；输入重复名或新特征名碰撞明确报错，避免静默丢数据。新增真实 degree1/degree2/interaction-only/bias 生成并缩放回归，以及输入重复和原有平方列碰撞拒绝回归。首次本地回归原 172 项通过，新 6 项因测试环境缺少 sklearn 无法运行，正在临时目录补齐测试依赖后重测。第八版 /opt/sack-backend-compare-20261003-fix8 以新统一源码隔离顺序预检与重测，保留第七版失败证据。

第八版本地测试依赖在 /private/tmp/sack-feature-test-deps 补齐（未改项目/服务器环境），完整回归 178 passed in 20.30s；git diff --check 通过。统一源码清单 SHA256=5e7a3e67d9b14a588edb02b0e0f622d25a2aaf0e78b86fc2767bfec170f389c2。新增 check-polynomial.py 从第七版真实清洗数据重放多项式生成、合并及 robust 缩放，两后端均通过才允许后续预检与付费运行。

第八版 prepare.py 已核对全部 263 源文件及两工作区原始数据，启动驱动 PID 810655 已脱离 SSH 运行。定时任务切换为 fix8 / 178 项测试；第七版验收备份 reports/sack-titanic-fix7-graphdb-acceptance-20261003.json。两后端完整流程未验收通过，代码仍未提交推送。

10 月 3 日 10:15 定时检查：第八版两后端八项 profile/检索预检、CSV 预览、真实 EDA JSON、多项式及后续缩放重放均通过；两后端 train12/test11 列覆盖完整，精简预检报告已刷新 fix8。GraphDB 完整任务于 10:05:50 启动，Data Preparation 和 Understand Background 已推进，目前 Preliminary EDA 规划中，无最终退出或异常；TuGraph 完整任务未启动。继续当前任务，不修改运行源码或重复启动。

10 月 3 日 11:01 定时检查：第八版 PEDA 第三轮完整性通过，unknown_fields_count=0、missing_schema_fields=[]、missing_tool_outputs=[]，已进入 IEDA 规划。GraphDB 服务活跃，尚无最终退出或结果，TuGraph 完整任务未启动。当前没有新的确定框架缺陷，不修改运行源码或重复启动。

10 月 3 日 11:31 定时检查：第八版深度洞察第三轮完整性通过；初步与深度均 unknown_fields_count=0、missing_schema_fields=[]、missing_tool_outputs=[]。11:26:48 已进入 DSP Preliminary EDA，实际完成相似 pipeline/洞察检索，服务活跃，无最终结果。TuGraph 完整任务仍未启动；继续等待 DSP 完成及最终预测验收，不把洞察通过当作完整成功。

10 月 3 日 13:15 实际验收：第八版 GraphDB 于 13:13:32 非主动完成，退出码 0，运行 3 小时 7 分 41 秒。accept.py graphdb 全部通过：DSP 完成，两类洞察 unknown=0 且字段/工具结果完整；DSP profile train12/test11 列及全部 300 维有限向量，cleaned/processed 四个数据文件和 418 行二分类预测有效，ID 与原始 test 一致，原始数据哈希未变。预测表头为流程标准化的 id/Survived，与原始 Kaggle PassengerId/Survived 不同，未提交 Kaggle，不能宣称后端全面等价。

确认 TuGraph 尚未启动后，于 13:15:27 顺序启动第八版 TuGraph 完整测试，驱动 PID 828042，systemd 服务 active，当前 Data Preparation；保持四小时限制，严禁重复启动。代码仍未提交推送，等待 TuGraph 同样完整验收。

10 月 3 日 13:57 定时检查：第八版 TuGraph 初步洞察首轮通过，unknown_fields_count=0，缺少字段/必需工具结果为空；13:54:14 进入 IEDA，深度脚本执行通过，正在 Reviewer 评审，深度洞察尚未完成。服务 active，无最终结果，不重复启动、不修改运行源码。

10 月 3 日 16:13 定时检查：TuGraph 三次独立 EDA 尝试耗尽，16:07:42 最后一轮 PEDA Planner 的 JSON 回复及格式修复均无法解析，异常为 Expected one JSON object, received invalid or ambiguous content。前两次深度洞察因生成代码参数/类型错误及字段/工具结果缺失未通过；保留的深度 validation 有9个 unknown 和缺少字段，不能作为当前成功证据。框架随后按既有回退逻辑从 Data Preparation 启动 DSP，服务仍 active，暂无最终退出。即使后续 DSP 完成，也须独立确认 EDA 状态与深度洞察门禁，不能用退出0代替完整验收。不修改运行源码、不重复启动。

## 第八版 TuGraph 超时与 Planner JSON 修复

TuGraph 于10月3日17:15:27四小时超时退出1，非主动停止，DSP停在 Feature Engineering 评审；已生成 cleaned/processed 数据，但无预测，独立 EDA 状态失败，深度洞察不完整。严格 acceptance=false，备份 sack-titanic-fix8-tugraph-acceptance-20261003.json；原始数据未变，profile仍为train12/test11列、300维有限向量。GraphDB同版通过完整验收，不能据此宣称两后端全面等价或把TuGraph失败归因迁移。

代码确认 EDA Planner JSON 重组提示例子使用 list=/str=及双重花括号，直接传给模型时并非合法JSON；且 _execute 在 _parse_json 已做一次格式修复仍失败后，会再次调用同一解析方法重复付费修复，历史只在成功后保存。已改为合法JSON示例、一次解析及可选 final_answer 解包，并在失败时保存 raw_json_plan_reply.txt、planner_history.json、planner_json_parse.json。新增直接/包裹JSON及失败不重复解析与证据保留回归、示例合法性回归。尚待新的统一源码两后端隔离完整重测，不恢复fix8。

Planner JSON 修复后的回归通过。临时依赖目录被清理，首次177 passed/6 failed（缺少sklearn）；仅恢复临时依赖后183 passed in23.35s，git diff --check通过。第九版 /opt/sack-backend-compare-20261003-fix9 已准备，两工作区263源文件及原始数据哈希一致，源码清单 SHA256=ffaa12206faa835a45d9685bca13778ccc1c7eba05685fab0684c34146b6ad7d。启动驱动 PID850387 已请求预检两后端后运行GraphDB，TuGraph未启动。预检报告暂保留第八版，完成后刷新。代码尚未提交推送。

10 月3日17:38：第九版两后端CSV预览、真实EDA JSON、多项式/缩放和八项profile/检索预检全部通过，train12/test11列完整，本地精简预检报告已刷新为fix9。GraphDB完整任务于17:38:05启动，Data Preparation阶段，服务active，无最终结果；TuGraph完整任务未启动。继续当前运行，不重复启动。

10月3日18:18检查：第九版 GraphDB 初步洞察首轮通过，unknown_fields_count=0、missing_schema_fields=[]、missing_tool_outputs=[]；18:12:28进入IEDA，正在评审，尚无深度质量结果或最终退出。TuGraph完整任务未启动，保持当前顺序运行。

10月3日21:16实际检查：第九版GraphDB三次独立EDA均未完整通过，20:47:09最后IEDA失败，最终validation有4个unknown、缺少聚类/条件依赖/交互潜力字段及detect_correlation_clusters输出。流程按既有逻辑回退到DSP Data Preparation，21:13进入DSP Data Cleaning，服务仍active，无最终退出。不能将回退DSP阶段推进认定为EDA成功；TuGraph未启动，待最终严格验收，不修改运行源码或重复启动。


## 第九版最终失败与第十版修复

第九版GraphDB于2026-10-03 21:38:05北京时间四小时超时退出1，非主动停止。严格验收false，已保存 sack-titanic-fix9-graphdb-acceptance-20261003.json。初步洞察完整，深度洞察缺字段，独立EDA状态失败，DSP未完成，无processed数据及418行预测；原始数据哈希不变，profile train12/test11完整。TuGraph未启动。

真实深度stdout表明 detect_conditional_dependencies 返回NaN，另未输出detect_correlation_clusters和复杂度的feature_interaction_potential；不能将其归因数据库后端或误称已有值被总结器丢失。eda_tools.py修复条件相关分析：统一完整行后回归、跳过常量残差和非有限相关系数；runtime_support.py拒绝洞察NaN/Infinity；eda_summarizer.py将缺失子字段映射为需要补跑的工具，即使已有部分工具结果。新增8项回归覆盖常量/缺失/无穷/正常数据、非有限洞察拒绝及部分复杂度反馈。191 passed in3.33s，git diff --check通过。

第十版 /opt/sack-backend-compare-20261003-fix10 已生成两份独立副本，263源文件及原始数据一致，源码清单SHA256=78e624f14841a913e84b4e30f1c090b3db1e5ed2dc98cd4a7f04692fc874bc3d。驱动PID872473已请求真实第九版数据conditional工具重放及两后端预检，全通过后才启动GraphDB；TuGraph需GraphDB严格验收通过才可启动。验收脚本增加非有限洞察检查。预检报告暂保留第九版历史。代码仍未提交推送，未达到双后端交付门槛。


Fix10: both backend preflights passed, including real fix9 cleaned-data conditional-dependency replay with finite values, CSV preview, JSON, polynomial/scaling, and all eight profile/retrieval checks. Profile coverage train12/test11 and all column vectors300/finite verified. GraphDB started 2026-10-03T13:56:01.590216+00:00 (21:56:01 Beijing), service active; TuGraph not started. Local preflight report refreshed. Full acceptance pending.


10月3日22:47检查：第十版GraphDB初步洞察通过，unknown_fields_count=0、missing_schema_fields=[]、missing_tool_outputs=[]。深度洞察仍在同一任务内重试，最新validation有10个unknown，尚未通过；对应真实stdout已含有限conditional_dependency_strength=0.2047、聚类、因果及各复杂度子工具结果，当前缺失不能直接判为工具未执行。保持运行，待质量重试结果，TuGraph未启动。不能将初步阶段通过视为完整验收。


10月3日23:10：GraphDB首轮独立EDA于22:55:25因IEDA质量score=0失败，当前按已有机制第二轮EDA，完整服务仍active且无最终退出。最后6个缺失字段均在complexity，真实stdout包含calculate_samples_per_feature、estimate_feature_interaction_potential、analyze_sparsity、estimate_signal_to_noise、estimate_inherent_uncertainty数值。本地确认EDASummarizer深度映射缺少这5个子工具，提示表明确写No mapped fields；已补齐对应6个模板字段，新增完整/unknown两项回归，193 passed in3.34s，diff检查通过。服务器fix10运行源码保持不变；本地待提交源码因此已新增未做完整测试的补丁，不能用fix10结果替代最终源码完整验收。等待当前任务结束后，根据结果使用全新隔离目录和统一源码必要重测，禁止并行启动、禁止覆盖运行源码。TuGraph未启动。


10月3日23:30：fix10第二轮Data Cleaning生成脚本多次失败。真实 traceback 指向ml_tools.detect_and_handle_outliers_iqr，nullable Int64列被小数IQR边界2.5截断时抛TypeError: Invalid value '2.5' for dtype Int64。另一个astype Int64失败发生在生成代码将已含小数列重新转换整数，不能静默取整更改数据。已修复IQR工具：仅实际需要小数边界替换整数时转Float64再clip，保持缺失值、行/ID及不需提升时的整数dtype。新增4种numeric dtype及无替换5回归；198 passed in3.04s。新增块CRLF导致首次diff检查提示后已只修正该块换行，diff检查通过。当前服务器源码不变、GraphDB仍active、无最终结果，TuGraph未启动。本地复杂度映射和IQR补丁均待全新统一源码完整验收，不能使用fix10验收替代。


10月4日00:43关键验收：fix10第三轮独立EDA成功，competition_process_status.json中titanic=success；两类真实eda_insight.json均可解析、无unknown/None/非有限值，validation unknown_fields_count=0、missing_schema_fields=[]、missing_tool_outputs=[]。00:37:31进入DSP Preliminary Exploratory Data Analysis，服务仍active，无最终退出，尚不能判完整DSP/预测通过。TuGraph未启动。当前运行源码仍为fix10；本地映射及IQR后续补丁尚待统一源码完整重测。


10月4日最终核实：fix10 GraphDB于01:42:01北京时间非主动退出1，未达到四小时限制；独立EDA成功、两类洞察完整，profile列及300维向量完整、原始数据哈希不变，但DSP停在Feature Engineering。生成脚本产生空processed_test.csv，TestTool.execute_tests读取时报pandas.errors.EmptyDataError，未捕获异常使整体退出，无submission。严格acceptance=false，保存sack-titanic-fix10-graphdb-acceptance-20261004.json；TuGraph未启动，两个服务inactive。

修复sack/Tools/unit_test.py：每个输出验收调用捕获Exception，将测试名、异常类型及原因作为失败反馈返回Developer，让现有修复路径处理坏输出；继续剩余验收，保留缺文件早返回及KeyboardInterrupt传播，不伪造数据或通过结果。新增空CSV、畸形CSV、缺文件、正常文件/缺文件早退出、用户中断5回归。统一包含复杂度映射、IQR及输出验收补丁后203 passed in4.44s，git diff --check通过。准备全新fix11，两副本源码清单SHA256=93e9d366520f4d3edc10f316dfe0de72314cc6bfc46cf20739f3842f2a38c792; final full acceptance pending; no commit/push.


10月4日09:22核实：fix11两后端CSV/多项式/EDA JSON/条件依赖及新增输出边界重放、八项profile/检索均通过；真实Titanic nullable Int64小数IQR上界2.5不再报错，真实fix10的419空行CSV被验收方法捕获并返回失败反馈，后续检查继续，5个复杂度子工具映射完整。初始驱动930996因预检脚本错误假设空CSV为零字节退出，未启动完整任务；只修正预检假设，续接驱动931420完成剩余检查，不重跑已通过的检查。原错误日志保留start-driver.log，当前continue-driver.log。两副本准备时263个清单文件一致；prepare.py随后按设计重置competition_process_status.json，运行时262个不可变源码与本地哈希完全一致，状态JSON作为运行产物单独核对。train12/test11列完整，所有列label/content向量300维且有限，精简预检报告已刷新fix11。

GraphDB完整任务于2026-10-04 09:19:09北京时间启动（2026-10-04T01:19:09.939784+00:00），服务active，当前独立EDA Data Preparation；TuGraph未启动。保持四小时上限，不覆盖源码、不重复启动。完整DSP及预测尚未验收，代码仍未提交推送。


10月4日09:31时间限制调整：用户要求放宽上限后，将每个后端完整任务从4小时改为6小时。当前GraphDB保留MainPID931937及09:19:09开始时间，使用当前单元专用临时drop-in及daemon-reload，RuntimeMaxUSec实际核实6h、服务active；没有重启或覆盖业务源码。systemd249的set-property直接调整不受支持，失败尝试未改变任务，随后配置方式成功。服务器run.py仅测试驱动上限改为21600秒，后续TuGraph同样6小时。当前GraphDB预计截止15:19:09北京时间；原始数据、数据库与严格验收规则不变。证据sack-titanic-fix11-time-limit-change-20261004.json，自动检查已同步6小时要求。


10月4日10:06检查：fix11 GraphDB初步洞察第二轮通过，真实eda_insight.json无unknown/None/非有限值，validation unknown_fields_count=0、missing_schema_fields=[]、missing_tool_outputs=[]。当前已进入IEDA，深度脚本执行通过，正在Reviewer评审，深度洞察尚未完整验收；服务active、六小时上限有效，无最终退出。TuGraph未启动。继续当前任务，不把初步通过视为完整流程成功。


10月4日最终GraphDB验收：fix11于11:50:20北京时间非主动退出0，运行约2小时31分11秒。accept.py graphdb真实accepted=true且errors=[]：完整DSP完成、独立EDA状态success、两类洞察未知0且字段/必需工具结果完整，无None/非有限值；cleaned/processed四个数据文件有效，profile train12/test11全列及300维有限向量，有效418行二分类预测ID与原始test一致，原始数据哈希不变。提交表头为标准化id/Survived，original_submission_schema_matches=false，与Kaggle原始PassengerId不同，未提交Kaggle。保存sack-titanic-fix11-graphdb-acceptance-20261004.json。两工作区262个不可变源码再次全部核对一致，状态JSON作为运行产物排除；本地源码仍需交付前再次核对。

确认GraphDB已退出、严格通过及TuGraph从未启动后，于13:43:54北京时间顺序启动同版TuGraph，驱动PID954459、服务MainPID954461、active，RuntimeMaxUSec实际6h；预计最晚上限19:43:54，当前独立EDA Data Preparation。未重复执行预检、未修改运行源码。完整TuGraph验收仍待完成，全部修复尚未提交推送，不能宣称双后端全部通过或全面等价。


10月4日TuGraph阶段检查：同版TuGraph独立EDA状态titanic=success，两类真实eda_insight.json均无unknown/None/非有限值，validation未知0、缺字段/必需工具结果为空。当前已进入DSP Data Cleaning检索，服务MainPID954461保持active、六小时上限有效，无最终退出或完整DSP/预测验收。继续当前任务，不重复启动，不把EDA通过当完整验收；双后端交付仍待TuGraph完成。


10月4日第十一版TuGraph最终失败：18:31:39北京时间非主动退出1，运行4小时47分44秒，未达到6小时上限。严格accepted=false；独立EDA和两类洞察完整、profile全列300维有限向量、原始数据不变、418行二分类submission文件存在，但DSP建模失败，不能凭文件存在宣称通过。真实失败反馈反复Test29按sample前100行均值错误拒绝全0标签，测试还会改写ID；生成代码受到误导尝试人为翻转预测，并把新结果写到submission/titanic而非验收路径。不能把这种分布调整当模型质量或成功证据。

真实FE代码将variance_feature_selection返回表的列名feature/variance当选中特征名，筛除后仅剩train(id,Survived)/test(id)。工具API本身返回feature名称表，属于生成代码误用；框架特征数量验收只设上限却漏掉至少一个真实预测特征。另Developer修复预算耗尽后最后一次成功执行未重新验收，旧not_pass_flag可导致错误失败。统一修复：预测验收只读，准确检查列/行/ID、有限数值与二分类标签或概率格式，不按sample均值推断预测分布；特征验收拒绝零预测特征并给出工具返回字段解释；最后成功修复重新验收。18回归新增后221 passed in6.13s，diff通过。下一轮fix12必须使用统一修复源码两份副本顺序重测，GraphDB也需重跑，不以fix11已通过替代最终源码验收。

用户要求数据库之外完全一致，已再次核对整个sack目录265个非运行产物文件两边哈希相同、模型config.json与共用启动脚本一致、两区原始数据完全相同，262不可变清单源码无差异。保存sack-titanic-fix11-backend-source-parity-20261004.json；状态JSON/缓存/日志及生成运行产物单独处理。不会为TuGraph写后端专用补丁。


Fix12 prepared from one source package, manifest SHA256 c79efd84db2061d7ffcf312837e562c2f5345bee651c0b2f83a86cc4c8a54d96. Both real preflights passed, including readonly validation of actual fix11 single-class predictions and rejection of its featureless processed train/test outputs; previous CSV, JSON, IQR, polynomial, conditional, complexity mapping, profile and eight retrieval checks also passed. Profile covers train12/test11 columns with finite300-dimensional vectors. Both entire sack directories contain266 matching non-runtime files (including shared configuration), all262 immutable manifest sources also match the final local source. Raw input hashes, model config and common launch script match; backend selection and isolated runtime paths differ. Saved fix12 backend parity evidence and refreshed preflight report.

GraphDB started2026-10-04T12:29:43.923697+00:00 (20:29:43 Beijing), MainPID989734, active and RuntimeMaxUSec=6h. TuGraph not started. DriverPID989341 completed both preflights before starting GraphDB. Full strict acceptance pending; no commit/push yet. New acceptance additionally requires nonempty matching predictor columns and891/418 processed train/test rows. Fix11 GraphDB old accepted result is historical evidence only: later checks found featureless processed outputs, so it does not meet the final strengthened acceptance.


Fix12 GraphDB check2026-10-04 21:14 Beijing: real preliminary eda_insight.json parsed and recursively checked, no unknown/None/nonfinite values. Validation completeness5.0, unknown_fields_count0, missing_schema_fields=[], missing_tool_outputs=[]. IEDA started21:12:38; service989734 active with6h limit, no final exit or completeDSP/prediction acceptance. TuGraph not started.


Fix12 GraphDB check2026-10-04 21:34 Beijing: independent EDA completed, titanic status success. Both real preliminary/deep insight JSON recursively verified without unknown/None/nonfinite values; both validation completeness5.0, unknown0, missing schema fields=[], missing required tool outputs=[]. DSP now running Preliminary Exploratory Data Analysis retrieval. MainPID989734 active, no final exit or completeDSP/processed predictors/prediction acceptance. TuGraph not started.


Fix12 GraphDB check2026-10-04 22:44 Beijing: Feature Engineering outputs independently read, processed train891/test418 rows, each38 real predictors excluding ID/target, feature sets match, both files have0 missing cells. This resolves the featureless output seen in fix11 for this GraphDB run; it is not final acceptance. Model Building, Validation, and Prediction started22:39:32; serviceactive with6h limit, no final exit or418prediction acceptance. TuGraph not started.


Fix12 GraphDB final acceptance: nonintentional exit0 at2026-10-04T15:04:33.741031+00:00 (23:04:33 Beijing), runtime2h34m49s. Actual accept.py accepted=true/errors=[]: completeDSP, independentEDA success and both insights complete/unknown0/no nonfinite values, all profile train12/test11 columns with finite300-dimensional vectors, cleaned/processed data and38 matching real predictors with891/418 rows, valid418binary predictions matching original testIDs, original raw hashes unchanged. Standardized submission id/Survived differs from originalKaggle PassengerId/Survived; original_submission_schema_matches=false, noKaggle submission. Saved sack-titanic-fix12-graphdb-acceptance-20261004.json.

Rechecked262 immutable sources in both server copies and local final workspace: no mismatches. After GraphDB finished/accepted and TuGraph never-started guard, sequentially started TuGraph once at2026-10-04T15:05:27.178749+00:00 (23:05:27 Beijing), driverPID1016570/MainPID1016572, serviceactive, RuntimeMaxUSec=6h, upper bound2026-10-05 05:05:27 Beijing. Current independentEDA Data Preparation; fullTuGraph acceptance pending. No code changes, commit orpush.
