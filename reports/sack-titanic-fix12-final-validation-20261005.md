# Titanic 第十二版最终验证

同一源码的 GraphDB 与 TuGraph 已顺序完成独立 EDA 和完整 DSP，真实 `accept.py` 对两边均返回 `accepted=true`、`errors=[]`。本地最后一次全套回归为 **221 passed**；交付前已确认业务源码没有改变，`git diff --check` 通过。

| 后端 | 开始（北京时间） | 结束（北京时间） | 退出 | 预测特征 | 预测 |
| --- | --- | --- | --- | --- | --- |
| GraphDB | 2026-10-04 20:29:43 | 2026-10-04 23:04:33 | 非主动 0 | train/test 各 38 个，集合相同 | 418 行二分类 |
| TuGraph | 2026-10-04 23:05:27 | 2026-10-05 01:37:21 | 非主动 0 | train/test 各 12 个，集合相同 | 418 行二分类 |

两边均核对完整 DSP 完成、独立 EDA success、两类洞察可解析且无 unknown/None/非有限值、缺字段和必需工具结果；profile train 12/test 11 列全覆盖，所有列 label/content 向量均为 300 维有限数值；cleaned/processed 数据有效，processed train 891/test 418 行且含匹配真实预测特征；预测 ID 与原始 test 一致，原始数据哈希不变。任务始终顺序执行，每个服务上限六小时，两边均提前正常结束。

两份目录 **266 个非运行产物文件**哈希相同；两后端的 **262 个不可变清单源码**与本地待提交源码一致。模型配置、原始输入和共用启动脚本一致；后端选择/连接参数、隔离运行路径以及状态 JSON/缓存/日志/生成产物单独处理。准备清单含 263 文件，运行状态 competition_process_status.json 变化后不作为不可变源码比较。

源清单 SHA256：`c79efd84db2061d7ffcf312837e562c2f5345bee651c0b2f83a86cc4c8a54d96`。完整实验及旧失败日志保留于 `/opt/sack-backend-compare-20261004-fix12` 和各历史隔离目录。没有恢复旧实验或修改原工作区用户内容。

预测表头为标准化 **id/Survived**，与原始 Kaggle **PassengerId/Survived** 不同，两边 `original_submission_schema_matches=false`。没有提交 Kaggle，也没有验证隐藏集准确率。两个随机模型工作流通过不能证明所有后端行为或输出全面等价。第十一版 GraphDB 旧验收放行无预测特征数据，最终第十二版已额外检查，旧结果只作历史证据。

证据：

- [最终精简证据](sack-titanic-fix12-final-evidence-20261005.json)：顺序、实际退出、真实验收、原始数据和源码一致性。
- [GraphDB 严格验收](sack-titanic-fix12-graphdb-acceptance-20261004.json)。
- [TuGraph 严格验收](sack-titanic-fix12-tugraph-acceptance-20261005.json)。
- [完整源码一致性](sack-titanic-fix12-backend-source-parity-20261004.json)。
- [实际预检](sack-titanic-fix-preflight-20261002.json)：当前内容为第十二版，两边含真实 profile/检索及历史失败工具和输出重放。
- [历史验证过程](sack-titanic-fix-validation-20261002.md)：保留失败、修复、六小时调整和阶段证据。

本地测试命令：

```sh
PYTHONPATH=/private/tmp/sack-feature-test-deps PYTHONDONTWRITEBYTECODE=1 \
/Users/mac/miniconda3/envs/sack-tugraph-test/bin/python -m pytest -q -p no:cacheprovider sack/knowledge/tests
```

PR：[sxswa1/SACK#1](https://github.com/sxswa1/SACK/pull/1)，head `codex/titanic-workflow-fix`、base `codex/tugraph-migration`。逐项代码修改和理由在 PR 正文中；保持 Draft，不合并。
