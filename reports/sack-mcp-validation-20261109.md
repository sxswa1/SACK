# MCP 报告服务部署与验证

日期：2026-11-09（北京时间）。实现提交：`93f6bd4a4b2cc435b12d49f078f60ae48b569e01`。
后续提交补充文档和验证证据，并限制测试子进程继承的环境变量；业务实现仍对应上述提交。

## 结果

| 验证 | 结果 |
| --- | --- |
| 本地 Python 3.12 新增回归 | 34 passed |
| 服务器独立 Python 3.10.21 环境新增回归 | 34 passed，2.75 秒 |
| 服务器完整原有离线回归 | 308 passed，13.43 秒 |
| 独立服务环境 pip check | No broken requirements found |
| 部署后的真实 Titanic 报告读取 | 两个独立官方 SDK 客户端同时读取，内容哈希一致 |
| 未带令牌及错误令牌 | 均返回 HTTP 401 |
| 原运行环境配置与代码入口 | 自动加载同一报告归档目录，归档入口可导入 |
| systemd 服务 | active/running，User=sackeda，ProtectSystem=strict |

新增回归覆盖真实 stdio/HTTP 协议、两个客户端并发、工具发现、鉴权、Host/Origin 校验、
失败重跑与草稿隔离、同名实验工作目录锁、中断恢复、历史证据导入、完整性校验、分页和路径越界。
测试使用实际 SDK 传输；没有操作实际 WorkBuddy/Codex 应用界面。
没有发起新的模型请求或完整数据科学训练任务，本轮结论针对报告接口及现有工作流回归。

## 部署位置

- 服务器：`root@60.204.211.83`。
- 独立根目录：`/opt/sack-mcp-20261109/`，源码在 `repo/`，独立依赖在 `venv/`。
- 服务：`sack-reports-mcp.service`，已启用开机启动。
- 监听：`127.0.0.1:8765`，MCP 路径 `/mcp`。
- 归档：`/opt/sack-mcp-20261109/reports/`。
- 私有令牌文件：`/opt/sack-mcp-20261109/private/tokens.json`，root:sackeda，0640。
- workbuddy/codex 使用分别生成的令牌。令牌值、原始报告全文和原运行配置不进入 Git。

本次采用 SSH 隧道供两个本地客户端访问，尚未配置公共 HTTPS 域名：

```bash
ssh -N -L 8765:127.0.0.1:8765 -i ~/.ssh/id_rsa root@60.204.211.83
```

两端配置 URL 均为 `http://127.0.0.1:8765/mcp`，分别使用对应令牌。
详细配置见 [部署指南](../docs/mcp-reports.md)。

## 真实历史报告证据

导入来源：`/opt/sack-backend-compare-20261004-fix12/tugraph/repo/data/competitions/titanic/research_report.md`。
导入前核对同轮 `runtime/acceptance.json`：accepted=true、errors=[]，且
exit_success_and_not_stopped=true、dsp_completion_logged=true。
原报告只读，生成与其 SHA-256 绑定的操作员完成回执后归档。

- 实验名：`titanic`。
- 运行 ID：`legacy_a57f2a83fcce54b70cd3f488`。
- 原报告与两客户端返回正文 SHA-256：`ca9ee45431e5b13e924991bf338730c9e6152f878f2bb937a681c66a4b2fb46f`。
- 正文长度：16997 个 Unicode 字符；两客户端均发现 3 个工具。
- 回执保存在服务器私有目录，不包含模型密钥。

机器可读的接口验收结果见 [JSON](sack-mcp-validation-20261109.json)。

## 现有流水线同步与回退

服务器现有 `/opt/sack-tugraph-runtime-20261015/repo/` 中的 framework 与 Summarizer
同步前哈希与功能分支基线一致。部署前检查该工作目录没有仍在运行的 `python -m sack run`。
仅同步这两个入口文件和新增 `sack/reporting/`，并在已有 `.env` 设置共享的 SACK_REPORT_ROOT。
保留其他配置和原文件权限、所有者。新运行可直接归档报告；旧未归档任务仍需要显式导入。

备份：`/opt/sack-mcp-20261109/private/pipeline-backup/`，包含旧 framework、Summarizer 与 `.env`。
回退时先停止 MCP 服务，在无运行任务时恢复备份文件和 `.env` 的原所有者/权限，
移走新增 `sack/reporting/`。归档目录可保留，不修改原始实验产物。
完整离线回归日志及运行记录保存在独立根目录。
