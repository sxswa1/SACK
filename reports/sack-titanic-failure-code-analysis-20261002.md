# Titanic 两后端测试失败的代码诊断

后续修复已在第十二版完成两后端顺序完整验证，221 项本地回归通过；详见[最终验证摘要](sack-titanic-fix12-final-validation-20261005.md)。本文保留初始失败诊断的代码和证据快照，不代表修复后当前行为。

诊断日期：2026-10-02（北京时间）。依据：已保存的最终对照报告与 JSON、上一轮已读取的 GraphDB 详细运行日志和 Reviewer 文件、原监控聊天保存的 TuGraph 命令输出、当前代码及无模型调用的离线复现。

初次诊断只读取代码和日志，未修改业务代码或重新运行 Titanic。初次补读时 SSH 在密钥交换前被关闭。2026-10-02 SSH 恢复后补读原 TuGraph 日志，已确认数值列导入失败为 `ModuleNotFoundError: No module named 'bitstring'`；后续修复和重测状态另见验证记录。

## 结论与证据等级

| 问题 | 判定 | 影响 |
| --- | --- | --- |
| 上一阶段脚本按固定行数截取，与当前前缀长度不匹配 | 已离线复现，DSP 第 27 行、独立 EDA 第 50 行均为 unmatched ')' | 两类深度分析脚本在真正执行分析前即失败 |
| 第一阶段错误地把最后阶段当作上一阶段 | 代码确认；与后续 EDA 轮次在 Data Preparation 出现拼接错误相符，完整逐次文件来源仍需运行快照 | 重试可能将上轮失败脚本拼回第一阶段 |
| 纯 JSON 被忽略，重新调用模型格式化后评分缺失，被默认置 0 | GraphDB 原始回复、review.json、日志和上一轮离线复现确认 | 实际代码执行和单元检查成功，阶段仍被判失败 |
| JSON 返回列表却按字典使用 | GraphDB 第三轮异常堆栈确认 | Reviewer 直接抛 TypeError |
| Fail 状态返回 None，失败日志继续访问其 phase/score | 两边日志与代码确认 | 产生二次异常，遮蔽原阶段失败 |
| 数值列处理异常后跳过，profile 不校验列覆盖 | 旧日志确认缺少 bitstring，数值 profile 模块导入失败 | 不完整 profile 仍被保存并用于检索 |
| profile 扫描整个目录、当前 profile 数据源指向独立 EDA 工作区 | 启动准备脚本、日志路径、五表 profile 输出确认 | 将标准化表、清洗表和提交模板混入同一个画像，且数据可能早于最终 DSP 输出 |
| 多层重试与额外模型格式化请求耗时 | 代码与阶段时间确认；未计算各环节精确占比 | TuGraph 达到整个服务四小时上限后终止 |

## 1. 语法错误由拼接代码稳定产生

`sack/Agents/agent_developer.py:87` 的 `_generate_code_file()` 读取上一阶段完整包装脚本，删除末尾入口，然后根据工具数量按固定偏移截取：

```python
previous_code = previous_code[8 + 2 + len(previous_tools):]
# 无工具时为 [8 + 1:]
```

但 `sack/Prompts/prompt_developer.py:1` 的 `PREFIX_IN_CODE_FILE` 已包含完整路径搜索循环、导入段、函数定义以及函数内基础导入。固定截取位置落在导入段内部，留下最后两个工具名、右括号和旧函数定义。

随后新前缀与残留片段再次拼接。即使当前模型返回完全正确的代码，生成脚本也会有多余右括号和重复函数。

### 离线验证

以 AST 提取并调用当前实际 `_generate_code_file()` 和 `_delete_output_in_code()`，按实际配置先生成具有七个清洗工具的上一阶段脚本，再分别生成 DSP 深度 EDA 与独立 IEDA 脚本。只用 `ast.parse()` 检查，不执行生成代码、不导入分析依赖、不调用模型：

```text
DSP unmatched ')' line 27 function_defs 2
EDA unmatched ')' line 50 function_defs 2
```

这与 TuGraph 最终 `deep_eda_run_code.py:27`、GraphDB 独立 EDA `deep_insight_extraction_run_code.py:50` 的错误位置一致。

调试为什么不能解决：`agent_developer.py:294` 传给调试器的是当前模型代码块，以及上一阶段的 `single_phase_code.txt`；真正执行的是加上前缀、截取片段后的完整脚本。调试器不能直接修改框架产生的错误片段，修好当前代码后下一次生成仍插入同样的残留内容。

建议：使用明确阶段片段或 AST 提取函数主体，移除固定行数截取；在提交执行前检查最终脚本语法，并把最终脚本及其来源交给调试器。

## 2. 第一阶段存在负索引回绕

`sack/state.py` 的 `get_previous_phase(type='code')` 在通用分支返回 `phases[current_phase_index - 1]`。Data Preparation 的索引为 0：

```text
GetEDAInsight 模式 -> IEDA Insight Extraction
DSPipeline 模式 -> Model Building, Validation, and Prediction
```

初次运行没有末阶段代码时不会触发导入；独立 EDA 第一轮已生成失败的深度脚本后，第二轮仍使用原工作区，从 Data Preparation 重来。此时 `_is_previous_code()` 可发现末阶段代码，并把它误认为前驱。GraphDB 后续 Data Preparation 出现 `unmatched ')'` 与此路径相符，但不能在没有逐次脚本快照的情况下认定每一次该阶段失败都由此引起。

建议：第一阶段明确没有前驱；重试限定本轮有效产物，记录产物所属运行和成功状态。

## 3. 回复格式与评分状态处理不可靠

`sack/Agents/agent_base.py:232` 的 `_parse_json()` 首先只匹配 Markdown JSON 围栏，不直接解析整个回复；合法纯 JSON 也会触发模型重组。原模式还是贪婪匹配，多块 JSON 也可能合并成无效内容。重组提示没有指定 Reviewer schema，解析器也不验证返回值是否为字典。

GraphDB 最后一轮 Reviewer 原始内容分别给 Planner 4、Developer 5。原文均是合法纯 JSON，没有围栏。日志记录两次重新格式化请求；保存的 review.json 却缺少有效 Developer 提取结果，随后 `_merge_dicts()` 在 `agent_reviewer.py:69` 用 `setdefault(agent_name, 0)` 补齐。

上一轮已直接解析服务器原始回复并调用原合并函数，正确得到 Planner 4、Developer 5。因此原始评分、名称大小写和正常合并规则不是这次丢分的原因。重组后的中间回复没有落盘，不能进一步确定是嵌套、字段名、类型还是内容发生变化。

`State.set_score()` 发现 Developer 为 0，直接将阶段分数设为 0。三轮阶段机会耗尽后，DSP 判 Fail。这里把格式化/解析失败当成实际评审不通过。

另一个已发生异常：`agent_reviewer.py:118` 访问 `reply['final_answer']`，只捕获 KeyError；当 JSON 实际是列表时抛出 TypeError。GraphDB 第三轮独立 EDA 的堆栈明确到达这里。

Markdown 解析日志需要单独理解：`_parse_markdown()` 没找到围栏时会记录 ERROR，但返回原文。这条日志本身不证明对应阶段已经失败。

建议：先直接解析 JSON，再提取代码块；按角色校验 schema；只针对格式问题进行有限重试，保留每一步原始/解析/规范化结果；解析失败设置独立状态，不能补成真实评审 0 分。

## 4. 失败状态的二次异常

`sack/sop.py:125` 在阶段未通过且耗尽机会时返回 `('Fail', None)`；`sack/get_history_edainsight.py:94` 接收该结果后，失败日志仍访问 `new_state.phase` 和 `new_state.score`。于是两边都出现 `NoneType.phase`。

这是失败后的记录缺陷，不是最先导致生成代码失败的原因。外层随后又从 Data Preparation 重试，导致有效上下文丢失、旧文件仍在，且日志文件以覆盖模式打开。

建议：保留失败的原 State，或返回含阶段、分数、异常和产物状态的结构；日志按运行/尝试分开保存。

## 5. TuGraph profile 的列遗漏与数据范围

真实新竞赛 profile 走 `sack/knowledge/api/utils.py` 的 `profile_single_competition()`。每列依次执行读取、类型转换、细粒度类型判别、ProfileCreator 工厂、统计与嵌入。整个列处理过程被 `except Exception` 包住，打印异常、跳过该列，然后继续追加表并返回竞赛 profile。

`sack/knowledge/api/api.py:364` 的验证只检查几个顶层字段和已保留列的 embedding 字段。它不比较源 CSV 列数，也没有要求关键数值列存在，因此少了大批列仍显示生成成功。

监控保存的 profile 只保留 21 列，主要为字符串类和二值 Survived；Age、Fare、Pclass、SibSp、Parch、id 被跳过。代码中二值整数会走 BooleanProfileCreator，其余整数/浮点走需要加载 PyTorch 模型的 Int/FloatProfileCreator，再计算统计和数值嵌入。因此现象指向共享的数值处理分支，不能把它当作 TuGraph 查询丢列。

SSH 恢复后，旧日志明确记录 Age、Fare、Parch、Pclass、SibSp、id 的工厂方法在导入 Int/FloatProfileCreator 时，经 NumericalProfileCreator 的 `import bitstring` 抛出 `ModuleNotFoundError: No module named 'bitstring'`。因此这些列是在本地模块导入阶段失败，尚未执行数值模型加载或嵌入，也不是 TuGraph 查询丢列。旧 utils 捕获并跳过异常，使依赖缺失进一步变成“生成成功但列不完整”。

另一个已确认问题：`_list_competition_csv_files()` 优先返回目录根层全部 CSV，不区分 train/test、cleaned_* 和 sample_submission。真实五张表均进入 profile。

对照准备脚本 `/private/tmp/sack-backend-compare-20261001/prepare.py` 将 `storage/current_comp/kaggle/titanic` 链接到独立 EDA 工作区。profile 日志路径也在这个链接下。独立 EDA 最终失败后，DSP 在另一工作区重新准备/清洗数据，但生成 profile 的 API 仍从 current_comp 路径读取；保存到 DSP 目录只是 persist_path，不会改变输入源。最终 profile 的大写列名与 DSP 最终小写表头不同，也说明不能把它视为最终 DSP 数据的完整画像。

建议：保存每列失败原因和成功覆盖率；关键列失败时拒绝作为有效完整画像；显式选择数据集版本和 train/test 输入，明确模板及派生数据是否参与，并绑定 profile 与输入文件哈希。

## 6. 超时与洞察不完整

TuGraph 20:02:11 开始，独立 EDA 三轮失败后到 22:08:28 才回退 DSP，已经消耗约 2 小时 6 分钟。23:37:52 进入 DSP 深度 EDA，最后仍在修复语法错误，00:02:12 被服务的 RuntimeMaxSec=14400 终止。最终输出为 timeout、TERM，不是正常完成。

代码有外层三轮完整 EDA、阶段三轮迭代、Developer 多次生成/调试，以及每轮定位、修复、合并的多次模型请求；纯 JSON 误判再增加额外请求。HELP 分支会减去一次 round 后再加回来，求助重生成不消耗同一个执行尝试计数；不能把 max_tries 看成严格的总模型调用次数上限。现有证据支持反复处理框架错误消耗时间，尚未精确分摊各模块耗时。

GraphDB 初步洞察的两个 unknown 对应正态性、多峰性字段。validation 只根据洞察字段完整程度标记缺少输出，不足以区分工具未调用、未打印和 Summarizer 未提取。EDASummarizer 保存 validation，但没有将其完整度纳入阶段评分；因此 EDA 提取成功与洞察完整不是同一验收条件。

独立深度 EDA 代码失败时，EDASummarizer 会跳过总结，解释了两边深度洞察 JSON 都没有生成。DSP 深度 EDA 与独立 IEDA 属于两条不同工作流，DSP 推进到深度分析不会自动证明前面的洞察 JSON 已补齐。

## 建议修复顺序

1. 固定行数拼接、第一阶段前驱及最终脚本语法校验。
2. JSON schema 解析与独立的解析失败状态，保留中间回复。
3. 失败 State 返回与重试产物隔离。
4. profile 数值异常堆栈、列覆盖率与输入版本选择。
5. EDA 完整性门控及整个工作流的总请求/时间预算。
6. GraphDB 公共 EDA API 的 dict/DataFrame 契约差异单独修复；此前预检证明存在，但不是已确认的本轮退出根因。

先用保存回复和固定代码片段进行无模型调用的回归验证，再决定完整任务验证。迁移检索验证与完整流程验收应保持独立；本轮错误证据不支持归因于迁移，也不支持全面等价结论。
