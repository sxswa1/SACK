# SACK 公网 MCP 接入

地址：`https://mcp.bdilabagent.cn/sack/mcp`。

通过现有域名的有效 HTTPS 证书提供访问，SACK 占用独立的 /sack/mcp 路径。
客户端直接连接公网，不需要安装 SSH、开启隧道或访问服务器终端。
所有请求仍要求各客户端自己的 Bearer 令牌，查询权限覆盖现有实验目录及报告历史。

## WorkBuddy

在 MCP 配置中填写以下内容，将占位符替换为管理员提供的 workbuddy 令牌：

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

## Codex

在用户配置 ~/.codex/config.toml 中编辑已有 sack_reports 条目，改为 HTTP 配置。
移除该条目原有的 command、args 等 stdio 启动字段，保留其他 MCP 服务。

```toml
[mcp_servers.sack_reports]
url = "https://mcp.bdilabagent.cn/sack/mcp"
http_headers = { Authorization = "Bearer <Codex令牌>" }
startup_timeout_sec = 30
tool_timeout_sec = 60
```

用户配置文件应仅当前用户可读，例如 chmod 600 ~/.codex/config.toml，不提交实际令牌。
也可使用 bearer_token_env_var="SACK_MCP_TOKEN"，由 Codex 启动环境提供令牌。
更新后重启 MCP 连接并新建对话，输入：“列出 sack_reports 中的实验并读取 spaceship-titanic 报告。”

参考 [Codex 官方配置](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)、
[WorkBuddy 官方配置](https://open.workbuddy.cn/en/docs/connector)。

## 服务端部署

代码及运行目录保持为 /opt/sack-tugraph-runtime-20261015/repo。
服务进程继续监听 127.0.0.1:8765，Nginx 在现有 TLS server 中把 /sack/mcp 转发到 /mcp。
认证请求头和 MCP 协议头转发给后端，流式代理关闭缓冲，不记录请求正文或令牌。

1. 把 [Nginx location 配置](../deploy/nginx-sack-mcp.location.conf) 安装到
   /etc/nginx/snippets/sack-reports-mcp.conf，并在 mcp.bdilabagent.cn 的 HTTPS server 块中 include 该文件。
2. 把 [systemd drop-in](../deploy/sack-reports-mcp-public.conf) 安装到
   /etc/systemd/system/sack-reports-mcp.service.d/public.conf，允许该域名的 Host 和 Origin。
3. 执行 nginx -t；通过后 systemctl daemon-reload、systemctl restart sack-reports-mcp、systemctl reload nginx。

域名解析到现有服务器，证书复用 /etc/letsencrypt/live/mcp.bdilabagent.cn/。
服务端访问令牌仍在 /opt/sack-tugraph-runtime-20261015/private/mcp-tokens.json，权限 root:sackeda、0640。
客户端不需要读取该服务器文件，由管理员分别发放对应令牌。

使用不带 Authorization 的请求验证时应返回 401；HTTP 200 不是唯一健康判断标准。
正确验收包括 initialize、tools/list 和 tools/call，核对报告 SHA-256，并测试错误令牌及非法 Origin 被拒绝。
本机有网络代理时需要让客户端使用现有系统代理；本地代理的 fake-IP DNS 不代表公网真实 DNS 地址。
不应关闭 TLS 证书校验来排查代理问题。

回退时移除新增 include 与 drop-in，nginx -t 后重启 MCP、reload Nginx；原 loopback/stdio 接口保持可用。
