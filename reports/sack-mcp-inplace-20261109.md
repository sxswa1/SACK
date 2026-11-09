# 原目录运行、Git 部署与历史报告恢复

日期：2026-11-09（北京时间）。业务实现提交：`10602e1b9dd6a5172f8fbd82ff0872db387b78af`。

## 固定目录与 Git

服务及 Codex 启动配置统一指向 `/opt/sack-tugraph-runtime-20261015/repo`，
MCP 独立依赖位于同一运行根目录的 `mcp-venv/`。
HTTP 服务已切换为该仓库代码，监听仍为 `127.0.0.1:8765/mcp`；现有令牌保持不变。
报告从 `repo/data/competitions/<name>/research_report.md` 直接读取。
轻量历史快照保存在 `repo/storage/experiment_reports`，不复制项目、数据和训练环境。

服务器先保存原有代码，再通过 Git bundle 导入并合并功能分支，没有覆盖服务器独有代码：

- 部署分支：`codex/runtime-inplace`。
- 原代码检查点：`3ce15b73e8930faf60b2ae1ca6f00048e5c9357e`。
- 检查点标签：`runtime-before-mcp-inplace-20261109`。
- 部署合并提交：`3736f7895e7b81d0d8b4014d2dbf063b011423f6`。
- 合并后 `git status --short` 为空。

原本未提交的更新已在检查点保留。原 EDA 运行状态文件内容和权限已保留，
从 Git 索引移除并忽略；数据、报告、私有配置不提交。
旧独立 MCP 目录保留为回退资料，已不作为服务或新 Codex 连接的启动目录。

## 已恢复的三个报告

来源均为：
`/opt/sack-tugraph-runtime-20261015/resumes/kaggle-three-qwen38flash-20261030/task-backup/competitions/<name>/research_report.md`。

这三份对应 **2026-10-29 Qwen3.7-Plus** 运行；恢复前核对原队列退出码为 0、
DSP 完成日志、训练执行回执、run_id 和验证分数。原备份保留，报告正文不改写。

| 原目录下的实验名 | 本地验证 | 原内部验收 |
| --- | --- | --- |
| ghouls-goblins-and-ghosts-boo | weighted F1 0.7513900709219858 | 未通过：独立 EDA；训练和预测已完成 |
| spaceship-titanic | accuracy 0.78205865439908 | 通过 |
| playground-series-s4e2 | weighted F1 0.8967132540549873 | 通过 |

每个原始实验目录中新增/恢复：

- `research_report.md`：原始报告全文。
- `report_provenance.json`：来源、代码/模型版本、分数、报告 SHA-256、验收失败项。
- `report_acceptance.json`：原验收记录副本。
- `run_manifest.json`：随后 Qwen3.8-Flash 重跑的真实失败状态（超时），与上述旧报告分开。

因此，MCP 返回这三份报告时 `report_source=workspace`、`is_latest_run=false`；
Ghouls 保留 `acceptance_passed=false`、`eda_status=fail`，不会把训练完成说成完整验收通过。
最新执行状态仍为失败，不冒充旧成功结果。

## 验证

- 本地新增/相关回归：45 passed。
- 原服务器仓库 MCP 回归：45 passed（2.95 秒）。
- 原服务器仓库完整离线回归：317 passed（13.31 秒），包含保留的服务器测试。
- 三份原目录报告与备份的 SHA-256 全部一致，验证分数与用户提供表格一致。
- 服务器 WorkspaceStore 已逐项读取三份报告，验证原文件来源、验收状态及最近失败运行。
- 部署后 HTTP 两客户端并发读取 Spaceship 报告成功，返回正文哈希与原文件一致，错误令牌和无令牌返回 401。
- 更新后的 Codex 启动配置已成功取回原 Titanic 报告。后续三报告本机复验遇到 SSH 握手超时；服务器验证已完成，SSH 保活代理继续自动重连。

目录列表已直接展示原目录中的 6 个实验：Ghouls、house-prices、house-prices2、
Playground S4E2、Spaceship Titanic、Titanic。两个没有核验最终报告的 house-prices 目录
仍可查询状态，不伪造报告。Titanic 原先归档的历史报告保持可读。

新客户端连接使用已更新的固定目录启动配置；已有长连接需刷新 MCP 连接以加载新版目录查询。
配置与后续 Git 更新命令见 [部署指南](../docs/mcp-reports.md)。
