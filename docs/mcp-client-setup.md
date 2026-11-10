# SACK MCP 配置指南：WorkBuddy 与 Codex

更新日期：2026-11-10。本文用于连接已部署的 SACK 实验报告服务。

配置完成后，可以在 WorkBuddy 或 Codex 中按实验名查询运行状态、读取最终报告。
两个客户端可以同时连接。客户端通过公网 HTTPS 访问，无需 SSH、端口转发或安装项目的 Python 依赖。

## 1. 准备地址和访问令牌

| 配置项 | 填写内容 |
| --- | --- |
| 服务地址 | `https://mcp.bdilabagent.cn/sack/mcp` |
| 传输方式 | Streamable HTTP |
| 身份验证 | Bearer Token，随 `Authorization` 请求头发送 |
| WorkBuddy 服务名 | `sack-reports` |
| Codex 服务名 | `sack_reports` |

向服务管理员领取对应客户端的访问令牌：WorkBuddy 使用 WorkBuddy 令牌，Codex 使用 Codex 令牌。
这里需要的是 **SACK MCP 访问令牌**，与 OpenAI API Key、模型平台密钥和 SSH 密钥无关。
当前令牌可读取服务配置范围内的所有实验及报告，两个客户端的令牌分别管理。

**只填写 URL 会被拒绝访问。** 当前服务使用静态 Bearer 认证，尚未提供 OAuth 登录流程。
请求头的完整格式为：

```text
Authorization: Bearer <访问令牌>
```

替换示例中的整个 `<访问令牌>`，不保留尖括号；`Bearer` 后保留一个空格。
如果客户端提供专门的“Bearer Token”输入框，只填写令牌本身；如果填写自定义请求头，则填写完整的 `Bearer <访问令牌>`。
文档中的令牌都是占位符，实际令牌仅保存在客户端私有配置中。

## 2. WorkBuddy 配置

### 打开自定义连接器

1. 打开 WorkBuddy，进入左侧的“专家·技能·连接器”，选择“连接器”页签。
2. 点击“自定义连接器”，进入 MCP 配置入口。不同版本的按钮名称可能略有差异，以客户端显示为准。
3. 为 SACK 添加以下配置；如果已存在同名服务，编辑该条目并保留其他服务配置。

入口说明见 [WorkBuddy 官方连接器使用指南](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Connector)。

### 填写 JSON 配置

将 `<WORKBUDDY_TOKEN>` 替换为管理员提供的 WorkBuddy 令牌：

```json
{
  "mcpServers": {
    "sack-reports": {
      "type": "streamableHttp",
      "url": "https://mcp.bdilabagent.cn/sack/mcp",
      "headers": {
        "Authorization": "Bearer <WORKBUDDY_TOKEN>"
      },
      "timeout": 60000
    }
  }
}
```

WorkBuddy 的传输类型字段按示例使用 `streamableHttp`，`timeout` 的单位为毫秒。
如果界面按字段填写，则选择 Streamable HTTP，并将 `Authorization` 添加到请求头中。
字段格式参考 [WorkBuddy 官方 MCP 配置说明](https://open.workbuddy.cn/docs/connector)。

### 保存并启用

保存配置，启用或重新连接 `sack-reports`。如果出现信任或工具调用提示，核对服务名称和只读查询用途后按需允许。
在新任务的连接器选择中启用该服务，然后输入：

```text
请使用 sack-reports，列出目前有哪些实验，并说明哪些实验已有可读取的最终报告。
```

## 3. Codex 配置

### 编辑用户配置文件

本指南使用用户级配置，默认路径如下；设置了 `CODEX_HOME` 时，以其对应的配置目录为准。

| 系统 | 默认文件位置 |
| --- | --- |
| macOS / Linux | `~/.codex/config.toml` |
| Windows | `%USERPROFILE%\.codex\config.toml` |

同一 Codex 主机上的桌面客户端、CLI 和 IDE 扩展共享 MCP 配置；换到其他电脑或远程执行环境时，需要分别配置和检查网络。
参考 [OpenAI Docs：MCP 连接配置](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。

在 `config.toml` 中添加以下内容，将 `<CODEX_TOKEN>` 替换为 Codex 令牌：

```toml
[mcp_servers.sack_reports]
url = "https://mcp.bdilabagent.cn/sack/mcp"
http_headers = { Authorization = "Bearer <CODEX_TOKEN>" }
enabled = true
startup_timeout_sec = 30
tool_timeout_sec = 60
enabled_tools = ["list_experiments", "get_experiment_status", "get_experiment_report"]
```

如果已存在 `[mcp_servers.sack_reports]`，直接编辑该段，避免重复声明。
从旧 SSH / STDIO 配置切换时，移除该条目原有的 `command`、`args`、`env`、`env_vars`、`cwd` 等进程启动字段，使用上面的 HTTP 配置。
其他 MCP 服务的配置继续保留。

`http_headers` 是 Codex 的请求头字段名；WorkBuddy 使用 `headers`，两者不能直接互换。
在 macOS / Linux 上，可将用户配置权限限制为仅自己读写：

```bash
chmod 600 ~/.codex/config.toml
```

### 重新加载连接

保存后，在 Codex 的“设置 → MCP servers”中找到 `sack_reports`，点击 Restart / 重启。
如果当前版本未提供重启按钮，可退出并重新打开客户端，再新建对话。
此服务使用配置中的令牌认证，无需执行 `codex mcp login sack_reports`；该命令用于 OAuth 登录。

在终端已安装 Codex CLI 时，也可查看配置列表：

```bash
codex mcp list
```

列表中出现 `sack_reports` 只能说明配置被识别，实际工具调用成功才表示接入完成。
在对话中输入：

```text
请调用 sack_reports 的 list_experiments，列出目前有哪些实验。
```

### 可选：从环境变量读取令牌

如果已有统一的环境变量管理，可以将上述 `http_headers` 一行替换为：

```toml
bearer_token_env_var = "SACK_MCP_TOKEN"
```

`SACK_MCP_TOKEN` 的值只放令牌本身，不添加 `Bearer ` 前缀。
确保它在 **启动 Codex 的进程环境** 中存在；在一个终端里设置变量，不代表从桌面图标启动的客户端也能读取。
固定请求头和环境变量两种方式选择一种即可。字段定义见 [OpenAI Docs：配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)。

## 4. 验证连接与读取报告

建议在两个客户端中分别完成以下操作；提示语里的服务名按客户端选择 `sack-reports` 或 `sack_reports`。

| 验证步骤 | 可直接发送的提示语 |
| --- | --- |
| 查询实验 | 请通过 SACK MCP 列出所有实验，并在有下一页时继续查询。 |
| 查询状态 | 请查询 spaceship-titanic 的运行状态，分别说明最近一次运行和可读取的报告版本。 |
| 获取报告 | 请读取 spaceship-titanic 的最终报告，展示 run_id、验收结论和报告正文；有分页时读取完整内容。 |

可用工具及其作用：

| 工具 | 主要参数 | 返回内容 |
| --- | --- | --- |
| `list_experiments` | `keyword`、`cursor`、`limit` | 原实验目录中的任务列表，包括尚无最终报告的实验；用 `next_cursor` 续查 |
| `get_experiment_status` | `experiment_name`、可选 `run_id` | 当前或指定运行的状态、可用报告及运行记录 |
| `get_experiment_report` | `experiment_name`、可选 `run_id`、`offset`、`max_chars` | Markdown 报告正文 `content`、报告版本、校验信息和分页位置 |

报告正文直接返回给智能体，可以用于展示或总结，无需智能体登录服务器下载文件。
实验名使用列表返回的准确名称，例如 `spaceship-titanic`。
报告默认每页最多 20000 个字符，可用 `max_chars` 调整，单页上限 50000。
当 `next_offset` 不是 `null` 时，下一次调用固定使用本次返回的 `run_id`，并把 `offset` 设置为 `next_offset`。

读取结果时，同时查看 `latest_run`、`is_latest_run` 和 `acceptance_passed`：
报告可能来自此前成功完成的运行，而最近一次重跑已失败；报告可读也不代表独立验收通过。
例如已恢复的 Ghouls 报告记录了训练完成及独立 EDA 验收失败，应同时说明这两个结果。
接口行为详见 [SACK 实验报告 MCP](mcp-reports.md)。

## 5. 常见问题与排查

| 现象 | 检查方法 |
| --- | --- |
| “MCP 服务器拒绝了访问” / HTTP 401 | 检查是否只填了 URL；确认请求头为 `Authorization: Bearer <有效令牌>`，占位符已替换且没有多余空格或换行；修改后重新连接 |
| 页面提示 OAuth 登录或登录失败 | 当前服务尚未提供 OAuth；按上面的请求头方式配置。在 Codex 中检查已有 `sack_reports` 条目 |
| HTTP 403 | 请管理员根据响应内容和服务端日志检查 Origin 或网关策略；该状态码本身不能证明令牌错误 |
| TLS 握手超时、连接超时、证书错误 | 检查客户端网络、DNS、代理和证书；握手尚未完成时，服务端还未进入令牌校验 |
| HTTP 404 / 返回其他服务内容 | 确认完整地址为 `/sack/mcp`，包括 `https://` 和域名；此网关按精确路径匹配，不在末尾添加 `/` |
| HTTP 502 / 503 | 请管理员检查 Nginx 和 MCP 后端服务是否正常运行 |
| 找不到三个工具 | 确认该服务已启用、当前任务允许使用该连接器，并重新加载 MCP；Codex 中同时检查 `enabled_tools` |
| `EXPERIMENT_NOT_FOUND` | 先调用 `list_experiments`，使用返回的准确实验名 |
| `REPORT_NOT_READY` | 连接和认证已完成，但该运行尚无经过核验的最终报告；调用 `get_experiment_status` 查看详情 |
| 能列出实验但报告内容不完整 | 检查 `next_offset`，固定 `run_id` 继续读取后续页 |

需要单独检查公网入口时，可执行以下 **不带令牌** 的请求：

```bash
curl --connect-timeout 10 --max-time 20 -i -X POST \
  https://mcp.bdilabagent.cn/sack/mcp
```

正常情况下返回 HTTP `401`，并带有 `WWW-Authenticate: Bearer`。
这只能验证 HTTPS 可达及入口要求认证；它没有验证你的令牌、MCP 初始化或报告读取。
接入成功应以客户端实际调用上述三个工具的结果为准。排查网络时保持 TLS 证书校验开启。

现有 [公网验证记录](../reports/sack-mcp-public-20261110.md)记录了 SDK 双客户端验证，
不等同于每台电脑上的 WorkBuddy / Codex 界面都已验证成功。
服务维护与网关配置见 [公网部署说明](mcp-public.md)。
