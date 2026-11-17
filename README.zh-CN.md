# Data Engineering

**面向 AI 全生命周期的数据研究与工程环境。**

[English](README.md) · [总体设计](docs/design.zh-CN.md) · [数据契约](docs/contracts.md) · [接入方式](docs/integrations.md) · [研究方向](docs/research.md) · [开发路线](docs/roadmap.md)

本项目负责 AI 系统从数据获取、生成、理解、加工、组织、交付到使用反馈的完整数据生命周期。既研究什么数据能带来什么能力，也提供把研究变成可重复流程的工具、接口、配方、提示词与运行环境。

服务范围包括传统机器学习、LLM、视觉与多模态模型、生成模型、Agent、机器人和科学实验系统。Qiushi Engine、RSI 和模型训练平台都可以接入；核心实现独立于它们，也不绑定模型厂商、Agent 框架或云平台。

## 覆盖什么

| 场景 | 本环境负责的数据工作 |
| --- | --- |
| 预训练与持续预训练 | 数据采集、解析、去重、质量与覆盖分析、混合采样、分词与打包配方、版本管理。 |
| 监督与偏好学习 | 标注、演示、对话、工具调用、偏好对、奖励与价值目标、标签分歧和不确定性。 |
| 强化学习与 Agent | 任务分布、环境和验证器版本、行动轨迹、奖励、失败、经验回放、难度课程。 |
| 评测 | 评测集构建、独立切分、污染分析、冻结版本、结果归因。 |
| 检索与记忆 | 文档、分块、向量与索引、上下文选择、权限继承、更新与纠错。 |
| 表格、图与时序模型 | 实体、标签、特征、时间一致连接、图关系、训练与在线特征一致性。 |
| 多模态与具身智能 | 图像、音频、视频、空间数据、传感器与动作同步、坐标系与完整轨迹。 |
| 科学实验 | 物理量、单位、误差、校准、仿真条件、实验干预与全过程关联。 |
| 持续运行 | 在线反馈、分布变化、主动采集、合成数据、保留与撤回传播。 |

上表是完整设计范围。当前已实现的是本地参考核心；大规模处理与各领域专用工具按[开发路线](docs/roadmap.md)接入。

## 核心设计

统一的是来源、版本、用途、关系和交付方式；领域数据保留自己的结构。同一段运行记录可以形成训练样本、检索资料或评测对象，每一种产物都保留其配方和来源。

数据产品由**数据内容、结构、生成配方、来源关系、用途与切分、发布清单**共同定义。修改标签、替换源数据、升级解析器或调整混合比例，都产生新的版本。模型、索引、评测器和 Agent 消费明确版本，再将使用结果关联回来。

研究环境同时包括方法研究、实验配方、工具运行、Agent 指引和外部接入。Skills 指导如何工作；MCP 承载工具调用；connectors 接入数据源；plugins 包装扩展能力。它们共用实际执行核心。

## 首版运行

需要 Python 3.11 及以上，无需 GPU 或模型 API key。

```sh
git clone https://github.com/Cherish0925/Data-Engineering.git
cd Data-Engineering
python -m pip install -e .
ai-data profile examples/records.jsonl
ai-data build examples/local.recipe.json --output runs/local-v1
ai-data verify runs/local-v1
```

示例包含文档、对话、表格行、测量记录和媒体引用。7 条输入得到 5 条保留记录：去除 1 条精确重复记录，排除 1 条未声明训练用途的记录；训练、验证、测试分别为 3、1、1 条。它们都是人为编写的格式示例，不是实验成绩。

先按来源分组、派生关系和相同内容建立关联，再执行用途过滤和去重。因此，即使评测记录被过滤，其已知副本和派生样本也仍留在评测分区；发生固定切分冲突时直接报告错误。这里实现的是精确重复与显式关联，语义近重复分析仍需后续接入。

发布目录包含三个分区、逐条处理决定、来源关联和带内容哈希的清单；已有目录不会被覆盖。`use="train"` 只表示按训练用途选择记录，训练程序仍须只读取 `train.jsonl`。当前输出保留通用记录结构，尚未分词或转换为特定训练器格式。

## Agent 与 Gym 接入

```sh
python -m pip install -e ".[mcp]"
ai-data connect --root examples --output data-engineering.local.json
ai-data build examples/gym.recipe.json --output runs/gym-v1
```

将生成的配置交给兼容的 MCP host，即可使用 `data_capabilities`、`data_profile`、`data_build`、`data_inspect`、`data_verify`。Python、CLI 与 MCP 使用同一套代码。仓库内还提供[操作 Skill](skills/data-engineering/SKILL.md)，供其他 Agent 环境安装或读取。

[Verifiable Agent Gym](https://github.com/Cherish0925/Verifiable-Agent-Gym) 继续负责执行任务与判分；本项目直接接收它的 export-v1 轨迹，保留任务切分、观察与行动、验证结果以及未评分状态。环境错误的空奖励不会被改成模型答错的零奖励。

## 当前状态

已实现本地 JSONL／Gym 导入、契约检查、精确去重、关联分组切分、用途过滤、版本冻结、来源记录、发布完整性检查、Python／CLI／MCP 和可信 connector 扩展入口。参考构建器在内存中处理记录。

后续重点是大规模数据处理、多模态解码、领域专用结构、训练器与索引适配、增量更新以及数据策略研究。目录和协议不等于这些能力已经完成；[总体设计](docs/design.zh-CN.md)明确整个项目的责任与演进方式。
