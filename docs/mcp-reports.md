# SACK 实验报告 MCP

本服务让 WorkBuddy、Codex 等 MCP 客户端按实验名获取已完成的数据科学任务最终报告。
支持同一 HTTP 服务上的独立并发客户端；查询不启动实验、不调用模型、不连接知识数据库。

## 安装与启动

服务只需要 Python 3.10+ 和 `requirements-mcp.txt`。使用独立环境，不安装完整训练依赖：

```bash
python3 -m venv /opt/sack-mcp/venv
/opt/sack-mcp/venv/bin/pip install -r requirements-mcp.txt
export SACK_REPORT_ROOT=/opt/sack-mcp/reports
export SACK_MCP_TOKEN_FILE=/opt/sack-mcp/private/tokens.json
/opt/sack-mcp/venv/bin/python -m sack.mcp
```

HTTP 默认地址 `http://127.0.0.1:8765/mcp`。无有效 Token 配置时拒绝启动。
独立服务与训练进程必须使用同一 `SACK_REPORT_ROOT`（或将其只读挂载给服务）。
SDK 明确锁定官方 v1 维护线 `mcp==1.28.1`，兼容现有 Python 3.10 运行环境；
不使用 v2 API，不自动跨大版本升级。参考[官方 v1 文档](https://py.sdk.modelcontextprotocol.io/v1/)。

使用下面的命令生成不同客户端的令牌，输出仅写入私有文件：

```bash
mkdir -p /opt/sack-mcp/private
python3 - <<'PY'
import json, os, secrets
path = '/opt/sack-mcp/private/tokens.json'
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    json.dump({name: secrets.token_urlsafe(32) for name in ('workbuddy', 'codex')}, stream)
PY
```

运行用户必须能够读取该文件。可使用 `root:<服务用户组>`、`0640` 和父目录 `0750`，
避免给其他用户读取权限。也可用环境变量 `SACK_MCP_TOKEN` 提供单个令牌。
更换令牌后重启服务。服务支持多个令牌，权限范围均为配置的整个报告归档目录；
目前没有按用户/实验划分的权限，也未实现 OAuth。

本地 stdio（由客户端启动进程，无 HTTP 端口，使用操作系统用户权限）：

```bash
python -m sack.mcp --transport stdio
```

## 两个客户端连接同一服务

WorkBuddy 配置示例，替换地址和私有令牌：

```json
{
  "mcpServers": {
    "sack-reports": {
      "type": "streamableHttp",
      "url": "http://127.0.0.1:8765/mcp",
      "headers": {"Authorization": "Bearer <WorkBuddy令牌>"}
    }
  }
}
```

Codex 的 `~/.codex/config.toml`：

```toml
[mcp_servers.sack_reports]
url = "http://127.0.0.1:8765/mcp"
bearer_token_env_var = "SACK_MCP_TOKEN"
```

在启动 Codex 的环境中提供对应令牌；桌面应用也需要能够读取该环境变量。
两个客户端可以同时读取同一 `run_id`，拿到的报告内容及校验值相同。
配置参考：[WorkBuddy](https://open.workbuddy.cn/docs/connector)、
[Codex MCP](https://developers.openai.com/codex/mcp)。

提示语示例：“获取 titanic 实验最近一次成功运行的最终报告，说明对应的运行版本。”

## 服务端与网络

服务器首先监听 loopback。开发或私有部署可使用 SSH 转发：

```bash
ssh -N -L 8765:127.0.0.1:8765 <服务器SSH别名>
```

然后两个本地客户端都连接 `http://127.0.0.1:8765/mcp`。
若本机有 HTTP 代理，应将 loopback 加入 `NO_PROXY`。
远程客户端无法访问其自身的 localhost 来连接服务器；必须保持隧道或使用可达的 HTTPS 地址。

正式域名部署时，在现有 HTTPS 网关代理 `/mcp`，保留 `Authorization` 和 MCP 请求头，
允许 POST/GET/DELETE，并将实际域名加入 Host 白名单：

```bash
python -m sack.mcp --allowed-host sack.example.com --allowed-host '127.0.0.1:*' \
  --allowed-origin https://sack.example.com
```

Host 和 Origin 校验保持开启。服务采用无状态 Streamable HTTP + JSON 响应，
不共享客户端会话或分页游标。GET 可能按 SDK 行为返回 405，这不代表 POST 工具调用不可用。
所有 HTTP 请求都验证令牌，包括初始化和工具发现；stdio 不使用 HTTP 令牌。

仓库提供 [systemd 示例](../deploy/sack-reports-mcp.service)。独立运行用户仅需读取源码、
归档和令牌，不应能修改归档。服务日志记录客户端标签、工具名及结果代码，不记录令牌和报告全文。

## 工具契约

| 工具 | 参数 | 行为 |
| --- | --- | --- |
| `list_experiments` | `keyword=""`, `cursor=null`, `limit=20` | 按实验名搜索，返回逐次运行记录；limit 1–100，按 next_cursor 续读 |
| `get_experiment_status` | `experiment_name`, `run_id=null` | 指定运行或最新运行的状态，同时提供最近成功运行 ID |
| `get_experiment_report` | `experiment_name`, `run_id=null`, `offset=0`, `max_chars=20000` | 获取已发布 Markdown，最多每页 50000 字符 |

名称精确匹配，支持中文、字母、数字、下划线、点和连字符，长度最多 160，首字符必须为字母、数字或下划线。
第一版实验名对应现有 `competition` 目录名。列表按 `(experiment_name, run_id)` 排序，游标是最后一条记录的键；
运行记录可在查询间新增，跨页不是整个目录的事务快照。

不指定 run_id 时获取最近一次成功且已发布的报告；`latest_run` 和 `is_latest_run` 明确指出
是否有更新的运行正在执行或已经失败。客户端必须展示选中的 run_id，避免把历史结果说成本次结果。
状态的“成功”表示流水线完成并发布报告，不代表泛化性能、Kaggle 得分或独立外部验收。

报告返回结构化结果及同内容的 JSON 文本，正文在 `content` 字段，原始 Markdown 不改写。
分页偏移按 Unicode 字符计数。后续页必须复用返回的 `run_id` 和 `next_offset`，
报告完整校验通过后才返回内容。报告全文上限 8 MiB；图表附件和 PDF 不在本版范围。

工具失败返回 MCP `isError=true`，并提供 `error.code/message`。
常见代码：`EXPERIMENT_NOT_FOUND`、`RUN_NOT_FOUND`、`REPORT_NOT_READY`、`INVALID_ARGUMENT`、
`ARTIFACT_MISSING`、`REPORT_INTEGRITY_ERROR`、`UNSAFE_PATH`、`CORRUPT_MANIFEST`。
认证失败为 HTTP 401；SDK 参数校验错误可能只有文本错误内容。

## 新实验的发布流程

```text
storage/experiment_reports/<experiment_name>/<run_id>/
├── manifest.json
└── research_report.md
```

`python -m sack run` 和公开 Python 入口 `run_sack_pipeline` 自动记录运行：

1. 取得实验工作目录锁；同目录并发执行被拒绝。
2. 创建唯一 run_id，原子写入 running 元信息。
3. 最后阶段 Summarizer 将报告写入本次归档，同时保留原工作目录的 research_report.md。
4. 整条流水线成功返回，且本次调用确实生成非空报告后，发布 succeeded/report_ready=true 及 SHA-256。
5. 异常或主动中断记录 failed/interrupted，草稿不对外提供；旧成功版本保持可查。

元信息包含 schema_version、运行状态和 UTC 时间；工作目录/进程信息只用于操作员恢复，不返回给 MCP 客户端。
文件写入采用同目录临时文件 + 原子替换；MCP 进程不写文件。归档应由可信运行用户维护，
不接受不可信用户直接修改目录。归档中的符号链接与越界路径会被拒绝。

SIGKILL、断电等无法执行退出处理。确认原进程已退出后，在原服务器上恢复记录：

```bash
python -m sack.reporting --root /opt/sack-mcp/reports recover-run \
  --experiment titanic --run-id <run_id> --workspace /path/to/data/competitions/titanic
```

恢复先验证原工作目录和主机，再尝试非阻塞取得同一锁；活跃的新式运行不会被误判为已中断。
旧版进程不认识此锁，部署前应让它们结束，避免新旧版本同时操作同一工作目录。

## 历史报告导入

历史导入是操作员命令，不暴露为 MCP 写工具，也不会自动把报告文件存在视为运行成功：

```bash
python -m sack.reporting --root /opt/sack-mcp/reports import-report \
  --experiment titanic --report /path/to/research_report.md
```

无证据时记录为 unknown，不能通过最终报告工具读取。
核实原运行的完成日志、退出码和验收记录之后，操作员制作与报告哈希绑定的 JSON 回执：

```json
{
  "accepted": true,
  "errors": [],
  "exit_code": 0,
  "report_sha256": "<实际报告的SHA256>",
  "completion_basis": "核对的原始完成日志及验收记录标识"
}
```

在导入命令后增加 `--evidence /path/to/receipt.json` 才发布为 succeeded。
回执是可信操作员的完成声明，导入器验证其结构及哈希绑定，不替代业务验收。
相同报告与回执重复导入返回同一个历史 run_id；原报告不修改。
不同历史运行建议使用不同回执，并在 completion_basis 记录原运行标识。
历史记录的 started_at 使用报告文件 mtime 排序，并返回 timestamp_source=report_mtime；
它不是已核实的原运行开始时间，completed_at 留空。

## 测试

```bash
pip install -r requirements-mcp.txt pytest==8.3.5
python -m pytest -q tests
```

覆盖真实 stdio/HTTP 协议、双客户端并发、鉴权、Host/Origin 校验、失败重跑、
分页和历史版本、SHA-256、目录锁、中断恢复、历史证据导入和流水线发布边界。
双客户端用官方 MCP SDK 模拟各自连接；不等于已操作实际 WorkBuddy/Codex UI。
原有回归仍可在完整 SACK 环境运行：`python -m pytest -q sack/knowledge/tests`。

对已经部署的 HTTP 服务做只读验收，可运行：

```bash
python scripts/verify_mcp_reports.py --url http://127.0.0.1:8765/mcp \
  --token-file /opt/sack-mcp/private/tokens.json --experiment titanic
```

令牌文件至少提供两个不同客户端的令牌。脚本验证未授权访问被拒绝、三个工具可发现、
并发客户端读取的报告与发布哈希一致；可用 `--expected-sha256` 再对照原始报告校验。
本次服务器部署与测试证据见 [2026-11-09 验证记录](../reports/sack-mcp-validation-20261109.md)。
