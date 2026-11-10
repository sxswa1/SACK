# SACK 公网 HTTPS MCP 验证

日期：2026-11-10（北京时间）。

公网地址：`https://mcp.bdilabagent.cn/sack/mcp`。
协议为 Streamable HTTP，所有调用需要客户端对应的 Bearer 令牌；不再要求客户端建立 SSH 隧道。

## 部署

- 继续使用原 Git 仓库 `/opt/sack-tugraph-runtime-20261015/repo`，没有复制项目。
- 功能提交：`9fb60260951fc8e5a8a15c4f3bc9419600f93a88`。
- 服务器 Git 部署合并提交：`5c2924306bb0f27c6fe5775ae5e3e5871583a606`，分支 codex/runtime-inplace。
- Nginx 仅新增现有 mcp.bdilabagent.cn HTTPS server 中的精确路径 /sack/mcp，转发到 127.0.0.1:8765/mcp。
- 复用现有域名证书；核对证书 SAN 匹配，当前到期时间 2027-01-14 01:35:50 UTC。
- 既有 snap.certbot.renew.timer 正常安排续期。
- systemd public drop-in 增加该域名 Host/Origin 白名单，保留 loopback 监听和令牌鉴权。
- nginx -t 通过；原站点配置已私有备份，失败时部署脚本会回退网关与 drop-in。

## 真实验证

1. 服务器通过公网 HTTPS 域名完成两个独立 SDK 客户端的初始化、工具发现和报告读取。
2. workbuddy/codex 两个令牌分别测试，均发现三个工具、列出六个原实验目录。
3. 三份恢复报告均从原工作目录读取，返回正文 SHA-256 与原文件一致，旧报告与最近失败重跑明确区分。
4. Ghouls 保留 acceptance_passed=false、eda_status=fail；其余两份原验收结论均为 true。
5. 无令牌及错误令牌返回 401；正确令牌但非法 Origin 返回 403；允许的 Origin 可正常完成调用。
6. GitHub Actions 从独立外部网络验证 HTTPS 证书及公网入口，未授权请求正确返回 401 Bearer：
   [独立公网检查](https://github.com/sxswa1/SACK/actions/runs/42744816690)、
   [PR 公网检查](https://github.com/sxswa1/SACK/actions/runs/42744816972)，两次均成功。

机器可读的协议和报告核验记录见 [JSON](sack-mcp-public-20261110.json)，不包含令牌值或报告全文。
本次修改是网关及部署配置；未修改报告查询业务代码或重新训练实验。

## 本机 Codex

已将用户配置 sack_reports 从 SSH stdio 改为上述公网 URL，设置正确的静态 Authorization 请求头。
令牌只保存在用户私有 0600 配置文件中，其他配置保留，原配置已私有备份。
CLI 已确认 transport=streamable_http、enabled=true、认证请求头已配置。
已有对话仍可能复用旧连接，需要重启 MCP 连接/新建对话以加载更新。

本机命令行的直连和现有系统代理路径都出现 TLS 握手超时；本机存在系统代理及 fake-IP DNS。
未改变系统网络设置或关闭证书校验，也不把这项结果声称为本机直接 HTTPS 验收通过。
独立外网检查已通过，因此公网入口并不依赖本机 SSH。客户端若也遇到超时，应检查其网络/代理路由。

安装和客户端配置见 [公网接入文档](../docs/mcp-public.md)。
