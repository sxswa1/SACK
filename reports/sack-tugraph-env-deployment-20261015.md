# TuGraph .env 服务器同步记录

日期：2026-10-15（北京时间）。状态：独立运行副本已部署，配置加载、相关回归及数据库连接验证通过。未启动案例或模型请求。

## 服务器位置

- 服务器：`root@60.204.211.83`。
- 运行根目录：`/opt/sack-tugraph-runtime-20261015/`。
- 项目目录：`/opt/sack-tugraph-runtime-20261015/repo/`。
- 私有配置：`/opt/sack-tugraph-runtime-20261015/repo/.env`。
- Python 入口：`/opt/sack-tugraph-runtime-20261015/sack-python`。
- 部署记录：`/opt/sack-tugraph-runtime-20261015/deployment.json`。
- 连接验证：`/opt/sack-tugraph-runtime-20261015/repo/.runtime/env-connectivity-verification.json`。

源码从已验收的 `/opt/sack-backend-compare-20261004-fix12/tugraph/repo` 复制，仅新增 `.env` 引导、模板、忽略规则、测试及依赖说明。其余业务 Python 文件哈希与源副本一致。原有实验目录未修改，未切换数据库或服务。

## 配置与资产

`.env` 从服务器现有 TuGraph 凭据文件与 `knowledge.env` 构建，权限为 `0600`，所有者为 `sackeda`；密码不写入此记录。后端为 `tugraph`，在线图为 `sack_kaggle_20261001`，Bolt 地址为 `bolt://127.0.0.1:7687`。现有进程环境变量优先于 `.env`。

沿用服务器现有 Conda 环境及已安装的 `python-dotenv 1.2.3`，未修改共享 Python 环境。模型 API 凭据保留现有文件引用。

Titanic 只复制 rawdata，未复制之前的 EDA/DSP 结果或状态；案例状态重置为空。历史 profiles 独立复制，模型、嵌入与历史图资产复用已有路径。当前竞赛洞察路径指向本副本自己的独立 EDA 目录；Chroma 使用本副本的 `.runtime/chroma`。本轮不是完整依赖环境重建或新一次端到端验收。

## 验证结果

- 使用入口自动切换到非特权账号 `sackeda`（UID 10001）。
- 未手动 source `.env`，12 个受检配置项均由包引导自动加载。
- 相关配置加载、factory 与 API 路由回归：16 passed。
- TuGraph 健康检查通过，竞赛列表为 70 条。
- `kaggle_column_embeddings` 和 `kaggle_competition_embeddings` 连接通过，默认事务为只读。
- 模型请求：0；案例运行：未启动。

同步包 SHA-256：`8bec2404aac3449bfcf87163b4ce36a1ededa70fc0f18ea2a10846937486b9a4`。

## 后续手动运行

以下命令需在服务器执行，会使用模型 API 并执行生成代码。首轮输入仅有 rawdata，因此显式从 Data Preparation 开始：

```bash
/opt/sack-tugraph-runtime-20261015/sack-python -u -m sack run \
  --competition titanic \
  --force-eda \
  --dsp-start-phase "Data Preparation"
```

入口会定位到新项目目录并使用已有 Conda Python；无需手动 source `.env`。此入口未内建六小时限制，旧实验的 systemd 限制不会自动继承。重复运行前先保留当前任务产物。
