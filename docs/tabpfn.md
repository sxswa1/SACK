# TabPFN 接入与验证

SACK 的 `train_and_validation_and_select_the_best_model` 支持可选模型名称
`TabPFN`，分类和回归分别使用 `TabPFNClassifier` 和 `TabPFNRegressor`。
默认候选模型列表保持不变，需要在计划或工具调用中显式选择。

## 安装与权重

在 Python 3.10 的 SACK 训练环境中执行：

```bash
python -m pip install -r requirements.txt -r requirements-tabpfn.txt
python -m pip check
```

固定使用 `tabpfn==2.1.3`，原始 TabPFN v2 权重。SciPy 从 1.10.1 更新为
1.11.4，以满足 TabPFN 的 `scipy>=1.11.1` 要求；其他既有顶层依赖版本不变。
不要直接升级 TabPFN 包或替换默认权重，适配器会拒绝不匹配的包版本和权重摘要。

| 模型 | 官方仓库 | 固定修订 | SHA-256 |
| --- | --- | --- | --- |
| 分类 | [Prior-Labs/TabPFN-v2-clf](https://huggingface.co/Prior-Labs/TabPFN-v2-clf) | `275f19d2add9c2c0de38f9ebaded3856599fa2e7` | `f65a35685aeef42e31b796d9bfa34e68d6fc780bc98e7bff7763802964cf435f` |
| 回归 | [Prior-Labs/TabPFN-v2-reg](https://huggingface.co/Prior-Labs/TabPFN-v2-reg) | `02a44705ff7790b50cded404bc59adb94da456a1` | `2ab5a07d5c41dfe6db9aa7ae106fc6de898326c2765be66505a07e2868c10736` |

文件名分别为 `tabpfn-v2-classifier.ckpt` 和 `tabpfn-v2-regressor.ckpt`。
首次选择 TabPFN 时从上述官方修订下载，加载前校验摘要；本地已有正确文件时可离线使用。
权重采用 [Prior Labs v2 许可](https://huggingface.co/Prior-Labs/TabPFN-v2-clf/blob/main/LICENSE.txt)，
项目不分发权重，也不向托管推理服务上传数据。

`.env` 可选配置：

```dotenv
SACK_TABPFN_DEVICE=auto
SACK_TABPFN_MODEL_DIR=/absolute/path/to/tabpfn-weights
SACK_TABPFN_N_ESTIMATORS=4
SACK_TABPFN_N_JOBS=1
```

`auto` 优先使用 CUDA，否则使用 CPU；也支持显式的 `cpu`、`cuda`、`cuda:<index>`。
未配置权重目录时使用 `~/.cache/tabpfn`。并行数和集成次数必须是正整数。
这些配置独立于智能体的 `SACK_MODEL_*` 大语言模型配置。

## 训练与预测

```python
from sack.Tools.ml_tools import train_and_validation_and_select_the_best_model

model = train_and_validation_and_select_the_best_model(
    X, y, problem_type='binary', selected_models=['TabPFN', 'SVM'])
predictions = model.predict(X_test)
```

`problem_type` 支持 `binary`、`multiclass`、`regression`。回归可选择
`['TabPFN', 'linear regression']`。返回值是一个模型。

- 沿用现有 processed CSV 特征表，排除 ID 和目标列，训练和测试特征列顺序必须相同。
- 限制按最终全量拟合数据计算：CPU 最多 1000 行，CUDA 最多 10000 行，最多
  500 个特征，分类最多 10 类。超限不会偷偷采样，也不绕过官方预训练限制。
- TabPFN 直接拟合，在与其他模型相同的 80/20 划分上验证；传统模型继续执行
  训练子集中的五折 GridSearchCV。二分类比较 accuracy，多分类比较 weighted F1，
  回归比较负 MSE。最终胜出模型在全部训练数据上重新拟合。
- 缺少依赖、权重不可用、超限、拟合或验证预测失败会记录错误并跳过 TabPFN。
  全量重新拟合失败时使用下一名已验证模型。所有候选都失败则报错。
- 回归审计要求原始有限数值目标，首版不支持对目标取对数等变换。分类仍支持
  一致的标签编码，写提交前恢复原始标签。回归提交与实际预测按 `rtol=1e-7`、
  `atol=1e-9` 比较；NaN、无穷值和伪造预测不能通过。
- 审计保留实际验证成绩、候选失败原因及全量拟合证据。TabPFN 额外记录包版本、
  权重修订与 SHA-256、设备、集成次数和并行数。

建模阶段只有一个预定义工具，其说明直接读取当前 Markdown 文件，避免已有 Chroma
集合中的旧枚举遮蔽 TabPFN；其他阶段保持原有检索方式，无需删除现有工具索引。

## 验证

无需权重或网络的行为回归：

```bash
python -m pytest -q sack/knowledge/tests/test_tabpfn_integration.py sack/knowledge/tests/test_stage_acceptance.py
```

使用真实权重执行二分类、多分类、回归，以及真实训练和提交一致性审计：

```bash
python scripts/validate_tabpfn.py \
  --output-dir /tmp/sack-tabpfn-validation \
  --model-dir /absolute/path/to/tabpfn-weights \
  --device cpu --n-estimators 1
```

输出目录必须不存在。脚本使用 sklearn 随包提供的 breast cancer、iris、diabetes
数据，各自生成独立 processed CSV、模型代码、提交及训练审计记录，并写入
`summary.json`。不调用付费 LLM、知识图数据库或 Kaggle。该验证证明建模工具与
审计链路可运行，不代表完整智能体工作流或 Kaggle 得分改进。

服务器部署前确认无活跃实验、Git 工作区无冲突，并保存现有环境版本和部署检查点。
在功能分支上安装依赖并执行上述检查。验证输出使用独立的新目录，保留历史实验数据。
本地结果不能替代服务器安装与验证结果。
