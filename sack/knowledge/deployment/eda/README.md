# EDA 服务器环境

此项目支持 Conda 安装 EDA 分析/Insight 生成依赖，不包含 Profile 生成所需的 Spark、Java、fastText 和列模型运行环境。它也不代表 Agent/TuGraph 端到端验收完成。

服务器根目录 `/opt/sack-eda-20260928`，不启动常驻服务、不开放端口、不自动运行付费任务。代码从 GitHub `codex/tugraph-migration` 分支克隆；原始 Titanic 数据只复制、不修改。

## Conda 安装

```bash
git clone --branch codex/tugraph-migration --single-branch https://github.com/sxswa1/SACK.git /opt/sack-eda-20260928/repo
/opt/sack-eda-20260928/miniforge3/bin/conda env create \
  --prefix /opt/sack-eda-20260928/conda-env \
  --file /opt/sack-eda-20260928/repo/sack/knowledge/deployment/eda/environment.eda.yml
/opt/sack-eda-20260928/miniforge3/bin/conda run \
  --prefix /opt/sack-eda-20260928/conda-env \
  python -m pip install -r /opt/sack-eda-20260928/repo/sack/knowledge/deployment/eda/requirements.txt
```

运行 Conda 版离线预检（工作目录须为克隆仓库根目录）：

```bash
cd /opt/sack-eda-20260928/repo
PYTHONPATH="$PWD:$PWD/sack" /opt/sack-eda-20260928/miniforge3/bin/conda run \
  --prefix /opt/sack-eda-20260928/conda-env \
  python -m sack.knowledge.deployment.eda.run_eda --check --competition titanic
```

需要把 `workspace/titanic` 链接到 `repo/data/eda_competitions/titanic`，以便仓库默认路径发现输入并将输出写入副本工作区。

## API 配置

编辑 `/opt/sack-eda-20260928/secrets/api_key.txt`，四行依次为：

1. API Key（原始字符串，无变量名、引号）
2. `qwen-plus` 等通用模型的 base URL
3. `qwen3-coder-plus` 的 base URL
4. `qwen3-vl-flash` 的 base URL

三个接口可以相同，但必须与 Key 的服务商/地域匹配，服务需要支持上述模型。当前项目只支持这一组模型共享一个 Key，不读取 `OPENAI_API_KEY`/`DASHSCOPE_API_KEY` 环境变量。不要将真实 Key 放入镜像、仓库、聊天消息或运行日志。

工具检索还会调用 `text-embedding-v3`（1024 维），使用第 2 行接口和同一 Key；同样会产生费用。Chroma 缓存隔离在 `workspace/.runtime/chroma`，不挂载现有数据库。

占位模板按阿里云百炼北京地域填写 `https://dashscope.aliyuncs.com/compatible-mode/v1`；其他地域需更换对应 endpoint，参见 [百炼官方文档](https://www.alibabacloud.com/help/zh/model-studio/model-calling-in-sub-workspace)。

凭据仅挂载到容器 `/app/sack/api_key.txt`（只读）；保留宿主文件 owner `10001:10001`、权限 `0600`。文件初始为占位模板，非有效 Key。

## 运行

```bash
sh /opt/sack-eda-20260928/code/sack/knowledge/deployment/eda/run.sh --check
# 显式允许付费 API 调用与生成代码执行后，再手动执行：
sh /opt/sack-eda-20260928/code/sack/knowledge/deployment/eda/run.sh --run
sh /opt/sack-eda-20260928/code/sack/knowledge/deployment/eda/run.sh --validate-results
```

`--check` 不发模型请求，导入依赖并检查输入、配置完整性。`--run` 只执行 Titanic，不扫描全部竞赛。不要重复运行覆盖已验收输出，重跑前先保留工作目录副本。运行未设自动重试/计划任务。

2026-09-28 服务器验证：镜像 `sack-eda-runtime:20260928`（ID `sha256:7271bae4f76c1d24b42022c0b2d239c154879a844f92160e43f90d6feb3dedcf`），`pip check` 无依赖冲突；只读、`--network none` 的 `--check` 通过。读取到 train 891x12、test 418x11、sample_submission 418x2，6 个 EDA 阶段可构造，离线 EDA 工具探针通过。该验证没有 API Key、没有出站网络，也没有生成模型调用或 EDA 结果。

输出位于 `/opt/sack-eda-20260928/workspace/titanic/` 的 `pre_insight_extraction` 与 `deep_insight_extraction`，同时检查 `eda_insight_validation.json` 和日志；工作流 success 或 JSON 文件存在不等于语义质量通过。模型失败可能输出 unknown 模板。

容器非 root、只读根文件系统、限制资源；Titanic 源 rawdata 只读，分析产物写到竞赛副本工作区。未挂载 Docker socket、TuGraph 数据/凭据或其他服务目录；付费运行需要网络，生成代码在容器中仍可访问 API Key，因此不是对恶意代码的绝对隔离。不得用 root 在宿主机执行模型生成代码。停止任务：`docker stop sack-eda-titanic`。

部署过程中保存 pip check、运行时导入检查、镜像 ID/摘要和输入统计。填 Key 后需要另行授权/执行真实模型和 EDA 验收。
