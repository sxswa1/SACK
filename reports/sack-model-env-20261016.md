# 模型名称迁入 .env（2026-10-16）

状态：模型选择已集中管理，服务器同步及相关验证通过；未重跑 house-prices 或 Titanic 完整工作流。

## 配置入口

模型选择统一在 `sack/model_config.py` 中解析，启动时继续由包引导自动加载源码根目录的 `.env`，已有进程环境优先。没有配置时使用模块中的默认模型；显式构造参数优先于角色默认值。空白模型配置会报出变量名，不静默落回旧模型。

| 配置键 | 默认值 | 用途 |
| --- | --- | --- |
| `SACK_MODEL_GENERAL` | `qwen-plus` | Reader、Planner、Reviewer、Summarizer、Retriever、知识要素提取的默认模型 |
| `SACK_MODEL_CODER` | `qwen3.7-plus` | Developer、EDADeveloper、调试与 LLM 辅助测试的默认模型 |
| `SACK_MODEL_VISION` | `qwen3.6-flash` | 图片描述与读取 |
| `SACK_MODEL_EMBEDDING` | `text-embedding-v3` | 工具文档 Chroma 嵌入，保留 1024 维参数 |
| `SACK_MODEL_KNOWLEDGE_EMBEDDING` | `Qwen3-Embedding-0.6B` | 旧知识嵌入客户端的独立契约，不替换历史本地模型资产 |

可选的 `SACK_MODEL_READER/PLANNER/REVIEWER/SUMMARIZER/RETRIEVER/KNOWLEDGE` 分别覆盖 GENERAL；`SACK_MODEL_DEVELOPER/DEBUG/TEST` 分别覆盖 CODER。模板列出这些覆盖键，默认保持继承，避免修改 CODER 后其他角色仍固定在旧名称。

## 调用与接口路由

- SOP、Retriever、Developer 中的调试/测试工具、图片工具、图片读取函数、工具嵌入与知识 LLMUsage 均使用集中配置。
- 通用、代码/调试/测试、视觉请求分别使用 `api_key.txt` 第 2、3、4 行接口；由调用角色显式路由，相同模型 ID 也可使用不同接口。
- 修复图片工具设置的模型未传到实际图片读取请求的问题，旧知识图片辅助函数复用相同入口。
- 保留仅传模型名的 APIHandler 调用兼容性；新模型可按环境配置识别其接口。
- 模型不存在的 404 直接保留原异常，不对相同模型重试五次；其他可重试异常耗尽后重新抛出保存的原始错误，修复 `UnboundLocalError` 遮蔽根因的问题。
- 模型名配置不等于任意供应商参数适配。切换工具嵌入模型应验证 1024 维契约并重建对应 Chroma 缓存；本次保留原嵌入模型。

## 服务器部署

- 项目：`/opt/sack-tugraph-runtime-20261015/repo`。
- 实际配置：`/opt/sack-tugraph-runtime-20261015/repo/.env`。
- 入口：`/opt/sack-tugraph-runtime-20261015/sack-python`。
- 备份：`/opt/sack-tugraph-runtime-20261015/backups/model-env-20261016-154605`。备份包含私有配置，目录权限为 0700；未上传到仓库。
- `.env` 补入 GENERAL、CODER、VISION、EMBEDDING，其他角色覆盖键以注释方式提供；所有既有配置保留，文件权限仍为 0600。
- 部署清单：`.runtime/model-env-deployment-20261016.json`。
- 验证记录：`.runtime/model-env-verification-20261016.json`。
- 源包 SHA-256：`66d59b84e036db839b47972303a7b803d39ce2ac351efe324a00437d44ccba5b`。

部署前核对改动文件的旧哈希并检查任务状态；未覆盖用户独立修改，也未修改历史实验目录、数据库、原始输入、Key 或账号密码。文件同步带备份及写入异常回滚，未重启或启动完整任务。

## 验证范围

- 本地模型配置、路由与已有相关回归：50 passed。
- 服务器现有运行环境下完整 `sack/knowledge/tests`：269 passed，7.51 秒，无模型请求。
- 真实构造 Reader、Planner、EDAPlanner、Developer、EDADeveloper、Reviewer、EDAReviewer、Summarizer、EDASummarizer，核对配置模型与 general/coder 接口角色，无生成调用。
- 部署前分别以最小文本请求确认 `qwen3.7-plus`、`qwen3.6-flash` 可调用。
- 部署后代码模型通过真实 APIHandler 请求，视觉模型通过 128×128 单色图片输入正确识别蓝色；两次请求使用小输出上限与禁用思考配置。
- 本轮最小生成验证共 4 次。没有执行完整案例，因此不将这些检查表述为新模型下的端到端成功或预测质量结论。

模型与接口配置更改后需启动新进程。服务器私有 `.env` 不提交 GitHub；维护者可用 `.env.example` 创建自己的配置。
