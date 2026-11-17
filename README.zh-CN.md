# Data Engineering

**面向 AI 的数据系统与研究方法：从原始来源到学习、检索、评测和使用反馈。**

[English](README.md) · [总体设计](docs/design.zh-CN.md) · [数据消费](docs/consumption.md) · [研究方向](docs/research.md) · [实现状态](docs/roadmap.md)

核心问题是：在计算预算下，什么数据能提升系统能力，怎样构造并持续交付这些数据？本项目连接来源快照、领域结构、处理配方、混合分布与消费反馈，覆盖预训练、后训练、多模态模型、Agent、检索与记忆、传统机器学习、机器人和科学实验。

核心独立于模型厂商、训练框架与云平台。Qiushi Engine、RSI 和其他 AI 系统都可以成为消费者。[OpenAI、Google DeepMind、Anthropic 与 DeepSeek 的公开工作](docs/frontier-workloads.md)提供工作负载依据，并指向后续需要解决的具体问题。

## 可运行的数据路径

v0.2 提供两类互补操作：**build** 将来源整理为带切分和来源关系的数据版本；**compose** 从固定版本中按预算构造消费序列，再由可恢复的 reader 交付。

| 操作 | 已实现能力 |
| --- | --- |
| 构建数据版本 | 规范 JSONL 与 Gym 导入、精确去重、父子与分组关系、确定性切分、用途选择、逐条处理记录。 |
| 构造消费分布 | 带权来源选择、确定性顺序、记录数或已有 token 计数预算、来源耗尽策略、带位置索引的 JSONL 分片。 |
| 交付数据 | 按 rank/world_size 分配样本、可选等长分配、索引读取、绑定数据版本和 rank 配置的恢复状态。 |
| 回收运行经验 | 将 Verifiable Agent Gym 的观察、动作、任务切分、验证结果及 rollout 元数据导入为轨迹记录。 |
| Agent 操作 | Python、CLI、MCP 共用核心，提供 connector 扩展入口和操作 Skill。 |

需要 Python 3.11 及以上，核心仅依赖标准库。

```sh
git clone https://github.com/Cherish0925/Data-Engineering.git
cd Data-Engineering
python -m pip install -e .
python examples/compose_training.py --output runs/training-example
ai-data verify-mixture runs/training-example/mixture
```

示例创建文本和代码两个来源版本，以 3:1 的来源权重抽取 1,000 条记录，生成分片，并演示四个 reader rank 中一个的断点恢复。修改生成的配方后，可构建新版本：

```sh
ai-data compose runs/training-example/mixture.recipe.json --output runs/mixture-v2
ai-data verify-mixture runs/mixture-v2
```

`python -m ai_data` 等价于 `ai-data`；没有 `python` 命令时可用 `python3` 或 `py -3.11`。

## 来源整理与数据消费

```sh
ai-data profile examples/records.jsonl
ai-data build examples/local.recipe.json --output runs/source-v1
ai-data verify runs/source-v1
ai-data inspect runs/source-v1
```

数据版本包含分区文件、来源关系、处理决定和由内容计算的发布清单。构建器先建立关联再过滤和去重，使已知副本与派生记录保留其切分关系。领域载荷保留自身结构：偏好对、传感器序列和表格各自有合适的表达方式。具体格式见[数据契约](docs/contracts.md)。

```python
from ai_data import MixtureReader

with MixtureReader("runs/training-example/mixture", rank=1, world_size=4) as reader:
    sample = next(reader)
    record = sample["record"]
    checkpoint = reader.state_dict()

with MixtureReader("runs/training-example/mixture", rank=1, world_size=4) as reader:
    reader.load_state_dict(checkpoint)
    next_sample = next(reader)
```

混合配方明确选择每个来源的分区。token 预算读取记录中指定字段的已有计数；分词器、编码方式和损失掩码由消费者定义。[消费说明](docs/consumption.md)给出配方、耗尽策略、rank 分配与恢复语义；[测量脚本](examples/measure_composition.py)分别测量来源准备、混合构建和读取。

## 任务数据与反馈

[Verifiable Agent Gym](https://github.com/Cherish0925/Verifiable-Agent-Gym)将任务记录变成可执行环境，记录外部策略的尝试。它的 SQL task pack 可直接读取本项目的数据版本；分组 rollout 导出通过 `gym-jsonl` 返回任务、策略、尝试、观察/动作与结果信息。

```sh
ai-data build examples/gym.recipe.json --output runs/gym-trajectories
ai-data verify runs/gym-trajectories
```

接入实际运行时，将配方指向 `agent-gym export` 或 `agent-gym export-rollouts` 文件并记录来源版本。Gym 负责环境交互和结果评价，Data Engineering 负责数据分布与产品，外部训练器负责模型推理和优化。数据策略、环境反馈与学习效果分别记录，并通过版本身份关联。

安装两个相邻目录中的仓库后，可直接运行完整的任务到经验流程：

```sh
python examples/experience_cycle.py --gym-tasks ../Verifiable-Agent-Gym/examples/sql-workload/tasks.jsonl --output runs/experience-cycle
```

示例构建 SQL 任务版本，采集八次分组尝试并产生成功与失败结果，再导入轨迹、构建三个分片，检查两个 reader rank 的分配和精确恢复。

## 研究与扩展

研究围绕能改变能力的数据决策展开：来源配比、合成候选筛选、任务难度、经验复用、多模态对齐与反馈更新。每个实验把明确的数据干预与消费者表现、资源预算联系起来，详见[研究方法](docs/research.md)和[公开工作负载依据](docs/frontier-workloads.md)。

```sh
python -m pip install -e ".[mcp]"
ai-data connect --root . --output data-engineering.local.json
```

将配置导入兼容的 MCP host，即可调用数据分析、构建、检查、混合和验证工具。[操作 Skill](skills/data-engineering/SKILL.md)与[接入说明](docs/integrations.md)提供 Agent 和 connector 的使用方法。

当前实现运行在本机：来源构建器在内存中处理记录，混合构建和读取使用磁盘索引与分片。近重复处理、模型专用分词/打包、多模态解码、远程 worker 和训练器适配是下一步工作。示例使用人工编写的记录和脚本策略展示数据流；实际学习收益需要接入消费者实验，具体安排见[开发路线](docs/roadmap.md)。

```sh
python -m pip install -e ".[mcp,test]"
python -m unittest discover -s tests -v
python -m pip wheel . --no-deps --wheel-dir dist
```

实现位于 `src/ai_data/`，可执行配方位于 `examples/`，研究方法位于 `docs/`。参与开发前请阅读 [AGENTS.md](AGENTS.md)。
