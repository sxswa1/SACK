# TuGraph 4.5.2 Docker 离线导入操作说明

更新时间：2026-09-28。适用于已安装 Docker 的 Linux x86_64 服务器。

## 工具边界

使用 `sack.knowledge.migration.load_tugraph_docker`。它不停止/重建服务容器，不开放端口，不修改用户密码，不切换 Agent 后端；仅运行一次性离线导入容器并生成一个新数据库目录。

关键保护：

- 目标数据库和结果目录必须不存在，父目录必须已存在；没有覆盖选项。
- 校验导入包 manifest、文件大小、SHA-256 和 TuGraph 目标版本；包、数据库、结果目录不能互相嵌套。
- 只使用本机 Docker 默认上下文，忽略远程 Docker 环境覆盖；校验已安装镜像是 linux/amd64，RepoDigest 与固定 4.5.2 摘要一致。实际运行锁定 image ID，且 `--pull never`。
- 原始导入包不挂载给容器。完整工作副本位于结果目录 `work/`，供导入器创建 `.import_tmp`；副本再次校验且必须与原始 manifest 一致。
- 容器 `--network none`，不挂载 Docker socket，不使用 privileged；只挂载工作副本和新数据库目录。
- `overwrite=false`、`continue_on_error=false`，默认 2 GiB/2 CPU 和 1800 秒超时。大数据导入须按容量规划显式调整资源，而非直接使用冒烟限制。
- 超时后只清理本次唯一命名的一次性导入容器，保留数据库、工作副本和日志。清理失败也记录结果，不能宣称任务成功。

镜像固定摘要为 `sha256:b1b0ecc39a580a7cbdac7b4b7ce35f6a92f0981254d314bc1c0a50ca71d4df0d`。默认使用服务器已经拉取的 DaoCloud 代理镜像；来源虽为代理，摘要必须匹配已验证的官方镜像。此工具不自动拉取镜像。

## 操作步骤

在服务器项目根目录执行。以下路径均为占位值，须替换为新目录，不能沿用正在运行服务的数据库路径。

```bash
# 1. 只读预检：不创建数据库/结果目录，也不启动导入容器
python3 -m sack.knowledge.migration.load_tugraph_docker \
  --package-dir /opt/sack-import/package \
  --database-dir /opt/sack-import/database-v1 \
  --result-dir /opt/sack-import/results-v1 \
  --graph sack_poc --dry-run

# 2. 核对镜像、mount、目标目录后执行；去掉 dry-run，其他参数保持一致
python3 -m sack.knowledge.migration.load_tugraph_docker \
  --package-dir /opt/sack-import/package \
  --database-dir /opt/sack-import/database-v1 \
  --result-dir /opt/sack-import/results-v1 \
  --graph sack_poc
```

必须检查 `import_result.json` 的 `status=passed` 和 `return_code=0`，以及完整 stdout/stderr 日志。返回码 0 只表示离线导入完成，不代表数据对账、API parity 或生产验收通过。

导入成功后，新目录可挂载到同版本服务容器的 `/var/lib/lgraph/data`。服务启动是独立、需审核的部署动作：不要让两个服务容器同时写入同一数据库目录，不要复用被占用的端口；密码使用用户指定配置，不自动轮换。新数据库的初始化凭据不得误认为继承了现有实例的密码。

随后用只读账号运行 `validate_tugraph`、`check_tugraph_compatibility`。只有固定冒烟包才运行 `verify_tugraph_smoke_fixture`；真实包必须进一步与 GraphDB 基线逐项比较。默认后端仍应保持 GraphDB。

## 失败与重试

失败会保留以下证据，不自动删除：

- 新数据库目录（可能含部分 Schema/数据，禁止启动为生产服务）；
- `work/` 导入包副本与导入临时文件；
- `lgraph_import.stdout.log`、`lgraph_import.stderr.log`；
- `import_result.json`（含命令、镜像摘要、manifest 摘要、时间和错误）。

重试必须使用另一组全新数据库和结果目录。不能手动添加 overwrite，不能对失败目录使用宽泛递归删除。清理失败目录是另一个需核对明确目标的操作。

## 本轮验证记录

- 本地知识图谱测试：129 项通过，包含 16 项 Docker 装载测试（含复制期间源包变化拦截）。
- 服务器实际 dry-run：通过，未创建数据库或结果目录。
- 固定 16 顶点/24 边包实际离线导入：返回码 0，导入完成。
- 本次新数据库：`/opt/sack-tugraph-loader-20260928/database`；未启动新的服务实例。
- 服务端记录：`/opt/sack-tugraph-loader-20260928/results/import_result.json` 及同目录日志。
- 最终版（含复制期间源包变化拦截）已另行实测，返回码 0、耗时约 3.68 秒；数据库 `database-final`、报告 `results-final/import_result.json` 均位于上述装载工具根目录，未启动服务。
- 既有两个 TuGraph 实例、固定测试密码和端口配置未被此工具改变。

这次是对装载工具的实测。此前固定冒烟图已通过结构对账、七项查询兼容性和十三项领域验证；真实源数据尚未找到，真实数据导入、GraphDB parity 和 Agent 双读尚未完成。
