# SACK 实验报告 MCP

服务直接查询原有实验工作目录，供 WorkBuddy、Codex 按实验名查状态、获取报告。
支持 Streamable HTTP 和 stdio；查询不运行实验、不调用模型、不连接知识数据库。

公网接入地址：`https://mcp.bdilabagent.cn/sack/mcp`。
客户端使用 Streamable HTTP 和自己的 Bearer 令牌直接连接，无需 SSH 或本地端口转发。
客户端操作见 [WorkBuddy / Codex 配置指南](mcp-client-setup.md)，
网关部署见 [公网 MCP 配置](mcp-public.md)。

## 固定运行目录

服务器统一使用 `/opt/sack-tugraph-runtime-20261015/`，不再按日期复制项目：

```text
/opt/sack-tugraph-runtime-20261015/
├── repo/                         # 同一个 Git 仓库，原地更新代码
│   ├── sack/
│   ├── data/competitions/<name>/  # 同名实验始终使用原工作目录
│   │   ├── research_report.md
│   │   ├── run_manifest.json      # 新版流水线的当前运行状态
│   │   ├── report_provenance.json # 恢复历史报告时的来源及验证分数
│   │   └── report_acceptance.json # 保留原验收结论，包括失败项
│   └── storage/experiment_reports/ # 轻量报告历史，不是项目/训练副本
├── mcp-venv/                     # 独立 MCP 依赖，避免影响训练环境
├── private/mcp-tokens.json
└── sack-python                   # 原有实验运行入口
```

Git 管理代码、依赖声明和文档。`data/`、`storage/`、`.env`、API 密钥及
`sack/competition_process_status.json` 是本地运行产物，不提交到 Git。
首次运行缺少 EDA 状态文件时按空状态处理，之后自动创建。

## 查询规则

| 工具 | 参数 | 行为 |
| --- | --- | --- |
| `list_experiments` | keyword、cursor、limit | 从原始工作目录列出实验，每个实验一行，包括没有报告的任务 |
| `get_experiment_status` | experiment_name、run_id? | 当前运行状态、可用报告、最近 20 次记录 |
| `get_experiment_report` | experiment_name、run_id?、offset、max_chars | 优先读取原目录中已核验的报告，旧版本必要时从报告历史读取 |

实验名精确对应 `data/competitions/<name>`，关键词搜索不区分大小写。
`SACK_EXPERIMENT_ROOT` 可以指定其他实验父目录，默认使用仓库原有 data/competitions。
列表按实验名排序，limit 为 1–100，使用返回的 next_cursor 续读。
仅在历史目录中有记录而原始实验目录已不存在的任务，不自动冒充当前工作目录。

新版流水线把当前状态原子保存到实验目录的 run_manifest.json。
没有元信息的旧目录也会展示，但状态为 unknown；单独存在报告文件不代表已核实完成。
已恢复历史报告的 report_provenance.json 记录其 SHA-256、原运行时间、训练和验收结果。
读取前核验报告正文；每页 1–50000 个 Unicode 字符，全文上限 8 MiB。
后续页必须固定返回的 run_id 和 next_offset；工作目录重跑后，已归档的旧页仍可读取。

`latest_run` 表示当前/最近一次执行，`available_report` 表示可读取的报告版本。
最近一次执行失败时，仍能返回此前完成的报告，并明确 is_latest_run=false。
报告的 status=succeeded 表示 DSP 已完成并生成报告；`acceptance_passed` 是独立验收结论。
例如 Ghouls 的训练报告可读，但 acceptance_passed=false、eda_status=fail，必须明确展示失败原因。
验证分数是本地留出集指标，不是 Kaggle 排行榜分数。

历史报告恢复时保留原文和原备份，核对训练执行回执、分数、退出码和 DSP 完成日志，
把证据写在对应工作目录；不把旧报告标记成最近一次重跑的结果。
没有完成证据的文件保持未核验，报告接口返回 REPORT_NOT_READY。

## 新实验与报告历史

继续使用原入口，例如：

```bash
/opt/sack-tugraph-runtime-20261015/sack-python -m sack run --competition titanic
```

工作目录始终是原 repo/data/competitions/titanic，不创建新的项目或训练副本。
运行开始时取得同名实验目录锁，生成唯一 run_id；报告仍写入该目录的 research_report.md。
只有整条流水线成功返回且本次实际生成了非空报告，才标记 report_ready=true。
失败和中断会记录状态；旧成功报告保留在 storage/experiment_reports/<name>/<run_id>。
该目录只存报告快照和 JSON 元信息，不复制数据、模型环境或整个仓库。

SIGKILL/断电可能遗留 running 状态。确认旧进程已退出后在原服务器执行：

```bash
cd /opt/sack-tugraph-runtime-20261015/repo
../mcp-venv/bin/python -m sack.reporting recover-run --experiment titanic \
  --run-id <run_id> --workspace /opt/sack-tugraph-runtime-20261015/repo/data/competitions/titanic
```

恢复检查主机、工作目录和目录锁，不把活跃运行改成中断。
操作员也可以用 `python -m sack.reporting import-report` 导入完整验收通过的其他历史报告；
回执要求 accepted=true、errors=[]、exit_code=0、report_sha256 和 completion_basis。
该命令不是 MCP 写工具；存在独立验收失败的历史报告应保留其原始失败证据。

## 依赖与服务

Python 3.10+，独立安装官方 SDK v1 维护线 mcp==1.28.1，避免升级训练环境：

```bash
cd /opt/sack-tugraph-runtime-20261015/repo
python3 -m venv ../mcp-venv
../mcp-venv/bin/python -m pip install -r requirements-mcp.txt
```

参考[官方 SDK 文档](https://py.sdk.modelcontextprotocol.io/v1/)。
环境变量：

- SACK_EXPERIMENT_ROOT：原实验父目录，默认 repo/data/competitions。
- SACK_REPORT_ROOT：报告历史目录，默认 repo/storage/experiment_reports。
- SACK_MCP_TOKEN_FILE：包含客户端标签到令牌的 JSON 对象，如 workbuddy、codex。
- 或用 SACK_MCP_TOKEN 提供单个令牌；令牌至少 24 字符，多客户端令牌不能相同。

令牌文件只读授权给服务账号，例如 root:sackeda、0640，父目录 0750。
HTTP 没有有效令牌时拒绝启动，所有请求（含初始化）都校验 Authorization。
Host/Origin 校验保持开启；归档与原实验目录中的符号链接和越界路径被拒绝。
服务日志记录标签、工具和结果代码，不记录令牌或报告全文。
令牌权限覆盖配置的整个实验/报告目录，本版未实现按实验分权或 OAuth。

[systemd 配置](../deploy/sack-reports-mcp.service) 使用固定仓库及独立 mcp-venv，
以 sackeda 运行，ProtectSystem=strict 限制服务写入；流水线进程仍可写入原实验目录。
进程内部 HTTP 地址为 http://127.0.0.1:8765/mcp，由 Nginx 发布为上述公网 HTTPS 地址。
本地调试也可使用 SSH 转发：

```bash
ssh -N -L 8765:127.0.0.1:8765 root@60.204.211.83
```

公网部署需要 HTTPS 网关并设置相应 --allowed-host、--allowed-origin。
本机代理应把 loopback 加入 NO_PROXY；stdio 使用操作系统/SSH 身份，不需要 HTTP Token。

## 客户端

WorkBuddy 示例（替换令牌）：

```json
{
  "mcpServers": {
    "sack-reports": {
      "type": "streamableHttp",
      "url": "https://mcp.bdilabagent.cn/sack/mcp",
      "headers": {"Authorization": "Bearer <WorkBuddy令牌>"}
    }
  }
}
```

Codex 使用同一公网 HTTPS 地址，在 ~/.codex/config.toml 中设置：

```toml
[mcp_servers.sack_reports]
url = "https://mcp.bdilabagent.cn/sack/mcp"
bearer_token_env_var = "SACK_MCP_TOKEN"
```

令牌要在 Codex 的运行环境中提供。两个客户端可以同时查询。
修改启动配置后重启 MCP 连接。参考 [WorkBuddy](https://open.workbuddy.cn/docs/connector)、
[Codex](https://developers.openai.com/codex/mcp)。

提示语：“列出 sack_reports 中的实验，并获取 spaceship-titanic 的历史最终报告，说明验收状态。”

## Git 原地更新与测试

服务器保留本地部署分支 codex/runtime-inplace，已有运行修复先保存为 Git 检查点，
再合并功能分支。后续在同一 repo 更新，不创建带日期的项目副本：

```bash
cd /opt/sack-tugraph-runtime-20261015/repo
git fetch origin
git merge --no-edit origin/codex/mcp-experiment-reports
../mcp-venv/bin/python -m pytest -q tests
sudo systemctl restart sack-reports-mcp.service
```

部署前确认没有活跃的实验，先处理代码冲突；不要用强制重置覆盖本地改动。
离线/服务器网络受限时可传输 Git bundle 并 git fetch 该 bundle，再合并同一提交。
回退使用 Git 检查点或已记录的部署提交，不删除或重新复制实验数据。

完整原有回归在训练环境运行：`python -m pytest -q sack/knowledge/tests`。
新增测试只需 MCP 依赖和 pytest==8.3.5，覆盖原目录发现、无报告任务、历史报告、
失败重跑、验收失败保留、目录锁、分页、路径安全及真实 HTTP/stdio 双客户端。

部署后的只读验收：

```bash
../mcp-venv/bin/python scripts/verify_mcp_reports.py \
  --token-file /opt/sack-tugraph-runtime-20261015/private/mcp-tokens.json --experiment spaceship-titanic
```

两个客户端均用官方 SDK 验证，不代表已操作实际客户端界面。
[首次部署记录](../reports/sack-mcp-validation-20261109.md)描述初始独立副本；后续以本指南固定目录为准。
